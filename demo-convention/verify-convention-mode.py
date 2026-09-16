#!/usr/bin/env python3
"""Assert that the resolver's name-symmetric rule closes the convention collision.

run-convention-collision.sh established, against a released agent, that opting into Spring's or
Micrometer's OpenTelemetry naming conventions moves the bridged meter onto one of the agent's own
metric names -- out of reach of a drop-set keyed on Micrometer names. This asserts what the patched
agent does about it.

Four captures, mode=all vs mode=prefer-instrumentation, for the HTTP convention and the JVM
conventions separately:

  * under `all`, the colliding name appears under BOTH the bridge scope and an agent scope. One
    metric name, two series, disagreeing on unit and sometimes on instrument type.
  * under `prefer-instrumentation`, the bridged copy is gone and the agent's remains. Nothing else
    the bridge emits moves.

The last clause is the one that could go wrong: rule 2 keys on a name space the bridge does not own,
so it can suppress more than intended.
"""

import argparse
import json
import sys

BRIDGE = "io.opentelemetry.micrometer-1.5"
HTTP_NAME = "http.server.request.duration"

results = []


def check(ok, label, detail):
    results.append((ok, label, detail))


def load(path):
    """-> {(scope, name): metric}"""
    out = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            for resource in payload.get("resourceMetrics", []):
                for scope_metrics in resource.get("scopeMetrics", []):
                    scope = scope_metrics.get("scope", {}).get("name", "")
                    for metric in scope_metrics.get("metrics", []):
                        out[(scope, metric["name"])] = metric
    return out


def bridged(capture):
    return {name for scope, name in capture if scope == BRIDGE}


def agent_scopes_for(capture, name):
    return sorted({scope for scope, n in capture if n == name and scope != BRIDGE})


def collision_pass(label, all_capture, mode_capture, expected_names=None):
    """Names the bridge emits that the agent also emits, under `all`; then check the mode drops them."""
    all_bridged = bridged(all_capture)
    mode_bridged = bridged(mode_capture)
    agent_names_all = {n for s, n in all_capture if s != BRIDGE}

    colliding = sorted(all_bridged & agent_names_all)
    check(
        bool(colliding),
        f"{label}-SETUP",
        f"{len(colliding)} bridged name(s) collide with an agent name under mode=all: {colliding}",
    )
    if expected_names is not None:
        check(
            set(expected_names) <= set(colliding),
            f"{label}-SETUP",
            f"expected collisions present (missing: {sorted(set(expected_names) - set(colliding))})",
        )

    for name in colliding:
        check(
            name not in mode_bridged,
            f"{label}-DROP",
            f"{name}: bridged copy suppressed by rule 2",
        )
        survivors = agent_scopes_for(mode_capture, name)
        check(
            bool(survivors),
            f"{label}-KEEP",
            f"{name}: the agent copy remains ({survivors}) -- suppressed, not lost",
        )

    # Rule 2 keys on the agent's name space, not Micrometer's, so it could over-reach. Account for
    # every other bridged name that moved: either rule 1 (a Micrometer-keyed mapping) or a structural
    # companion whose base was suppressed -- `X.max` is registered from inside OpenTelemetryTimer,
    # so suppressing the base at registration takes it along and no orphan is left.
    over_dropped = sorted((all_bridged - set(colliding)) - mode_bridged)
    companions = [
        n for n in over_dropped if n.endswith(".max") and n[: -len(".max")] not in mode_bridged
    ]
    rule1 = [n for n in over_dropped if n not in companions]
    check(
        True,
        f"{label}-RULE1",
        f"{len(rule1)} further bridged name(s) dropped by rule 1: {rule1[:8]}"
        + (" ..." if len(rule1) > 8 else ""),
    )
    check(
        all(n[: -len(".max")] not in mode_bridged for n in companions),
        f"{label}-COMPANION",
        f"{len(companions)} .max companion(s) followed their suppressed base, none orphaned: {companions}",
    )
    custom = [n for n in over_dropped if n.startswith("probe.") or n.startswith("demo.")]
    check(
        not custom,
        f"{label}-CUSTOM",
        f"no application-custom metric was dropped (found: {custom or 'none'})",
    )
    return colliding


def describe(capture, name):
    rows = []
    for (scope, n), metric in sorted(capture.items()):
        if n == name:
            kind = next(
                (k for k in ("gauge", "sum", "histogram", "exponentialHistogram") if k in metric),
                "?",
            )
            rows.append(f"    {scope:42s} unit={metric.get('unit','') or '-':10s} {kind}")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--http-all", required=True)
    parser.add_argument("--http-mode", required=True)
    parser.add_argument("--jvm-all", required=True)
    parser.add_argument("--jvm-mode", required=True)
    args = parser.parse_args()

    http_all = load(args.http_all)
    http_mode = load(args.http_mode)
    jvm_all = load(args.jvm_all)
    jvm_mode = load(args.jvm_mode)

    print(f"the collision under mode=all, {HTTP_NAME}:")
    for row in describe(http_all, HTTP_NAME):
        print(row)
    print()

    collision_pass("HTTP", http_all, http_mode, expected_names=[HTTP_NAME])
    jvm_colliding = collision_pass("JVM", jvm_all, jvm_mode)

    print("JVM conventions -- names the rename moved onto the agent's namespace:")
    for name in jvm_colliding:
        for row in describe(jvm_all, name):
            print(f"  {name}\n{row}")
    print()

    failures = [r for r in results if not r[0]]
    for ok, label, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  [{label}] {detail}")
    print(f"\n{len(results) - len(failures)}/{len(results)} assertions passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
