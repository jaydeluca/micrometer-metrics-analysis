#!/usr/bin/env bash
# Layer A vs Layer B acceptance run for the metric-bridge-interop prototype spike.
#
# Requires an agent built from the metric-bridge-interop/prefer-instrumentation-spike branch:
#   AGENT_JAR=<path-to>/opentelemetry-javaagent-*-SNAPSHOT.jar ./run-mode.sh
#
# Four runs of the real agent:
#   1. baseline          DemoApp, bridge on, no mode        -> every bridged metric present
#   2. mode              DemoApp, mode=prefer-instrumentation -> the suppression set is gone
#   3. read-marked       CompositeReadApp, mode on            -> composite reads stay correct
#   4. read-unmarked     CompositeReadApp, mode on + the spike lever that returns plain Micrometer
#                        noops instead of marked instruments -- the artifact a MeterFilter DENY
#                        leaves behind, i.e. Layer A
#
# verify-mode.py asserts 1 vs 2; runs 3 and 4 print PROBE lines it reads directly.
#
# Runs 3 and 4 are REPEATED, because the failure they probe is nondeterministic.
# AbstractCompositeMeter holds its per-registry children in an IdentityHashMap (:23,36), so
# firstChild() iterates in identity-hash order -- which varies from JVM run to JVM run. An unmarked
# noop is therefore read back wrongly only in the runs where the bridge's child happens to sort
# first: measured 6 of 10 runs. One run of each would make this suite flaky in both directions, so
# the claim is stated over a sample instead: marked must be correct in EVERY run, unmarked must be
# corrupted in at least one.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$DIR/.." && pwd)"
OUT_DIR="$DIR/out"
AGENT_JAR="${AGENT_JAR:-$DIR/.agent/opentelemetry-javaagent.jar}"
RUN_MILLIS="${DEMO_RUN_MILLIS:-15000}"

mkdir -p "$OUT_DIR"
[[ -f "$AGENT_JAR" ]] || { echo "no agent jar at $AGENT_JAR — set AGENT_JAR"; exit 1; }
echo ">> agent jar: $AGENT_JAR"

echo ">> building demo app"
(cd "$ROOT" && ./gradlew -q :demo-dedup:installDist)
LIBS="$DIR/build/install/demo-dedup/lib/*"

run() {
  local label="$1" config="$2" mainclass="$3" outfile="$4"; shift 4
  local rawlog="${outfile%.jsonl}.log"
  rm -f "$outfile" "$rawlog"
  echo ">> [$label] $mainclass (config: $(basename "$config"))"
  java \
    -javaagent:"$AGENT_JAR" \
    -Dotel.config.file="$config" \
    -Dotel.experimental.config.file="$config" \
    -Dotel.service.name=micrometer-mode-demo \
    -Ddemo.run.millis="$RUN_MILLIS" \
    "$@" \
    -cp "$LIBS" \
    "com.grafana.micrometer.demo.$mainclass" > "$rawlog" 2>&1 \
    || { echo "run failed; see $rawlog"; tail -30 "$rawlog"; exit 1; }
  grep '"resourceMetrics"' "$rawlog" | sed 's/^[^{]*//' > "$outfile" || true
  echo ">> [$label] $(wc -l < "$outfile" | tr -d ' ') OTLP export line(s) -> $outfile"
}

BASE_CFG="$DIR/config/config-baseline.yaml"
MODE_CFG="$DIR/config/config-mode-prefer-instrumentation.yaml"

rm -f "$OUT_DIR"/mode-read-marked-*.jsonl "$OUT_DIR"/mode-read-marked-*.log \
      "$OUT_DIR"/mode-read-unmarked-*.jsonl "$OUT_DIR"/mode-read-unmarked-*.log

run baseline      "$BASE_CFG" DemoApp          "$OUT_DIR/mode-baseline.jsonl"
run mode          "$MODE_CFG" DemoApp          "$OUT_DIR/mode-prefer.jsonl"
run probe-all     "$BASE_CFG" CompositeReadApp "$OUT_DIR/mode-probe-all.jsonl"

REPEATS="${MODE_PROBE_REPEATS:-6}"
for i in $(seq 1 "$REPEATS"); do
  run "read-marked/$i"   "$MODE_CFG" CompositeReadApp "$OUT_DIR/mode-read-marked-$i.jsonl"
  run "read-unmarked/$i" "$MODE_CFG" CompositeReadApp "$OUT_DIR/mode-read-unmarked-$i.jsonl" \
    -Dotel.javaagent.micrometer.spike.unmarked-suppression=true
done

echo
echo ">> verifying"
python3 "$DIR/verify-mode.py" \
  "$OUT_DIR/mode-baseline.jsonl" \
  "$OUT_DIR/mode-prefer.jsonl" \
  "$OUT_DIR/mode-probe-all.jsonl" \
  "$OUT_DIR/mode-read-marked-1.jsonl" \
  "$OUT_DIR"
