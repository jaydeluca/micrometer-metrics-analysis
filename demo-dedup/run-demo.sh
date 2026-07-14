#!/usr/bin/env bash
# End-to-end validation of the Micrometer-dedup declarative-config views.
#
# Runs the demo app under the REAL OpenTelemetry Java agent twice — once with the Micrometer bridge
# on and no views (baseline), once with the bridge on and the dedup views (deduped) — capturing each
# run's metrics as OTLP JSON, then diffs them per instrumentation scope with verify.py.
#
# No Docker / no backend: the agent's otlp_file/development exporter writes the OTLP payload straight
# to a file, which preserves the instrumentation scope name we need to tell the bridged copy from the
# native one.
#
# Usage:   ./run-demo.sh
# Env:     AGENT_VERSION=<x.y.z>   pin an agent release (default: latest)
#          DEMO_RUN_MILLIS=15000   how long the app generates activity
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
AGENT_DIR="$DIR/.agent"
OUT_DIR="$DIR/out"
AGENT_JAR="$AGENT_DIR/opentelemetry-javaagent.jar"
RUN_MILLIS="${DEMO_RUN_MILLIS:-15000}"

mkdir -p "$AGENT_DIR" "$OUT_DIR"

# --- 1. Fetch the agent jar (pinned version or latest release) --------------------------------
if [[ ! -f "$AGENT_JAR" ]]; then
  if [[ -n "${AGENT_VERSION:-}" ]]; then
    URL="https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${AGENT_VERSION}/opentelemetry-javaagent.jar"
  else
    URL="https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/latest/download/opentelemetry-javaagent.jar"
  fi
  echo ">> downloading agent: $URL"
  curl -fsSL -o "$AGENT_JAR" "$URL"
fi
echo ">> agent jar: $AGENT_JAR"
java -jar "$AGENT_JAR" 2>/dev/null || true  # prints the agent version banner on some builds

# --- 2. Build the demo app ---------------------------------------------------------------------
echo ">> building demo app"
(cd "$ROOT" && ./gradlew -q :demo-dedup:installDist)
LIBS="$DIR/build/install/demo-dedup/lib/*"

# --- 3. Run helper -----------------------------------------------------------------------------
# The Micrometer bridge is enabled inside the YAML (distribution.javaagent.instrumentation.enabled);
# under declarative config the -Dotel.instrumentation.*.enabled system property is NOT consulted.
# The otlp_file/development exporter emits OTLP JSON through the agent logger (its output_stream key
# is ignored by the bundled provider), so we capture the whole process output and extract the JSON
# lines (each metric export is one {"resourceMetrics":...} object).
run() {
  local label="$1" config="$2" outfile="$3"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] running app under agent (config: $(basename "$config"))"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dotel.service.name=micrometer-dedup-demo \
    -Ddemo.run.millis="$RUN_MILLIS" \
    -cp "$LIBS" \
    com.grafana.micrometer.demo.DemoApp > "$rawlog" 2>&1 || { echo "app run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  # Extract OTLP JSON export lines, stripping any log-line prefix before the first '{'.
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] extracted $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

run baseline "$DIR/config/config-baseline.yaml" "$OUT_DIR/baseline.jsonl"
run deduped  "$DIR/config/config-deduped.yaml"  "$OUT_DIR/deduped.jsonl"

# --- 4. Assert ---------------------------------------------------------------------------------
echo
echo ">> verifying"
python3 "$DIR/verify.py" "$OUT_DIR/baseline.jsonl" "$OUT_DIR/deduped.jsonl" "$DIR/config/config-deduped.yaml"
