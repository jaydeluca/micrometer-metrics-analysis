#!/usr/bin/env python3
"""Diff the micrometer-1.5 bridge's emitted surface across otel.instrumentation.common.v3-preview.

Reads OTLP-JSON captures produced by run-surface-delta.sh and, for each (v2, v3) pair, reports what
the bridge's own instrumentation scope emits differently: metrics added, metrics removed, and
metrics whose unit or OTLP data type changed. Metrics from other scopes (the agent's native
instrumentation) are summarized separately so an agent-wide v3-preview effect is not mistaken for a
bridge effect.

The point is to replace flag-name reasoning with a measurement: the proposal has to state the
bridge's behavior under both v2 and v3-preview, and the surface is what "behavior" means here.

Usage:
  diff-surface.py --pair <label> <v2.jsonl> <v3.jsonl> [--pair ...] [--agent-version X.Y.Z]

Exit code is always 0 — this is a characterization tool, not an assertion suite.
"""
import argparse
import json
import sys
from collections import defaultdict

BRIDGE_SCOPE = "io.opentelemetry.micrometer-1.5"

DATA_KEYS = ("gauge", "sum", "histogram", "exponentialHistogram", "summary")


def data_type(metric):
    """Coarse OTLP data type, with monotonicity for sums (counter vs up-down counter)."""
    for key in DATA_KEYS:
        if key in metric:
            if key == "sum":
                return "sum(monotonic)" if metric[key].get("isMonotonic") else "sum(up-down)"
            return key
    return "unknown"


def load(path):
    """(scope, name) -> {"unit": str, "type": str} across every export line in the file."""
    surface = {}
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
                        if not name:
                            continue
                        surface[(scope, name)] = {
                            "unit": m.get("unit", ""),
                            "type": data_type(m),
                        }
    return surface, lines


def scoped(surface, scope):
    return {n: v for (s, n), v in surface.items() if s == scope}


def report_by_scope(label, v2_path, v3_path):
    """Scope-level view, for deltas that are about a whole bridge switching on or off."""
    v2, v2_lines = load(v2_path)
    v3, v3_lines = load(v3_path)

    print(f"\n{'=' * 78}\nPAIR: {label} (by scope)")
    print(f"  v2 (v3-preview off): {v2_path}  [{v2_lines} export(s)]")
    print(f"  v3 (v3-preview on):  {v3_path}  [{v3_lines} export(s)]")
    if v2_lines == 0 or v3_lines == 0:
        print("  !! no OTLP export lines parsed — did the app run under the agent?")
        return

    counts = defaultdict(lambda: [0, 0])
    for (s, _n) in v2:
        counts[s][0] += 1
    for (s, _n) in v3:
        counts[s][1] += 1

    width = max(len(s) for s in counts)
    print(f"\n  {'scope':<{width}}  {'v2':>5}  {'v3':>5}   verdict")
    for s in sorted(counts):
        n2, n3 = counts[s]
        if n2 and not n3:
            verdict = "GONE under v3-preview"
        elif n3 and not n2:
            verdict = "APPEARS under v3-preview"
        elif n2 != n3:
            verdict = f"changed ({n2 - n3:+d})"
        else:
            verdict = "unchanged"
        print(f"  {s:<{width}}  {n2:>5}  {n3:>5}   {verdict}")

    for s in sorted(counts):
        n2, n3 = counts[s]
        if n2 and not n3:
            gone = sorted(n for (sc, n) in v2 if sc == s)
            print(f"\n  all {len(gone)} metric(s) lost with scope `{s}`:")
            for n in gone:
                print(f"    - {n}")


def report_pair(label, v2_path, v3_path):
    v2, v2_lines = load(v2_path)
    v3, v3_lines = load(v3_path)

    print(f"\n{'=' * 78}\nPAIR: {label}\n  v2 (v3-preview off): {v2_path}  [{v2_lines} export(s)]")
    print(f"  v3 (v3-preview on):  {v3_path}  [{v3_lines} export(s)]")
    if v2_lines == 0 or v3_lines == 0:
        print("  !! no OTLP export lines parsed — did the app run under the agent?")
        return

    b2, b3 = scoped(v2, BRIDGE_SCOPE), scoped(v3, BRIDGE_SCOPE)
    print(f"\n  bridge scope `{BRIDGE_SCOPE}`: {len(b2)} metrics under v2, {len(b3)} under v3")

    removed = sorted(set(b2) - set(b3))
    added = sorted(set(b3) - set(b2))
    changed = sorted(n for n in set(b2) & set(b3) if b2[n] != b3[n])

    if not (removed or added or changed):
        print("  NO DELTA — the bridge emits an identical surface under both.")
    for n in removed:
        print(f"  - REMOVED under v3: {n:<44} unit={b2[n]['unit']!r} type={b2[n]['type']}")
    for n in added:
        print(f"  + ADDED   under v3: {n:<44} unit={b3[n]['unit']!r} type={b3[n]['type']}")
    for n in changed:
        print(f"  ~ CHANGED under v3: {n:<44} {b2[n]} -> {b3[n]}")

    # Other scopes, so an agent-wide v3-preview effect is visibly not a bridge effect.
    o2 = {(s, n) for (s, n) in v2 if s != BRIDGE_SCOPE}
    o3 = {(s, n) for (s, n) in v3 if s != BRIDGE_SCOPE}
    other_removed, other_added = sorted(o2 - o3), sorted(o3 - o2)
    print(f"\n  other scopes (agent-native): {len(o2)} metrics under v2, {len(o3)} under v3")
    for s, n in other_removed:
        print(f"  - REMOVED under v3: {n:<44} scope={s}")
    for s, n in other_added:
        print(f"  + ADDED   under v3: {n:<44} scope={s}")
    if not (other_removed or other_added):
        print("  (no change)")

    return {"removed": removed, "added": added, "changed": changed}


def report_naming(pairs_surfaces):
    """Cross-pair view: the same demo metric under identity vs prometheus_mode naming."""
    print(f"\n{'=' * 78}\nBRIDGE SURFACE BY CONFIGURATION (demo.* only)\n")
    all_names = sorted({n for surf in pairs_surfaces.values() for n in surf if n.startswith("demo.")})
    cols = list(pairs_surfaces)
    width = max((len(n) for n in all_names), default=20)
    print(f"  {'metric':<{width}}  " + "  ".join(f"{c:<9}" for c in cols))
    for n in all_names:
        marks = "  ".join(f"{'yes' if n in pairs_surfaces[c] else '-':<9}" for c in cols)
        print(f"  {n:<{width}}  {marks}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=3, action="append", metavar=("LABEL", "V2", "V3"), required=True)
    ap.add_argument("--agent-version", default="(unspecified)")
    ap.add_argument("--by-scope", action="store_true",
                    help="report per-scope metric counts instead of per-metric bridge diffs")
    ap.add_argument("--no-name-table", action="store_true",
                    help="skip the cross-configuration demo.* name table")
    args = ap.parse_args()

    print(f"micrometer-1.5 bridge surface delta — agent {args.agent_version}")

    surfaces = {}
    for label, v2_path, v3_path in args.pair:
        if args.by_scope:
            report_by_scope(label, v2_path, v3_path)
        else:
            report_pair(label, v2_path, v3_path)
        for suffix, path in ((f"{label[:4]}-v2", v2_path), (f"{label[:4]}-v3", v3_path)):
            surf, _ = load(path)
            surfaces[suffix] = scoped(surf, BRIDGE_SCOPE)

    if not args.no_name_table:
        report_naming(surfaces)
    return 0


if __name__ == "__main__":
    sys.exit(main())
