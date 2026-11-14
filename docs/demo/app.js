/* QEC Edge Lab web twin. All data in data.js comes from real IBM runs (see export_web_demo.py). */
(() => {
  "use strict";
  const DATA = window.QEC_DATA;
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const pct = (x) => (x === 0 ? "0" : x >= 0.01 ? (100 * x).toFixed(1) + "%" : (100 * x).toFixed(2) + "%");

  /* ---------------------------------------------------------------- Part 1: be the decoder */
  const shotRun = $("shotRun"), shotD = $("shotD");
  for (const [key, v] of Object.entries(DATA.shots)) shotRun.add(new Option(v.label, key));
  const fillD = () => {
    shotD.innerHTML = "";
    for (const s of DATA.shots[shotRun.value].sets) shotD.add(new Option(`${2 * s.d - 1} (d=${s.d})`, s.d));
    shotD.value = "5";
  };
  fillD();
  const score = { n: 0, you: 0, maj: 0, uf: 0, ai: 0 };
  let cur = null, answered = false;

  const set = () => DATA.shots[shotRun.value].sets.find((s) => s.d === +shotD.value);

  function decodeShot(shot, d, R) {
    const W = d - 1, bits = shot.b.split("").map(Number);
    const syn = [];
    for (let t = 0; t < R; t++) syn.push(bits.slice(t * W, (t + 1) * W));
    const data = bits.slice(R * W);
    const fin = [];
    for (let i = 0; i < W; i++) fin.push(data[i] ^ data[i + 1]);
    const layers = [...syn, fin];
    const det = layers.map((l, t) => l.map((v, i) => v ^ (t ? layers[t - 1][i] : 0)));
    return { data, det };
  }

  function drawShot() {
    const s = set(), { d, rounds: R } = s;
    const { data, det } = decodeShot(cur, d, R);
    const svg = $("shotSvg");
    svg.innerHTML = "";
    const compact = (svg.parentElement.clientWidth || 600) < 520;
    const cols = 2 * d - 1, left = compact ? 64 : 118, colW = compact ? 44 : Math.min(62, 560 / cols), top = 20, rowH = compact ? 50 : 46;
    const fs = compact ? 17 : 12;
    const Wt = left + cols * colW + 16, Ht = top + (R + 2) * rowH + 26;
    svg.setAttribute("viewBox", `0 0 ${Wt} ${Ht}`);
    const x = (c) => left + c * colW + colW / 2;
    const yRow = (r) => top + r * rowH + rowH / 2;
    // data qubit world-lines
    for (let i = 0; i < d; i++) el("line", { x1: x(2 * i), y1: yRow(0) - 14, x2: x(2 * i), y2: yRow(R + 1), class: "q-line" }, svg);
    const labels = compact ? [...Array.from({ length: R }, (_, t) => `Round ${t + 1}`), "Final", "Data"]
      : [...Array.from({ length: R }, (_, t) => `Check round ${t + 1}`), "Final comparison", "Data readout"];
    labels.forEach((t, r) => { const e = el("text", { x: 2, y: yRow(r) + fs / 3, "font-size": fs }, svg); e.textContent = t; });
    for (let r = 0; r <= R; r++)
      for (let i = 0; i < d - 1; i++) {
        const ev = det[r][i] === 1, sz = compact ? 26 : 22;
        el("rect", { x: x(2 * i + 1) - sz / 2, y: yRow(r) - sz / 2, width: sz, height: sz, rx: 5, class: "q-check" + (ev ? " ev" : "") }, svg);
      }
    data.forEach((v, i) => {
      const dis = answered && v !== cur.t;
      el("circle", { cx: x(2 * i), cy: yRow(R + 1), r: compact ? 17 : 14, class: "q-data" + (v ? " one" : "") + (dis ? " dis" : "") }, svg);
      const tx = el("text", { x: x(2 * i), y: yRow(R + 1) + (compact ? 6 : 4), style: `font-size:${compact ? 16 : 11}px`, "text-anchor": "middle", class: "q-val" + (v ? " on" : "") }, svg);
      tx.textContent = v;
    });
    const nEv = det.flat().reduce((a, b) => a + b, 0);
    const ones = data.reduce((a, b) => a + b, 0);
    $("shotMeta").textContent = `${DATA.shots[shotRun.value].label} · ${2 * d - 1} qubits (${d} data + ${d - 1} checks) · ` +
      `${R} rounds · ${nEv} red clue${nEv === 1 ? "" : "s"} · final readout: ${ones} of ${d} read 1` +
      (cur.p ? " · tricky (hand-picked)" : " · real shot");
  }

  function newShot(tricky, withClues) {
    let pool = set().shots.filter((s) => s.p === (tricky ? 1 : 0));
    if (withClues) pool = pool.filter((s) => { const x = decodeShot(s, set().d, set().rounds).det.flat(); return x.reduce((a, b) => a + b, 0) >= 2; });
    cur = pool[Math.floor(Math.random() * pool.length)];
    answered = false;
    $("verdicts").hidden = true;
    $("guessBox").hidden = false;
    drawShot();
    const f = set().full;
    $("shotNote").innerHTML = `Over all ${f.n.toLocaleString()} real shots at this size: majority vote wrong ${pct(f.majority)}, ` +
      `union-find wrong ${pct(f.ufw)}, AI wrong <b>${pct(f.ai)}</b>. Most random shots are easy; "tricky" shots are hand-picked ` +
      `from those where the decoders disagree. The AI's answer for every shot comes from a network that never saw that shot.`;
  }

  function answer(g) {
    if (answered) return;
    answered = true;
    const t = cur.t;
    score.n++; score.you += g === t; score.maj += cur.m === t; score.uf += cur.u === t; score.ai += cur.a === t;
    const row = (name, v) => `<span>${name}: ${v}</span><span class="${v === t ? "ok" : "bad"}">${v === t ? "✓ right" : "✗ wrong"}</span>`;
    $("truthLine").textContent = `IBM actually stored a ${t}.`;
    $("vYou").innerHTML = row("You", g);
    $("vMaj").innerHTML = row("Majority vote", cur.m);
    $("vUf").innerHTML = row("Union-find (Arduino)", cur.u);
    $("vAi").innerHTML = row("AI decoder (Arduino)", cur.a);
    const s = set(), ones = decodeShot(cur, s.d, s.rounds).data.reduce((a, b) => a + b, 0);
    const flipped = t ? s.d - ones : ones;
    let why = `${flipped} of ${s.d} data qubits ended up flipped (red outline).`;
    if (cur.m !== t) why += " More than half flipped, so a simple vote fails; the clues are needed.";
    if (cur.a === t && cur.u !== t && t === 1)
      why += " On this chip a stored 1 fades into a 0 far more often than the reverse; the AI learned that from the data.";
    else if (cur.a === t && cur.u !== t) why += " The AI learned this chip's typical error patterns from the data.";
    else if (cur.a !== t && cur.u === t) why += " Here the classical decoder wins: no decoder is perfect.";
    $("whyLine").textContent = why;
    $("verdicts").hidden = false;
    $("guessBox").hidden = true;
    for (const [k, id] of [["you", "sYou"], ["maj", "sMaj"], ["uf", "sUf"], ["ai", "sAi"]]) $(id).textContent = score[k];
    $("sN").textContent = score.n;
    drawShot();
  }

  document.querySelectorAll("[data-guess]").forEach((b) => b.addEventListener("click", () => answer(+b.dataset.guess)));
  $("nextShot").addEventListener("click", () => newShot(false));
  $("trickyShot").addEventListener("click", () => newShot(true));
  shotRun.addEventListener("change", () => { fillD(); newShot(false); });
  shotD.addEventListener("change", () => newShot(false));
  let lastCompact = null;
  addEventListener("resize", () => { const c = $("shotSvg").parentElement.clientWidth < 520; if (c !== lastCompact) { lastCompact = c; drawShot(); } });
  newShot(false, true);

  /* ---------------------------------------------------------------- Part 2: results chart */
  const SERIES = [
    { key: "majority", name: "Majority vote", color: "--maj" },
    { key: "ufw", name: "Union-find weighted (Arduino)", color: "--ufw" },
    { key: "pm", name: "PyMatching, best error model (laptop reference)", color: "--pm" },
    { key: "ai", name: "AI decoder (trained on the Arduino)", color: "--ai" },
  ];
  const resRun = $("resRun");
  DATA.runs.forEach((r, i) => resRun.add(new Option(`${r.label} · job ${r.job}`, i)));
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  $("resLegend").innerHTML = SERIES.map((s) => `<span><i class="sw" style="background:var(${s.color})"></i>${s.name}</span>`).join("");

  function drawResults() {
    const run = DATA.runs[+resRun.value], rates = run.rates;
    const svg = $("resSvg"); svg.innerHTML = "";
    const Wt = 640, Ht = 380, L = 62, Rm = 16, T = 16, B = 52;
    svg.setAttribute("viewBox", `0 0 ${Wt} ${Ht}`);
    const ds = rates.map((r) => r.d), dmin = Math.min(...ds), dmax = Math.max(...ds);
    const ymin = 1e-4, ymax = 0.3, floor = 1.25e-4;
    const X = (d) => L + ((d - dmin) / (dmax - dmin)) * (Wt - L - Rm);
    const Y = (p) => T + (Math.log10(ymax) - Math.log10(Math.max(p, ymin))) / (Math.log10(ymax) - Math.log10(ymin)) * (Ht - T - B);
    for (const p of [1e-4, 1e-3, 1e-2, 1e-1]) {
      el("line", { x1: L, x2: Wt - Rm, y1: Y(p), y2: Y(p), class: "grid-line" }, svg);
      const t = el("text", { x: L - 8, y: Y(p) + 4, "text-anchor": "end", class: "axis-t" }, svg);
      t.textContent = p >= 0.01 ? `${100 * p}%` : `${+(100 * p).toFixed(2)}%`;
    }
    for (const d of ds) {
      const t = el("text", { x: X(d), y: Ht - B + 18, "text-anchor": "middle", class: "axis-t" }, svg);
      t.textContent = 2 * d - 1;
    }
    const xl = el("text", { x: (L + Wt - Rm) / 2, y: Ht - 10, "text-anchor": "middle", "font-size": 13 }, svg);
    xl.textContent = "Qubits used for one protected bit";
    const yl = el("text", { x: 14, y: (T + Ht - B) / 2, "text-anchor": "middle", "font-size": 13, transform: `rotate(-90 14 ${(T + Ht - B) / 2})` }, svg);
    yl.textContent = "Share of shots decoded wrong";
    const box = svg.parentElement;
    let tip = box.querySelector(".tip");
    if (!tip) { tip = document.createElement("div"); tip.className = "tip"; tip.hidden = true; box.appendChild(tip); }
    for (const s of SERIES) {
      const pts = rates.filter((r) => r[s.key] !== null && r[s.key] !== undefined);
      const col = css(s.color);
      el("path", { d: pts.map((r, i) => `${i ? "L" : "M"}${X(r.d)},${Y(r[s.key] || floor)}`).join(""), class: "series", stroke: col,
        "stroke-width": s.key === "ai" ? 4 : 3 }, svg);
      for (const r of pts) {
        const v = r[s.key];
        const c = el("circle", { cx: X(r.d), cy: Y(v || floor), r: s.key === "ai" ? 6 : 5, class: "pt" + (v ? "" : " zero"), fill: col }, svg);
        if (!v) c.setAttribute("stroke", col);
        const show = () => {
          tip.hidden = false;
          tip.innerHTML = `<b>${s.name}</b><br>${2 * r.d - 1} qubits (d=${r.d}): ` +
            (v ? `${pct(v)} wrong (${Math.round(v * r.shots)} of ${r.shots.toLocaleString()})` : `0 of ${r.shots.toLocaleString()} wrong`);
          const bb = svg.getBoundingClientRect(), sc = bb.width / Wt;
          tip.style.left = Math.min(bb.width - 200, X(r.d) * sc + 14) + "px";
          tip.style.top = (Y(v || floor) * sc - 10) + "px";
        };
        c.addEventListener("mouseenter", show); c.addEventListener("click", show);
        c.addEventListener("mouseleave", () => (tip.hidden = true));
      }
    }
    // callout
    const r5 = rates.find((r) => r.d === 5);
    const best5 = Math.min(r5.ufw, r5.pm);
    const big = rates.filter((r) => r.d >= 11 && r.ai !== null);
    const aiLoses = big.some((r) => r.ai > Math.min(r.ufw, r.pm));
    const maxGain = rates.filter((r) => r.d <= 9 && r.ai > 0).reduce((m, r) => Math.max(m, Math.min(r.ufw, r.pm) / r.ai), 0);
    const r3 = rates.find((r) => r.d === 3), r21 = rates.find((r) => r.d === 21);
    $("resCallout").innerHTML =
      `<p style="margin:0 0 6px">With <b>9 qubits</b>, the AI decoder was wrong on <b>${pct(r5.ai)}</b> of shots; the best classical ` +
      `decoder on ${pct(best5)}: <b>${(best5 / r5.ai).toFixed(1)}× fewer mistakes</b>. Best gain on this run: ${maxGain.toFixed(1)}×.</p>` +
      `<p style="margin:0 0 6px">Error correction works: majority vote went from ${pct(r3.majority)} wrong with 5 qubits to ` +
      `${pct(r21.majority)} with 41 qubits.</p>` +
      (aiLoses ? `<p style="margin:0">With 21+ qubits the AI levels off around 0.2–0.3% while classical decoders keep improving, so the ` +
        `best design uses the AI for small codes and union-find for large ones.</p>` : `<p style="margin:0">On this chip the AI was at least as good as the classical decoders at every size tested.</p>`);
  }
  resRun.addEventListener("change", drawResults);
  drawResults();
  matchMedia("(prefers-color-scheme: light)").addEventListener("change", drawResults);

  /* ---------------------------------------------------------------- Part 3: real time */
  const TM = DATA.timing, rtDec = $("rtDec");
  TM.decoders.forEach((d, i) => rtDec.add(new Option(d.name, i)));
  const TAU_MIN = 1, TAU_MAX = 2000;                                  // µs, log scale
  const vToTau = (v) => TAU_MIN * Math.pow(TAU_MAX / TAU_MIN, v / 1000);
  const tauToV = (t) => 1000 * Math.log(t / TAU_MIN) / Math.log(TAU_MAX / TAU_MIN);
  const fmtT = (us) => us < 1000 ? `${us < 10 ? us.toFixed(1) : Math.round(us)} µs` : us < 1e6 ? `${(us / 1000).toFixed(us < 1e4 ? 2 : 1)} ms` : `${(us / 1e6).toFixed(1)} s`;
  let v = tauToV(20), work = 0, hist = new Array(13).fill(0), sound = false, actx = null;

  // LED matrix
  const leds = [];
  for (let i = 0; i < 104; i++) { const d = document.createElement("div"); d.className = "led"; $("matrix").appendChild(d); leds.push(d); }
  const drawMatrix = () => {
    for (let r = 0; r < 8; r++) for (let c = 0; c < 13; c++) {
      const h = hist[c], lit = 7 - r < h;
      leds[r * 13 + c].className = "led" + (lit ? (h > 2 ? " on" : " dim") : "");
    }
    if (hist[12] === 0) leds[7 * 13 + 12].className = "led dim";
  };

  // scale labels positioned on the log axis
  const lab = document.querySelector(".scale-labels");
  lab.style.position = "relative"; lab.style.height = "16px";
  [...lab.children].forEach((s, i) => {
    const t = [1, 10, 100, 1000][i];
    s.style.position = "absolute"; s.style.left = (tauToV(t) / 10) + "%";
    s.style.transform = i === 0 ? "none" : i === 3 ? "translateX(-50%)" : "translateX(-50%)";
  });

  function arcPath(frac) {
    const a0 = -135 * Math.PI / 180, a1 = a0 + frac * 270 * Math.PI / 180, r = 50, cx = 60, cy = 60;
    const p = (a) => `${cx + r * Math.sin(a)},${cy - r * Math.cos(a)}`;
    return `M${p(a0)} A${r},${r} 0 ${frac * 270 > 180 ? 1 : 0} 1 ${p(a1)}`;
  }
  function renderKnob() {
    const frac = v / 1000, tau = vToTau(v), dec = TM.decoders[+rtDec.value];
    $("knobArc").setAttribute("d", arcPath(Math.max(0.001, frac)));
    $("knobTick").setAttribute("transform", `rotate(${-135 + frac * 270} 60 60)`);
    $("knob").setAttribute("aria-valuenow", Math.round(v));
    $("knob").setAttribute("aria-valuetext", fmtT(tau) + " per round");
    $("tauVal").textContent = fmtT(tau);
    $("tauRange").value = Math.round(v);
    $("scaleNow").style.left = frac * 100 + "%";
    $("scaleLimit").style.left = tauToV(dec.limit_us) / 10 + "%";
    $("measured").innerHTML = `Measured on the real board (${TM.backend}, ${2 * TM.d - 1} qubits): <b>${dec.name}</b> needs ` +
      `${dec.mean_us} µs per shot, so its limit is <b>${dec.limit_us} µs per round</b> (vertical line on the scale). It kept up at ` +
      `${dec.kept_up[0]} µs (max ${dec.kept_up[1]} waiting) and fell behind at ${dec.fell_behind[0]} µs ` +
      `(${dec.fell_behind[1].toLocaleString()} waiting after one replay).`;
  }
  const setV = (nv) => { v = Math.max(0, Math.min(1000, nv)); renderKnob(); };

  // knob interaction: rotate by pointer angle
  const knob = $("knob");
  const angleToV = (e) => {
    const b = knob.getBoundingClientRect();
    let a = Math.atan2(e.clientX - (b.left + b.width / 2), -(e.clientY - (b.top + b.height / 2))) * 180 / Math.PI;
    a = Math.max(-135, Math.min(135, a));
    return (a + 135) / 270 * 1000;
  };
  knob.addEventListener("pointerdown", (e) => { knob.setPointerCapture(e.pointerId); setV(angleToV(e)); });
  knob.addEventListener("pointermove", (e) => { if (knob.hasPointerCapture(e.pointerId)) setV(angleToV(e)); });
  knob.addEventListener("keydown", (e) => {
    const step = { ArrowUp: 10, ArrowRight: 10, ArrowDown: -10, ArrowLeft: -10, PageUp: 100, PageDown: -100 }[e.key];
    if (step) { e.preventDefault(); setV(v + step); }
  });
  knob.addEventListener("wheel", (e) => { e.preventDefault(); setV(v - Math.sign(e.deltaY) * 15); }, { passive: false });
  $("tauRange").addEventListener("input", (e) => setV(+e.target.value));
  document.querySelectorAll("[data-tau]").forEach((b) => b.addEventListener("click", () => setV(tauToV(+b.dataset.tau))));
  rtDec.addEventListener("change", () => { work = 0; renderKnob(); });
  $("clearBtn").addEventListener("click", () => { work = 0; hist.fill(0); drawMatrix(); });
  $("soundBtn").addEventListener("click", () => {
    sound = !sound;
    $("soundBtn").textContent = sound ? "Sound on (buzzer)" : "Sound off";
    $("soundBtn").setAttribute("aria-pressed", sound);
    if (sound && !actx) { try { actx = new (window.AudioContext || window.webkitAudioContext)(); } catch (_) { sound = false; } }
    if (actx && actx.state === "suspended") actx.resume();
  });
  function buzz() {
    if (!sound || !actx) return;
    const o = actx.createOscillator(), g = actx.createGain();
    o.type = "square"; o.frequency.value = 220;
    g.gain.setValueAtTime(0.06, actx.currentTime); g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime + 0.07);
    o.connect(g).connect(actx.destination); o.start(); o.stop(actx.currentTime + 0.08);
  }

  // queue simulation: one "window" of real shots per tick (like the board's live mode)
  const WINDOW = 4000;
  function tick() {
    const dec = TM.decoders[+rtDec.value], tau = vToTau(v), A = TM.rounds * tau, S = dec.mean_us;
    let maxB = 0, latSum = 0;
    for (let n = 0; n < WINDOW; n++) {
      work = Math.max(0, work - A);                                    // time passes until the next shot arrives
      const s = S * (0.88 + 0.24 * Math.random());
      const b = Math.ceil(work / S);                                   // shots still waiting when this one arrives
      if (b > maxB) maxB = b;
      work += s;
      latSum += work;
    }
    hist.shift();
    let h = 0, x = maxB; while (x > 0 && h < 8) { h++; x = Math.floor(x / 2); }
    hist.push(h);
    drawMatrix();
    const busy = S / A, waiting = Math.ceil(work / S) - 1;
    $("stBusy").textContent = busy > 9.99 ? ">999%" : Math.round(busy * 100) + "%";
    $("stBacklog").textContent = Math.max(0, waiting).toLocaleString();
    $("stLat").textContent = fmtT(latSum / WINDOW);
    const st = $("rtStatus");
    if (maxB > 64) { st.className = "status bad"; st.textContent = `FALLING BEHIND · ${Math.max(0, waiting).toLocaleString()} shots waiting`; buzz(); }
    else if (busy > 0.8) { st.className = "status busy"; st.textContent = "Busy: close to the limit"; }
    else { st.className = "status ok"; st.textContent = "Keeping up"; }
  }
  rtDec.value = "0";
  const qTau = parseFloat(new URLSearchParams(location.search).get("tau"));   // e.g. ?tau=2 opens the knob at 2 µs
  if (qTau > 0) v = Math.max(0, Math.min(1000, tauToV(qTau)));
  renderKnob(); drawMatrix();
  setInterval(tick, 160);
})();
