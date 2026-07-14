#!/usr/bin/env python3
"""Build a self-contained HTML explorer for the Micrometer vs OTel metric comparison.

Reads the machine-readable join (inventory/comparison.json), enriches each row with its
concept-map rationale (tools/concept_map.yaml) and per-bucket caveats (compare.BUCKET_NOTES),
inlines it all into one static HTML file, and writes output/explorer.html.

The output has NO external dependencies and needs NO server — open it directly in a browser
(file://). Regenerate after re-running compare.py:

    python3 tools/compare.py          # refresh inventory/comparison.json
    python3 tools/build_explorer.py   # -> output/explorer.html
"""

import json
from pathlib import Path

from compare import BUCKET_NOTES  # reuse the same caveats the markdown report uses

import yaml

REPO = Path(__file__).resolve().parent.parent


def md_inline(s):
    """Minimal markdown -> HTML for the note strings: `code` and **bold**. Escapes the rest."""
    import html
    import re

    s = html.escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def load_concept_notes():
    """Map (otel_name, micrometer_name) -> note from the curated concept map."""
    data = yaml.safe_load(open(REPO / "tools" / "concept_map.yaml")) or {}
    notes = {}
    for p in data.get("pairs", []):
        note = (p.get("note") or "").strip()
        if note:
            notes[(p["otel"], p["micrometer"])] = note
    return notes


def build():
    comparison = json.load(open(REPO / "inventory" / "comparison.json"))
    concept_notes = load_concept_notes()

    # Flatten buckets into a single row list, attaching bucket + per-pair note.
    rows = []
    for bucket, brows in comparison["buckets"].items():
        for r in brows:
            note = concept_notes.get((r.get("otel"), r.get("micrometer")), "")
            rows.append({**r, "bucket": bucket, "note": note})

    bucket_notes_html = {b: md_inline(n) for b, n in BUCKET_NOTES.items()}

    payload = {
        "meta": {
            "otelVersion": comparison.get("otelVersion"),
            "otelCommit": comparison.get("otelCommit"),
            "micrometerVersions": comparison.get("micrometerVersions"),
            "capturedTechnologies": comparison.get("capturedTechnologies"),
        },
        "rows": rows,
        "bucketNotes": bucket_notes_html,
    }

    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
    out = REPO / "output" / "explorer.html"
    out.write_text(html)
    print(f"wrote {out}  ({len(rows)} rows, {len(comparison['buckets'])} buckets)")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Micrometer vs OTel — metric explorer</title>
<style>
  :root {
    --bg: #0f1419; --panel: #1a2029; --panel2: #232b36; --border: #2e3742;
    --fg: #e6e9ed; --muted: #8b97a6; --accent: #4a9eff;
    --direct: #2ea043; --semantic: #d29922; --partial: #58a6ff;
    --gap-otel: #db6d28; --gap-mm: #a371f7;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  header { padding: 16px 20px; border-bottom: 1px solid var(--border); background: var(--panel); }
  h1 { margin: 0 0 4px; font-size: 18px; }
  .prov { color: var(--muted); font-size: 12px; }
  .prov code { color: var(--fg); background: var(--panel2); padding: 1px 5px; border-radius: 4px; }
  main { padding: 16px 20px; max-width: 1400px; }
  .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 14px; }
  input[type=search] {
    background: var(--panel2); border: 1px solid var(--border); color: var(--fg);
    padding: 7px 10px; border-radius: 6px; font-size: 14px; min-width: 240px;
  }
  select, button {
    background: var(--panel2); border: 1px solid var(--border); color: var(--fg);
    padding: 7px 10px; border-radius: 6px; font-size: 13px; cursor: pointer;
  }
  button:hover, select:hover { border-color: var(--accent); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    padding: 4px 9px; border-radius: 14px; font-size: 12px; cursor: pointer;
    border: 1px solid var(--border); background: var(--panel2); color: var(--muted);
    user-select: none;
  }
  .chip.on { color: #fff; border-color: transparent; }
  .chip.on.direct { background: var(--direct); }
  .chip.on.semantic { background: var(--semantic); color: #1a1a1a; }
  .chip.on.partial { background: var(--partial); color: #08121f; }
  .chip[data-k="gap-otel-only"].on { background: var(--gap-otel); }
  .chip[data-k="gap-mm-only"].on { background: var(--gap-mm); }
  .count { color: var(--muted); font-size: 13px; margin-left: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { position: sticky; top: 0; background: var(--panel); cursor: pointer; white-space: nowrap; user-select: none; }
  th:hover { color: var(--accent); }
  tbody tr:hover { background: var(--panel); }
  td code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
  .badge.direct { background: var(--direct); color: #fff; }
  .badge.semantic { background: var(--semantic); color: #1a1a1a; }
  .badge.partial { background: var(--partial); color: #08121f; }
  .badge.gap-otel-only { background: var(--gap-otel); color: #fff; }
  .badge.gap-mm-only { background: var(--gap-mm); color: #fff; }
  .dim { color: var(--muted); }
  .note { color: var(--muted); font-size: 12px; max-width: 360px; }
  .bnote {
    background: var(--panel2); border-left: 3px solid var(--accent); padding: 8px 12px;
    margin: 8px 0 14px; border-radius: 0 6px 6px 0; font-size: 13px; color: var(--fg);
  }
  .bnote code { color: var(--accent); }
  .summary { margin-bottom: 18px; overflow-x: auto; }
  .summary td.n { text-align: right; font-variant-numeric: tabular-nums; cursor: pointer; }
  .summary td.n:hover { color: var(--accent); text-decoration: underline; }
  .summary tr.active td:first-child { color: var(--accent); font-weight: 600; }
  .empty { padding: 30px; text-align: center; color: var(--muted); }
</style>
</head>
<body>
<header>
  <h1>Micrometer vs OpenTelemetry Java agent — metric explorer</h1>
  <div class="prov" id="prov"></div>
</header>
<main>
  <div class="summary" id="summary"></div>

  <div class="controls">
    <input type="search" id="q" placeholder="search metric name (otel or micrometer)…" autofocus>
    <div class="chips" id="classChips"></div>
    <select id="bucket"><option value="">all technologies</option></select>
    <button id="kafka">hide Kafka (254)</button>
    <button id="reset">reset</button>
    <span class="count" id="count"></span>
  </div>

  <div id="bnote"></div>

  <table id="tbl">
    <thead><tr>
      <th data-s="bucket">technology</th>
      <th data-s="otel">OTel metric</th>
      <th data-s="micrometer">Micrometer metric</th>
      <th data-s="class">class</th>
      <th data-s="otelType">OTel instr / unit</th>
      <th data-s="mmType">MM instr / unit</th>
      <th data-s="note">note</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <div class="empty" id="empty" hidden>no rows match the current filters</div>
</main>

<script>
const DATA = __DATA__;
const CLASSES = ["direct","semantic","partial","gap-otel-only","gap-mm-only"];
const state = { q: "", classes: new Set(CLASSES), bucket: "", hideKafka: false, sort: "bucket", dir: 1 };

const $ = s => document.querySelector(s);
const dash = "—";
const esc = s => (s==null?"":String(s)).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const cell = v => (v && v !== dash && v !== "None") ? `<code>${esc(v)}</code>` : `<span class="dim">${dash}</span>`;

// provenance
$("#prov").innerHTML =
  `OTel registry <code>${esc(DATA.meta.otelVersion)}</code> @ <code>${esc(DATA.meta.otelCommit)}</code>` +
  ` &nbsp;·&nbsp; Micrometer <code>${esc((DATA.meta.micrometerVersions||[]).join(", "))}</code>` +
  ` &nbsp;·&nbsp; ${DATA.rows.length} metric pairs across ${new Set(DATA.rows.map(r=>r.bucket)).size} technologies`;

// class filter chips
const chipBox = $("#classChips");
CLASSES.forEach(k => {
  const c = document.createElement("span");
  c.className = `chip on ${k}`;
  c.dataset.k = k;
  c.textContent = k;
  c.onclick = () => { state.classes.has(k) ? state.classes.delete(k) : state.classes.add(k);
                      c.classList.toggle("on"); render(); };
  chipBox.appendChild(c);
});

// bucket dropdown
[...new Set(DATA.rows.map(r=>r.bucket))].sort().forEach(b => {
  const o = document.createElement("option"); o.value = b; o.textContent = b; $("#bucket").appendChild(o);
});

$("#q").oninput = e => { state.q = e.target.value.toLowerCase().trim(); render(); };
$("#bucket").onchange = e => { state.bucket = e.target.value; render(); };
$("#kafka").onclick = () => { state.hideKafka = !state.hideKafka;
  $("#kafka").textContent = state.hideKafka ? "show Kafka (254)" : "hide Kafka (254)"; render(); };
$("#reset").onclick = () => {
  state.q=""; state.bucket=""; state.hideKafka=false; state.classes=new Set(CLASSES); state.sort="bucket"; state.dir=1;
  $("#q").value=""; $("#bucket").value=""; $("#kafka").textContent="hide Kafka (254)";
  chipBox.querySelectorAll(".chip").forEach(c=>c.classList.add("on")); render();
};
document.querySelectorAll("th[data-s]").forEach(th => th.onclick = () => {
  const s = th.dataset.s; state.dir = (state.sort === s) ? -state.dir : 1; state.sort = s; render();
});

function filtered() {
  return DATA.rows.filter(r => {
    if (state.hideKafka && r.bucket === "kafka") return false;
    if (state.bucket && r.bucket !== state.bucket) return false;
    if (!state.classes.has(r.class)) return false;
    if (state.q) {
      const hay = (r.otel + " " + r.micrometer + " " + r.note).toLowerCase();
      if (!hay.includes(state.q)) return false;
    }
    return true;
  });
}

function renderSummary() {
  const buckets = [...new Set(DATA.rows.map(r=>r.bucket))].sort();
  let h = `<table><thead><tr><th>technology</th>` +
          CLASSES.map(c=>`<th class="n" style="text-align:right">${c.replace('gap-','').replace('-only','')}</th>`).join("") +
          `<th class="n" style="text-align:right">total</th></tr></thead><tbody>`;
  for (const b of buckets) {
    const rs = DATA.rows.filter(r=>r.bucket===b);
    const active = state.bucket===b ? " class=active" : "";
    h += `<tr${active}><td style="cursor:pointer" onclick="pickBucket('${b}')">${b}</td>`;
    for (const c of CLASSES) {
      const n = rs.filter(r=>r.class===c).length;
      h += `<td class="n" ${n?`onclick="pickBucketClass('${b}','${c}')"`:""}>${n||'<span class=dim>·</span>'}</td>`;
    }
    h += `<td class="n">${rs.length}</td></tr>`;
  }
  const tot = c => DATA.rows.filter(r=>r.class===c).length;
  h += `<tr style="font-weight:600;border-top:2px solid var(--border)"><td>all</td>` +
       CLASSES.map(c=>`<td class="n">${tot(c)}</td>`).join("") +
       `<td class="n">${DATA.rows.length}</td></tr>`;
  h += `</tbody></table>`;
  $("#summary").innerHTML = h;
}

window.pickBucket = b => { state.bucket = b===state.bucket?"":b; $("#bucket").value=state.bucket; render(); };
window.pickBucketClass = (b,c) => {
  state.bucket = b; $("#bucket").value=b;
  state.classes = new Set([c]);
  chipBox.querySelectorAll(".chip").forEach(ch=>ch.classList.toggle("on", ch.dataset.k===c));
  render();
};

function render() {
  renderSummary();
  let rows = filtered();
  const s = state.sort, d = state.dir;
  rows.sort((a,b) => {
    const av=(a[s]||"").toString(), bv=(b[s]||"").toString();
    return av<bv ? -d : av>bv ? d : 0;
  });

  // bucket note (only when a single bucket with a caveat is in focus)
  const bn = state.bucket && DATA.bucketNotes[state.bucket];
  $("#bnote").innerHTML = bn ? `<div class="bnote">${bn}</div>` : "";

  $("#rows").innerHTML = rows.map(r => `
    <tr>
      <td>${esc(r.bucket)}</td>
      <td>${cell(r.otel)}</td>
      <td>${cell(r.micrometer)}</td>
      <td><span class="badge ${r.class}">${r.class.replace('gap-','gap: ').replace('-only','')}</span></td>
      <td>${cell(r.otelType)} ${r.otelUnit && r.otelUnit!==dash?`<span class=dim>/</span> ${cell(r.otelUnit)}`:''}</td>
      <td>${cell(r.mmType)} ${r.mmUnit && r.mmUnit!=='None'?`<span class=dim>/</span> ${cell(r.mmUnit)}`:''}</td>
      <td class="note">${esc(r.note)}</td>
    </tr>`).join("");
  $("#empty").hidden = rows.length > 0;
  $("#count").textContent = `${rows.length} of ${DATA.rows.length} rows`;
}

render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
