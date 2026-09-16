#!/usr/bin/env python3
"""Assert what `metrics.mode: prefer-instrumentation` does, and what it leaves in the composite.

Two independent questions:

1. *Export.* Diff the baseline capture against the mode capture. Every bridged metric whose name is
   in the spike's suppression set must be gone; every other bridged metric must survive; no
   agent-native scope may move at all.

2. *Reads.* The CompositeReadApp probe writes PROBE lines. With the marker (Layer B) the sibling
   SimpleMeterRegistry must answer reads correctly. Without it (a plain Micrometer noop -- what a
   MeterFilter DENY leaves behind, i.e. Layer A) reads can come back wrong, which is the whole
   reason the layer choice matters.

   This is asserted over a SAMPLE of runs, not a single one. AbstractCompositeMeter keeps its
   per-registry children in an IdentityHashMap (:23,36), and firstChild() (:52-53) returns whichever
   the identity-hash order puts first -- so an unmarked noop corrupts the read only in the runs where
   the bridge's child sorts ahead of the sibling. Measured at 6 of 10 runs. The asymmetry is the
   finding: Layer B is correct in every run, Layer A is wrong in some, which is worse than being
   wrong in all of them because it survives a CI pass.

3. *Companions.* Suppressing a Timer at registration takes its `.max` gauge with it, because the
   companion is registered from inside OpenTelemetryTimer. An exact-name SDK view drops the base and
   orphans the companion; this should not.

Usage: verify-mode.py <baseline.jsonl> <mode.jsonl> <probe-all.jsonl> <probe-mode.jsonl> <out-dir>

<out-dir> is scanned for mode-read-marked-*.log and mode-read-unmarked-*.log, one pair per repeat.
"""

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dropset  # noqa: E402

BRIDGE_SCOPE = "io.opentelemetry.micrometer-1.5"

# The expected drop-set is DERIVED, not copied. dropset.py reads the same generated relation the
# agent reads (inventory/bridge-mapping-*.tsv) and resolves it for a stock v2 agent: no
# semantic-convention opt-in, no preview, no v3-preview, current JDK. Two independent
# implementations of the resolver agreeing is evidence; disagreeing is a finding either way.
#
# The agreement is asserted behaviourally rather than by comparing counts: sections 1-3 below
# require the agent's actual drops to equal this set exactly, which is a stronger check than
# reading the resolver's own FINE log line (and needs no debug logging enabled).
RULE1, RULE2 = dropset.resolve()
SUPPRESSED = RULE1 | RULE2

# Companion instruments are suppressed *structurally*, not by name: the bridge registers `X.max`
# from inside OpenTelemetryTimer/OpenTelemetryDistributionSummary, so suppressing the registration
# of `X` means the companion is never created. The predicate only ever sees the registration id.
#
# Only `.max` is stripped, and only when the base is itself in the capture -- which is the evidence
# that `X` was registered as a timer or summary. LongTaskTimer's `.active`/`.duration` and
# FunctionTimer's `.count`/`.sum` are deliberately NOT stripped: those types never export their base
# name, so a stripped form cannot be distinguished from an independent meter that merely ends in the
# same segment. `jvm.classes.loaded.count` is exactly that case -- it is its own Micrometer gauge and
# is correctly KEPT, while `jvm.classes.loaded` is in the drop-set. Stripping `.count` would have
# produced a false failure here.
COMPANION_SUFFIX = ".max"


def expected_dropped(name, present):
    """Whether the mode should drop this exported metric, given the names present in the capture."""
    if name in SUPPRESSED:
        return True
    if name.endswith(COMPANION_SUFFIX):
        base = name[: -len(COMPANION_SUFFIX)]
        return base in SUPPRESSED and base in present
    return False

results = []


def check(ok, label, detail):
    results.append((ok, label, detail))


def load_pairs(path):
    """-> set of (scope, metric name) across every export in the capture."""
    pairs = set()
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
                        pairs.add((scope, metric["name"]))
    return pairs


def probe_reads(path):
    """-> {metric name: value read back through the composite}."""
    reads = {}
    pattern = re.compile(r"PROBE read name=(\S+) expected=(\S+) got=(\S+)")
    with open(path) as handle:
        for line in handle:
            match = pattern.search(line)
            if match:
                reads[match.group(1)] = (float(match.group(2)), float(match.group(3)))
    return reads


def main():
    baseline_path, mode_path, probe_all_path, probe_mode_path, out_dir = sys.argv[1:6]

    baseline = load_pairs(baseline_path)
    mode = load_pairs(mode_path)

    bridged_baseline = {name for scope, name in baseline if scope == BRIDGE_SCOPE}
    bridged_mode = {name for scope, name in mode if scope == BRIDGE_SCOPE}
    native_baseline = {(s, n) for s, n in baseline if s != BRIDGE_SCOPE}
    native_mode = {(s, n) for s, n in mode if s != BRIDGE_SCOPE}

    print(
        f"parsed {len(baseline)} baseline / {len(mode)} mode (scope,metric) pairs; "
        f"{len(bridged_baseline)} bridged in baseline, {len(bridged_mode)} in mode"
    )
    print(
        f"derived drop-set: {len(RULE1)} rule-1 (mapped names) + {len(RULE2)} rule-2 "
        f"(agent names) = {len(SUPPRESSED)} total, of which "
        f"{len(bridged_baseline & SUPPRESSED)} are actually emitted by this app\n"
    )

    should_drop = {n for n in bridged_baseline if expected_dropped(n, bridged_baseline)}

    # --- 1. every bridged metric in the suppression set is gone ---------------------------------
    if not should_drop:
        check(False, "SETUP", "baseline emitted no metric in the suppression set — nothing to test")
    for name in sorted(should_drop):
        check(name not in bridged_mode, "DROP", f"{name} in suppression set -> gone")

    # --- 2. everything else the bridge emitted survives ------------------------------------------
    for name in sorted(bridged_baseline - should_drop):
        check(name in bridged_mode, "KEEP", f"{name} not in suppression set -> kept")

    # --- 3. nothing new appeared, and no native scope moved --------------------------------------
    check(
        not (bridged_mode - bridged_baseline),
        "NO-NEW",
        f"mode added no bridged metric (added: {sorted(bridged_mode - bridged_baseline) or 'none'})",
    )
    check(
        native_baseline == native_mode,
        "NATIVE",
        f"agent-native scopes untouched ({len(native_baseline)} pairs)",
    )

    # --- 4. the .max companion follows its base ---------------------------------------------------
    # Suppressing a Timer at registration means its .max gauge is never created either, because the
    # companion is registered from inside OpenTelemetryTimer and that object is never constructed.
    # An exact-name SDK view has no equivalent -- it drops the base and orphans the companion.
    # Measured on CompositeReadApp, which registers a Timer whose name is in the suppression set.
    probe_all = {name for scope, name in load_pairs(probe_all_path) if scope == BRIDGE_SCOPE}
    probe_mode = {name for scope, name in load_pairs(probe_mode_path) if scope == BRIDGE_SCOPE}

    timer_bases = sorted(n for n in probe_all & SUPPRESSED if f"{n}.max" in probe_all)
    if not timer_bases:
        check(
            False,
            "SETUP",
            "probe emitted no suppressed timer with a .max companion — companion claim untested",
        )
    for name in timer_bases:
        check(name not in probe_mode, "COMPANION", f"{name} (timer base) suppressed")
        check(
            f"{name}.max" not in probe_mode,
            "COMPANION",
            f"{name}.max followed its base — no orphan",
        )

    # --- 5. composite reads, marked (Layer B) ----------------------------------------------------
    # The claim is unconditional: every read, in every run. Layer B does not depend on iteration
    # order, because the agent's firstChild() rewrite skips the marker deterministically.
    marked_logs = sorted(glob.glob(os.path.join(out_dir, "mode-read-marked-*.log")))
    if not marked_logs:
        check(False, "SETUP", f"no mode-read-marked-*.log in {out_dir}")
    marked_runs = 0
    marked_wrong_runs = 0
    for path in marked_logs:
        reads = probe_reads(path)
        if not reads:
            check(False, "SETUP", f"no PROBE read lines in {os.path.basename(path)}")
            continue
        marked_runs += 1
        wrong = {n: v for n, v in reads.items() if v[1] != v[0]}
        if wrong:
            marked_wrong_runs += 1
        check(
            not wrong,
            "READ-B",
            f"{os.path.basename(path)}: all {len(reads)} reads correct"
            + (f" (wrong: {sorted(wrong)})" if wrong else ""),
        )

    # --- 6. composite reads, unmarked (the Layer A artifact) --------------------------------------
    # The claim is existential, and deliberately so -- see the module docstring. Corruption depends
    # on IdentityHashMap order, so it is asserted across the sample rather than per run.
    unmarked_logs = sorted(glob.glob(os.path.join(out_dir, "mode-read-unmarked-*.log")))
    if not unmarked_logs:
        check(False, "SETUP", f"no mode-read-unmarked-*.log in {out_dir}")
    corrupted_runs = []
    unmarked_runs = 0
    for path in unmarked_logs:
        reads = probe_reads(path)
        if not reads:
            check(False, "SETUP", f"no PROBE read lines in {os.path.basename(path)}")
            continue
        unmarked_runs += 1
        corrupted = {
            name
            for name, (expected, got) in reads.items()
            if got != expected and name in SUPPRESSED
        }
        if corrupted:
            corrupted_runs.append((os.path.basename(path), sorted(corrupted)))

        # The control must never be corrupted, in any run, either way. If it ever is, the probe is
        # measuring something other than suppression and every read conclusion is void.
        for name, (expected, got) in sorted(reads.items()):
            if name in SUPPRESSED:
                continue
            check(
                got == expected,
                "READ-A-CTL",
                f"{os.path.basename(path)}: control {name} read back {got}, expected {expected}",
            )

    check(
        bool(corrupted_runs),
        "READ-A",
        f"an unmarked noop corrupts composite reads in {len(corrupted_runs)}/{unmarked_runs} runs "
        f"(order-dependent, so >=1 is the claim; corrupted names per affected run: "
        f"{[names for _, names in corrupted_runs] or 'none'})",
    )
    check(
        marked_runs > 0 and marked_wrong_runs == 0 and bool(corrupted_runs),
        "LAYER",
        f"asymmetry holds: marked correct in {marked_runs - marked_wrong_runs}/{marked_runs} runs, "
        f"unmarked corrupted in {len(corrupted_runs)}/{unmarked_runs}",
    )

    for ok, label, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:11} {detail}")

    passed = sum(1 for ok, _, _ in results if ok)
    print(f"\n{passed}/{len(results)} assertions passed.")
    if passed != len(results):
        print("RESULT: FAIL")
        return 1
    print(
        "RESULT: PASS — the mode drops exactly its derived set, and the marker keeps composite reads "
        "intact in every run where an unmarked noop would not."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
