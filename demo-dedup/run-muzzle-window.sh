#!/usr/bin/env bash
# The muzzle window — decision 2 of the metric-bridge-interop prototype stage.
#
# `prefer-instrumentation` resolves "the agent already emits this" from the semantic-convention
# gate and from whether the instrumentation is enabled. Neither is the same as the instrumentation
# having been APPLIED: muzzle matches per class load against the library version actually on the
# application's class path, and the agent's hikaricp-3.0 module declares versions [3.0.0,).
#
# HikariCP has shipped a Micrometer metrics tracker since 2.7, so the Micrometer copy of the pool
# metrics exists on both sides of that floor while the agent's copy exists on only one. Four runs,
# same app, same agent, same config — only the HikariCP jar and the mode change:
#
#   1. above-all    Hikari 5.1.0, mode=all      -> both copies present (the duplication)
#   2. above-mode   Hikari 5.1.0, mode=prefer   -> Micrometer copy dropped, agent copy remains
#   3. below-all    Hikari 2.7.9, mode=all      -> only the Micrometer copy exists (muzzle declined)
#   4. below-mode   Hikari 2.7.9, mode=prefer   -> dropped anyway. THE WINDOW: signal lost outright.
#
# Plus a short 5th run with agent debug logging on, to capture the muzzle mismatch itself rather
# than inferring it from the absence of metrics.
#
# All runs set otel.semconv-stability.opt-in=database: the agent's pool metrics are gated on it, so
# without it the resolver correctly withholds the drop and nothing interesting happens either side.
#
#   AGENT_JAR=<path-to>/opentelemetry-javaagent-*-SNAPSHOT.jar ./run-muzzle-window.sh
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
OUT_DIR="$DIR/out"
AGENT_JAR="${AGENT_JAR:-$DIR/.agent/opentelemetry-javaagent.jar}"
RUN_MILLIS="${DEMO_RUN_MILLIS:-15000}"

mkdir -p "$OUT_DIR"
[[ -f "$AGENT_JAR" ]] || { echo "no agent jar at $AGENT_JAR — set AGENT_JAR"; exit 1; }
echo ">> agent jar: $AGENT_JAR"

echo ">> building demo app and both HikariCP class paths"
(cd "$ROOT" && ./gradlew -q :demo-dedup:installDist :demo-dedup:hikariAboveFloorLibs :demo-dedup:hikariBelowFloorLibs)
BASE_LIBS="$DIR/build/install/demo-dedup/lib/*"
ABOVE_LIBS="$DIR/build/hikari-above-floor/*"
BELOW_LIBS="$DIR/build/hikari-below-floor/*"

run() {
  local label="$1" config="$2" hikari="$3" outfile="$4"; shift 4
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] $(basename "$config") + $(basename "$(dirname "$hikari")")"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dotel.service.name=micrometer-muzzle-window \
    -Dotel.semconv-stability.opt-in=database \
    -Ddemo.run.millis="$RUN_MILLIS" \
    "$@" \
    -cp "$BASE_LIBS:$hikari" \
    com.grafana.micrometer.demo.MuzzleWindowApp > "$rawlog" 2>&1 \
    || { echo "run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s), hikari $(grep -o 'PROBE hikaricp.version=.*' "$rawlog" | head -1)"
}

BASE_CFG="$DIR/config/config-baseline.yaml"
MODE_CFG="$DIR/config/config-mode-prefer-instrumentation.yaml"

run above-all  "$BASE_CFG" "$ABOVE_LIBS" "$OUT_DIR/muzzle-above-all.jsonl"
run above-mode "$MODE_CFG" "$ABOVE_LIBS" "$OUT_DIR/muzzle-above-mode.jsonl"
run below-all  "$BASE_CFG" "$BELOW_LIBS" "$OUT_DIR/muzzle-below-all.jsonl"
run below-mode "$MODE_CFG" "$BELOW_LIBS" "$OUT_DIR/muzzle-below-mode.jsonl"

# The muzzle decision itself, not inferred from missing metrics. MuzzleMatcher logs the mismatch at
# FINE, promoted to WARNING when the agent is in debug mode (MuzzleMatcher.java:53).
echo ">> [muzzle-log] capturing the mismatch with agent debug logging"
DEMO_RUN_MILLIS=2000 java \
  -javaagent:"$AGENT_JAR" \
  -Dotel.config.file="$MODE_CFG" \
  -Dotel.experimental.config.file="$MODE_CFG" \
  -Dotel.javaagent.debug=true \
  -Dotel.semconv-stability.opt-in=database \
  -Ddemo.run.millis=2000 \
  -cp "$BASE_LIBS:$BELOW_LIBS" \
  com.grafana.micrometer.demo.MuzzleWindowApp > "$OUT_DIR/muzzle-below-debug.log" 2>&1 || true
grep -c "mismatched references" "$OUT_DIR/muzzle-below-debug.log" >/dev/null 2>&1 \
  && echo ">> [muzzle-log] mismatch lines captured" || echo ">> [muzzle-log] no mismatch lines found"

echo
echo ">> verifying"
python3 "$DIR/verify-muzzle-window.py" \
  "$OUT_DIR/muzzle-above-all.jsonl" \
  "$OUT_DIR/muzzle-above-mode.jsonl" \
  "$OUT_DIR/muzzle-below-all.jsonl" \
  "$OUT_DIR/muzzle-below-mode.jsonl" \
  "$OUT_DIR/muzzle-below-debug.log"
