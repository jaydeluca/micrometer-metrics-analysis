#!/usr/bin/env python3
"""Pull the OpenTelemetry Java agent metric inventory from the ecosystem-explorer registry.

This is the OTel-side counterpart to the runtime Micrometer capture (harness-tier*). Where the
Micrometer inventory is derived by binding meters and reading them back, the OTel inventory is
derived from the registry that the agent's integration tests already produce. The output is shaped
to join cleanly against ``inventory/micrometer-*.json`` (see ``tools/compare.py``).

The registry stores metrics per library under a ``telemetry`` block carrying a ``when:`` condition
(``default``, a config-flag gate, a ``otel.semconv-stability.opt-in=...`` gate, or a ``JavaNN``
runtime gate). The same metric name is declared by many libraries and under several ``when``
conditions, so we collapse to one record per ``(name, when)`` and aggregate the declaring libraries.

Two registry file formats are supported:

* **0.5 and earlier** inline the definitions at ``libraries[].telemetry[].metrics[]``.
* **0.6** (first seen in ``v2.31.0``) hoists shared definitions into a top-level
  ``definitions.metrics`` catalog and references them by id from
  ``libraries[].telemetry[].metric_refs[]``. We resolve those refs against the catalog, matching
  the explorer's own resolver in
  ``ecosystem-automation/explorer-db-builder/.../instrumentation_transformer.py``
  (unknown refs are warned about and skipped, never fatal).

Usage:
    python3 tools/extract_otel_inventory.py \
        [--registry-root ~/code/projects/opentelemetry-ecosystem-explorer] \
        [--version v2.29.0] \
        [--out inventory/otel-<version>.json]

If --version is omitted, the latest stable ``vX.Y.Z`` dir is used (``-SNAPSHOT`` ignored).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


# --- line-tracking YAML loader (so every record carries a file:line citation) ----------------

class LineLoader(yaml.SafeLoader):
    pass


def _compose_node(self, parent, index):
    line = self.line
    node = yaml.composer.Composer.compose_node(self, parent, index)
    node.__dict__["__line__"] = line + 1
    return node


def _construct_mapping(self, node, deep=False):
    mapping = yaml.constructor.SafeConstructor.construct_mapping(self, node, deep=deep)
    mapping["__line__"] = node.__dict__["__line__"]
    return mapping


LineLoader.compose_node = _compose_node
LineLoader.construct_mapping = _construct_mapping


# --- canonical technology spine ---------------------------------------------------------------
# Derived deterministically from the (semconv-structured) metric name prefix. This is the shared
# bucket vocabulary both inventories are aligned on; keep it in sync with compare.py.
PREFIX_BUCKETS = [
    ("http.server.", "http.server"),
    ("http.client.", "http.client"),
    ("rpc.client.", "rpc"),
    ("rpc.server.", "rpc"),
    ("db.client.connections.", "db.pool"),   # legacy plural
    ("db.client.connection.", "db.pool"),    # stable singular
    ("db.client.operation.", "db.client"),
    ("db.client.", "db.client"),
    ("messaging.", "messaging"),
    ("gen_ai.", "genai"),
    ("failsafe.", "resilience"),
    ("iceberg.", "iceberg"),
    ("jvm.", "jvm"),
    ("system.", "system"),
    ("process.", "system"),
    ("runtime.java.", "system"),
]


def bucket_for(name: str) -> str:
    for prefix, bucket in PREFIX_BUCKETS:
        if name.startswith(prefix):
            return bucket
    return name.split(".", 1)[0]  # fallback: first dotted segment


def gate_for(when: str) -> str:
    """Coarse category of a ``when`` condition, for filtering / display.

    The categories are chosen to answer "under which agent configuration does the agent actually
    emit this?", because a consumer deciding whether a bridged duplicate can be dropped needs to
    know whether the native copy is present. Note ``semconv-stability`` has two spellings in the
    registry — the older ``opt-in=`` and the newer ``preview=`` (which carries 171 of 302 records
    at v2.31.1, nearly all Kafka) — and both are semconv-stability gates rather than
    per-instrumentation experimental toggles.
    """
    if when == "default":
        return "default"
    if "semconv-stability.opt-in" in when:
        return "semconv-opt-in"
    if "semconv-stability.preview" in when:
        return "semconv-preview"
    if "common.v3-preview" in when:
        return "v3-preview"
    if re.fullmatch(r"Java\d+", when or ""):
        return "java-version"
    return "experimental-flag"


def latest_stable_version(versions_dir: Path) -> str:
    versions = []
    for child in versions_dir.iterdir():
        if not child.is_dir():
            continue
        m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", child.name)
        if m:
            versions.append((tuple(int(g) for g in m.groups()), child.name))
    if not versions:
        sys.exit(f"no stable vX.Y.Z dirs under {versions_dir}")
    return max(versions)[1]


def git_short_sha(repo: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--registry-root",
        default=os.path.expanduser("~/code/projects/opentelemetry-ecosystem-explorer"),
        help="checkout of opentelemetry-ecosystem-explorer",
    )
    ap.add_argument("--version", default=None, help="registry version dir (default: latest stable)")
    ap.add_argument("--out", default=None, help="output JSON path (default: inventory/otel-<version>.json)")
    args = ap.parse_args()

    registry_root = Path(args.registry_root).expanduser()
    versions_dir = registry_root / "ecosystem-registry" / "java" / "javaagent"
    if not versions_dir.is_dir():
        sys.exit(f"registry dir not found: {versions_dir}")

    version = args.version or latest_stable_version(versions_dir)
    yaml_path = versions_dir / version / "instrumentation.yaml"
    if not yaml_path.is_file():
        sys.exit(f"instrumentation.yaml not found: {yaml_path}")

    repo_root = Path(__file__).resolve().parent.parent
    out_path = Path(args.out) if args.out else repo_root / "inventory" / f"otel-{version}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = yaml.load(yaml_path.read_text(), Loader=LineLoader)
    libraries = data["libraries"]

    # Registry file_format 0.6 (first seen in v2.31.0) deduplicated metric definitions into a
    # top-level `definitions.metrics` map keyed by `<name>-<hash>`, and replaced the inline
    # `telemetry[].metrics[]` list with `telemetry[].metric_refs[]` naming those keys. 0.5 and
    # earlier inline the definitions. Support both: resolve refs here, and let the loop below treat
    # the resolved definition exactly like an inline one.
    file_format = str(data.get("file_format", "0.5"))
    definition_metrics = ((data.get("definitions") or {}).get("metrics") or {})
    unresolved_refs: set[str] = set()

    def metrics_of(tel: dict) -> list[dict]:
        """Metric definitions declared by one telemetry block, in either file format."""
        resolved = [m for m in (tel.get("metrics") or []) if isinstance(m, dict)]
        for ref in tel.get("metric_refs") or []:
            definition = definition_metrics.get(ref)
            if isinstance(definition, dict):
                # Citation points at the definition rather than the usage site — in 0.6 there is
                # exactly one definition per distinct metric shape, so this is the better anchor.
                resolved.append(definition)
            else:
                unresolved_refs.add(str(ref))
        return resolved

    # Collapse libraries[].telemetry[].metrics[] to one record per (name, when), aggregating the
    # declaring libraries. The first declaration wins for instrument/data_type/unit/description and
    # supplies the citation line; divergences are recorded so they surface rather than hide.
    records: dict[tuple[str, str], dict] = {}
    total_entries = 0
    libs_with_metrics = set()

    # `custom` holds non-library entries (methods, external-annotations, jmx-metrics, ...). None
    # declare metrics at v2.31.1, but the explorer's own resolver walks it too, so walk it here
    # rather than let a future format change silently drop metrics.
    for lib in [*libraries, *(data.get("custom") or [])]:
        lib_id = Path(lib["source_path"]).name if lib.get("source_path") else lib.get("display_name", "?")
        for tel in lib.get("telemetry") or []:
            when = tel.get("when", "default")
            metrics = metrics_of(tel)
            for m in metrics:
                if not isinstance(m, dict) or "name" not in m:
                    continue
                total_entries += 1
                libs_with_metrics.add(lib_id)
                name = m["name"]
                attr_keys = [a["name"] for a in (m.get("attributes") or []) if isinstance(a, dict) and "name" in a]
                key = (name, when)
                rec = records.get(key)
                if rec is None:
                    rec = {
                        "name": name,
                        "instrument": m.get("instrument"),
                        "dataType": m.get("data_type"),
                        "unit": m.get("unit"),
                        "attributeKeys": sorted(set(attr_keys)),
                        "description": m.get("description"),
                        "technology": bucket_for(name),
                        "when": when,
                        "gate": gate_for(when),
                        "emittedBy": [],
                        "cite": f"instrumentation.yaml:{m.get('__line__')}",
                        "divergences": [],
                        "source": "registry",
                    }
                    records[key] = rec
                else:
                    # union attribute keys across declaring libraries; flag field divergences
                    rec["attributeKeys"] = sorted(set(rec["attributeKeys"]) | set(attr_keys))
                    for field, got in (("instrument", m.get("instrument")),
                                       ("dataType", m.get("data_type")),
                                       ("unit", m.get("unit"))):
                        if got is not None and rec[field] != got:
                            note = f"{lib_id}: {field}={got} (vs {rec[field]})"
                            if note not in rec["divergences"]:
                                rec["divergences"].append(note)
                if lib_id not in rec["emittedBy"]:
                    rec["emittedBy"].append(lib_id)

    meters = sorted(records.values(), key=lambda r: (r["technology"], r["name"], r["when"]))
    for r in meters:
        r["emittedBy"].sort()
        r["libraryCount"] = len(r["emittedBy"])
        if not r["divergences"]:
            del r["divergences"]

    by_bucket: dict[str, int] = {}
    for r in meters:
        by_bucket[r["technology"]] = by_bucket.get(r["technology"], 0) + 1

    inventory = {
        "header": {
            "registryVersion": version,
            "fileFormat": file_format,
            "registryCommit": git_short_sha(registry_root),
            "registryPath": str(yaml_path.relative_to(registry_root)),
            "extractedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "totalLibraries": len(libraries),
            "librariesWithMetrics": len(libs_with_metrics),
            "totalMetricEntries": total_entries,
            "uniqueRecords": len(meters),
            "uniqueMetricNames": len({r["name"] for r in meters}),
            "recordsByTechnology": dict(sorted(by_bucket.items())),
            "source": "ecosystem-registry",
        },
        "meters": meters,
    }

    out_path.write_text(json.dumps(inventory, indent=2) + "\n")

    if unresolved_refs:
        print(
            f"  WARNING: {len(unresolved_refs)} metric_ref(s) had no definition and were skipped: "
            + ", ".join(sorted(unresolved_refs)[:5])
            + (" ..." if len(unresolved_refs) > 5 else ""),
            file=sys.stderr,
        )

    h = inventory["header"]
    print(f"wrote {out_path}")
    print(f"  registry {version} (file_format {h['fileFormat']}) @ {h['registryCommit']}")
    print(f"  {h['totalLibraries']} libraries, {h['librariesWithMetrics']} emit metrics")
    print(f"  {h['totalMetricEntries']} entries -> {h['uniqueRecords']} (name,when) records, "
          f"{h['uniqueMetricNames']} unique names")
    print("  by technology: " + ", ".join(f"{k}={v}" for k, v in h["recordsByTechnology"].items()))


if __name__ == "__main__":
    main()
