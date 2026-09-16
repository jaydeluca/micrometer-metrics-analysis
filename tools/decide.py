#!/usr/bin/env python3
"""Produce the per-instrument bridge decision table: keep / rename / drop, with a reason.

This is the specification for a `strict-semconv`-style bridge mode, and the test oracle a
prototype can be graded against. For each Micrometer instrument the harness actually captured, it
answers: **should the OTel Micrometer bridge emit this, and if so under what name?**

The ordering matters and is not obvious — *drop first, then rename*. Renaming a metric the agent
already emits natively converts a harmless different-name duplicate into a same-name/different-type
collision, which is the exact case opentelemetry-java-instrumentation#15451 opens with. So:

    1. the agent already emits this concept  -> drop (duplicate)
    2. non-conforming and a rename cannot fix it -> drop (non-conforming)
    3. a defined semconv metric covers it, and the agent does NOT emit it -> rename
    4. otherwise -> keep

Inputs (all produced by the rest of this repo, plus two external checkouts):
  - inventory/micrometer-*.json      runtime-captured Micrometer instruments (harness-tier*)
  - inventory/otel-<version>.json    what the agent emits (tools/extract_otel_inventory.py)
  - inventory/comparison*.json       the curated + exact-name join (tools/compare.py)
  - semantic-conventions/model/      the *defined* semconv metrics, for rename targets

Why the semconv model as well as the agent registry: the registry says what the agent emits, which
is a subset of what semconv defines. A rename target has to be a defined semconv metric even when
no agent instrumentation emits it — that is precisely the "fills a gap under a semconv name" case.

Usage:
    python3 tools/decide.py [--otel inventory/otel-v2.31.1.json]
                            [--comparison inventory/comparison-v2.31.1.json]
                            [--semconv ~/code/explore/semantic-conventions]
                            [--json-out inventory/decisions-<version>.json]
                            [--out output/decision-table-<version>.md]
"""
import argparse
import glob
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# --- conformance rules --------------------------------------------------------------------------
#
# Every rule cites the semantic-conventions text it enforces, so a reviewer can argue with the rule
# rather than with the tool. Rules that CANNOT be checked mechanically are listed in
# UNCHECKABLE below and reported alongside the table — that list is what decides whether a bridge
# mode can be a rule engine or needs a curated list.

# Unit words that show up as a name component. Presence means the name encodes its own unit, which
# semconv says it should not: "Conventional metrics ... SHOULD NOT include the units in the metric
# name" (semantic-conventions docs/general/metrics.md:82-84). Note the spec allows units in a name
# "when it provides additional meaning", so this rule produces candidates, not verdicts.
UNIT_NAME_TOKENS = {
    "seconds", "second", "sec", "secs",
    "millis", "milliseconds", "millisecond", "ms",
    "nanos", "nanoseconds", "nanosecond", "ns",
    "micros", "microseconds", "microsecond", "us",
    "bytes", "byte", "kb", "mb", "gb",
    "percent", "percentage", "ratio", "hz",
}

# UCUM codes the two inventories actually use, plus the annotation form `{...}` and the unity `1`.
# "Units should follow the Unified Code for Units of Measure" (docs/general/metrics.md:97-98).
UCUM_OK = {
    "1", "s", "ms", "ns", "us", "By", "%", "Cel", "W", "J", "Hz", "m", "kg", "d", "h", "min",
    "By/s", "1/s", "{fault}/s",
}

# Micrometer base units that are plainly non-UCUM, mapped to what UCUM would want. Used only to
# make the report actionable; the rule itself is "is this a UCUM code or an annotation".
NON_UCUM_HINTS = {
    "bytes": "By", "seconds": "s", "milliseconds": "ms", "nanoseconds": "ns",
    "threads": "{thread}", "classes": "{class}", "tasks": "{task}", "operations": "{operation}",
    "buffers": "{buffer}", "connections": "{connection}", "objects": "{object}",
    "events": "{event}", "requests": "{request}", "messages": "{message}", "files": "{file}",
    # `%` is a valid UCUM unit. Do NOT map percent onto the unity `1`: unity is a 0..1 fraction
    # while Micrometer's percent values are 0..100, so that mapping would be a silent 100x scale
    # error. Unit normalization may only rewrite the unit string, never imply a value conversion.
    "percent": "%", "records": "{record}", "sessions": "{session}", "rows": "{row}",
}

UNCHECKABLE = [
    ("precision / descriptiveness", "naming.md:86-94",
     "Whether a name is 'descriptive and unambiguous' is a judgement call. `executor.active` is "
     "checkable only by a human who knows it means threads."),
    ("snake_case within a dot component", "naming.md:75-77",
     "Detecting that a component is multi-word needs a dictionary. `bytes_consumed_rate` is "
     "correct snake_case; `classes.loaded` splits one concept across two components — no regex "
     "separates those cases."),
    ("justified pluralization", "naming.md:249-262",
     "Plural is allowed when the value is a countable quantity, which the spec ties to the unit "
     "being an annotation. Micrometer units are mostly non-UCUM words, so the test is unreliable "
     "on exactly the metrics it would judge."),
    ("concept equivalence", "n/a",
     "That `hikaricp.connections.active` and `db.client.connection.count` are the same concept is "
     "human-asserted (tools/concept_map.yaml). No mechanical test exists."),
    ("instrument-type correctness for Micrometer-only metrics", "n/a",
     "Type conformance can only be checked against a semconv counterpart. A Micrometer-only "
     "metric has none, so its type cannot be judged non-conforming."),
]


def name_components(name: str) -> list[str]:
    return name.split(".")


def check_conformance(name: str, unit, mm_type: str) -> list[dict]:
    """Mechanically checkable semconv conformance findings for one Micrometer instrument."""
    findings = []
    comps = name_components(name)

    unit_comps = [c for c in comps if c in UNIT_NAME_TOKENS]
    if unit_comps:
        findings.append({
            "rule": "unit-in-name",
            "cite": "semantic-conventions docs/general/metrics.md:82-84",
            "detail": f"name encodes its unit via component(s) {unit_comps}",
            "fixable_by_rename": True,
        })

    if comps[-1] == "total" or name.endswith("_total"):
        findings.append({
            "rule": "total-suffix",
            "cite": "semantic-conventions docs/general/naming.md:273-280",
            "detail": "Counters and UpDownCounters SHOULD NOT append `total`",
            "fixable_by_rename": True,
        })

    if name != name.lower():
        findings.append({
            "rule": "not-lowercase",
            "cite": "semantic-conventions docs/general/naming.md:59",
            "detail": "names SHOULD be lowercase",
            "fixable_by_rename": True,
        })

    unit_str = "" if unit is None else str(unit)
    if unit_str and unit_str not in ("None",):
        is_annotation = unit_str.startswith("{") and unit_str.endswith("}")
        if not is_annotation and unit_str not in UCUM_OK:
            hint = NON_UCUM_HINTS.get(unit_str)
            findings.append({
                "rule": "non-ucum-unit",
                "cite": "semantic-conventions docs/general/metrics.md:97-98",
                "detail": f"base unit {unit_str!r} is not a UCUM code"
                          + (f"; UCUM would use {hint!r}" if hint else ""),
                # A rename cannot change a unit. But the *bridge* can: it already owns the
                # translation of Micrometer's baseUnit into the OTel instrument's unit at
                # Bridging.java:60-63, where it currently passes the string through verbatim. So a
                # non-UCUM unit is fixable — by normalization, not by renaming.
                "fixable_by_rename": False,
                "fixable_by_unit_normalization": hint is not None,
                "normalizedUnit": hint,
            })

    return findings


# --- loaders ------------------------------------------------------------------------------------

def load_micrometer() -> list[dict]:
    """Every captured Micrometer instrument, de-duplicated on (name, type, unit)."""
    seen: dict[tuple, dict] = {}
    for path in sorted(glob.glob(str(REPO / "inventory" / "micrometer-*.json"))):
        data = json.load(open(path))
        for m in data["meters"]:
            key = (m["name"], m["meterType"], m.get("baseUnit"))
            if key not in seen:
                seen[key] = m
    return sorted(seen.values(), key=lambda m: (m.get("technology") or "", m["name"]))


def load_otel(path: str) -> tuple[dict, dict]:
    data = json.load(open(path))
    by_name: dict[str, list[dict]] = defaultdict(list)
    for m in data["meters"]:
        by_name[m["name"]].append(m)
    return data["header"], by_name


def load_semconv_metrics(root: Path) -> dict[str, dict]:
    """Every *defined* semconv metric (not just the ones the agent emits)."""
    defined: dict[str, dict] = {}
    for path in (root / "model").rglob("*.yaml"):
        try:
            doc = yaml.safe_load(path.read_text())
        except Exception:
            continue
        for group in (doc or {}).get("groups") or []:
            if not isinstance(group, dict) or group.get("type") != "metric":
                continue
            name = group.get("metric_name")
            if not name:
                continue
            defined[name] = {
                "instrument": group.get("instrument"),
                "unit": group.get("unit"),
                "stability": group.get("stability"),
                "source": str(path.relative_to(root)),
            }
    return defined


def load_curated_matches(path: str) -> dict[str, list[dict]]:
    """Micrometer name -> matched OTel rows, from the curated + exact-name join."""
    data = json.load(open(path))
    out: dict[str, list[dict]] = defaultdict(list)
    for rows in data["buckets"].values():
        for e in rows:
            if e["class"] in ("direct", "partial", "semantic"):
                out[e["micrometer"]].append(e)
    return out, data


def normalized(name: str) -> str:
    """Collapse the two bridges' separator conventions onto one key.

    Micrometer's KafkaClientMetrics dots the Kafka client's native metric names
    (`kafka.consumer.bytes.consumed.rate`); the agent's kafka-clients-metrics bridge keeps the
    underscores (`kafka.consumer.bytes_consumed_rate`). Same underlying client metric, two names,
    zero exact-name overlap — so a name-keyed join misses the single largest duplicate cluster in
    the dataset unless the separator is normalized away.
    """
    return name.replace("_", ".").lower()


# --- the decision -------------------------------------------------------------------------------

# Registry modules that are themselves metric bridges rather than instrumentation. A duplicate
# against one of these is bridge-vs-bridge, which #15451 explicitly scopes in but which resolves
# differently: the Kafka bridge is on by default in v2 and off under v3-preview.
BRIDGE_MODULES = {"kafka-clients-0.11", "kafka-clients-2.6"}


def agent_emission(mm_name: str, curated: dict, otel_by_name: dict) -> dict | None:
    """How (and whether) the agent emits this concept natively."""
    rows = curated.get(mm_name)
    if rows:
        otel_name = rows[0]["otel"]
        match_origin = rows[0]["origin"]
        klass = rows[0]["class"]
    else:
        # fall back to separator-normalized name matching (the Kafka bridge-vs-bridge case)
        target = normalized(mm_name)
        hit = next((n for n in otel_by_name if normalized(n) == target), None)
        if hit is None:
            return None
        otel_name, match_origin, klass = hit, "normalized-name", "direct"

    records = otel_by_name.get(otel_name, [])
    if not records:
        return None
    gates = {r["gate"] for r in records}
    modules = sorted({m for r in records for m in r["emittedBy"]})
    return {
        "otelName": otel_name,
        "matchOrigin": match_origin,
        "class": klass,
        # "always on" if any declaration of this metric is ungated
        "alwaysOn": "default" in gates,
        "gates": sorted(gates),
        "conditionalOn": modules,
        "viaBridge": bool(modules) and set(modules) <= BRIDGE_MODULES,
        "otelInstrument": records[0].get("instrument"),
        "otelUnit": records[0].get("unit"),
    }


# Populated from tools/concept_map.yaml at startup: Micrometer name -> asserted OTel name.
CONCEPT_TARGETS: dict[str, str] = {}


def rename_target(mm_name: str, semconv: dict) -> str | None:
    """The semconv name this Micrometer metric should be renamed onto, if any.

    Returns None unless a human asserted the equivalence AND the target is a defined semconv
    metric. Callers only reach this after establishing the agent does not already emit the concept,
    so anything returned here is a gap-filling rename rather than a duplicate-manufacturing one.
    """
    target = CONCEPT_TARGETS.get(mm_name)
    if target is None or target == mm_name:
        return None
    if target not in semconv:
        return None
    return target


def decide(m: dict, emission: dict | None, semconv: dict) -> dict:
    name = m["name"]
    findings = check_conformance(name, m.get("baseUnit"), m["meterType"])
    # Unfixable = no available repair. A finding the bridge can repair by normalizing the unit is
    # not a reason to throw the metric away; see the non-ucum-unit rule.
    unfixable = [
        f for f in findings
        if not f["fixable_by_rename"] and not f.get("fixable_by_unit_normalization")
    ]
    normalizable = [f for f in findings if f.get("fixable_by_unit_normalization")]

    # 1. duplicate of something the agent emits natively -> drop
    if emission is not None:
        reason = f"agent emits {emission['otelName']}"
        if emission["viaBridge"]:
            reason += " via its own metric bridge (bridge-vs-bridge)"
        if not emission["alwaysOn"]:
            reason += f"; gated on {','.join(emission['gates'])}"
        return {
            "decision": "drop",
            "dropClass": "duplicate",
            "reason": reason,
            "conditional": not emission["alwaysOn"],
            "findings": findings,
        }

    # 2. non-conforming in a way renaming cannot fix -> drop
    if unfixable:
        return {
            "decision": "drop",
            "dropClass": "non-conforming",
            "reason": "; ".join(f"{f['rule']}: {f['detail']}" for f in unfixable),
            "conditional": False,
            "findings": findings,
        }

    # 3. a defined semconv metric covers this concept and the agent does NOT emit it -> rename.
    #
    # The only source of "this Micrometer metric means the same as that semconv metric" is the
    # curated concept map — concept equivalence is not mechanically decidable (see UNCHECKABLE).
    # A rename target must therefore be (a) asserted by the concept map, (b) a *defined* semconv
    # metric, and (c) NOT emitted by the agent, since otherwise renaming onto it would manufacture
    # the same-name/different-type collision this ordering exists to avoid.
    target_name = rename_target(name, semconv)
    if target_name is not None:
        return {
            "decision": "rename",
            "renameTo": target_name,
            "reason": f"concept-mapped to defined semconv metric {target_name}, "
                      "which the agent does not emit",
            "conditional": False,
            "findings": findings,
        }

    name_findings = [f for f in findings if f["rule"] != "non-ucum-unit"]
    if name_findings:
        # Name-level violations with nowhere to rename to. Under the settled `strict-semconv`
        # definition (drop non-conforming, rename what can be renamed) these are drops.
        return {
            "decision": "drop",
            "dropClass": "non-conforming",
            "reason": "; ".join(f"{f['rule']}: {f['detail']}" for f in name_findings)
                      + " (no semconv target to rename onto)",
            "conditional": False,
            "findings": findings,
        }

    # 4. the only problem is a unit the bridge can normalize -> keep it, with a corrected unit.
    if normalizable:
        return {
            "decision": "normalize-unit",
            "normalizeUnitTo": normalizable[0]["normalizedUnit"],
            "reason": f"Micrometer-only metric, conforming apart from base unit "
                      f"{m.get('baseUnit')!r} -> {normalizable[0]['normalizedUnit']!r}",
            "conditional": False,
            "findings": findings,
        }

    # 4. conforming, Micrometer-only -> keep
    return {
        "decision": "keep",
        "reason": "no agent equivalent and no mechanical conformance violation",
        "conditional": False,
        "findings": findings,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    default_otel = sorted(glob.glob(str(REPO / "inventory" / "otel-*.json")))
    ap.add_argument("--otel", default=default_otel[-1] if default_otel else None)
    ap.add_argument("--comparison", default=str(REPO / "inventory" / "comparison.json"))
    ap.add_argument("--semconv", default=os.path.expanduser("~/code/explore/semantic-conventions"))
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    otel_header, otel_by_name = load_otel(args.otel)
    version = otel_header.get("registryVersion", "unknown")
    curated, comparison = load_curated_matches(args.comparison)
    semconv = load_semconv_metrics(Path(args.semconv).expanduser())
    micrometer = load_micrometer()

    # Guard against pairing a freshly-extracted OTel inventory with a stale join: the two are
    # pinned independently, and a mismatch produces a plausible-looking but wrong table.
    joined_version = comparison.get("otelVersion")
    if joined_version and joined_version != version:
        raise SystemExit(
            f"version mismatch: --otel is registry {version} but --comparison was built against "
            f"{joined_version}.\nRe-run tools/compare.py --otel {args.otel} "
            f"--json-out inventory/comparison-{version}.json first."
        )

    concept = yaml.safe_load((REPO / "tools" / "concept_map.yaml").read_text()) or {}
    for pair in concept.get("pairs") or []:
        CONCEPT_TARGETS.setdefault(pair["micrometer"], pair["otel"])

    json_out = Path(args.json_out or REPO / "inventory" / f"decisions-{version}.json")
    md_out = Path(args.out or REPO / "output" / f"decision-table-{version}.md")

    rows = []
    for m in micrometer:
        emission = agent_emission(m["name"], curated, otel_by_name)
        d = decide(m, emission, semconv)
        rows.append({
            "name": m["name"],
            "meterType": m["meterType"],
            "baseUnit": m.get("baseUnit"),
            "technology": m.get("technology"),
            "emittedBy": m.get("emittedBy"),
            "agent": emission,
            **d,
        })

    # Why the rename bucket comes out the size it does. A rename needs a human-asserted
    # equivalence whose target the agent does not already emit; count how many survive each filter
    # so an empty bucket is evidence rather than an absence.
    emitted_names = set(otel_by_name)
    rename_funnel = {
        "conceptMapPairs": len(CONCEPT_TARGETS),
        "targetDefinedInSemconv": sum(1 for t in CONCEPT_TARGETS.values() if t in semconv),
        "targetNotEmittedByAgent": sum(1 for t in CONCEPT_TARGETS.values()
                                       if t not in emitted_names),
        "targetDefinedAndNotEmitted": sum(1 for t in CONCEPT_TARGETS.values()
                                          if t in semconv and t not in emitted_names),
    }

    result = {
        "otelRegistryVersion": version,
        "renameFunnel": rename_funnel,
        "otelRegistryFileFormat": otel_header.get("fileFormat"),
        "micrometerVersions": comparison.get("micrometerVersions"),
        "semconvDefinedMetrics": len(semconv),
        "instruments": len(rows),
        "uncheckableRules": [
            {"rule": r, "cite": c, "why": w} for r, c, w in UNCHECKABLE
        ],
        "decisions": rows,
    }
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(result, indent=2) + "\n")

    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(render_markdown(result))

    print(f"wrote {json_out} and {md_out}")
    print_summary(result)


def print_summary(result: dict) -> None:
    rows = result["decisions"]
    print(f"  registry {result['otelRegistryVersion']}, micrometer "
          f"{result['micrometerVersions']}, {len(rows)} captured instruments")
    buckets = Counter(
        r["decision"] if r["decision"] != "drop" else f"drop:{r['dropClass']}" for r in rows
    )
    for k, v in buckets.most_common():
        print(f"    {v:4d}  {k}")
    cond = sum(1 for r in rows if r.get("conditional"))
    bridge = sum(1 for r in rows if (r.get("agent") or {}).get("viaBridge"))
    print(f"    {cond:4d}  of the drops are CONDITIONAL (agent's copy is gated)")
    print(f"    {bridge:4d}  of the drops are bridge-vs-bridge")
    f = result["renameFunnel"]
    print(f"  rename funnel: {f['conceptMapPairs']} concept-map pairs -> "
          f"{f['targetDefinedInSemconv']} target a defined semconv metric -> "
          f"{f['targetNotEmittedByAgent']} target something the agent does not emit -> "
          f"{f['targetDefinedAndNotEmitted']} eligible to rename")


def render_markdown(result: dict) -> str:
    rows = result["decisions"]
    out = []
    out.append("# Bridge decision table\n")
    out.append(f"Registry `{result['otelRegistryVersion']}` "
               f"(file_format {result['otelRegistryFileFormat']}) vs Micrometer "
               f"`{', '.join(result['micrometerVersions'] or [])}`. "
               f"{len(rows)} captured Micrometer instruments; "
               f"{result['semconvDefinedMetrics']} defined semconv metrics consulted.\n")
    buckets = Counter(
        r["decision"] if r["decision"] != "drop" else f"drop:{r['dropClass']}" for r in rows
    )
    out.append("## Summary\n")
    out.append("| Decision | Count |")
    out.append("|---|---|")
    for k, v in buckets.most_common():
        out.append(f"| `{k}` | {v} |")
    out.append("")

    out.append("## Rules that cannot be checked mechanically\n")
    out.append("These decide whether a bridge mode can be a rule engine or needs a curated list.\n")
    out.append("| Rule | Cite | Why not mechanical |")
    out.append("|---|---|---|")
    for u in result["uncheckableRules"]:
        out.append(f"| {u['rule']} | `{u['cite']}` | {u['why']} |")
    out.append("")

    by_tech: dict[str, list] = defaultdict(list)
    for r in rows:
        by_tech[r["technology"] or "?"].append(r)

    out.append("## Per-instrument decisions\n")
    for tech in sorted(by_tech):
        out.append(f"### {tech}\n")
        out.append("| Micrometer instrument | Type | Unit | Decision | Reason |")
        out.append("|---|---|---|---|---|")
        for r in sorted(by_tech[tech], key=lambda x: x["name"]):
            decision = r["decision"]
            if decision == "drop":
                decision = f"drop ({r['dropClass']})"
                if r.get("conditional"):
                    decision += " ⚠️cond"
            reason = r["reason"].replace("|", "\\|")
            out.append(f"| `{r['name']}` | {r['meterType']} | `{r.get('baseUnit')}` | "
                       f"{decision} | {reason} |")
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
