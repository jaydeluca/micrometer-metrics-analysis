#!/usr/bin/env python3
"""Assert that Spring's semconv-named observation convention defeats a Micrometer-name-keyed drop-set.

Reads the two captures produced by run-convention-collision.sh — identical agent configuration,
differing only in which ServerRequestObservationConvention bean the app registers — and asserts:

  default run  bridge emits `http.server.requests`; the agent natively emits
               `http.server.request.duration` from its own HTTP instrumentation. Two names, so the
               duplicate is diagnosable, and the drop-set's `http.server.requests` row fires.

  otel run     bridge emits `http.server.request.duration` — the SAME name the agent emits — and
               the drop-set has no row under that key, so `prefer-instrumentation` does not fire.
               The duplicate is now same-name and undiagnosable, and the policy is silent about it.

It also characterizes the collision rather than only asserting it: unit, OTLP data type, and
attribute-key sets on both sides of the shared name, because that is what determines whether a
backend can tell the two series apart.

Exit code 0 = every assertion holds, 1 = at least one failed.
"""
import argparse
import json
import os
import sys

BRIDGE = "io.opentelemetry.micrometer-1.5"
MICROMETER_NAME = "http.server.requests"
SEMCONV_NAME = "http.server.request.duration"

DATA_KEYS = ("gauge", "sum", "histogram", "exponentialHistogram", "summary")


def data_type(metric):
    for key in DATA_KEYS:
        if key in metric:
            if key == "sum":
                return "sum(monotonic)" if metric[key].get("isMonotonic") else "sum(up-down)"
            return key
    return "unknown"


def attr_keys(metric):
    """Union of attribute keys across the metric's data points."""
    keys = set()
    for key in DATA_KEYS:
        if key in metric:
            for dp in metric[key].get("dataPoints", []):
                for attr in dp.get("attributes", []):
                    if "key" in attr:
                        keys.add(attr["key"])
    return keys


def load(path):
    """(scope, name) -> {"unit", "type", "attrs"} across every OTLP-JSON export line."""
    surface, lines = {}, 0
    if not os.path.exists(path):
        return surface, 0
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
            resource_metrics = obj.get("resourceMetrics", [obj]) if "resourceMetrics" in obj else [obj]
            for rm in resource_metrics:
                for sm in rm.get("scopeMetrics", []):
                    scope = sm.get("scope", {}).get("name", "")
                    for m in sm.get("metrics", []):
                        name = m.get("name")
                        if not name:
                            continue
                        entry = surface.setdefault(
                            (scope, name), {"unit": m.get("unit", ""), "type": data_type(m), "attrs": set()}
                        )
                        entry["attrs"] |= attr_keys(m)
    return surface, lines


def native_holders(surface, name):
    """Scopes other than the bridge that emit `name`."""
    return sorted(s for (s, n) in surface if n == name and s != BRIDGE)


def drop_row(decisions, name):
    for row in decisions.get("decisions", []):
        if row.get("name") == name:
            return row
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--default", dest="default_path", required=True)
    parser.add_argument("--otel", dest="otel_path", required=True)
    parser.add_argument("--otel-jvm", dest="otel_jvm_path", required=False)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--agent-version", default="unknown")
    args = parser.parse_args()

    default_surface, default_lines = load(args.default_path)
    otel_surface, otel_lines = load(args.otel_path)
    with open(args.decisions, encoding="utf-8") as f:
        decisions = json.load(f)

    print(f"agent {args.agent_version} | decisions pinned to registry {decisions.get('otelRegistryVersion')}")
    print(f"default-convention capture: {default_lines} export line(s)")
    print(f"otel-convention capture:    {otel_lines} export line(s)")

    results = []

    def check(ok, act, detail):
        results.append((bool(ok), act, detail))

    check(default_lines > 0, "default run exported OTLP", f"{default_lines} line(s)")
    check(otel_lines > 0, "otel run exported OTLP", f"{otel_lines} line(s)")

    # --- the default convention: two names, so the duplicate is visible -----------------------
    d_bridge_mm = (BRIDGE, MICROMETER_NAME) in default_surface
    check(d_bridge_mm, f"default: bridge emits {MICROMETER_NAME}", "present" if d_bridge_mm else "ABSENT")

    d_native = native_holders(default_surface, SEMCONV_NAME)
    check(bool(d_native), f"default: agent natively emits {SEMCONV_NAME}", ", ".join(d_native) or "ABSENT")

    d_bridge_semconv = (BRIDGE, SEMCONV_NAME) in default_surface
    check(
        not d_bridge_semconv,
        "default: no same-name collision on the bridge scope",
        "bridge does not emit the semconv name" if not d_bridge_semconv else "bridge ALSO emits it",
    )

    mm_row = drop_row(decisions, MICROMETER_NAME)
    check(
        mm_row is not None and mm_row.get("decision") == "drop",
        f"default: drop-set has a drop row for {MICROMETER_NAME}",
        f"{mm_row.get('decision')}({mm_row.get('dropClass')}) — {mm_row.get('reason')}" if mm_row else "NO ROW",
    )

    # --- the otel convention: one name, and the policy key changes underneath it --------------
    o_bridge_semconv = (BRIDGE, SEMCONV_NAME) in otel_surface
    check(
        o_bridge_semconv,
        f"otel: bridge emits {SEMCONV_NAME}",
        "present" if o_bridge_semconv else "ABSENT",
    )

    o_bridge_mm = (BRIDGE, MICROMETER_NAME) in otel_surface
    check(
        not o_bridge_mm,
        f"otel: bridge no longer emits {MICROMETER_NAME}",
        "gone" if not o_bridge_mm else "STILL PRESENT",
    )

    o_native = native_holders(otel_surface, SEMCONV_NAME)
    check(
        bool(o_native) and o_bridge_semconv,
        "otel: same-name collision across scopes",
        f"bridge + {', '.join(o_native)}" if o_native else "no native copy found",
    )

    semconv_row = drop_row(decisions, SEMCONV_NAME)
    check(
        semconv_row is None,
        f"otel: drop-set has NO row for {SEMCONV_NAME}",
        "absent — a name-keyed policy misses it" if semconv_row is None else f"row exists: {semconv_row.get('decision')}",
    )

    # --- characterize the collision -----------------------------------------------------------
    print("\ncollision shape under the otel convention:")
    if o_bridge_semconv and o_native:
        bridge_entry = otel_surface[(BRIDGE, SEMCONV_NAME)]
        for scope in o_native:
            native_entry = otel_surface[(scope, SEMCONV_NAME)]
            print(f"\n  {SEMCONV_NAME}")
            print(f"    bridge  scope={BRIDGE}")
            print(f"            unit={native_entry['unit']!r} vs {bridge_entry['unit']!r}  type={bridge_entry['type']}")
            print(f"    native  scope={scope}")
            print(f"            unit={native_entry['unit']!r}  type={native_entry['type']}")
            print(f"    unit agrees:  {bridge_entry['unit'] == native_entry['unit']}")
            print(f"    type agrees:  {bridge_entry['type'] == native_entry['type']}")
            shared = sorted(bridge_entry["attrs"] & native_entry["attrs"])
            only_bridge = sorted(bridge_entry["attrs"] - native_entry["attrs"])
            only_native = sorted(native_entry["attrs"] - bridge_entry["attrs"])
            print(f"    attrs shared:      {shared}")
            print(f"    attrs bridge-only: {only_bridge}")
            print(f"    attrs native-only: {only_native}")
            check(
                bridge_entry["attrs"] != native_entry["attrs"],
                "otel: the two same-name series carry different attribute keys",
                f"{len(only_bridge)} bridge-only, {len(only_native)} native-only",
            )
    else:
        print("  (not measurable — one side of the collision is missing; see the FAILs above)")

    # --- the JVM/CPU half: the rename that is NOT unit-protected ------------------------------
    # The rename set is derived from the captures rather than hard-coded: micrometer-core's
    # convention/otel classes rename some meters in a binder and leave others hardcoded (e.g.
    # jvm.threads.live stays, jvm.threads.states becomes jvm.thread.count), so any hand-written
    # mapping would be asserting the harness's assumptions instead of measuring the code.
    if args.otel_jvm_path:
        jvm_surface, jvm_lines = load(args.otel_jvm_path)
        check(jvm_lines > 0, "otel-jvm run exported OTLP", f"{jvm_lines} line(s)")

        before = {n for (s, n) in default_surface if s == BRIDGE}
        after = {n for (s, n) in jvm_surface if s == BRIDGE}
        gone, appeared = sorted(before - after), sorted(after - before)

        print(f"\nJVM/CPU conventions: {len(gone)} bridged name(s) gone, {len(appeared)} appeared")
        print(f"  gone:     {gone}")
        print(f"  appeared: {appeared}")

        collided, no_row, unit_disagrees = [], [], []
        print("\n  each new name, against the agent's own instrumentation:")
        for name in appeared:
            natives = native_holders(jvm_surface, name)
            row = drop_row(decisions, name)
            b = jvm_surface[(BRIDGE, name)]
            n = jvm_surface.get((natives[0], name)) if natives else None
            if natives:
                collided.append(name)
            if row is None:
                no_row.append(name)
            if n and b["unit"] != n["unit"]:
                unit_disagrees.append((name, b["unit"], n["unit"]))
            print(
                f"    {name:<30} native={(natives[0].split('.')[-1] if natives else 'NONE'):<26}"
                f" unit {b['unit']!r} vs {(n['unit'] if n else '-')!r:<10}"
                f" type {b['type']} vs {(n['type'] if n else '-')}"
                f"  drop-set={'NO ROW' if row is None else row['decision']}"
            )

        check(
            bool(appeared) and len(collided) == len(appeared),
            "otel-jvm: every renamed metric collides with an agent-native name",
            f"{len(collided)}/{len(appeared)}",
        )
        check(
            len(no_row) == len(appeared),
            "otel-jvm: no renamed metric has a drop-set row",
            f"{len(no_row)}/{len(appeared)} absent from the drop-set",
        )
        check(
            len(unit_disagrees) == len(collided),
            "otel-jvm: every collision disagrees on unit",
            f"{len(unit_disagrees)}/{len(collided)}",
        )
        # The one case unit normalization (lever A5) cannot fix: `ns` is a valid UCUM code, so no
        # UCUM-validity rule flags it, yet it is 10^9 off the semconv unit for this metric name.
        cpu = jvm_surface.get((BRIDGE, "jvm.cpu.time"))
        cpu_natives = native_holders(jvm_surface, "jvm.cpu.time")
        cpu_native = jvm_surface.get((cpu_natives[0], "jvm.cpu.time")) if cpu_natives else None
        check(
            bool(cpu and cpu_native) and cpu["unit"] == "ns" and cpu_native["unit"] == "s",
            "otel-jvm: jvm.cpu.time is a value-scale error, not a spelling one",
            f"bridge={cpu['unit']!r} native={cpu_native['unit']!r}" if cpu and cpu_native else "one side missing",
        )
    else:
        jvm_surface = {}

    # --- surface summary, for the writeup -----------------------------------------------------
    for label, surface in (("default", default_surface), ("otel", otel_surface)):
        bridged = sorted(n for (s, n) in surface if s == BRIDGE)
        print(f"\n{label} run: {len(bridged)} bridged metric(s) on {BRIDGE}")
        for name in bridged:
            entry = surface[(BRIDGE, name)]
            print(f"    {name:<45} unit={entry['unit']!r:<12} type={entry['type']}")

    width = max(len(act) for _, act, _ in results)
    print("\nassertions:")
    passed = 0
    for ok, act, detail in results:
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {act:<{width}}  {detail}")

    print(f"\n{passed}/{len(results)} assertions passed.")
    if passed != len(results):
        print("RESULT: FAIL")
        return 1
    print(
        "RESULT: PASS — a user-authored convention bean, invisible to agent config, moves the meter "
        "onto the agent's own metric name and out of the drop-set's key space."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
