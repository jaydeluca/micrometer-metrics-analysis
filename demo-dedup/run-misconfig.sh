#!/usr/bin/env bash
# Reproduce the worked misconfiguration of FM-3 (metric-bridge-interop, work-stream 01 task 1.2).
#
# The narrative, in four runs of the REAL agent over the same app:
#
#   A  sysprops     -Dotel.instrumentation.micrometer.enabled=true, no config file.
#                   The working starting point: custom business metrics present, JVM duplicated.
#   B  naive-views  A's flags PLUS -Dotel.experimental.config.file=config-misconfig-naive.yaml.
#                   The user's fix for the duplication. The duplication goes away. So does the
#                   bridge, and with it every custom metric — silently.
#   C  fixed        B plus `distribution.javaagent.instrumentation.enabled: [micrometer]`.
#                   What they meant. Duplicates dropped, custom metrics kept.
#   D  env-ignored  C, but with OTEL_METRICS_EXPORTER=none in the environment. If metrics still
#                   arrive, declarative config really did stop reading the OTEL_* SDK vars.
#
# Note the exporters differ by necessity, not by choice: run A cannot use the declarative-only
# `otlp_file/development` exporter, so it uses `logging-otlp`. Both preserve instrumentation scope,
# which is the only property the assertions depend on. (That the exporter has to be re-declared at
# all when moving to a config file is itself trap #3 in this story.)
#
# Usage:   ./run-misconfig.sh
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
MAIN=com.grafana.micrometer.demo.MisconfigApp

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

# Extract OTLP JSON from either exporter: `otlp_file/development` logs {"resourceMetrics":[...]}
# per line, `logging-otlp` logs a bare ResourceMetrics {"resource":...,"scopeMetrics":[...]}.
extract() {
  grep -E '"resourceMetrics"|"scopeMetrics"' "$1" | sed 's/^[^{]*//' > "$2" || true
}

run() {
  local label="$1"; shift
  local outfile="$OUT_DIR/misconfig-$label.jsonl"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] running MisconfigApp under agent"
  java "$@" \
    -javaagent:"$AGENT_JAR" \
    -Dotel.service.name=micrometer-misconfig-demo \
    -Ddemo.run.millis="$RUN_MILLIS" \
    -cp "$LIBS" \
    "$MAIN" > "$rawlog" 2>&1 || { echo "run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  extract "$rawlog" "$outfile"
  echo ">> [$label] extracted $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

# A — the working starting point. No config file; the system property is honored.
run sysprops \
  -Dotel.instrumentation.micrometer.enabled=true \
  -Dotel.metrics.exporter=logging-otlp -Dotel.traces.exporter=none -Dotel.logs.exporter=none \
  -Dotel.metric.export.interval=3000

# B — the misconfiguration. Same flags, plus a config file. The property is now ignored.
run naive-views \
  -Dotel.instrumentation.micrometer.enabled=true \
  -Dotel.config.file="$DIR/config/config-misconfig-naive.yaml" \
  -Dotel.experimental.config.file="$DIR/config/config-misconfig-naive.yaml"

# C — the fix.
run fixed \
  -Dotel.instrumentation.micrometer.enabled=true \
  -Dotel.config.file="$DIR/config/config-misconfig-fixed.yaml" \
  -Dotel.experimental.config.file="$DIR/config/config-misconfig-fixed.yaml"

# D — same as C, but with an OTEL_* SDK var that would silence metrics if it were still read.
echo ">> [env-ignored] re-running the fixed config with OTEL_METRICS_EXPORTER=none in the env"
export OTEL_METRICS_EXPORTER=none
run env-ignored \
  -Dotel.instrumentation.micrometer.enabled=true \
  -Dotel.config.file="$DIR/config/config-misconfig-fixed.yaml" \
  -Dotel.experimental.config.file="$DIR/config/config-misconfig-fixed.yaml"
unset OTEL_METRICS_EXPORTER

echo
echo ">> verifying"
python3 "$DIR/verify-misconfig.py" "$OUT_DIR" --agent-version "$AGENT_VERSION"
