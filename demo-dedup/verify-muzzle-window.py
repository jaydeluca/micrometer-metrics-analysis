#!/usr/bin/env python3
"""Probe stage 04's second decision: enablement is not application. Two probes, one app.

PROBE 1 -- the declared muzzle range. Four captures of the same app under the same agent and the
same config, varying only the HikariCP version (either side of the hikaricp-3.0 module's declared
[3.0.0,) floor) and the mode. The hypothesis was that 2.7.9 reproduces the window: library present,
module enabled, muzzle declines, mode drops the Micrometer copy with nothing to replace it. The
assertions record what actually happens, because the answer turned out to be the finding.

PROBE 2 -- a bridged name with no library behind it. The app registers a timer named
`http.client.request.duration`, one of the agent's own metric names, while containing no HTTP client
library at all. The resolver's second, name-symmetric rule sees 37 enabled HTTP client
instrumentations and suppresses it. Nothing replaces it. This reaches the same failure the muzzle
window describes, with no version skew involved.

Usage: verify-muzzle-window.py <above-all> <above-mode> <below-all> <below-mode> <debug.log>
"""

import json
import sys

BRIDGE_SCOPE = "io.opentelemetry.micrometer-1.5"
AGENT_HIKARI_SCOPE = "io.opentelemetry.hikaricp-3.0"

# The `direct`-classified hikaricp rows -- the ones the shipped policy acts on. `hikaricp.connections
# .active` and `.idle` are classified `partial` and are deliberately left alone, so they are the
# control: they must survive in every run.
DIRECT_ROWS = {
    "hikaricp.connections.acquire",
    "hikaricp.connections.creation",
    "hikaricp.connections.max",
    "hikaricp.connections.min",
    "hikaricp.connections.pending",
    "hikaricp.connections.timeout",
    "hikaricp.connections.usage",
}
NON_DIRECT_ROWS = {"hikaricp.connections.active", "hikaricp.connections.idle"}

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


def names_in(pairs, scope):
    return {name for s, name in pairs if s == scope}


def main():
    above_all_p, above_mode_p, below_all_p, below_mode_p, debug_p = sys.argv[1:6]

    above_all = load_pairs(above_all_p)
    above_mode = load_pairs(above_mode_p)
    below_all = load_pairs(below_all_p)
    below_mode = load_pairs(below_mode_p)

    aa_bridge = names_in(above_all, BRIDGE_SCOPE)
    am_bridge = names_in(above_mode, BRIDGE_SCOPE)
    ba_bridge = names_in(below_all, BRIDGE_SCOPE)
    bm_bridge = names_in(below_mode, BRIDGE_SCOPE)

    aa_agent = names_in(above_all, AGENT_HIKARI_SCOPE)
    am_agent = names_in(above_mode, AGENT_HIKARI_SCOPE)
    ba_agent = names_in(below_all, AGENT_HIKARI_SCOPE)
    bm_agent = names_in(below_mode, AGENT_HIKARI_SCOPE)

    print("bridged hikaricp.* / agent db.client.* per run:")
    for label, bridge, agent in (
        ("above-all ", aa_bridge, aa_agent),
        ("above-mode", am_bridge, am_agent),
        ("below-all ", ba_bridge, ba_agent),
        ("below-mode", bm_bridge, bm_agent),
    ):
        hik = sorted(n for n in bridge if n.startswith("hikaricp."))
        print(f"  {label}  bridge={len(hik):2d}  agent={len(agent):2d}  {hik}")
    print()

    # --- setup: compare like with like. Two of the nine hikaricp rows are a Timer and a Counter
    # that never record in this app (no connection-creation timing, no acquisition timeout), so they
    # are absent from every capture; the experiment is over the rows Micrometer actually emitted, and
    # both sides must emit the same ones or the runs are not comparable.
    emitted_direct = (aa_bridge & DIRECT_ROWS) | (ba_bridge & DIRECT_ROWS)
    check(
        bool(emitted_direct),
        "SETUP",
        f"Micrometer emitted {len(emitted_direct)} of the {len(DIRECT_ROWS)} direct rows: {sorted(emitted_direct)}",
    )
    check(
        (aa_bridge & DIRECT_ROWS) == (ba_bridge & DIRECT_ROWS),
        "SETUP",
        "both HikariCP versions produce the same Micrometer rows, so the runs are comparable",
    )

    # --- 1. above the floor, the agent instruments HikariCP and the mode is a clean swap ----------
    check(bool(aa_agent), "ABOVE", f"agent emits its own pool metrics ({len(aa_agent)} names)")
    for name in sorted(emitted_direct):
        check(name not in am_bridge, "ABOVE-DROP", f"{name} dropped by the mode")
    check(
        bool(am_agent),
        "ABOVE-KEEP",
        f"the agent copy survives the mode ({len(am_agent)} names) -- no signal lost",
    )

    # --- 2. below the DECLARED floor. The hypothesis under test is that muzzle declines here; the
    #        assertion is written to record what actually happens either way, because the answer is
    #        the finding. Muzzle checks references, not versions, and hikaricp-3.0's build file says
    #        outright that it cannot assert the inverse of its declared range.
    muzzle_declined = not ba_agent
    check(
        True,
        "BELOW",
        "muzzle DECLINED on HikariCP 2.7.9 -- no agent copy"
        if muzzle_declined
        else f"muzzle ACCEPTED HikariCP 2.7.9 despite the declared [3.0.0,) floor; the agent emits "
        f"{len(ba_agent)} pool metrics from a version outside its declared support range",
    )

    # --- 3. either way, what happens to the Micrometer copy below the floor -----------------------
    for name in sorted(emitted_direct):
        check(name not in bm_bridge, "BELOW-DROP", f"{name} dropped by the mode below the floor")
    lost = sorted(emitted_direct - bm_bridge) if muzzle_declined else []
    check(
        (len(lost) == len(emitted_direct)) if muzzle_declined else bool(bm_agent),
        "BELOW-OUTCOME",
        f"{len(lost)} metrics lost outright (window reached)"
        if muzzle_declined
        else f"the agent copy replaces them ({len(bm_agent)} names) -- the window is NOT reached here",
    )

    # --- 3b. the .max companions follow their suppressed bases, as Layer B implies -----------------
    companions_all = {
        n
        for n in aa_bridge
        if n.endswith(".max") and n.startswith("hikaricp.") and n not in DIRECT_ROWS
    }
    check(
        bool(companions_all),
        "COMPANION-SETUP",
        f"mode=all emits {len(companions_all)} hikaricp .max companions: {sorted(companions_all)}",
    )
    check(
        not (companions_all & am_bridge),
        "COMPANION",
        f"all of them gone under the mode (left behind: {sorted(companions_all & am_bridge) or 'none'})",
    )

    # --- 4. the non-direct rows are the control: untouched in every run ---------------------------
    for name in sorted(NON_DIRECT_ROWS):
        if name in ba_bridge:
            check(
                name in bm_bridge,
                "CONTROL",
                f"{name} is classified partial -> survives the mode on both sides",
            )

    # --- 5. probe 2: a semconv-named user metric with no library behind it ------------------------
    # Rule 2 keys on the bridged name. `http.client.request.duration` is one of the agent's own
    # names, gated `default` over 37 HTTP client instrumentations, none of which this application
    # contains -- there is no HTTP client on the class path at all. If the mode drops it, the user
    # loses a metric nothing replaces, and no version skew was required to get there.
    collide = "http.client.request.duration"
    check(
        collide in aa_bridge,
        "RULE2-SETUP",
        f"{collide} is bridged under mode=all (found: {collide in aa_bridge})",
    )
    check(
        collide not in am_bridge,
        "RULE2-DROP",
        f"{collide} dropped by the mode -- rule 2 fired on an enabled-but-absent instrumentation",
    )
    http_agent_scopes = sorted(
        {s for s, n in above_mode if n == collide and s != BRIDGE_SCOPE}
    )
    check(
        not http_agent_scopes,
        "RULE2-LOSS",
        f"and no agent scope emits it ({http_agent_scopes or 'none'}) -- lost outright, no muzzle "
        "window needed",
    )

    # --- 6. the muzzle decision itself, from the agent's own log ----------------------------------
    mismatch_lines = []
    try:
        with open(debug_p, errors="replace") as handle:
            for line in handle:
                if "mismatched references" in line:
                    mismatch_lines.append(line.strip())
    except OSError:
        pass
    check(
        True,
        "MUZZLE-LOG",
        f"agent logged {len(mismatch_lines)} muzzle mismatch line(s) for this app"
        + (" -- none of them hikaricp" if not any("hikaricp" in l for l in mismatch_lines) else ""),
    )
    if mismatch_lines:
        print("  muzzle log:", mismatch_lines[0][:200], "\n")

    failures = [r for r in results if not r[0]]
    for ok, label, detail in results:
        print(f"  {'PASS' if ok else 'FAIL'}  [{label}] {detail}")
    print(f"\n{len(results) - len(failures)}/{len(results)} assertions passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
