#!/usr/bin/env bash
# Prefix experiment: can declarative-config metric Views add a prefix to ALL Micrometer metrics?
#
# Runs DemoApp under the OTel Java agent three times (bridge on throughout):
#   baseline  config/config-baseline.yaml          no views
#   wildcard  config/config-prefix-wildcard.yaml   one `*` view -> single literal name (naive attempt)
#   explicit  config/config-prefix-explicit.yaml   one view per metric -> literal micrometer.<name>
# then verify-prefix.py contrasts the bridged metric surface across the three, and we grep each run's
# raw log for the SDK duplicate-metric conflict warnings the wildcard attempt provokes.
#
# Reuses the same agent jar / build path as run-demo.sh.
# Usage:  ./run-prefix-experiment.sh
# Env:    AGENT_VERSION=<x.y.z>   pin an agent release (default: latest)
#         DEMO_RUN_MILLIS=15000   how long the app generates activity
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

# --- 2. Build the demo app ---------------------------------------------------------------------
echo ">> building demo app"
(cd "$ROOT" && ./gradlew -q :demo-dedup:installDist)
LIBS="$DIR/build/install/demo-dedup/lib/*"

# --- 3. Run helper -----------------------------------------------------------------------------
run() {
  local label="$1" config="$2" outfile="$3"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] running app under agent (config: $(basename "$config"))"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dotel.service.name=micrometer-prefix-demo \
    -Ddemo.run.millis="$RUN_MILLIS" \
    -cp "$LIBS" \
    com.grafana.micrometer.demo.DemoApp > "$rawlog" 2>&1 || { echo "app run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] extracted $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

run baseline "$DIR/config/config-baseline.yaml"        "$OUT_DIR/baseline.jsonl"
run wildcard "$DIR/config/config-prefix-wildcard.yaml" "$OUT_DIR/prefix-wildcard.jsonl"
run explicit "$DIR/config/config-prefix-explicit.yaml" "$OUT_DIR/prefix-explicit.jsonl"

# --- 4. Surface the SDK conflict warnings the wildcard attempt provokes ------------------------
echo
echo ">> SDK duplicate/conflict warnings in the wildcard run:"
if grep -iE 'duplicate|conflict|already.*(registered|exist)' "$OUT_DIR/prefix-wildcard.log" \
     | sed 's/^/     /' | head -20; then :; else echo "     (none matched — inspect prefix-wildcard.log)"; fi

# --- 5. Assert ---------------------------------------------------------------------------------
echo
echo ">> verifying"
python3 "$DIR/verify-prefix.py" \
  "$OUT_DIR/baseline.jsonl" "$OUT_DIR/prefix-wildcard.jsonl" "$OUT_DIR/prefix-explicit.jsonl"
