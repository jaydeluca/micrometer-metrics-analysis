# micrometer-metrics-inventory

Derive a **Micrometer metrics inventory at runtime**: construct Micrometer binders,
bind them to a `SimpleMeterRegistry`, drive minimal activity, read the resulting
`Meter`s back out, and serialize them to a machine-readable inventory file. This
mirrors how an OpenTelemetry inventory is derived from running integration tests,
so the two inventories can later be joined and diffed.

> Repo-name candidates (placeholder for now): `micrometer-metrics-inventory`,
> `micrometer-inventory`, `mm-semconv-inventory`, `micrometer-otel-diff`.

## Layout

```
capture-core/     # MeterRegistry capturer + JSON model + serializer
harness-tier0/    # pure-JVM / system / logging / executor / virtual-thread binders
harness-tier1/    # in-process libraries: caches, Commons Pool 2, Netty, OkHttp pool, HikariCP (H2)
harness-tier2/    # real traffic: Kafka (Testcontainers), gRPC + HTTP clients (in-process)
harness-tier3/    # Spring Boot app: http.server/client.requests, jdbc.connections.*, tomcat.*, spring.*
tools/            # OTel-side extractor + the join/report tool (Python)
inventory/        # generated output: micrometer-*.json, otel-*.json, comparison.json
output/           # generated comparison-report.md
```

Tier 0 (pure JVM) and Tier 1 (in-process libraries, no Docker/Spring) are built. Tier 2
(Testcontainers) has started with Kafka — the dynamic `kafka.*` names that can only be
enumerated by running a real client. Remaining Tier 2 targets (Mongo, JDBC pools, servlet
containers, HTTP clients, gRPC, JMS) and Tier 3 (Spring Boot) are next — see work-streams
Stage 5. The OTel inventory and the join/report tool are in `tools/` (Python); see
`tools/README.md`.

**The Kafka run needs Docker.** `runKafka` pins the docker-java API version (`api.version` system
property) and disables Ryuk by default, since modern Docker Desktop rejects docker-java's 1.32
fallback. Override via `DOCKER_API_VERSION` / `DOCKER_HOST` / `TESTCONTAINERS_RYUK_DISABLED` env
vars if your setup differs. `runGrpc` is fully in-process and needs no Docker.

> **Tier 1 note on JDBC pools:** only HikariCP has native (non-Spring) Micrometer metrics
> (`hikaricp.connections.*`, via `MicrometerMetricsTrackerFactory` — captured here against
> in-memory H2). DBCP2 / Tomcat JDBC / c3p0 / Vibur / Druid / Oracle UCP surface through
> Spring's `DataSourcePoolMetrics` (`jdbc.connections.*`) and belong to the Tier 3 Spring harness.

## The comparison, end to end

```bash
./gradlew :harness-tier0:run :harness-tier1:run    # -> inventory/micrometer-tier{0,1}.json
./gradlew :harness-tier2:runGrpc                    # -> inventory/micrometer-tier2-grpc.json        (no Docker)
./gradlew :harness-tier2:runHttpClient              # -> inventory/micrometer-tier2-httpclient.json   (no Docker)
./gradlew :harness-tier2:runKafka                   # -> inventory/micrometer-tier2-kafka.json        (needs Docker)
./gradlew :harness-tier3:runSpring                  # -> inventory/micrometer-tier3.json              (no Docker)
python3 tools/extract_otel_inventory.py            # -> inventory/otel-<ver>.json
python3 tools/compare.py                            # -> output/comparison-report.md + inventory/comparison.json
python3 tools/build_explorer.py                     # -> output/explorer.html  (interactive UI)
```

`build_explorer.py` inlines `inventory/comparison.json` (enriched with the concept-map rationale
and per-bucket caveats) into a single dependency-free `output/explorer.html` — open it directly in
a browser (no server). Search by metric name, filter by technology and match class, click the
summary matrix to drill in, hide the bridged Kafka set.

Tier 2 is split into per-technology run tasks (Kafka needs Docker; gRPC is in-process). Each
writes its own `inventory/micrometer-tier2-<tech>.json`, all merged by `compare.py`.

The Java side captures Micrometer at runtime; the Python side pulls the OTel agent's
metrics from the ecosystem-explorer registry and joins them on a shared per-technology
spine. Metric pairs are classed `direct` / `semantic` / `partial` / `gap`; OTel metrics in
a technology the Micrometer harness hasn't reached yet are labeled `awaiting-mm-tierN`, so
missing harness coverage is never mistaken for a real Micrometer gap.

## Run

```bash
./gradlew :harness-tier0:run
# writes inventory/micrometer-tier0.json and prints a coverage summary
```

The Micrometer version is pinned in `gradle/libs.versions.toml` (currently
**1.15.0**) and stamped into every record, so M6 can bump one line and diff.

## Per-record shape

```json
{
  "name": "jvm.memory.used",
  "meterType": "GAUGE",          // coarse Meter.Type (collapses FunctionCounter→COUNTER, etc.)
  "baseUnit": "bytes",           // null kept, not omitted — an absent unit is a captured fact
  "tagKeys": ["area", "id"],
  "description": "The amount of used memory",
  "emittedBy": "io.micrometer.core.instrument.binder.jvm.JvmMemoryMetrics",
  "technology": "jvm",
  "conventionVariant": "micrometer",
  "deprecated": false,
  "captureTier": 0,
  "micrometerVersion": "1.15.0",
  "jdk": "21",
  "source": "runtime"
}
```

The header stamps Micrometer version, git sha (only when built from source),
timestamp, JDK, OS, and per-tier attempted-vs-captured counts so silent coverage
gaps are visible. **Coverage == harness coverage**: a binder we don't exercise
won't appear.

## Finding: the convention variants, and what "otel" actually means in 1.15.x

The design anticipates capturing each JVM/CPU binder under both the default Micrometer
convention and an OpenTelemetry naming, tagged `conventionVariant: micrometer | otel`.
Verified against the published jars, there are two layers to this:

1. **No binder-level semconv switch exists.** `JvmMemoryMetrics`, `ProcessorMetrics`,
   etc. have exactly two constructors — `()` and `(Iterable<Tag>)` — no convention
   argument. `micrometer-core` has no `semconv`/`otel` naming hook; the
   `*ObservationConvention` types are for HTTP/gRPC observations, not JVM metric names.
   So a binder cannot be *told* to emit semconv names.

2. **The `otel` variant is therefore derived from the OTLP registry's export naming.**
   For each binder we apply `OtlpMeterRegistry`'s `NamingConvention` to the captured
   meters — i.e. the names an OpenTelemetry collector would actually receive
   (`OtlpMeterNaming`). No network publisher is started; only the convention is borrowed.

**Empirical result at tier 0: the OTLP export naming is identity — 0/53 names and
0/53 tag-key sets diverge from the Micrometer stored names.** This is expected (OTLP
uses dotted names natively, unlike Prometheus's snake_case) and is itself the captured
fact: *Micrometer's OTLP export preserves its dotted names verbatim*. The run prints
this divergence count every time, so a future version that starts transforming names
will show up immediately. Because divergence is currently zero, the `otel` rows are
verbatim copies of the `micrometer` rows apart from the variant tag — kept for now so
the M5 join can match an OTel inventory directly on `conventionVariant: otel`.
```
