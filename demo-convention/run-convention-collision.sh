#!/usr/bin/env bash
# Does opting into Spring's semconv-named observation convention defeat a drop-set keyed on
# Micrometer's historical metric name? (metric-bridge-interop, stage 02 item A3.)
#
# Runs ConventionProbeApp — a real Spring Boot 4 web app — under the REAL agent twice, with the
# Micrometer bridge on and identical agent configuration. The ONLY difference is which
# ServerRequestObservationConvention bean the app registers:
#
#   default  DefaultServerRequestObservationConvention          -> meter `http.server.requests`
#   otel     OpenTelemetryServerRequestObservationConvention    -> meter `http.server.request.duration`
#                                                                  (spring-web, @since 7.0)
#
# The drop-set (inventory/decisions-v2.31.1.json) holds a drop(duplicate) row for
# `http.server.requests` and no row for `http.server.request.duration`, so the `otel` run is the
# case where `prefer-instrumentation` looks up a key that is not there — while the collision it
# exists to prevent is at its worst, because both sides now share one metric name.
#
# Usage:   ./run-convention-collision.sh
# Env:     AGENT_VERSION=<x.y.z>   pin an agent release (default: 2.31.1)
#          DEMO_RUN_MILLIS=12000   how long the app stays up after driving traffic
#          PROBE_PORT=18080        port the app binds
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
AGENT_VERSION="${AGENT_VERSION:-2.31.1}"
AGENT_DIR="$DIR/.agent-$AGENT_VERSION"
OUT_DIR="$DIR/out"
AGENT_JAR="$AGENT_DIR/opentelemetry-javaagent.jar"
RUN_MILLIS="${DEMO_RUN_MILLIS:-12000}"
PROBE_PORT="${PROBE_PORT:-18080}"

mkdir -p "$AGENT_DIR" "$OUT_DIR"

if [[ ! -f "$AGENT_JAR" ]]; then
  # Reuse demo-dedup's cached jar when it is the same version rather than downloading twice.
  SIBLING="$ROOT/demo-dedup/.agent-$AGENT_VERSION/opentelemetry-javaagent.jar"
  if [[ -f "$SIBLING" ]]; then
    echo ">> reusing cached agent jar from demo-dedup"
    cp "$SIBLING" "$AGENT_JAR"
  else
    URL="https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${AGENT_VERSION}/opentelemetry-javaagent.jar"
    echo ">> downloading agent: $URL"
    curl -fsSL -o "$AGENT_JAR" "$URL"
  fi
fi
echo ">> agent jar: $AGENT_JAR ($(unzip -p "$AGENT_JAR" META-INF/MANIFEST.MF | grep Implementation-Version | tr -d '\r'))"

echo ">> building probe app"
(cd "$ROOT" && ./gradlew -q :demo-convention:installDist)
LIBS="$DIR/build/install/demo-convention/lib/*"

run() {
  local label="$1" convention="$2" jvm_convention="${3:-micrometer}"
  local outfile="$OUT_DIR/convention-$label.jsonl"
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] running ConventionProbeApp under agent (http: $convention, jvm: $jvm_convention)"
  # Watchdog: Tomcat runs non-daemon threads, so a probe that dies before its System.exit would
  # otherwise hang this script indefinitely rather than failing.
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$DIR/config/config-convention.yaml" \
    -Dotel.experimental.config.file="$DIR/config/config-convention.yaml" \
    -Dprobe.convention="$convention" \
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

run default  default micrometer
run otel     otel    micrometer
# The JVM/CPU half. Boot 4.1.1 wires micrometer-core's four MeterConvention interfaces through
# ObjectProvider, so `convention/otel/*` became reachable from Boot. Held separate from the HTTP run
# so each rename's effect is attributable.
run otel-jvm default otel

echo
echo ">> verifying"
python3 "$DIR/verify-convention.py" \
  --default "$OUT_DIR/convention-default.jsonl" \
  --otel "$OUT_DIR/convention-otel.jsonl" \
  --otel-jvm "$OUT_DIR/convention-otel-jvm.jsonl" \
  --decisions "$ROOT/inventory/decisions-v2.31.1.json" \
  --agent-version "$AGENT_VERSION"
