#!/usr/bin/env python3
"""Resolve the expected `prefer-instrumentation` drop-set, independently of the agent.

The agent resolves this in Java, in AgentEmissionResolver. This is a second implementation reading
the same generated relation (inventory/bridge-mapping-*.tsv), so that the harness asserts against a
derivation rather than against a copy of the code under test. The two agreeing is evidence; the two
disagreeing is a finding either way.

Kept deliberately small: it models only the gates that appear in the data, and fails closed on
anything it does not recognise -- the same direction the Java resolver fails.
"""

from __future__ import annotations

import os

DEFAULT_MAPPING = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inventory",
    "bridge-mapping-v2.31.1.tsv",
)

# Mirrors AgentEmissionResolver: the four instrumentation names in the data whose module overrides
# defaultEnabled(), of the 134 the data references.
V3_PREVIEW_DISABLED = {"kafka-clients-0.11", "jedis-1.4", "lettuce-5.1"}
DEFAULT_DISABLED = {"apache-commons-pool-2.0", "micrometer-1.5"}

SHIPPED_CLASSES = {"direct"}


def load(path: str = DEFAULT_MAPPING):
    mappings: dict[str, tuple[str, str]] = {}
    emissions: dict[str, list[tuple[str, list[str]]]] = {}
    with open(path) as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            kind, a, b, c = parts
            if kind == "M":
                mappings[a] = (b, c)
            elif kind == "A":
                emissions.setdefault(a, []).append((b, c.split(",")))
    return mappings, emissions


def _split_conditions(when: str) -> list[tuple[str, list[str]]]:
    """`k=v[,v]...[,k2=v2]` -> [(key, [values])]. A comma token with no `=` extends the last value list."""
    conditions: list[tuple[str, list[str]]] = []
    for token in when.split(","):
        key, sep, value = token.partition("=")
        if sep:
            conditions.append((key, [value]))
        elif conditions:
            conditions[-1][1].append(token)
        else:
            return []
    return conditions


def gate_satisfied(when: str, *, opt_in: set[str], preview: set[str], v3: bool, java: int) -> bool:
    if when == "default":
        return True
    if when.startswith("Java"):
        return java >= int(when[len("Java") :])
    conditions = _split_conditions(when)
    if not conditions:
        return False
    for key, values in conditions:
        if key == "otel.semconv-stability.opt-in":
            if not set(values) <= opt_in:
                return False
        elif key == "otel.semconv-stability.preview":
            if not all(v.startswith("messaging") for v in values) or "messaging" not in preview:
                return False
        elif key == "otel.instrumentation.common.v3-preview":
            if not v3:
                return False
        else:
            # an experimental flag nobody set in these runs
            return False
    return True


def instrumentation_enabled(name: str, *, v3: bool, common_default: bool = True) -> bool:
    if name in DEFAULT_DISABLED:
        return False
    if name in V3_PREVIEW_DISABLED:
        return common_default and not v3
    return common_default


def emits_natively(otel_name, emissions, **config) -> bool:
    v3 = config["v3"]
    for when, instrumentations in emissions.get(otel_name, []):
        if not gate_satisfied(when, **config):
            continue
        if any(instrumentation_enabled(i, v3=v3) for i in instrumentations):
            return True
    return False


def resolve(
    *,
    opt_in: set[str] | None = None,
    preview: set[str] | None = None,
    v3: bool = False,
    java: int = 21,
    path: str = DEFAULT_MAPPING,
):
    """-> (mapped Micrometer names the mode drops, all agent metric names it also suppresses)."""
    mappings, emissions = load(path)
    config = {
        "opt_in": opt_in or set(),
        "preview": preview or set(),
        "v3": v3,
        "java": java,
    }
    rule1 = {
        micrometer
        for micrometer, (otel, klass) in mappings.items()
        if klass in SHIPPED_CLASSES and emits_natively(otel, emissions, **config)
    }
    rule2 = {name for name in emissions if emits_natively(name, emissions, **config)}
    return rule1, rule2


if __name__ == "__main__":
    for label, kwargs in (
        ("stock v2", {}),
        ("+ opt-in=database", {"opt_in": {"database"}}),
        ("+ opt-in=database,rpc,service.peer", {"opt_in": {"database", "rpc", "service.peer"}}),
        ("+ preview=messaging", {"preview": {"messaging"}}),
        ("v3-preview", {"v3": True}),
        ("v3-preview + preview=messaging", {"v3": True, "preview": {"messaging"}}),
    ):
        rule1, rule2 = resolve(**kwargs)
        print(f"{label:38s} rule1={len(rule1):3d}  rule2={len(rule2):3d}")
