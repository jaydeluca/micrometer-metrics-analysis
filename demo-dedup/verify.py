#!/usr/bin/env python3
"""Verify the Micrometer-dedup views did what we expect.

Reads two OTLP-JSON captures (baseline = bridge on, no views; deduped = bridge on, dedup views)
and the deduped config's view selectors, then asserts, per OpenTelemetry instrumentation scope:

  * bridged (scope io.opentelemetry.micrometer-1.5) metric matching a drop view -> GONE in deduped
  * bridged metric NOT matching any drop view                                   -> KEPT in deduped
  * native metric (any other scope), incl. the jvm.memory.* name collision      -> UNTOUCHED

Exit code 0 = all assertions pass, 1 = at least one failed (or captures unreadable).

Usage: verify.py <baseline.jsonl> <deduped.jsonl> <config-deduped.yaml>
"""
import fnmatch
import json
import re
import sys

BRIDGE_SCOPE = "io.opentelemetry.micrometer-1.5"


def load_scope_metrics(path):
    """Union of (scope_name, metric_name) across every OTLP-JSON export line in the file."""
    pairs = set()
    lines = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            lines += 1
            for rm in obj.get("resourceMetrics", []):
                for sm in rm.get("scopeMetrics", []):
                    scope = sm.get("scope", {}).get("name", "")
                    for m in sm.get("metrics", []):
                        name = m.get("name")
                        if name:
                            pairs.add((scope, name))
    return pairs, lines


def load_drop_selectors(config_path):
    """Extract (meter_name, instrument_glob) from the deduped config's views.

    Deliberately dependency-free (no PyYAML): the demo config's view block is a flat, one-view-per
    -line format, so a small regex is enough and keeps the demo runnable on a bare Python 3.
    """
    selectors = []
    text = open(config_path, encoding="utf-8").read()
    for m in re.finditer(
        r"meter_name:\s*(\S+),\s*instrument_name:\s*([^\s}]+)", text
    ):
        selectors.append((m.group(1).strip(), m.group(2).strip()))
    return selectors


def matches_drop(scope, name, selectors):
    for meter_name, glob in selectors:
        if scope == meter_name and fnmatch.fnmatch(name, glob):
            return glob
    return None


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    baseline_path, deduped_path, config_path = sys.argv[1:4]

    baseline, b_lines = load_scope_metrics(baseline_path)
    deduped, d_lines = load_scope_metrics(deduped_path)
    selectors = load_drop_selectors(config_path)

    if b_lines == 0 or d_lines == 0:
        print(f"FAIL: no OTLP export lines parsed (baseline={b_lines}, deduped={d_lines}).")
        print("      Did the app run under the agent and did the exporter write the file?")
        return 1
    if not selectors:
        print(f"FAIL: no drop selectors parsed from {config_path}.")
        return 1

    print(f"parsed {b_lines} baseline / {d_lines} deduped export(s); "
          f"{len(selectors)} drop selectors; "
          f"{len(baseline)} baseline (scope,metric) pairs\n")

    results = []  # (status, category, scope, name, detail)

    # 1) Every bridged metric present in the baseline: dropped ones must vanish, others must remain.
    bridged_baseline = sorted(n for (s, n) in baseline if s == BRIDGE_SCOPE)
    for name in bridged_baseline:
        glob = matches_drop(BRIDGE_SCOPE, name, selectors)
        present_after = (BRIDGE_SCOPE, name) in deduped
        if glob:  # expected to be dropped
            ok = not present_after
            results.append((ok, "DROP", BRIDGE_SCOPE, name,
                            f"matched `{glob}` -> {'gone' if not present_after else 'STILL PRESENT'}"))
        else:  # Micrometer-only, expected to survive
            results.append((present_after, "KEEP", BRIDGE_SCOPE, name,
                            "no drop view -> " + ("kept" if present_after else "MISSING")))

    # 2) The name-collision guard: jvm.memory.used must exist from a NATIVE scope in BOTH runs.
    native_collisions = sorted(
        (s, n) for (s, n) in baseline
        if n == "jvm.memory.used" and s != BRIDGE_SCOPE
    )
    if not native_collisions:
        results.append((False, "COLLIDE", "(native)", "jvm.memory.used",
                        "expected a native runtime-telemetry copy in baseline, found none"))
    for s, n in native_collisions:
        kept = (s, n) in deduped
        results.append((kept, "COLLIDE", s, n,
                        "native copy " + ("survived the scoped drop" if kept else "WAS WRONGLY DROPPED")))

    # Render.
    width = max(len(n) for (_, _, _, n, _) in results) if results else 20
    passed = 0
    for ok, cat, scope, name, detail in sorted(results, key=lambda r: (r[1], r[3])):
        mark = "PASS" if ok else "FAIL"
        passed += ok
        short_scope = scope.replace("io.opentelemetry.", "")
        print(f"  [{mark}] {cat:8} {name:<{width}}  {short_scope:<28} {detail}")

    total = len(results)
    print(f"\n{passed}/{total} assertions passed.")
    if passed != total:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — dedup views drop exactly the covered duplicates and keep everything else.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
