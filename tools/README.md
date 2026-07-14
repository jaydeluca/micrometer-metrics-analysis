# tools/ — OTel side + comparison

The Java modules (`capture-core`, `harness-tier*`) capture the **Micrometer** inventory at runtime.
These scripts produce the **OTel** inventory and **join the two**. Both inventories land in
`inventory/` so the comparison is one repo.

```
registry YAML ──extract_otel_inventory.py──▶ inventory/otel-<ver>.json ┐
                                                                        ├─compare.py─▶ output/comparison-report.md
harness-tier* run ─────────────────────────▶ inventory/micrometer-*.json ┘            inventory/comparison.json
```

## `extract_otel_inventory.py`

Pulls the agent's emitted metrics from the ecosystem-explorer registry
(`libraries[].telemetry[].metrics[]`, gated by `when:`), collapsing to one record per
`(name, when)` and aggregating the declaring libraries. Output is shaped to join against the
Micrometer inventory; every record keeps a `instrumentation.yaml:LINE` citation.

```bash
python3 tools/extract_otel_inventory.py            # latest stable registry version -> inventory/otel-<ver>.json
python3 tools/extract_otel_inventory.py --version v2.29.0 --registry-root ~/code/projects/opentelemetry-ecosystem-explorer
```

Reconciles with `context/otel-metrics.md`: 248 libraries, 110 emit metrics, 285 entries → 77 unique
names.

## `compare.py`

Joins the two inventories and renders the overlap/delta. Three layers, cheapest first:

1. **Exact-name join** — same metric name on both sides (e.g. `jvm.memory.used`). `direct` vs
   `semantic` is decided from instrument-type + unit compatibility.
2. **Curated concept map** (`concept_map.yaml`) — cross-name equivalences a human asserted
   (`jvm.gc.duration` ↔ `jvm.gc.pause`). This is the only hand-maintained input.
3. **Leftovers = gaps** — unmatched on either side. A gap in a technology the Micrometer harness has
   not captured yet is labeled `awaiting-mm-tierN` (not a true gap) so harness coverage is never
   mistaken for a Micrometer gap.

```bash
python3 tools/compare.py        # reads inventory/{otel-*,micrometer-*}.json + concept_map.yaml
```

Classes: `direct`, `semantic`, `partial`, `gap-otel-only`, `gap-mm-only`, `awaiting-mm-tierN`.

## Refresh both sides for a new version

```bash
./gradlew :harness-tier0:run                       # (+ tier1/2/3 as they land) → micrometer-*.json
python3 tools/extract_otel_inventory.py --version vX.Y.Z
python3 tools/compare.py
```

Bump `gradle/libs.versions.toml` (Micrometer) and `--version` (OTel) independently; the comparison
is "pin two versions → run both capture pipelines → diff."

## Requirements

Python 3.10+ with `pyyaml`. Read-only against a local
`opentelemetry-ecosystem-explorer` checkout.
