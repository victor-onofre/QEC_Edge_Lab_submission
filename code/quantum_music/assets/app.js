const ui = new WebUI();
const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";

let cfg = { knob_steps: 64, n_bins: 32, hardware: false };
let history = [];
let last = null;
let playing = -1;
let busy = false;

const NAMES = ["A", "A#", "B", "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#"];
const noteName = (n) => NAMES[n % 12] + (3 + Math.floor((n + 9) / 12));
const mod = (a, b) => ((a % b) + b) % b;
const pct = (x) => Math.round(x * 100) + "%";

// ================= Connection & messages =================
ui.on_connect(() => { setPill("conn", "connected", "ok"); ui.send_message("hello", {}); });
ui.on_disconnect(() => setPill("conn", "offline", "bad"));

ui.on_message("status", (s) => {
  cfg = { ...cfg, ...s };
  $("slider").max = cfg.knob_steps - 1;
  $("segSim").classList.toggle("active", !s.hardware);
  $("segHw").classList.toggle("active", !!s.hardware);
  setPill("backend", s.backend || "-", s.hardware ? "hw" : "sim");
  busy = !["idle", "playing"].includes(s.phase);
  const err = (s.phase || "").startsWith("error");
  setPill("phase", s.phase || "-", err ? "bad" : busy ? "busy" : "ok");
  setPill("gates", s.twoq != null ? `depth ${s.depth} · ${s.twoq} two-qubit gates` : `depth ${s.depth ?? "-"}`, "muted");
  $("runBtn").disabled = busy;
  drawDial();
});

ui.on_message("circuit", (c) => { $("circuit").textContent = c.text; });
ui.on_message("history", (h) => { history = h || []; last = history[history.length - 1] || null; renderAll(); });
ui.on_message("result", (r) => {
  history.push(r);
  if (history.length > 200) history.shift();
  last = r; playing = -1;
  renderAll();
});
ui.on_message("note", (n) => { playing = n.i; drawHist(); drawNotes(); });
ui.on_message("knob", (k) => { $("slider").value = mod(k.value, cfg.knob_steps); drawDial(); });

// ================= Controls =================
$("slider").addEventListener("input", drawDial);
$("slider").addEventListener("change", () => ui.send_message("set_phase", { value: Number($("slider").value) }));
$("runBtn").addEventListener("click", () => ui.send_message("rerun", {}));
$("segSim").addEventListener("click", () => { if (cfg.hardware) ui.send_message("set_hardware", { on: false }); });
$("segHw").addEventListener("click", () => {
  if (cfg.hardware) return;
  if (confirm("Switch to real IBM quantum hardware?\nEach run uses part of your monthly quota.")) {
    ui.send_message("set_hardware", { on: true });
  }
});

function setPill(id, text, cls = "") {
  const el = $(id);
  el.className = "pill " + cls;
  el.querySelector("b").textContent = text;
  el.title = text;
}

// ================= SVG helpers =================
function el(tag, attrs, parent) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function text(parent, x, y, str, cls, anchor = "middle") {
  const t = el("text", { x, y, class: cls, "text-anchor": anchor }, parent);
  t.textContent = str;
  return t;
}
function gradient(svg, id, color, o1, o2) {
  const defs = el("defs", {}, svg);
  const g = el("linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
  el("stop", { offset: "0%", "stop-color": color, "stop-opacity": o1 }, g);
  el("stop", { offset: "100%", "stop-color": color, "stop-opacity": o2 }, g);
}
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// ================= Rendering =================
function renderAll() { drawDial(); drawKpis(); drawHist(); drawNotes(); drawFringe(); drawTable(); }

function currentPhase() {
  const v = Number($("slider").value);
  const deg = (360 * v) / cfg.knob_steps;
  const bin = (deg / 360) * cfg.n_bins;
  const onGrid = Math.abs(bin - Math.round(bin)) < 1e-9;
  return { v, deg, bin, onGrid };
}

// ---- Circular phase dial with a radial histogram of the last result ----
function drawDial() {
  const svg = $("dial");
  svg.innerHTML = "";
  const C = 130, R = 82, N = cfg.n_bins;
  const { v, deg, bin, onGrid } = currentPhase();
  const P = (r, d) => [C + r * Math.sin((d * Math.PI) / 180), C - r * Math.cos((d * Math.PI) / 180)];

  el("circle", { cx: C, cy: C, r: R, class: "d-ring" }, svg);
  if (deg > 0.01) {
    const [x, y] = P(R, deg);
    el("path", { d: `M ${C} ${C - R} A ${R} ${R} 0 ${deg > 180 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}`, class: "d-arc" }, svg);
  }

  // radial histogram: one spoke per possible note, length = measured probability
  const counts = last ? last.counts : null;
  const top = counts ? Math.max(...counts) || 1 : 1;
  for (let k = 0; k < N; k++) {
    const a = (k * 360) / N;
    const len = 4 + (counts ? (counts[k] / top) * 30 : 0);
    const [x1, y1] = P(R + 10, a);
    const [x2, y2] = P(R + 10 + len, a);
    let cls = "d-tick";
    if (counts && counts[k] > 0) cls += " hit";
    if (last && k === last.expected) cls += " exp";
    el("line", { x1, y1, x2, y2, class: cls }, svg);
  }
  [0, 8, 16, 24].forEach((k) => {
    const [x, y] = P(R - 22, (k * 360) / N);
    text(svg, x, y + 4, noteName(k), "d-label");
  });

  const [kx, ky] = P(R, deg);
  el("circle", { cx: kx, cy: ky, r: 9, class: "d-knob" }, svg);

  text(svg, C, C - 2, deg.toFixed(1) + "°", "d-big");
  text(svg, C, C + 20, onGrid ? noteName(mod(Math.round(bin), N)) : "between notes", onGrid ? "d-note" : "d-small");
  text(svg, C, C + 38, `knob ${v}`, "d-small");

  $("phiInfo").textContent = onGrid ? "on grid · constructive interference" : "off grid · partial interference";
}

function drawKpis() {
  if (!last) return;
  $("kHit").textContent = pct(last.hit);
  $("kIdeal").textContent = pct(last.hit_ideal);
  $("kTvd").textContent = last.tvd.toFixed(3);
  $("kNote").textContent = noteName(last.expected);
  $("mHit").style.width = pct(last.hit);
  $("mHit").style.background = last.hardware ? cssVar("--hw") : cssVar("--accent");
  $("mIdeal").style.left = `calc(${pct(last.hit_ideal)} - 1px)`;
}

// ---- Bar chart of all 32 outcomes ----
function drawHist() {
  const svg = $("hist");
  svg.innerHTML = "";
  gradient(svg, "barGrad", cssVar("--accent"), 0.75, 0.2);
  const W = 720, H = 290, L = 44, R = 10, T = 12, B = 34;
  const N = cfg.n_bins, bw = (W - L - R) / N;

  if (!last) {
    el("line", { x1: L, y1: H - B, x2: W - R, y2: H - B, class: "c-axis" }, svg);
    text(svg, W / 2, H / 2, "Waiting for the first run…", "c-empty");
    return;
  }
  const total = last.shots || last.counts.reduce((a, b) => a + b, 0);
  const probs = last.counts.map((c) => c / total);
  const maxP = Math.max(...probs, ...last.ideal);
  const yMax = Math.min(1, Math.ceil(maxP * 4 + 0.0001) / 4);
  const Y = (p) => H - B - (p / yMax) * (H - B - T);

  [0, 0.5, 1].forEach((f) => {
    const p = f * yMax;
    el("line", { x1: L, y1: Y(p), x2: W - R, y2: Y(p), class: "c-grid" }, svg);
    text(svg, L - 8, Y(p) + 4, pct(p), "c-tick", "end");
  });

  const curNote = playing >= 0 ? last.notes[playing] : -1;
  for (let k = 0; k < N; k++) {
    const x = L + k * bw;
    const h = Math.max(0, Y(0) - Y(probs[k]));
    let cls = "c-bar";
    if (k === last.expected) cls += " exp";
    if (k === curNote) cls += " play";
    if (h > 0) el("rect", { x: x + 2, y: Y(0) - h, width: bw - 4, height: h, rx: 3, class: cls }, svg);
    const nearExp = Math.abs(k - last.expected) <= 2 && k !== last.expected;
    if ((k % 4 === 0 && !nearExp) || k === last.expected) {
      text(svg, x + bw / 2, H - B + 18, noteName(k), "c-tick" + (k === last.expected ? " strong" : ""));
    }
  }
  // ideal distribution as dashed line + dots
  let d = "";
  last.ideal.forEach((p, k) => { d += (k ? "L" : "M") + (L + k * bw + bw / 2).toFixed(1) + "," + Y(p).toFixed(1); });
  el("path", { d, class: "c-ideal-line" }, svg);
  last.ideal.forEach((p, k) => {
    if (p > 0.01) el("circle", { cx: L + k * bw + bw / 2, cy: Y(p), r: 3, class: "c-ideal-dot" }, svg);
  });
  el("line", { x1: L, y1: Y(0), x2: W - R, y2: Y(0), class: "c-axis" }, svg);
}

// ---- Melody chips ----
function drawNotes() {
  const box = $("notes");
  if (!last) return;
  box.innerHTML = "";
  last.notes.forEach((n, i) => {
    const d = document.createElement("div");
    d.className = "chip" + (n === last.expected ? " good" : "") + (i === playing ? " now" : "");
    d.innerHTML = `${noteName(n)}<small>${i + 1}</small>`;
    box.appendChild(d);
  });
  const good = last.notes.filter((n) => n === last.expected).length;
  $("melodyInfo").textContent = `${good} of ${last.notes.length} notes on ${noteName(last.expected)} · ${last.backend}`;
}

// ---- Hit probability vs distance from the nearest note: theory + every run ----
// offset = (phase in note units) - nearest note, from -0.5 to +0.5
function theory(offset) {
  const N = cfg.n_bins;
  if (Math.abs(offset) < 1e-9) return 1;
  return Math.sin(Math.PI * offset) ** 2 / (N * N * Math.sin((Math.PI * offset) / N) ** 2);
}
function offsetOf(phiDeg) {
  const b = (phiDeg / 360) * cfg.n_bins;
  return b - Math.round(b);
}

function drawFringe() {
  const svg = $("fringe");
  svg.innerHTML = "";
  gradient(svg, "areaGrad", cssVar("--accent"), 0.28, 0.0);
  const W = 720, H = 250, L = 44, R = 14, T = 12, B = 40;
  const X = (o) => L + ((o + 0.5) / 1) * (W - L - R);
  const Y = (p) => H - B - p * (H - B - T);

  [0, 0.5, 1].forEach((f) => {
    el("line", { x1: L, y1: Y(f), x2: W - R, y2: Y(f), class: "c-grid" }, svg);
    text(svg, L - 8, Y(f) + 4, pct(f), "c-tick", "end");
  });
  [[-0.5, "halfway ←"], [-0.25, ""], [0, "on the note"], [0.25, ""], [0.5, "→ halfway"]].forEach(([o, lab]) => {
    if (lab) text(svg, X(o), H - B + 18, lab, "c-tick" + (o === 0 ? " strong" : ""), o === -0.5 ? "start" : o === 0.5 ? "end" : "middle");
  });
  text(svg, (L + W - R) / 2, H - 6, "distance of φ from the nearest note", "c-tick");

  let line = "";
  for (let o = -0.5; o <= 0.5001; o += 0.005) line += (line ? "L" : "M") + X(o).toFixed(1) + "," + Y(theory(o)).toFixed(1);
  el("path", { d: `${line} L ${X(0.5)} ${Y(0)} L ${X(-0.5)} ${Y(0)} Z`, class: "c-area" }, svg);
  el("path", { d: line, class: "c-theory" }, svg);
  el("line", { x1: L, y1: Y(0), x2: W - R, y2: Y(0), class: "c-axis" }, svg);

  history.forEach((r, i) => {
    const isLast = r === last;
    let o = offsetOf(r.phi_deg);
    if (Math.abs(Math.abs(o) - 0.5) < 1e-6) o = i % 2 ? 0.5 : -0.5;        // spread halfway points over both edges
    const jitter = ((i * 37) % 11 - 5) * 0.003;                               // keep overlapping dots visible
    const c = el("circle", { cx: X(Math.max(-0.5, Math.min(0.5, o + jitter))), cy: Y(r.hit), r: isLast ? 6 : 4,
      class: "c-pt " + (r.hardware ? "hw" : "sim") + (isLast ? " last" : "") }, svg);
    const t = el("title", {}, c);
    t.textContent = `#${r.run} ${r.backend}: φ=${r.phi_deg.toFixed(1)}°, hit ${pct(r.hit)} (ideal ${pct(r.hit_ideal)})`;
  });
  if (!history.length) text(svg, W / 2, H / 2 + 40, "Runs will appear here as dots", "c-empty");
}

// ---- History table ----
function drawTable() {
  const tb = $("hist-table");
  $("histCount").textContent = `${history.length} run${history.length === 1 ? "" : "s"}`;
  if (!history.length) return;
  tb.innerHTML = "";
  history.slice(-50).reverse().forEach((r) => {
    const tr = document.createElement("tr");
    tr.title = `${r.time} · ${r.seconds}s` + (r.job_id && r.job_id !== "-" ? ` · job ${r.job_id}` : "");
    const badge = `<span class="badge ${r.hardware ? "hw" : "sim"}">${r.hardware ? r.backend : "sim"}</span>`;
    tr.innerHTML =
      `<td class="hint">${r.run}</td><td>${badge}</td><td>${r.phi_deg.toFixed(1)}°</td>` +
      `<td>${noteName(r.expected)}</td><td>${pct(r.hit)} <span class="hint">/ ${pct(r.hit_ideal)}</span></td>` +
      `<td>${r.tvd.toFixed(3)}</td>`;
    tb.appendChild(tr);
  });
}

drawDial();
drawHist();
drawFringe();
