#!/usr/bin/env python3
"""Assert the worked misconfiguration behaves as the narrative claims.

Reads the four captures produced by run-misconfig.sh and asserts, per instrumentation scope:

  A sysprops     bridge ON  -> custom metrics present, jvm.memory.used present TWICE (two scopes)
  B naive-views  bridge OFF -> the duplication is gone (looks fixed) AND every custom metric is
                 gone (is not fixed), with nothing logged to say so
  C fixed        bridge ON  -> bridged duplicates dropped by views, custom metrics kept,
                 and jvm.gc.pause.max survives the exact-name view (the second trap)
  D env-ignored  C + OTEL_METRICS_EXPORTER=none -> metrics still exported, i.e. the env var
                 stopped being read once a config file was active

Exit code 0 = every assertion holds, 1 = at least one failed.

Usage: verify-misconfig.py <out-dir> [--agent-version X.Y.Z]
"""
import argparse
import json
import os
import re
import sys

BRIDGE = "io.opentelemetry.micrometer-1.5"
CUSTOM = ("orders.placed", "orders.latency")


def load(path):
    """(scope, name) pairs across every OTLP-JSON export line.

    Accepts both shapes the two exporters emit: `otlp_file/development` writes
    {"resourceMetrics": [...]}, `logging-otlp` writes a bare ResourceMetrics object.
    """
    pairs, lines = set(), 0
    if not os.path.exists(path):
        return pairs, 0
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
            for rm in obj.get("resourceMetrics", [obj]):
                for sm in rm.get("scopeMetrics", []):
                    scope = sm.get("scope", {}).get("name", "")
                    for m in sm.get("metrics", []):
                        if m.get("name"):
                            pairs.add((scope, m["name"]))
    return pairs, lines


def scopes_for(pairs, name):
    return sorted(s for (s, n) in pairs if n == name)


def bridged(pairs):
    return sorted(n for (s, n) in pairs if s == BRIDGE)


def micrometer_warnings(logpath):
    """Anything in the run log that would tell a user the bridge did not start."""
    if not os.path.exists(logpath):
        return []
    hits = []
    with open(logpath, encoding="utf-8", errors="replace") as f:
        for line in f:
            if re.search(r"\b(WARN|WARNING|SEVERE|ERROR)\b", line) and "micrometer" in line.lower():
                hits.append(line.strip())
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--agent-version", default="(unspecified)")
    args = ap.parse_args()

    runs = {}
    for label in ("sysprops", "naive-views", "fixed", "env-ignored"):
        path = os.path.join(args.out_dir, f"misconfig-{label}.jsonl")
        runs[label] = load(path) + (path.replace(".jsonl", ".log"),)

    print(f"worked misconfiguration (FM-3) — agent {args.agent_version}\n")
    for label, (pairs, lines, _log) in runs.items():
        print(f"  {label:<12} {lines:>2} export(s), {len(pairs):>3} (scope,metric) pair(s), "
              f"{len(bridged(pairs)):>2} bridged")
    print()

    a, _, _ = runs["sysprops"]
    b, _, b_log = runs["naive-views"]
    c, _, _ = runs["fixed"]
    d, d_lines, _ = runs["env-ignored"]

    results = []

    def check(ok, act, detail):
        results.append((bool(ok), act, detail))

    # --- A: the working starting point -------------------------------------------------------
    for name in CUSTOM:
        check((BRIDGE, name) in a, "A start",
              f"custom metric `{name}` reaches OTel via the bridge")
    mem_scopes = scopes_for(a, "jvm.memory.used")
    check(len(mem_scopes) >= 2, "A start",
          f"jvm.memory.used arrives from {len(mem_scopes)} scopes (the duplication): {mem_scopes}")

    # --- B: the misconfiguration -------------------------------------------------------------
    check(len(bridged(b)) == 0, "B break",
          f"bridge emitted nothing at all ({len(bridged(b))} metrics) — it never started")
    b_mem = scopes_for(b, "jvm.memory.used")
    check(len(b_mem) == 1, "B break",
          f"duplication LOOKS fixed: jvm.memory.used now from {len(b_mem)} scope {b_mem}")
    for name in CUSTOM:
        check((BRIDGE, name) not in b, "B break",
              f"custom metric `{name}` silently GONE — the actual damage")
    warnings = micrometer_warnings(b_log)
    check(not warnings, "B break",
          "nothing in the agent log warns about micrometer"
          if not warnings else f"log DOES warn: {warnings[:2]}")

    # --- C: the fix ---------------------------------------------------------------------------
    for name in CUSTOM:
        check((BRIDGE, name) in c, "C fix", f"custom metric `{name}` is back")
    check((BRIDGE, "jvm.memory.used") not in c, "C fix",
          "bridged jvm.memory.used dropped by the view")
    check(len(scopes_for(c, "jvm.memory.used")) == 1, "C fix",
          "the agent's native jvm.memory.used survives the scoped drop")
    check((BRIDGE, "jvm.gc.pause") not in c, "C fix",
          "bridged jvm.gc.pause dropped by the exact-name view")
    # The second trap: the companion the exact-name view does not match.
    check((BRIDGE, "jvm.gc.pause.max") in c, "C trap",
          "`jvm.gc.pause.max` SURVIVES the exact-name view — the companion needs a glob")

    # --- D: the env var is no longer read -----------------------------------------------------
    check(d_lines > 0 and len(d) > 0, "D env",
          f"OTEL_METRICS_EXPORTER=none was ignored: {d_lines} export(s) still arrived")

    width = max(len(a_) for (_, a_, _) in results)
    passed = 0
    for ok, act, detail in results:
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {act:<{width}}  {detail}")

    print(f"\n{passed}/{len(results)} assertions passed.")
    if passed != len(results):
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — the misconfiguration reproduces, and its symptom looks like success.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
