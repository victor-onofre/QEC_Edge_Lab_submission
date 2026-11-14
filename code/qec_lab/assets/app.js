const ui = new WebUI();
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

// error-rate series: [label, css class, getter(row) -> {fails, n} | null, dashed]
const ERR = [
  { label: "majority (all shots)", cls: "maj", get: (r) => ({ p: r.maj_full, n: r.n_total }), dashed: true },
  { label: "UF fast", cls: "uf", get: (r) => ({ p: r.err.uf_fast, n: r.n_decoded }) },
  { label: "UF weighted", cls: "ufw", get: (r) => ({ p: r.err.uf_weighted, n: r.n_decoded }) },
  { label: "PyMatching weighted", cls: "pm", get: (r) => (r.pm && r.pm.pm_weighted !== undefined ? { p: r.pm.pm_weighted, n: r.n_total } : null), dashed: true },
];
const CYC = [
  { key: "majority", label: "majority + detectors", cls: "maj" },
  { key: "greedy", label: "greedy", cls: "gre" },
  { key: "uf_naive", label: "UF naive", cls: "naive" },
  { key: "uf_fast", label: "UF fast", cls: "uf" },
  { key: "uf_weighted", label: "UF weighted", cls: "ufw" },
];
let mode = "sim";
let rows = [];
let runs = [];
let busy = false;

// ================= connection =================
ui.on_connect(() => { setPill("conn", "connected", "ok"); ui.send_message("hello", {}); });
ui.on_disconnect(() => setPill("conn", "offline", "bad"));

ui.on_message("status", (s) => {
  const ph = s.phase || "-";
  busy = !(ph === "idle" || ph === "done" || ph.startsWith("error"));
  setPill("phase", ph, ph.startsWith("error") ? "bad" : busy ? "busy" : "ok");
  setPill("backend", s.backend || "-", (s.mode || "").includes("noise") ? "sim" : "hw");
  setPill("timer", s.timer || "-", "muted");
  ["runBtn", "redecodeBtn", "importBtn"].forEach((id) => ($(id).disabled = busy));
});
ui.on_message("defaults", (d) => {
  $("dists").value = d.distances.join(",");
  $("rounds").value = d.rounds; $("shots").value = d.shots; $("dshots").value = d.decode_shots;
  $("p").value = d.p; $("q").value = d.q; updateSliders(); estimate();
});
ui.on_message("runs", (r) => { runs = r || []; drawRuns(); });
ui.on_message("history", (h) => { rows = h || []; renderAll(); });
ui.on_message("clear", () => { rows = []; renderAll(); });
ui.on_message("result", (r) => { rows.push(r); renderAll(); });

// ================= controls =================
function setMode(m) {
  mode = m;
  $("segSim").classList.toggle("active", m === "sim");
  $("segHw").classList.toggle("active", m === "hw");
  $("simOnly").style.display = m === "sim" ? "" : "none";
  estimate();
}
$("segSim").onclick = () => setMode("sim");
$("segHw").onclick = () => setMode("hw");
["dists", "rounds", "shots", "dshots"].forEach((id) => $(id).addEventListener("input", estimate));
["p", "q"].forEach((id) => $(id).addEventListener("input", updateSliders));
function updateSliders() {
  $("pVal").textContent = (Number($("p").value) * 100).toFixed(1) + "%";
  $("qVal").textContent = (Number($("q").value) * 100).toFixed(1) + "%";
}
function params() {
  return {
    kind: "run", mode,
    distances: $("dists").value.split(/[ ,;]+/).map(Number).filter((d) => d >= 3 && d <= 25),
    rounds: Number($("rounds").value), shots: Number($("shots").value),
    decode_shots: Number($("dshots").value), p: Number($("p").value), q: Number($("q").value),
  };
}
function estimate() {
  const p = params();
  const maxd = Math.max(...p.distances, 3);
  $("estimate").textContent = mode === "hw"
    ? `${p.distances.length * 2} circuits · ≤ ${2 * maxd - 1} qubits · ≈ ${Math.ceil(p.distances.length * 2 * p.shots * 0.0004)} s QPU`
    : `${p.distances.length} distances · ${p.decode_shots} shots each on the MCU`;
}
$("runBtn").onclick = () => {
  const p = params();
  if (!p.distances.length) { alert("Enter at least one distance between 3 and 25."); return; }
  if (mode === "hw" && !confirm(`Run ${p.distances.length * 2} circuits on IBM hardware?\nThis uses part of your monthly quota.`)) return;
  ui.send_message("run", p);
};
$("redecodeBtn").onclick = () => {
  const name = $("runSel").value;
  if (!name) { alert("Select a saved run first."); return; }
  ui.send_message("run", { kind: "redecode", name, decode_shots: Number($("dshots").value) });
};
$("importBtn").onclick = () => {
  const id = $("jobId").value.trim();
  if (!id) { alert("Paste an IBM job ID."); return; }
  ui.send_message("run", { kind: "import", job_id: id, decode_shots: Number($("dshots").value) });
};
$("runSel").onchange = () => {
  const r = runs.find((x) => x.name === $("runSel").value);
  $("runInfo").textContent = r ? `${r.backend} · ${r.rounds} rounds · d=${r.distances.join(",")}` : "";
};

function drawRuns() {
  const sel = $("runSel");
  const keep = sel.value;
  sel.innerHTML = "";
  if (!runs.length) { sel.insertAdjacentHTML("beforeend", `<option disabled>no saved runs yet</option>`); return; }
  runs.forEach((r) => {
    const o = document.createElement("option");
    o.value = r.name;
    o.textContent = `${r.created.replace(/^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d).*/, "$1-$2-$3 $4:$5")} · ${r.backend} · r${r.rounds}`;
    sel.appendChild(o);
  });
  if (keep) sel.value = keep;
}

function setPill(id, text, cls = "") {
  const el = $(id);
  el.className = "pill " + cls;
  el.querySelector("b").textContent = text;
  el.title = text;
}

// ================= svg helpers =================
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function text(parent, x, y, s, cls, anchor = "middle") {
  const t = el("text", { x, y, class: cls, "text-anchor": anchor }, parent);
  t.textContent = s;
  return t;
}
const fmtSci = (v) => (v >= 0.01 ? (v * 100).toFixed(1) + "%" : v.toExponential(1));
const fmtCyc = (v) => (v >= 10000 ? (v / 1000).toFixed(0) + "k" : v >= 1000 ? (v / 1000).toFixed(1) + "k" : Math.round(v));

function axesLog(svg, W, H, dists, yMin, yMax, yFmt) {
  const L = 58, R = 16, T = 14, B = 34;
  const dMin = Math.min(...dists), dMax = Math.max(...dists);
  const X = (d) => (dMax === dMin ? (L + W - R) / 2 : L + ((d - dMin) / (dMax - dMin)) * (W - L - R));
  const ly0 = Math.log10(yMin), ly1 = Math.log10(yMax);
  const Y = (v) => H - B - ((Math.log10(Math.max(v, yMin)) - ly0) / (ly1 - ly0)) * (H - B - T);
  for (let e = Math.ceil(ly0); e <= Math.floor(ly1); e++) {
    el("line", { x1: L, y1: Y(10 ** e), x2: W - R, y2: Y(10 ** e), class: "c-grid" }, svg);
    text(svg, L - 8, Y(10 ** e) + 4, yFmt(10 ** e), "c-tick", "end");
  }
  dists.forEach((d) => text(svg, X(d), H - B + 18, "d=" + d, "c-tick"));
  el("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, class: "c-axis" }, svg);
  return { X, Y, L, R };
}
function legend(id, items) {
  $(id).innerHTML = items.map((s) => `<span class="dot ${s.cls}"></span>${s.label}`).join(" ");
}

// ================= charts =================
function drawErr() {
  const svg = $("errChart");
  svg.innerHTML = "";
  const series = ERR.filter((s) => rows.some((r) => s.get(r)));
  legend("errLegend", series);
  if (!rows.length) { text(svg, 360, 135, "Waiting for results…", "c-empty"); return; }
  const pts = rows.flatMap((r) => series.map((s) => s.get(r)).filter(Boolean));
  const floor = Math.min(...pts.map((v) => 0.5 / Math.max(1, v.n)));
  const yMax = Math.min(1, 10 ** Math.ceil(Math.log10(Math.max(...pts.map((v) => v.p), floor * 10))));
  const yMin = 10 ** Math.floor(Math.log10(floor));
  const ax = axesLog(svg, 720, 270, rows.map((r) => r.d), yMin, yMax, fmtSci);
  series.forEach((s, si) => {
    const off = (si - (series.length - 1) / 2) * 4;
    let d = "";
    rows.forEach((r, i) => {
      const v = s.get(r); if (!v) return;
      const y = v.p > 0 ? v.p : 0.5 / v.n;
      d += (d ? "L" : "M") + (ax.X(r.d) + off).toFixed(1) + "," + ax.Y(y).toFixed(1);
    });
    el("path", { d, class: "c-line " + s.cls + (s.dashed ? " dashed" : "") }, svg);
    rows.forEach((r) => {
      const v = s.get(r); if (!v) return;
      const zero = v.p === 0;
      if (!zero) {
        const sd = Math.sqrt(v.p * (1 - v.p) / v.n);
        el("line", { x1: ax.X(r.d) + off, x2: ax.X(r.d) + off, y1: ax.Y(Math.max(v.p - sd, yMin)), y2: ax.Y(v.p + sd), class: "c-err " + s.cls }, svg);
      }
      const c = el("circle", { cx: ax.X(r.d) + off, cy: ax.Y(zero ? 0.5 / v.n : v.p), r: 4.5, class: "c-pt " + s.cls + (zero ? " hollow" : "") }, svg);
      el("title", {}, c).textContent = `${s.label}, d=${r.d}: ${zero ? "0" : fmtSci(v.p)} (n=${v.n})`;
    });
  });
}

function drawCyc() {
  const svg = $("cycChart");
  svg.innerHTML = "";
  legend("cycLegend", [...CYC, { cls: "budget", label: "budget (1 µs / round)" }]);
  if (!rows.length) { text(svg, 550, 130, "Waiting for results…", "c-empty"); return; }
  const budget = rows[0].cpu_mhz * rows[0].rounds;
  const vals = rows.flatMap((r) => CYC.map((k) => r.cycles[k.key].avg)).filter((v) => v > 0);
  const yMin = 10 ** Math.floor(Math.log10(Math.max(1, Math.min(...vals, budget) / 2)));
  const yMax = 10 ** Math.ceil(Math.log10(Math.max(...vals, budget) * 1.5));
  const ax = axesLog(svg, 1100, 260, rows.map((r) => r.d), yMin, yMax, fmtCyc);
  el("line", { x1: ax.L, y1: ax.Y(budget), x2: 1100 - ax.R, y2: ax.Y(budget), class: "c-budget" }, svg);
  text(svg, 1100 - ax.R - 4, ax.Y(budget) - 6, `real-time budget ${Math.round(budget)} cycles`, "c-tick budget", "end");
  CYC.forEach((k) => {
    let d = "";
    rows.forEach((r, i) => { d += (i ? "L" : "M") + ax.X(r.d).toFixed(1) + "," + ax.Y(Math.max(r.cycles[k.key].avg, yMin)).toFixed(1); });
    el("path", { d, class: "c-line " + k.cls }, svg);
    rows.forEach((r) => {
      const c = el("circle", { cx: ax.X(r.d), cy: ax.Y(Math.max(r.cycles[k.key].avg, yMin)), r: 4, class: "c-pt " + k.cls }, svg);
      el("title", {}, c).textContent = `${k.label}, d=${r.d}: avg ${Math.round(r.cycles[k.key].avg)} cycles (${(r.cycles[k.key].avg / r.cpu_mhz).toFixed(1)} µs), max ${Math.round(r.cycles[k.key].max)}`;
    });
  });
}

// ================= KPIs + table =================
function drawKpis() {
  if (!rows.length) return;
  const last = rows[rows.length - 1];
  const avg = (k) => rows.reduce((a, r) => a + r[k], 0) / rows.length;
  if (last.p_data0 !== undefined) {
    $("kPd").textContent = `${(avg("p_data0") * 100).toFixed(1)}% / ${(avg("p_data1") * 100).toFixed(1)}%`;
    $("kPm").textContent = `|0⟩ / |1⟩ data error per round (|1⟩ ×${(avg("p_data1") / Math.max(1e-6, avg("p_data0"))).toFixed(1)}, T1 decay) · measurement ${(avg("p_meas") * 100).toFixed(1)}%`;
  } else {
    $("kPd").textContent = (avg("p_data") * 100).toFixed(2) + "%";
    $("kPm").textContent = `measurement error ${(avg("p_meas") * 100).toFixed(2)}% (estimated from the syndromes)`;
  }
  const sp = rows.map((r) => r.cycles.uf_naive.avg / Math.max(1, r.cycles.uf_fast.avg));
  $("kSpeed").textContent = `×${Math.min(...sp).toFixed(1)}–${Math.max(...sp).toFixed(1)}`;
  const fu = rows.reduce((a, r) => a + r.fails.uf_fast, 0), fw = rows.reduce((a, r) => a + r.fails.uf_weighted, 0);
  $("kWeight").textContent = fu ? `${fw} vs ${fu}` : "–";
  const inB = rows.filter((r) => r.cycles.uf_fast.avg <= r.cpu_mhz * r.rounds);
  $("kBudget").textContent = inB.length ? "d=" + Math.max(...inB.map((r) => r.d)) : "none";
  const big = rows[rows.length - 1];
  $("kBudgetSub").textContent = `fast UF at d=${big.d}: ${(big.cycles.uf_fast.avg / big.cpu_mhz).toFixed(1)} µs vs ${big.rounds} µs budget`;
  $("kpiHint").textContent = `${last.mode === "hw" ? last.backend : "noise model"} · ${last.rounds} rounds`;
}

function drawTable() {
  const tb = $("tbody");
  if (!rows.length) { tb.innerHTML = `<tr><td colspan="14" class="empty">Run an experiment or re-decode a saved run</td></tr>`; $("tableHint").textContent = "no runs yet"; return; }
  tb.innerHTML = "";
  const e = (p, n, f) => `${p === 0 ? "0" : fmtSci(p)}${f !== undefined ? ` <span class="hint">(${f})</span>` : ""}`;
  rows.forEach((r) => {
    const budget = r.cpu_mhz * r.rounds;
    const ok = r.cycles.uf_fast.avg <= budget;
    const pm = r.pm && r.pm.pm_weighted !== undefined ? e(r.pm.pm_weighted) : `<span class="hint">laptop tool</span>`;
    const checks = r.transport_mismatch || r.uf_disagree
      ? `<span class="badge bad">${r.transport_mismatch} / ${r.uf_disagree}</span>` : `<span class="badge ok">ok</span>`;
    tb.insertAdjacentHTML("beforeend",
      `<tr><td><b>${r.d}</b></td><td>${r.qubits}</td><td>${r.p_data0 !== undefined ? `${(r.p_data0 * 100).toFixed(2)}% <span class="hint">/</span> ${(r.p_data1 * 100).toFixed(2)}%` : (r.p_data * 100).toFixed(2) + "%"}</td><td>${(r.p_meas * 100).toFixed(2)}%</td>` +
      `<td>${r.defects_per_shot.toFixed(2)}</td>` +
      `<td class="majtxt">${e(r.maj_full)}</td><td class="uftxt">${e(r.err.uf_fast, r.n_decoded, r.fails.uf_fast)}</td>` +
      `<td class="ufwtxt">${e(r.err.uf_weighted, r.n_decoded, r.fails.uf_weighted)}</td><td class="pmtxt">${pm}</td>` +
      `<td>${fmtCyc(r.cycles.uf_naive.avg)}</td><td>${fmtCyc(r.cycles.uf_fast.avg)} <span class="hint">/ ${fmtCyc(r.cycles.uf_fast.max)}</span></td>` +
      `<td>${fmtCyc(r.cycles.uf_weighted.avg)}</td>` +
      `<td><span class="badge ${ok ? "ok" : "bad"}">${ok ? "in" : "×" + (r.cycles.uf_fast.avg / budget).toFixed(0)}</span></td><td>${checks}</td></tr>`);
  });
  const last = rows[rows.length - 1];
  $("tableHint").textContent = `${last.mode === "hw" ? "IBM " + last.backend : "noise model"} · ${last.rounds} rounds · ${last.n_decoded} shots on MCU, ${last.n_total} on Linux · ${last.bridge_ms_per_shot.toFixed(1)} ms/shot over Bridge`;
  $("layoutNote").textContent = "* = all shots, decoded on the Linux side. Checks = transport mismatches / naive-vs-fast UF disagreements." +
    (last.mode === "hw" ? ` Job ${last.job_id}${last.line && last.line.length ? " · qubits " + last.line.join("–") : ""}.` : "");
}

function renderAll() { drawErr(); drawCyc(); drawKpis(); drawTable(); }

updateSliders(); estimate(); drawRuns(); renderAll();

// =====================================================================================
// Stage 2 · real-time replay
// =====================================================================================
const RTDEC = {
  uf_fast: { label: "UF fast", cls: "uf" }, uf_weighted: { label: "UF weighted", cls: "ufw" },
  uf_naive: { label: "UF naive", cls: "naive" }, majority: { label: "majority", cls: "maj" }, greedy: { label: "greedy", cls: "gre" },
};
let rtPoints = [];
let rtLoaded = null;
let liveData = [];
let liveRunning = false;

// ---- tabs ----
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
  ["tabAcc", "tabRt"].forEach((id) => ($(id).hidden = id !== b.dataset.tab));
  if (b.dataset.tab === "tabRt") renderRt();
}));

// ---- formatting ----
const fmtNs = (ns) => (ns >= 1e9 ? (ns / 1e9).toFixed(2) + " s" : ns >= 1e6 ? (ns / 1e6).toFixed(ns >= 1e7 ? 0 : 2) + " ms" : ns >= 1e3 ? (ns / 1e3).toFixed(ns >= 1e4 ? 0 : 2) + " µs" : Math.round(ns) + " ns");
const tauFromSlider = (v) => Math.round(20 * Math.pow(500000 / 20, v / 100));   // 20 ns .. 500 µs, log scale

// ---- messages ----
ui.on_message("runs", (r) => fillRtSource(r || []));
ui.on_message("status", (s) => {
  const ph = s.phase || "";
  const b = !(ph === "idle" || ph === "done" || ph.startsWith("error"));
  ["rtLoadBtn", "rtSweepBtn"].forEach((id) => ($(id).disabled = b));
  $("rtLiveBtn").disabled = b;
  if (!ph.startsWith("live") && liveRunning && !b) { liveRunning = false; $("lvVerdict").textContent = "stopped"; $("lvVerdict").className = "verdict"; }
});
ui.on_message("rt_loaded", (L) => { rtLoaded = L; showLoaded(); });
ui.on_message("rt_sweep_start", () => { rtPoints = []; renderRt(); });
ui.on_message("rt_point", (p) => { rtPoints.push(p); renderRt(); });
ui.on_message("rt_live", (w) => {
  liveRunning = true;
  liveData.push({ ...w, t: Date.now() });
  if (liveData.length > 120) liveData.shift();
  const period = w.tau_ns * w.rounds;
  $("lvTau").textContent = fmtNs(w.tau_ns);
  $("lvBack").textContent = w.max_backlog.toLocaleString();
  $("lvLat").textContent = fmtNs(w.mean_ns);
  const ok = w.max_backlog <= 8;
  $("lvVerdict").textContent = ok ? `keeping up · shot every ${fmtNs(period)}` : `FALLING BEHIND · ${w.max_backlog.toLocaleString()} shots waiting`;
  $("lvVerdict").className = "verdict " + (ok ? "ok" : "bad");
  $("rtKnob").textContent = w.knob ? "τ set by the knob" : "τ set by the slider (turn the knob to take over)";
  if (!w.knob) { /* keep slider */ } else { $("rtTauVal").textContent = fmtNs(w.tau_ns); }
  drawLive();
});

// ---- controls ----
function fillRtSource(list) {
  const sel = $("rtSource");
  const keep = sel.value;
  sel.innerHTML = `<option value="noise">noise model (fresh shots)</option>` +
    list.map((r) => `<option value="${r.name}" data-d="${r.distances.join(",")}">${r.created.replace(/^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d).*/, "$1-$2-$3 $4:$5")} · ${r.backend}</option>`).join("");
  if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep;
  else if (list.length) sel.value = list[0].name;
  fillRtD();
}
function fillRtD() {
  const opt = $("rtSource").selectedOptions[0];
  const ds = opt && opt.dataset.d ? opt.dataset.d.split(",").map(Number) : [3, 5, 7, 9, 11, 15, 21, 25];
  const keep = Number($("rtD").value) || 11;
  $("rtD").innerHTML = ds.map((d) => `<option value="${d}">d = ${d} (${2 * d - 1} qubits)</option>`).join("");
  $("rtD").value = ds.includes(keep) ? keep : ds[Math.floor(ds.length / 2)];
}
$("rtSource").addEventListener("change", fillRtD);
$("rtLoadBtn").onclick = () => ui.send_message("run", {
  kind: "rt_load", source: $("rtSource").value, d: Number($("rtD").value), state: $("rtState").value,
  n: Number($("rtN").value), p: Number($("p").value), q: Number($("q").value), rounds: Number($("rounds").value),
});
$("rtSweepBtn").onclick = () => {
  if (!rtLoaded) { alert("Load shots into the MCU first (step 1)."); return; }
  const decs = [...document.querySelectorAll("#rtDecs input:checked")].map((x) => x.value);
  if (!decs.length) { alert("Pick at least one decoder."); return; }
  ui.send_message("run", { kind: "rt_sweep", decoders: decs, tau_min_ns: Number($("rtTmin").value),
    tau_max_ns: Number($("rtTmax").value), points: Number($("rtPts").value), n: Number($("rtSweepN").value) });
};
$("rtTau").addEventListener("input", () => ($("rtTauVal").textContent = fmtNs(tauFromSlider(Number($("rtTau").value)))));
$("rtLiveBtn").onclick = () => {
  if (!rtLoaded) { alert("Load shots into the MCU first (step 1)."); return; }
  liveData = [];
  ui.send_message("run", { kind: "rt_live", decoder: $("rtLiveDec").value, tau_ns: tauFromSlider(Number($("rtTau").value)) });
  $("lvVerdict").textContent = "starting…";
};
$("rtLiveStop").onclick = () => ui.send_message("rt_live_stop", {});

function showLoaded() {
  const L = rtLoaded;
  if (!L) return;
  $("rtLoaded").innerHTML =
    `<b>d = ${L.d}</b> · ${L.rounds} rounds · ${L.state === "both" ? "|0⟩ + |1⟩" : "|" + L.state + "⟩"} · ${L.backend}<br>` +
    `${L.shots.toLocaleString()} shots × ${L.stride} bytes = <b>${L.kb} KB</b> in STM32 RAM · loaded in ${L.load_s} s<br>` +
    `estimated p<sub>data</sub> ${(L.p_data * 100).toFixed(2)}% · p<sub>meas</sub> ${(L.p_meas * 100).toFixed(2)}% · ` +
    `<span class="badge ${L.transport_ok ? "ok" : "bad"}">transport ${L.transport_ok ? "ok" : "MISMATCH"}</span>`;
}

// ---- charts ----
function logAxes(svg, W, H, xMin, xMax, yMin, yMax, xFmt, yFmt) {
  const L = 62, R = 16, T = 14, B = 36;
  const lx0 = Math.log10(xMin), lx1 = Math.log10(xMax), ly0 = Math.log10(yMin), ly1 = Math.log10(yMax);
  const X = (v) => L + ((Math.log10(Math.max(v, xMin)) - lx0) / (lx1 - lx0)) * (W - L - R);
  const Y = (v) => H - B - ((Math.log10(Math.max(v, yMin)) - ly0) / (ly1 - ly0)) * (H - B - T);
  for (let e = Math.ceil(ly0); e <= Math.floor(ly1); e++) {
    el("line", { x1: L, y1: Y(10 ** e), x2: W - R, y2: Y(10 ** e), class: "c-grid" }, svg);
    text(svg, L - 8, Y(10 ** e) + 4, yFmt(10 ** e), "c-tick", "end");
  }
  for (let e = Math.ceil(lx0); e <= Math.floor(lx1); e++) {
    el("line", { x1: X(10 ** e), y1: T, x2: X(10 ** e), y2: H - B, class: "c-grid" }, svg);
    text(svg, X(10 ** e), H - B + 18, xFmt(10 ** e), "c-tick");
  }
  text(svg, (L + W - R) / 2, H - 4, "round time τ", "c-tick");
  el("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, class: "c-axis" }, svg);
  return { X, Y, L, R, T, B, W, H };
}

function limitFor(dec) {   // tau below which the decoder cannot keep up = mean decode time / rounds
  const pts = rtPoints.filter((p) => p.decoder === dec);
  if (!pts.length) return null;
  const slow = pts.reduce((a, p) => (p.tau_ns > a.tau_ns ? p : a), pts[0]);
  return slow.service_ns / slow.rounds;
}

function drawRtCharts() {
  const decs = [...new Set(rtPoints.map((p) => p.decoder))];
  legend("rtLatLegend", decs.map((d) => RTDEC[d]));
  legend("rtBackLegend", decs.map((d) => RTDEC[d]));
  ["rtLatChart", "rtBackChart"].forEach((id) => ($(id).innerHTML = ""));
  if (!rtPoints.length) {
    text($("rtLatChart"), 360, 150, "Run a sweep to see where each decoder stops keeping up", "c-empty");
    text($("rtBackChart"), 360, 150, "…", "c-empty");
    return;
  }
  const taus = rtPoints.map((p) => p.tau_ns);
  const xMin = 10 ** Math.floor(Math.log10(Math.min(...taus))), xMax = 10 ** Math.ceil(Math.log10(Math.max(...taus)));
  // latency
  const lats = rtPoints.flatMap((p) => [p.p50_ns, p.p99_ns]).filter((v) => v > 0);
  const svgL = $("rtLatChart");
  const a = logAxes(svgL, 720, 300, xMin, xMax, 10 ** Math.floor(Math.log10(Math.min(...lats))), 10 ** Math.ceil(Math.log10(Math.max(...lats))), fmtNs, fmtNs);
  // backlog
  const svgB = $("rtBackChart");
  const backs = rtPoints.map((p) => Math.max(1, p.max_backlog));
  const b = logAxes(svgB, 720, 300, xMin, xMax, 1, 10 ** Math.ceil(Math.log10(Math.max(...backs, 10))), fmtNs, (v) => (v >= 1000 ? v / 1000 + "k" : String(v)));
  decs.forEach((dec) => {
    const cls = RTDEC[dec].cls;
    const pts = rtPoints.filter((p) => p.decoder === dec).sort((x, y) => x.tau_ns - y.tau_ns);
    const lim = limitFor(dec);
    [[svgL, a], [svgB, b]].forEach(([svg, ax]) => {
      if (lim) el("line", { x1: ax.X(lim), x2: ax.X(lim), y1: ax.T, y2: ax.H - ax.B, class: "c-limit " + cls }, svg);
    });
    const path = (ax, f) => pts.map((p, i) => (i ? "L" : "M") + ax.X(p.tau_ns).toFixed(1) + "," + ax.Y(f(p)).toFixed(1)).join("");
    el("path", { d: path(a, (p) => p.p99_ns), class: "c-line " + cls }, svgL);
    el("path", { d: path(a, (p) => p.p50_ns), class: "c-line dashed " + cls }, svgL);
    el("path", { d: path(b, (p) => Math.max(1, p.max_backlog)), class: "c-line " + cls }, svgB);
    pts.forEach((p) => {
      const c1 = el("circle", { cx: a.X(p.tau_ns), cy: a.Y(p.p99_ns), r: 4, class: "c-pt " + cls + (p.keeps_up ? "" : " hollow") }, svgL);
      el("title", {}, c1).textContent = `${RTDEC[dec].label} τ=${fmtNs(p.tau_ns)}: p99 ${fmtNs(p.p99_ns)}, median ${fmtNs(p.p50_ns)}`;
      const c2 = el("circle", { cx: b.X(p.tau_ns), cy: b.Y(Math.max(1, p.max_backlog)), r: 4, class: "c-pt " + cls + (p.keeps_up ? "" : " hollow") }, svgB);
      el("title", {}, c2).textContent = `${RTDEC[dec].label} τ=${fmtNs(p.tau_ns)}: max backlog ${p.max_backlog}`;
    });
  });
}

function drawLive() {
  const svg = $("rtLiveChart");
  svg.innerHTML = "";
  const W = 1100, H = 200, L = 62, R = 16, T = 12, B = 24;
  if (!liveData.length) { text(svg, W / 2, H / 2, "Start live mode and turn the knob", "c-empty"); return; }
  const yMax = 10 ** Math.ceil(Math.log10(Math.max(10, ...liveData.map((w) => w.max_backlog + 1))));
  const Y = (v) => H - B - (Math.log10(v + 1) / Math.log10(yMax)) * (H - B - T);
  [0, ...Array.from({ length: Math.round(Math.log10(yMax)) }, (_, e) => 10 ** (e + 1))].forEach((v) => {
    el("line", { x1: L, y1: Y(v), x2: W - R, y2: Y(v), class: "c-grid" }, svg);
    text(svg, L - 8, Y(v) + 4, v >= 1000 ? v / 1000 + "k" : String(v), "c-tick", "end");
  });
  const bw = (W - L - R) / 120;
  liveData.forEach((w, i) => {
    const x = L + (120 - liveData.length + i) * bw;
    const h = Y(0) - Y(w.max_backlog);
    const r = el("rect", { x: x + 1, y: Y(w.max_backlog), width: Math.max(1, bw - 2), height: Math.max(1, h), rx: 2, class: "c-livebar " + (w.max_backlog <= 8 ? "ok" : "bad") }, svg);
    el("title", {}, r).textContent = `τ ${fmtNs(w.tau_ns)} · backlog ${w.max_backlog} · mean latency ${fmtNs(w.mean_ns)}`;
  });
  el("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, class: "c-axis" }, svg);
  text(svg, L, H - 6, "older", "c-tick", "start");
  text(svg, W - R, H - 6, "now · bar height = max backlog per 100 ms window (log scale)", "c-tick", "end");
}

function drawRtTable() {
  const tb = $("rtTbody");
  if (!rtPoints.length) { tb.innerHTML = `<tr><td colspan="11" class="empty">Load shots and run a sweep</td></tr>`; $("rtLimits").textContent = ""; return; }
  tb.innerHTML = rtPoints.map((p) => {
    const R = RTDEC[p.decoder];
    return `<tr><td class="${R.cls}txt">${R.label}</td><td>${fmtNs(p.tau_ns)}</td><td>${fmtNs(p.tau_ns * p.rounds)}</td>` +
      `<td>${fmtNs(p.service_ns)}</td><td>${fmtNs(p.service_max_ns)}</td><td>${fmtNs(p.p50_ns)}</td><td>${fmtNs(p.p99_ns)}</td>` +
      `<td>${fmtNs(p.max_ns)}</td><td>${p.max_backlog.toLocaleString()}</td><td>${p.fails} / ${p.shots}</td>` +
      `<td><span class="badge ${p.keeps_up ? "ok" : "bad"}">${p.keeps_up ? "keeps up" : "falls behind"}</span></td></tr>`;
  }).join("");
  const decs = [...new Set(rtPoints.map((p) => p.decoder))];
  $("rtLimits").textContent = "limit τ* = mean decode / rounds: " + decs.map((d) => `${RTDEC[d].label} ${fmtNs(limitFor(d))}`).join(" · ");
}

function renderRt() { drawRtCharts(); drawRtTable(); drawLive(); showLoaded(); }
$("rtTauVal").textContent = fmtNs(tauFromSlider(Number($("rtTau").value)));
renderRt();
