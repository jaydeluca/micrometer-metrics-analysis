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
