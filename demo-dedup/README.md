# demo-dedup — end-to-end validation of the Micrometer dedup views

Experiments with declarative-config views in
`jay-assistant/projects/micrometer-otel-metrics-comparison/output/micrometer-dedup-config/otel-javaagent-micrometer-dedup.yaml`
with OpenTelemetry Java agent with the Micrometer bridge on,
they drop the bridged metrics that duplicate the agent's native instrumentation and keep
everything else — including the native copy of a name that *collides* (`jvm.memory.used`).

```bash
./run-demo.sh
```

## What it does

1. Downloads the OTel Java agent (latest release by default; pin with `AGENT_VERSION=x.y.z`).
2. Builds `DemoApp` (`installDist`), which binds a spread of Micrometer core binders to
   `io.micrometer.core.instrument.Metrics.globalRegistry` — the registry the agent's bridge
   attaches to (`MetricsInstrumentation` advice on the `Metrics` static initializer).
3. Runs the app under the agent **twice**, both with the bridge enabled:
   - `config/config-baseline.yaml` — no views (all duplicates present)
   - `config/config-deduped.yaml` — the dedup views (selectors verbatim from the deliverable)
   The agent's `otlp_file/development` exporter emits OTLP JSON via its logger; the script
   captures the process output and extracts the `{"resourceMetrics":...}` lines.
4. `verify.py` reads both captures + the deduped config's view selectors and asserts, per
   OpenTelemetry instrumentation scope:
   - bridged (scope `io.opentelemetry.micrometer-1.5`) metric matching a drop view → **gone**
   - bridged metric with no matching drop view → **kept**
   - native metric (any other scope), incl. the `jvm.memory.used` collision → **untouched**

The binders are chosen to cover all three cases: collisions (`jvm.memory.*`), drops
(`jvm.gc.pause`, `jvm.classes.loaded`, `process.*`, `system.*`, ...), and keeps
(`cache.*`, `jvm.gc.memory.allocated`, `jvm.threads.daemon`, `process.uptime`, ...).


Outputs into `out/` (git-ignored): `*.jsonl` (extracted OTLP) and `*.log` (raw run output).

## Misconfiguration experiment — the fix that looks like it worked

`./run-misconfig.sh` reproduces the way a competent user gets Micrometer + agent wrong. Four runs of
the real agent (2.31.1) over `MisconfigApp`, asserted by `verify-misconfig.py` (15/15).

The app has **custom business metrics** (`orders.placed`, `orders.latency`) that only the bridge can
collect, plus JVM binders that duplicate `jvm.memory.used` against the agent's native copy.

| Run | Config | (scope, metric) pairs | Bridged |
|---|---|---|---|
| `sysprops` | `-Dotel.instrumentation.micrometer.enabled=true`, no config file | 27 | **15** |
| `naive-views` | + a views YAML, no enable node | 13 | **0** |
| `fixed` | + `distribution.javaagent.instrumentation.enabled: [micrometer]` | 24 | 11 |
| `env-ignored` | `fixed` + `OTEL_METRICS_EXPORTER=none` in the env | 24 | 11 |

Adding a config file to get views makes the agent stop reading `otel.instrumentation.*.enabled`, so
the bridge never starts. **The duplication disappears — which is exactly what the user was watching
for — because every bridged metric disappeared**, `orders.*` included. The string `micrometer`
appears **zero** times in that run's log; the one WARN emitted is about `file_format`.

Two more traps fire in the same script: the `fixed` run's exact-name view for `jvm.gc.pause` leaves
an orphaned `jvm.gc.pause.max` behind, and `env-ignored` shows `OTEL_*` SDK variables are no longer
read once a config file is active.

## Surface-delta experiment — what actually changes under `v3-preview`?

`./run-surface-delta.sh` answers it by capture rather than by reading flag names. Six runs of the
real agent (**2.31.1** by default — the `.max` change landed in 2.31.0, so the 2.29.0 jar `run-demo.sh`
pins shows nothing), diffed per instrumentation scope by `diff-surface.py`.

`BridgeSurfaceApp` registers **one meter of every Micrometer type** under `demo.*` names, plus
`JvmGcMetrics` as a real-binder control. `KafkaSurfaceApp` builds a `KafkaProducer` against a dead
port and binds Micrometer's `KafkaClientMetrics` to it — **no Docker**, because a Kafka client
registers its metrics with every configured `MetricsReporter` at construction, which is where the
agent injects its own.

Three results:

1. **Under default config the only bridge delta is `.max`** — 22 metrics → 19, exactly one companion
   per `Timer`/`DistributionSummary`. Nothing added, renamed, or retyped.
2. **The custom-meter statistic-suffix reordering is invisible unless `prometheus_mode` is on**,
   because `Bridging`'s two branches agree under the identity naming convention. Under
   `prometheus_mode` five names move (`demo.custom.value.bytes` → `demo.custom.bytes.value`), which
   aligns custom `Meter`s with what `FunctionTimer`/`LongTaskTimer` already did.
3. **The agent's Kafka bridge goes 59 → 2 metrics** while the Micrometer side holds at 60. The two
   survivors are `messaging.client.*`, emitted by the Kafka *messaging* instrumentation on the **same
   scope name** as the bridge — so unlike `micrometer-1.5`, the Kafka bridge cannot be scope-pinned
   by a view.

The v2 Kafka run is also the cleanest artifact for the duplication problem itself: 119 instruments
for one producer, **0 exact-name overlap**, **59/59 after normalizing `_` → `.`**.

## Prefix experiment — can Views rename all Micrometer metrics with a prefix?

**No — not as a bulk operation.** `./run-prefix-experiment.sh` proves it end-to-end (three runs:
baseline, naive wildcard, explicit per-metric).

Two facts, both verified by `verify-prefix.py`:

1. **Wildcard prefix collapses instead of prefixing.** `stream.name` is a static literal, not a
   template (there is no `micrometer.{name}` syntax), so a `*` selector renames every matched
   instrument to the *same* name. In the run, all 34 bridged metrics collapsed onto a single
   `micrometer.all`, and the SDK logged `MetricStorageRegistry - Found duplicate metric definition:
   micrometer.all / Conflicting view registered` once per instrument.
2. **Explicit one-view-per-metric renames work but don't scale.** Each enumerated metric moved to
   its `micrometer.<name>` (original gone); the 29 metrics we didn't list kept their original names.
   Prefixing the whole surface this way means hand-listing every metric and silently missing any you
   forget.

Bulk prefixing belongs elsewhere: a Collector `transform`/`metricstransform` processor (regex rename
scoped to `io.opentelemetry.micrometer-1.5`), or a Micrometer-side `MeterFilter` on the global
registry applied before the bridge.

## Bridge-mode experiment — Layer A vs Layer B, and mode vs views

`./run-mode.sh` needs a **patched agent** built from the `metric-bridge-interop`
`prefer-instrumentation-spike` branch, which adds an experimental
`otel.instrumentation.micrometer.experimental.metrics.mode` (declarative:
`java.micrometer.metrics/development.mode`). Every script here now takes `AGENT_JAR=<path>` to run
against a locally built agent instead of a downloaded release.

```bash
AGENT_JAR=~/code/projects/opentelemetry-java-instrumentation/javaagent/build/libs/opentelemetry-javaagent-2.32.0-SNAPSHOT.jar ./run-mode.sh
```

Five runs, asserted by `verify-mode.py` (45/45). Two independent questions:

1. **What stops being exported.** `DemoApp` under `config-baseline.yaml` vs
   `config-mode-prefer-instrumentation.yaml`. Every assertion is keyed on
   `(instrumentation scope, metric name)` — never on name alone, because the bridge and the agent's
   native instrumentation both emit `jvm.memory.used`, and the bridge ships `X` alongside `X.max`
   and `X.count`, so prefix matching silently lies.
2. **What is left in the composite.** `CompositeReadApp` adds a `SimpleMeterRegistry` to
   `Metrics.globalRegistry` and reads suppressed meters back through it — the path Actuator's
   `/actuator/metrics` takes. It runs twice: once normally, once with
   `-Dotel.javaagent.micrometer.spike.unmarked-suppression=true`, which makes the bridge leave plain
   Micrometer noops instead of marked instruments — the artifact a `MeterFilter` DENY produces.

The result: **4/4 suppressed meters read back correctly when the placeholder carries the
`OpenTelemetryInstrument` marker, and 4/4 read back `0.0` without it** (control unaffected in both).
That is the acceptance test for suppressing inside the bridge rather than filtering in front of it.

The same run also shows the mode's drop-set is a **strict subset** of the shipped views file — 14
drops shared, 4 dropped by views only (`jvm.gc.pause`, `jvm.gc.pause.max`, `jvm.threads.live`,
`process.cpu.time`), 0 by the mode only — and that a suppressed `Timer` takes its `.max` companion
with it instead of orphaning it.
