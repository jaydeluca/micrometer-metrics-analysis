#!/usr/bin/env bash
# Does the resolver's second, name-symmetric rule close the convention collision?
# (metric-bridge-interop, stage 04, following on from run-convention-collision.sh.)
#
# run-convention-collision.sh established the problem against a released agent: when the app opts
# into Spring's or Micrometer's OpenTelemetry naming conventions, the bridge emits metrics under the
# agent's own names, and a drop-set keyed on Micrometer names has no row for them. This script runs
# the same probe app against the PATCHED agent and asks whether rule 2 fires.
#
# Four runs, one config difference each:
#
#   http-all    otel HTTP convention,  mode=all     -> `http.server.request.duration` twice, one name
#   http-mode   otel HTTP convention,  mode=prefer  -> the bridged copy should be gone
#   jvm-all     otel JVM conventions,  mode=all     -> 8 renamed JVM metrics colliding with the agent
#   jvm-mode    otel JVM conventions,  mode=prefer  -> the bridged copies should be gone
#
#   AGENT_JAR=<path-to>/opentelemetry-javaagent-*-SNAPSHOT.jar ./run-convention-mode.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
OUT_DIR="$DIR/out"
AGENT_JAR="${AGENT_JAR:-$DIR/.agent/opentelemetry-javaagent.jar}"
RUN_MILLIS="${DEMO_RUN_MILLIS:-12000}"
PROBE_PORT="${PROBE_PORT:-18081}"

mkdir -p "$OUT_DIR"
[[ -f "$AGENT_JAR" ]] || { echo "no agent jar at $AGENT_JAR — set AGENT_JAR"; exit 1; }
echo ">> agent jar: $AGENT_JAR"

echo ">> building probe app"
(cd "$ROOT" && ./gradlew -q :demo-convention:installDist)
LIBS="$DIR/build/install/demo-convention/lib/*"

run() {
  local label="$1" config="$2" http_convention="$3" jvm_convention="$4"
  local outfile="$OUT_DIR/mode-$label.jsonl"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] http:$http_convention jvm:$jvm_convention $(basename "$config")"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dprobe.convention="$http_convention" \
    -Dprobe.jvm.convention="$jvm_convention" \
    -Dprobe.port="$PROBE_PORT" \
    -Ddemo.run.millis="$RUN_MILLIS" \
    -cp "$LIBS" \
    com.grafana.micrometer.convention.ConventionProbeApp > "$rawlog" 2>&1 &
  local pid=$!
  local deadline=$(( (RUN_MILLIS / 1000) + 120 ))
  local waited=0
  while kill -0 "$pid" 2>/dev/null; do
    if (( waited >= deadline )); then
      echo "!! [$label] still running after ${deadline}s — killing; see $rawlog"
      kill -9 "$pid" 2>/dev/null || true
      tail -40 "$rawlog"
      exit 1
    fi
    sleep 2
    waited=$(( waited + 2 ))
  done
  wait "$pid" || { echo "run failed; see $rawlog"; tail -40 "$rawlog"; exit 1; }
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] extracted $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

BASE_CFG="$DIR/config/config-convention.yaml"
MODE_CFG="$DIR/config/config-convention-mode.yaml"

run http-all  "$BASE_CFG" otel    micrometer
run http-mode "$MODE_CFG" otel    micrometer
run jvm-all   "$BASE_CFG" default otel
run jvm-mode  "$MODE_CFG" default otel

echo
echo ">> verifying"
python3 "$DIR/verify-convention-mode.py" \
  --http-all "$OUT_DIR/mode-http-all.jsonl" \
  --http-mode "$OUT_DIR/mode-http-mode.jsonl" \
  --jvm-all "$OUT_DIR/mode-jvm-all.jsonl" \
  --jvm-mode "$OUT_DIR/mode-jvm-mode.jsonl"
