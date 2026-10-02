#!/usr/bin/env python3
"""Generate the agent-side mapping resource the `prefer-instrumentation` resolver reads.

The proposal's central claim is that the drop policy cannot be a frozen list of metric names,
because whether the agent emits a counterpart depends on the agent's *effective* configuration.
So what ships is not a name list but a small relation:

    M  micrometerName -> otelName, concept-map class
    A  otelName       -> one row per way the agent can emit it: (when-condition, instrumentations)

The bridge resolves, at meter-registration time, "is there an enabled instrumentation with a
satisfied gate that emits the counterpart?" — an OR-fold over the A rows for the mapped name.
The A rows serve both resolver rules:

  * rule 1 (name-keyed)     M row maps a Micrometer name onto an agent name, then A resolves it
  * rule 2 (name-symmetric) the bridged name IS an agent name — look it up in A directly.
                            This is the case a name-keyed drop-set structurally cannot express,
                            i.e. Micrometer's and Spring's OTel naming conventions.

Inputs are the two files the testbed already produces; nothing here is hand-authored.

    tools/gen_dropset.py inventory/decisions-v2.31.1.json inventory/otel-v2.31.1.json <out.txt> [out.java]

If <out.java> is given, the same relation is also emitted as a generated Java source file for the
agent's micrometer-1.5 javaagent module. A data *resource* would be the production shape, but the
class that resolves the policy (`MicrometerSingletons`) is an exposed helper class injected into
the application class loader (`MicrometerInstrumentationModule.java:44-48`), so resource lookup
there does not go through the agent class loader. A generated constant sidesteps that for the
prototype without changing what the data is or where it comes from.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

# The concept-map classes the shipped default acts on. D1: `direct` only — measured against the
# views config author's hand decisions, `direct` predicted 145/145 of their drops while the
# non-`direct` rows split 5/5. `partial` and `semantic` rows are emitted with their class so the
# curation boundary stays visible in the data, and the resolver filters them out.
SHIPPED_CLASSES = ("direct",)


def load(path: str):
    with open(path) as f:
        return json.load(f)


def javaagent_emitters(agent_root: str) -> set[str]:
    """Instrumentation names the *javaagent* can emit, from the agent source tree.

    The registry's `emittedBy` lists the module that declares each metric, and that includes
    library-only modules -- `kafka-clients-2.6`, `spring-webmvc-5.3`, `iceberg-1.8` and eight others
    have no `javaagent` directory at all. Those emit only when a user wires the library
    instrumentation by hand, which the bridge cannot observe, so a javaagent-side policy must not
    treat them as evidence that the agent emits a counterpart.

    This matters most where the proposal's value is concentrated. 96 of the Kafka rows list both
    `kafka-clients-0.11` (the javaagent metrics module, disabled under v3-preview) and
    `kafka-clients-2.6` (library-only). OR-folding over both keeps the drop alive under v3-preview
    with nothing replacing it -- the exact failure the proposal warns a frozen list would cause.
    """
    import os

    root = os.path.join(agent_root, "instrumentation")
    emitters: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root):
        if "build" in dirpath.split(os.sep):
            dirnames[:] = [d for d in dirnames if d != "build"]
            continue
        if "javaagent" in dirnames:
            emitters.add(os.path.basename(dirpath))
    return emitters


JAVA_HEADER = '''/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package io.opentelemetry.javaagent.instrumentation.micrometer.v1_5;

/**
 * The mapping data the {@code prefer-instrumentation} resolver evaluates. Generated -- do not edit.
 *
 * <p>Two kinds of row, tab-separated:
 *
 * <ul>
 *   <li>{@code M<TAB>micrometerName<TAB>otelName<TAB>conceptClass} -- a Micrometer metric and the
 *       agent metric it duplicates, from the project's curated concept map.
 *   <li>{@code A<TAB>otelName<TAB>whenCondition<TAB>instrumentations} -- one way the agent can emit
 *       one of its own metrics. OR-folded: the agent emits {@code otelName} if any row's condition
 *       holds and any of its instrumentations is enabled.
 * </ul>
 *
 * <p>The A rows are the reason this is a relation and not a name list. Whether a given drop is safe
 * depends on the agent's effective configuration, and 126 of the 155 mapped rows are gated on
 * something a shipped list cannot see.
 *
 * <p>Provenance: {0}
 */
final class BridgeMappingData {

  static final String[] ROWS = {
'''

JAVA_FOOTER = '''  };

  private BridgeMappingData() {}
}
'''


def write_java(path: str, provenance: str, rows: list[str]) -> None:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")

    body = "".join(f'    "{esc(r)}",\n' for r in rows)
    with open(path, "w") as f:
        f.write(JAVA_HEADER.replace("{0}", provenance) + body + JAVA_FOOTER)


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        print(__doc__.strip())
        return 2
    decisions_path, otel_path, out_path = argv[1:4]
    java_path = argv[4] if len(argv) == 5 else None
    agent_root = os.environ.get(
        "AGENT_ROOT", os.path.expanduser("~/code/projects/opentelemetry-java-instrumentation")
    )
    decisions = load(decisions_path)
    otel = load(otel_path)

    # --- A rows: how the agent can emit each of its own metric names -----------------------
    # One row per (name, when) pair. `emittedBy` is the set of instrumentations that declare the
    # metric under that condition; any one of them being enabled satisfies the row.
    agent_emitters = javaagent_emitters(agent_root)
    alternatives: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    excluded: set[str] = set()
    dropped_rows = 0
    for rec in otel["meters"]:
        keep = [m for m in rec["emittedBy"] if m in agent_emitters]
        excluded.update(m for m in rec["emittedBy"] if m not in agent_emitters)
        if not keep:
            dropped_rows += 1
            continue
        alternatives[rec["name"]][rec["when"]].update(keep)
    print(
        f"  excluded {len(excluded)} library-only instrumentation names "
        f"({dropped_rows} A rows had no javaagent emitter left): {sorted(excluded)}",
        file=sys.stderr,
    )

    # --- M rows: the Micrometer -> agent concept mapping -----------------------------------
    mappings: list[tuple[str, str, str]] = []
    for row in decisions["decisions"]:
        if row.get("dropClass") != "duplicate":
            continue
        agent = row.get("agent") or {}
        otel_name = agent.get("otelName")
        if not otel_name:
            continue
        if otel_name not in alternatives:
            # A concept-map assertion whose target the registry does not catalogue cannot be
            # resolved against the agent's configuration, so it must not ship as a drop.
            print(f"  skip {row['name']}: target {otel_name} not in registry", file=sys.stderr)
            continue
        mappings.append((row["name"], otel_name, agent.get("class") or "unknown"))
    mappings.sort()

    header = decisions.get("otelRegistryVersion") or otel["header"]["registryVersion"]
    micrometer_versions = decisions.get("micrometerVersions") or []

    provenance = "registry {}, micrometer {}, {} mappings over {} agent metric names".format(
        header,
        ",".join(micrometer_versions) if micrometer_versions else "unknown",
        len(mappings),
        len(alternatives),
    )

    data_rows: list[str] = []
    for mm_name, otel_name, klass in mappings:
        data_rows.append(f"M\t{mm_name}\t{otel_name}\t{klass}")
    for otel_name in sorted(alternatives):
        for when in sorted(alternatives[otel_name]):
            insts = ",".join(sorted(alternatives[otel_name][when]))
            data_rows.append(f"A\t{otel_name}\t{when}\t{insts}")

    lines: list[str] = []
    lines.append("# Generated by tools/gen_dropset.py -- do not edit.")
    lines.append("#")
    lines.append("# V <key>=<value>...          provenance")
    lines.append("# M <micrometer> <otel> <cls> a Micrometer metric and the agent metric it duplicates")
    lines.append("# A <otel> <when> <insts>     one way the agent can emit <otel>; OR-folded")
    lines.append("#")
    lines.append("# Fields are tab-separated. <insts> is comma-separated.")
    lines.append("#")
    lines.append(
        "# Emitters with no javaagent module are excluded -- they emit only when a user wires the"
    )
    lines.append("# library instrumentation by hand, which the bridge cannot observe:")
    lines.append("#   " + ", ".join(sorted(excluded)))
    lines.append(
        "V\tregistry={}\tmicrometer={}\tmappings={}\tagentNames={}".format(
            header,
            ",".join(micrometer_versions) if micrometer_versions else "unknown",
            len(mappings),
            len(alternatives),
        )
    )
    lines.extend(data_rows)

    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    if java_path:
        write_java(java_path, provenance, data_rows)
        print(f"wrote {java_path}")

    shipped = [m for m in mappings if m[2] in SHIPPED_CLASSES]
    print(f"wrote {out_path}")
    print(f"  M rows: {len(mappings)} ({len(shipped)} classified {'/'.join(SHIPPED_CLASSES)})")
    print(f"  A rows: {sum(len(v) for v in alternatives.values())} over {len(alternatives)} agent metric names")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
