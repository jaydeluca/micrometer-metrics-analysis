#!/usr/bin/env python3
"""Report on the prefix experiment: can metric Views add a prefix to Micrometer metrics?

Compares the bridge-scope (io.opentelemetry.micrometer-1.5) metric surface across three runs:

  baseline  — bridge on, no views
  wildcard  — one `*` view renaming everything to a single literal name (the naive "prefix all")
  explicit  — one view per metric, each with a literal `micrometer.<name>` target

and asserts the two facts the experiment is meant to establish:

  1. WILDCARD FAILS: `*` + a static `name` does NOT yield 30+ `micrometer.*` names. Every instrument
     collapses onto the one literal name, so the distinct bridged-name count crashes toward 1 and the
     SDK logs duplicate-metric conflicts (see the *.log grep in run-prefix-experiment.sh).
  2. EXPLICIT WORKS but does not scale: each enumerated metric appears ONLY under its `micrometer.*`
     name (original gone), while every metric we did NOT list keeps its original name untouched.

Exit 0 = both facts hold, 1 = otherwise.

Usage: verify-prefix.py <baseline.jsonl> <wildcard.jsonl> <explicit.jsonl>
"""
import json
import sys

BRIDGE_SCOPE = "io.opentelemetry.micrometer-1.5"

# The exact renames declared in config-prefix-explicit.yaml (original -> prefixed).
EXPLICIT_RENAMES = {
    "cache.gets": "micrometer.cache.gets",
    "cache.size": "micrometer.cache.size",
    "process.uptime": "micrometer.process.uptime",
    "jvm.threads.daemon": "micrometer.jvm.threads.daemon",
    "jvm.gc.pause": "micrometer.jvm.gc.pause",
}


def bridged_names(path):
    """Set of metric names emitted under the bridge scope across every export line in the file."""
    names = set()
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
                    if sm.get("scope", {}).get("name", "") != BRIDGE_SCOPE:
                        continue
                    for m in sm.get("metrics", []):
                        if m.get("name"):
                            names.add(m["name"])
    return names, lines


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    base_p, wild_p, expl_p = sys.argv[1:4]
    base, b_lines = bridged_names(base_p)
    wild, w_lines = bridged_names(wild_p)
    expl, e_lines = bridged_names(expl_p)

    if not (b_lines and w_lines and e_lines):
        print(f"FAIL: empty capture (baseline={b_lines}, wildcard={w_lines}, explicit={e_lines}).")
        return 1

    print(f"bridged metric names per run:  baseline={len(base)}  "
          f"wildcard={len(wild)}  explicit={len(expl)}\n")

    results = []  # (ok, label, detail)

    # --- Fact 1: the wildcard prefix attempt collapses instead of prefixing. ---------------------
    prefixed_in_wild = sorted(n for n in wild if n.startswith("micrometer."))
    # Success would have been ~len(base) distinct micrometer.* names; instead we expect a collapse.
    collapsed = len(wild) < len(base)
    results.append((
        collapsed,
        "WILDCARD collapses (does NOT prefix all)",
        f"baseline had {len(base)} bridged names; wildcard emits {len(wild)} "
        f"({', '.join(sorted(wild)) or 'none'})",
    ))
    # And it did NOT produce a per-metric prefixed set.
    results.append((
        len(prefixed_in_wild) < len(base),
        "WILDCARD did not yield a prefixed set",
        f"only {len(prefixed_in_wild)} `micrometer.*` name(s): {prefixed_in_wild or 'none'}",
    ))

    # --- Fact 2: explicit per-metric views rename correctly (original gone, prefixed present). ----
    for orig, pref in sorted(EXPLICIT_RENAMES.items()):
        was_present = orig in base
        now_prefixed = pref in expl
        orig_gone = orig not in expl
        ok = was_present and now_prefixed and orig_gone
        results.append((
            ok,
            f"EXPLICIT rename {orig}",
            f"baseline={'yes' if was_present else 'NO'} -> "
            f"{pref} {'present' if now_prefixed else 'MISSING'}, "
            f"original {'gone' if orig_gone else 'STILL PRESENT'}",
        ))

    # --- Fact 2b: metrics we did NOT enumerate keep their original names untouched in `explicit`. -
    not_renamed = sorted(n for n in base if n not in EXPLICIT_RENAMES)
    untouched = [n for n in not_renamed if n in expl]
    results.append((
        len(untouched) == len(not_renamed),
        "EXPLICIT leaves un-enumerated metrics untouched",
        f"{len(untouched)}/{len(not_renamed)} non-listed bridged metrics kept their original name",
    ))

    width = max(len(l) for (_, l, _) in results)
    passed = 0
    for ok, label, detail in results:
        mark = "PASS" if ok else "FAIL"
        passed += ok
        print(f"  [{mark}] {label:<{width}}  {detail}")

    total = len(results)
    print(f"\n{passed}/{total} assertions passed.")
    if passed != total:
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — Views cannot bulk-prefix (wildcard collapses); only explicit "
          "one-view-per-metric renames work, and they don't scale to the whole surface.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
