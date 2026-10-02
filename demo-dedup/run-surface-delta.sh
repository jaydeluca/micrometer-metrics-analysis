#!/usr/bin/env bash
# Empirically confirm the micrometer-1.5 bridge's emitted-surface delta across
# otel.instrumentation.common.v3-preview (metric-bridge-interop, work-stream 01 task 1.3).
#
# Runs BridgeSurfaceApp — one meter of every Micrometer type — under the REAL agent four times:
#
#   A  v2 (v3-preview off), prometheus_mode off   <- today's default
#   B  v3-preview on,       prometheus_mode off
#   C  v2,                  prometheus_mode on
#   D  v3-preview on,       prometheus_mode on
#
# A-vs-B isolates the `.max` suppression; C-vs-D additionally exposes the custom-Meter
# statistic-suffix ordering, which is invisible under the identity naming convention.
#
# NOTE the agent version: the `.max` suppression landed in 2.31.0 (CHANGELOG #19397), so the
# 2.29.0 jar that run-demo.sh pins does NOT exhibit it. Default here is 2.31.1, matching the
# registry pin the decision table uses.
#
# Usage:   ./run-surface-delta.sh
# Env:     AGENT_VERSION=<x.y.z>   pin an agent release (default: 2.31.1)
#          DEMO_RUN_MILLIS=12000   how long the app generates activity
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
AGENT_VERSION="${AGENT_VERSION:-2.31.1}"
AGENT_DIR="$DIR/.agent-$AGENT_VERSION"
OUT_DIR="$DIR/out"
AGENT_JAR="$AGENT_DIR/opentelemetry-javaagent.jar"
RUN_MILLIS="${DEMO_RUN_MILLIS:-12000}"

mkdir -p "$AGENT_DIR" "$OUT_DIR"

if [[ ! -f "$AGENT_JAR" ]]; then
  URL="https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${AGENT_VERSION}/opentelemetry-javaagent.jar"
  echo ">> downloading agent: $URL"
  curl -fsSL -o "$AGENT_JAR" "$URL"
fi
echo ">> agent jar: $AGENT_JAR ($(unzip -p "$AGENT_JAR" META-INF/MANIFEST.MF | grep Implementation-Version | tr -d '\r'))"

echo ">> building demo app"
(cd "$ROOT" && ./gradlew -q :demo-dedup:installDist)
LIBS="$DIR/build/install/demo-dedup/lib/*"

run() {
  local label="$1" config="$2" mainclass="$3"
  local outfile="$OUT_DIR/surface-$label.jsonl"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] running ${mainclass##*.} under agent (config: $(basename "$config"))"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dotel.service.name=micrometer-surface-demo \
    -Ddemo.run.millis="$RUN_MILLIS" \
    -cp "$LIBS" \
    "$mainclass" > "$rawlog" 2>&1 || { echo "run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] extracted $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

SURFACE=com.grafana.micrometer.demo.BridgeSurfaceApp
KAFKA=com.grafana.micrometer.demo.KafkaSurfaceApp

run v2      "$DIR/config/config-surface-v2.yaml"      "$SURFACE"
run v3      "$DIR/config/config-surface-v3.yaml"      "$SURFACE"
run v2-prom "$DIR/config/config-surface-v2-prom.yaml" "$SURFACE"
run v3-prom "$DIR/config/config-surface-v3-prom.yaml" "$SURFACE"

# The other half of the v2/v3 delta: the agent's kafka-clients-metrics bridge is on by default
# today and off under v3-preview, which is what 115 of the 155 duplicate drops depend on.
run kafka-v2 "$DIR/config/config-surface-v2.yaml" "$KAFKA"
run kafka-v3 "$DIR/config/config-surface-v3.yaml" "$KAFKA"

echo
echo ">> diffing"
python3 "$DIR/diff-surface.py" \
  --pair identity "$OUT_DIR/surface-v2.jsonl" "$OUT_DIR/surface-v3.jsonl" \
  --pair prometheus_mode "$OUT_DIR/surface-v2-prom.jsonl" "$OUT_DIR/surface-v3-prom.jsonl" \
  --agent-version "$AGENT_VERSION"

echo
echo ">> diffing kafka (scope-level, both bridges)"
python3 "$DIR/diff-surface.py" \
  --pair kafka "$OUT_DIR/surface-kafka-v2.jsonl" "$OUT_DIR/surface-kafka-v3.jsonl" \
  --agent-version "$AGENT_VERSION" --by-scope --no-name-table
