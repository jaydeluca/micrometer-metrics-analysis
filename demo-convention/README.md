# demo-convention — does a semconv-named Micrometer meter defeat a name-keyed drop-set?

```bash
./run-convention-collision.sh
```

Two runs of a real Spring Boot 4 web app under the **real** OTel Java agent, with byte-identical
agent configuration. The only difference is which `ServerRequestObservationConvention` bean the app
registers:

| Run | Beans | Effect |
|---|---|---|
| `default` | Boot's defaults | HTTP timer named `http.server.requests` |
| `otel` | `OpenTelemetryServerRequestObservationConvention` (`spring-web`, `@since 7.0`) | HTTP timer named `http.server.request.duration` |
| `otel-jvm` | the four `OpenTelemetryJvm*MeterConventions` (micrometer-core) | 8 JVM/CPU meters renamed |

Those new names are the ones **the agent itself emits**. `verify-convention.py` asserts the
consequence (16/16) and characterizes each collision: unit, OTLP data type, and attribute-key sets on
both sides of the shared name.

## What it establishes

- The bridged HTTP timer moves from `http.server.requests` to `http.server.request.duration`, so a
  drop-set keyed on the Micrometer name — which is what
  `inventory/decisions-v2.31.1.json` is — has **no row** to match, and a
  `prefer-instrumentation`-style policy declines to drop.
- The resulting duplicate is *worse* than the one the policy does catch: same name, same unit (`s`),
  same instrument type (histogram), and unequal attribute keys (bridge adds `error`, `error.type`,
  `outcome`; native adds `network.protocol.version`), with both series counting the same requests.
  Two different names are diagnosable; one name with two attribute shapes is not.
- The bridge's structural suffixes follow the renamed base, so `http.server.request.duration.max`,
  `.active.active` and `.active.duration` appear too — three names under a semconv prefix that are
  not semconv metrics.
- **The JVM/CPU half is worse.** Spring Boot 4.1.1 wires micrometer-core's four `MeterConvention`
  interfaces through `ObjectProvider`, so enabling them renames 8 meters onto
  `runtime-telemetry`'s own names. **8/8 collide, 8/8 are absent from the drop-set, 8/8 disagree on
  unit, 4/8 on instrument type.** `jvm.cpu.time` arrives in `ns` against the agent's `s` — and `ns`
  is valid UCUM, so unit normalization cannot catch it.
- A stock Boot 4 app with actuator + web bridges **56–57 metrics**, which is the measured size of the
  problem the agent's own `SpringBootActuatorInstrumentationModule.defaultEnabled() == false`
  comment refers to.

Full writeup, with citations:
`jay-assistant/projects/metric-bridge-interop/research/20260825-convention-collision-probe.md`.

## Notes for re-running

- **Why a separate Gradle module** rather than a fourth app in `demo-dedup`: this needs Spring Boot 4
  on the runtime classpath, and `demo-dedup`'s three experiments all launch from one shared
  `build/install/demo-dedup/lib/*`. Adding Spring there would change the agent's instrumentation
  decisions for runs that already carry verified assertion counts (35/35, 15/15).
- **Boot metrics reach the bridge only via a second module.** `SpringBootActuatorInstrumentationModule`
  injects the bridge registry as a Spring bean and shares the instrumentation name `micrometer`, so
  the config's `enabled: [micrometer]` turns both on. It is `defaultEnabled() == false` upstream.
- **`-parameters` is set explicitly** in `build.gradle.kts`. The Boot Gradle plugin normally supplies
  it; we use only the BOM. Without it Spring cannot resolve `@PathVariable` names, every request
  500s, and the probe measures an error path instead of a route.
- **Service name is set in the YAML**, not with `-Dotel.service.name` — once a config file is active
  the agent stops reading the SDK system properties and `OTEL_*` variables.

Outputs land in `out/` (git-ignored): `*.jsonl` (extracted OTLP) and `*.log` (raw run output).
