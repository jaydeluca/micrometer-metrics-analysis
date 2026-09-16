# experiment-meterfilter — `MeterFilter` semantics inside a `CompositeMeterRegistry`

Answers the `metric-bridge-interop` project's stage-02 questions **A1** and **A1b**: does a
`MeterFilter` installed on one child of a `CompositeMeterRegistry` deny only for that child, and are
meters registered before a child is added back-filled into it (with that child's filters applied)?

The leading design in that project — filter at the OTel agent's bridge registry, in front of its
eager OTel instrument construction — is only correct if the answer to A1 is yes.

```bash
./gradlew :experiment-meterfilter:run
```

One `main()`, no test framework. Prints PASS/FAIL per assertion and exits non-zero on any failure.

## The six experiments

| | What it establishes |
|---|---|
| E1 | A DENY on one child suppresses the meter in that child only; siblings register and record normally |
| E2 | A DENY prevents the child from *constructing* the meter, not just from publishing it |
| E3 | Meters registered before a child is added are back-filled into it, and the child's filters are applied to the back-fill (values recorded before the add are not replayed) |
| E3b | A filter installed *after* a meter is registered does not retro-apply to it |
| E4 | A DENY leaves a Micrometer **noop** in the composite meter's children, and `firstChild()` can answer reads from it — measured across both add orders |
| E5 | `MeterFilter#map` never reaches synthetic meters (percentile gauges); `accept`/DENY does |

E4 is the one that matters for the agent: its ASM-patched `firstChild()` skips children by the
`OpenTelemetryInstrument` marker interface, and a Micrometer noop is not one — so filtering
re-opens the read-corruption hole that patch exists to close.

Full write-up, with citations:
`jay-assistant/projects/metric-bridge-interop/research/20260824-composite-meterfilter-experiment.md`