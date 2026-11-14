"""QEC Decoder Lab - Stage 1.5.

Repetition codes run on IBM hardware (or a noise model). The raw shots are
  * saved to python/runs/ (re-decode later without using the QPU),
  * used on the Linux side to estimate the device's error model (p_ij method),
  * streamed to the STM32, which decodes them with five classical decoders
    (majority, greedy, union-find naive, union-find fast, union-find weighted)
    and an AI decoder (small neural network trained here in numpy, qec_ai.py,
    run on the STM32 with integer arithmetic), and measures CPU cycles for each.
Old IBM jobs can be imported by job ID (no QPU time).
"""
import json, math, random, threading, time
from pathlib import Path
import numpy as np
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
import qec_common as qc
import qec_ai

HERE = Path(__file__).parent
RUNS = HERE / "runs"
CFG = json.loads((HERE / "ibm_config.json").read_text())
DEFAULTS = {
    "distances": [3, 5, 7, 9, 11, 15, 21, 25],
    "rounds": 3,
    "shots": 2000,          # shots per (distance, logical state)
    "decode_shots": 400,    # streamed to the MCU per distance (both states together)
    "p": 0.02,              # noise model: data flip probability per round
    "q": 0.04,              # noise model: measurement flip probability
}
MCU_DECODERS = ["majority", "greedy", "uf_naive", "uf_fast", "uf_weighted", "ai"]
AI = MCU_DECODERS.index("ai")
MAX_D, MAX_R = 25, 10

try:
    import pymatching            # optional: no prebuilt wheel for Linux ARM + Python 3.13
except Exception:
    pymatching = None

ui = WebUI()
state = {"phase": "idle", "mode": "-", "backend": "-", "timer": "-", "run": "-"}
results = []
request = None
cv = threading.Condition()
timer_info = {"mode": None, "hz": 1_000_000, "cpu_hz": 160_000_000}


# ---------------- helpers ----------------
def ui_send(event, data):
    try:
        ui.send_message(event, data)
    except Exception as e:
        print(f"UI send {event} failed: {e}")


def push_status():
    ui_send("status", state)


def set_phase(p):
    state["phase"] = p
    print("phase:", p)
    push_status()


def bcall(name, *args):
    return Bridge.call(name, *args)


def safe_bcall(name, *args):
    try:
        return Bridge.call(name, *args)
    except Exception as e:
        print(f"Bridge call {name} failed: {e}")
        return None


def read_timer():
    try:
        mode = bcall("qec_timer", 0)
        timer_info.update(mode=mode, hz=bcall("qec_timer", 1) & 0xFFFFFFFF, cpu_hz=bcall("qec_timer", 2) & 0xFFFFFFFF)
        names = {0: "micros (1 µs)", 1: "Zephyr hw cycles", 2: "DWT cycle counter"}
        state["timer"] = f"{names.get(mode, '?')} @ {timer_info['hz'] / 1e6:.0f} MHz"
    except Exception as e:
        state["timer"] = f"unavailable ({e})"
    push_status()


def ticks_to_cycles(t):
    return t * timer_info["cpu_hz"] / timer_info["hz"]


def ibm_service():
    from qiskit_ibm_runtime import QiskitRuntimeService
    return QiskitRuntimeService(channel="ibm_cloud", token=CFG["token"], instance=CFG["instance"])


# ---------------- shot sources ----------------
def simulate(d, rounds, shots, p, q, truth, rng):
    W = d - 1
    x = np.full((shots, d), truth, dtype=np.uint8)
    out = np.zeros((shots, rounds * W + d), dtype=np.uint8)
    for t in range(rounds):
        x ^= (rng.random((shots, d)) < p).astype(np.uint8)
        out[:, t * W:(t + 1) * W] = x[:, :-1] ^ x[:, 1:] ^ (rng.random((shots, W)) < q).astype(np.uint8)
    x ^= (rng.random((shots, d)) < p).astype(np.uint8)
    out[:, rounds * W:] = x ^ (rng.random((shots, d)) < q).astype(np.uint8)
    return out


def find_line(backend, length, tries=300, seed=7):
    n = backend.num_qubits
    adj = {i: set() for i in range(n)}
    for a, b in backend.coupling_map.get_edges():
        adj[a].add(b)
        adj[b].add(a)
    rng = random.Random(seed)
    for _ in range(tries):
        start = rng.randrange(n)
        path, seen = [start], {start}
        stack = [iter(rng.sample(sorted(adj[start]), len(adj[start])))]
        steps = 0
        while stack and len(path) < length and steps < 50_000:
            steps += 1
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                seen.discard(path.pop())
                continue
            if nxt in seen:
                continue
            path.append(nxt)
            seen.add(nxt)
            stack.append(iter(rng.sample(sorted(adj[nxt]), len(adj[nxt]))))
        if len(path) >= length:
            return path[:length]
    raise RuntimeError(f"no line of {length} qubits found")


def rep_code_circuit(d, rounds, truth):
    from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister
    W = d - 1
    q = QuantumRegister(2 * d - 1, "q")          # q[2k] = data k, q[2k+1] = ancilla k
    sregs = [ClassicalRegister(W, f"s{t}") for t in range(rounds)]
    final = ClassicalRegister(d, "final")
    circ = QuantumCircuit(q, *sregs, final)
    if truth:
        for k in range(d):
            circ.x(q[2 * k])
    for t in range(rounds):
        circ.barrier()
        for i in range(W):
            circ.cx(q[2 * i], q[2 * i + 1])
        for i in range(W):
            circ.cx(q[2 * i + 2], q[2 * i + 1])
        for i in range(W):
            circ.measure(q[2 * i + 1], sregs[t][i])
        for i in range(W):
            circ.reset(q[2 * i + 1])
    circ.barrier()
    for k in range(d):
        circ.measure(q[2 * k], final[k])
    return circ


def bits_from_strings(strings, width):
    arr = np.frombuffer("".join(strings).encode(), dtype=np.uint8).reshape(len(strings), width) - ord("0")
    return arr[:, ::-1]


def rows_from_pub(data):
    """Rebuild shot rows from one Sampler PUB result (registers s0..s{R-1}, final)."""
    rounds = 0
    while hasattr(data, f"s{rounds}"):
        rounds += 1
    final = getattr(data, "final")
    d = final.num_bits
    parts = [bits_from_strings(getattr(data, f"s{t}").get_bitstrings(), d - 1) for t in range(rounds)]
    parts.append(bits_from_strings(final.get_bitstrings(), d))
    return np.concatenate(parts, axis=1).astype(np.uint8), d, rounds


def run_hardware(dists, rounds, shots):
    from qiskit_ibm_runtime import SamplerV2
    from qiskit.transpiler import generate_preset_pass_manager
    set_phase("connecting to IBM")
    backend = ibm_service().least_busy(operational=True, simulator=False)
    state["backend"] = backend.name
    line = find_line(backend, 2 * max(dists) - 1)
    print(f"Using {backend.name}, line of {len(line)} qubits: {line}")
    isas = []
    for d in dists:
        pm = generate_preset_pass_manager(backend=backend, optimization_level=1, initial_layout=line[:2 * d - 1])
        for truth in (0, 1):
            set_phase(f"transpiling d={d} |{truth}⟩")
            isas.append(pm.run(rep_code_circuit(d, rounds, truth)))
    set_phase(f"submitting {len(isas)} circuits to {backend.name}")
    job = SamplerV2(mode=backend).run(isas, shots=shots)
    print("job", job.job_id())
    while not job.in_final_state():
        set_phase(f"{str(job.status()).lower()} on {backend.name} (job {job.job_id()[:8]}…)")
        time.sleep(3)
    return raw_from_result(job.result()), {"backend": backend.name, "line": line, "job_id": job.job_id(), "mode": "hw"}


def raw_from_result(res):
    raw, rounds = {}, None
    for pub in res:
        rows, d, r = rows_from_pub(pub.data)
        rounds = r
        truth = int(np.mean(qc.majority_logical(rows, d, r)) > 0.5)   # infer |0> / |1> from the data
        raw[(d, truth)] = rows
    return raw


def import_job(job_id):
    set_phase(f"fetching job {job_id[:8]}… from IBM")
    job = ibm_service().job(job_id)
    res = job.result()
    raw = raw_from_result(res)
    try:
        backend = job.backend().name
    except Exception:
        backend = "ibm"
    rounds = rows_from_pub(res[0].data)[2]
    return raw, rounds, {"backend": backend, "job_id": job_id, "line": [], "mode": "hw"}


# ---------------- MCU streaming ----------------
def upload_ai(model):
    """Send the AI model to the MCU; True if the MCU's checksum matches."""
    try:
        return qec_ai.upload(bcall, model) == qec_ai.checksum(model)
    except Exception as e:
        print("AI model upload failed:", e)
        return False


def decode_on_mcu(rows, d, rounds, truth, caps, progress_cb, model=None):
    nbits = bcall("qec_config", d, rounds, truth)
    if nbits != rows.shape[1]:
        raise RuntimeError(f"MCU expects {nbits} bits, got {rows.shape[1]}")
    cw = qc.pack_caps(caps)
    for off in range(0, len(cw), 4):
        chunk = cw[off:off + 4] + [0] * (4 - len(cw[off:off + 4]))
        bcall("qec_weights", off, *chunk)
    ai_ok = model is not None and upload_ai(model)
    py_ai = qec_ai.predict(model, rows) if ai_ok else None
    fails = [0] * len(MCU_DECODERS)
    defects = disagree = mism = ai_mism = 0
    t0 = time.time()
    for i, row in enumerate(rows):
        words = qc.pack_bits(row)
        for off in range(0, len(words), 4):
            chunk = words[off:off + 4] + [0] * (4 - len(words[off:off + 4]))
            bcall("qec_load", off, *chunk)
        r = bcall("qec_decode")
        mask, ndef = r & 0xFF, r >> 8
        for k in range(len(MCU_DECODERS)):
            fails[k] += (mask >> k) & 1
        defects += ndef
        disagree += int(((mask >> 2) & 1) != ((mask >> 3) & 1))   # naive vs fast union-find
        py_maj = int(row[rounds * (d - 1):].sum() * 2 > d)
        mism += int(((mask & 1) == 1) != (py_maj != truth))
        if ai_ok:                                                  # MCU network == Python network?
            ai_mism += int(((mask >> AI) & 1) != int(py_ai[i] != truth))
        if i % 25 == 0:
            progress_cb(i)
    stats = {name: {"avg": ticks_to_cycles(max(0, bcall("qec_stat", k, 0))),
                    "max": ticks_to_cycles(max(0, bcall("qec_stat", k, 1)))} for k, name in enumerate(MCU_DECODERS)}
    return fails, defects, stats, mism, disagree, (time.time() - t0) / max(1, len(rows)), ai_ok, ai_mism


def pymatching_errors(det, rows, d, rounds, truth, edges, B, probs):
    """Optional reference decoder (only if pymatching is installed)."""
    if pymatching is None:
        return None
    out = {}
    for label, w in (("pm_uniform", np.ones(len(edges))), ("pm_weighted", np.log((1 - probs) / probs))):
        m = pymatching.Matching()
        for (u, v, left, _), wk in zip(edges, w):
            fid = {0} if left else set()
            if v == B:
                m.add_boundary_edge(u, fault_ids=fid, weight=float(wk))
            else:
                m.add_edge(u, v, fault_ids=fid, weight=float(wk))
        flip = m.decode_batch(det)[:, 0]
        out[label] = int(((rows[:, rounds * (d - 1)] ^ flip) != truth).sum())
    return out


# ---------------- analysis of one run ----------------
def analyze(raw, rounds, dshots, meta, run_name):
    dists = sorted({d for d, _ in raw})
    results.clear()
    ui_send("clear", {"distances": dists, "rounds": rounds})
    safe_bcall("qec_led_show", 1)
    state["run"] = run_name
    push_status()
    total = len(dists) * 2
    done = 0
    for col, d in enumerate(dists):
        edges, B = qc.build_graph(d, rounds)
        dets = {t: qc.detection_events(raw[(d, t)], d, rounds) for t in (0, 1)}
        # Error model per logical state: on IBM hardware |1> data qubits decay (T1) and see ~10x more
        # flips than |0>, so weights must come from the SAME state. The MCU subset (first rows) is
        # decoded with weights estimated on the remaining, held-out rows of that state.
        n_sub = max(1, dshots // 2)
        probs = {}
        for t in (0, 1):
            held = dets[t][n_sub:] if len(dets[t]) - n_sub >= 200 else dets[t][len(dets[t]) // 2:]
            probs[t] = qc.estimate_edge_probs(held, edges, B)
        # AI decoder: one network for both states (it never sees the label), trained on the same
        # held-out rows; its full-statistics error is cross-fitted over all shots.
        ai_model, ai_full = None, None
        if qec_ai.fits(d, rounds):
            set_phase(f"training AI decoder d={d}")
            tr_rows, tr_truth = [], []
            for t in (0, 1):
                r_t = raw[(d, t)]
                held = r_t[n_sub:] if len(r_t) - n_sub >= 200 else r_t[len(r_t) // 2:]
                tr_rows.append(held)
                tr_truth.append(np.full(len(held), t, dtype=np.uint8))
            ai_model = qec_ai.train(np.concatenate(tr_rows), np.concatenate(tr_truth), d, rounds)
            all_rows = np.concatenate([raw[(d, 0)], raw[(d, 1)]])
            all_truth = np.repeat(np.array([0, 1], dtype=np.uint8), [len(raw[(d, 0)]), len(raw[(d, 1)])])
            f_ai, n_ai = qec_ai.cross_val(all_rows, all_truth, d, rounds)
            ai_full = f_ai / max(1, n_ai)
        per_state = {t: qc.summarize_probs(qc.estimate_edge_probs(dets[t], edges, B), edges) for t in (0, 1)}
        p_all = qc.estimate_edge_probs(np.concatenate([dets[0], dets[1]]), edges, B)
        model = qc.summarize_probs(p_all, edges)
        agg = {"fails": [0] * len(MCU_DECODERS), "defects": 0, "n": 0, "mism": 0, "disagree": 0,
               "cyc": {n: {"avg": 0.0, "max": 0.0} for n in MCU_DECODERS}, "maj_full": 0, "n_full": 0,
               "pm": {}, "ms_per_shot": 0.0, "ai_ok": ai_model is not None, "ai_mism": 0}
        for truth in (0, 1):
            rows = raw[(d, truth)]
            agg["maj_full"] += int((qc.majority_logical(rows, d, rounds) != truth).sum())
            agg["n_full"] += len(rows)
            if pymatching is not None:   # all shots, weights cross-fitted on two halves of this state
                half = len(rows) // 2
                pa = qc.estimate_edge_probs(dets[truth][half:], edges, B)
                pb = qc.estimate_edge_probs(dets[truth][:half], edges, B)
                for part, pr in ((slice(0, half), pa), (slice(half, None), pb)):
                    pm = pymatching_errors(dets[truth][part], rows[part], d, rounds, truth, edges, B, pr)
                    for k, v in pm.items():
                        agg["pm"][k] = agg["pm"].get(k, 0) + v
            sub = rows[:n_sub]
            caps = qc.probs_to_caps(probs[truth])

            def prog(i, _done=done, _n=len(sub), _t=truth):
                set_phase(f"MCU decoding d={d} |{_t}⟩ {i}/{_n}")
                safe_bcall("qec_led_progress", int(100 * (_done + i / max(1, _n)) / total))

            fails, defects, stats, mism, dis, sec, ai_ok, ai_mism = decode_on_mcu(sub, d, rounds, truth, caps, prog, ai_model)
            agg["ai_ok"] = agg["ai_ok"] and ai_ok
            agg["ai_mism"] += ai_mism
            for k in range(len(MCU_DECODERS)):
                agg["fails"][k] += fails[k]
            agg["defects"] += defects
            agg["mism"] += mism
            agg["disagree"] += dis
            agg["ms_per_shot"] += sec * 1000 * len(sub)
            for n in MCU_DECODERS:
                agg["cyc"][n]["avg"] += stats[n]["avg"] * len(sub)
                agg["cyc"][n]["max"] = max(agg["cyc"][n]["max"], stats[n]["max"])
            agg["n"] += len(sub)
            done += 1
        n = max(1, agg["n"])
        for name in MCU_DECODERS:
            agg["cyc"][name]["avg"] /= n
        row = {
            "d": d, "rounds": rounds, "qubits": 2 * d - 1, "n_decoded": agg["n"], "n_total": agg["n_full"],
            "defects_per_shot": agg["defects"] / n,
            "err": {name: agg["fails"][k] / n for k, name in enumerate(MCU_DECODERS)},
            "fails": {name: agg["fails"][k] for k, name in enumerate(MCU_DECODERS)},
            "maj_full": agg["maj_full"] / max(1, agg["n_full"]),
            "pm": {k: v / max(1, agg["n_full"]) for k, v in agg["pm"].items()},
            "p_data": model["p_data"], "p_meas": model["p_meas"],
            "p_data0": per_state[0]["p_data"], "p_data1": per_state[1]["p_data"],
            "cycles": agg["cyc"], "transport_mismatch": agg["mism"], "uf_disagree": agg["disagree"],
            "ai_ok": agg["ai_ok"], "ai_full": ai_full, "ai_mismatch": agg["ai_mism"],
            "ai_params": (qec_ai.n_inputs(d, rounds) + 2) * qec_ai.MAX_H + 1 if ai_model else 0,
            "bridge_ms_per_shot": agg["ms_per_shot"] / n,
            "cpu_mhz": timer_info["cpu_hz"] / 1e6, "timer": state["timer"],
            "mode": meta.get("mode", "sim"), "backend": meta.get("backend", "-"),
            "line": meta.get("line", [])[:2 * d - 1], "job_id": meta.get("job_id", "-"), "run": run_name,
        }
        if not agg["ai_ok"]:               # no model (too large) or upload failed: majority fallback ran
            row["err"]["ai"] = row["fails"]["ai"] = row["cycles"]["ai"] = None
        results.append(row)
        ui_send("result", row)
        e = row["err"]["uf_weighted"]
        safe_bcall("qec_led_bar", min(12, col * (13 // max(1, len(dists)))),
                   8 if e == 0 else max(0, min(8, round(-math.log10(e) * 2))))
        print(f"d={d:2d} p_data={model['p_data']:.4f} p_meas={model['p_meas']:.4f} | "
              + " ".join(f"{k} {row['err'][k]:.4f}" for k in MCU_DECODERS if row['err'][k] is not None)
              + f" | cycles naive {agg['cyc']['uf_naive']['avg']:.0f} fast {agg['cyc']['uf_fast']['avg']:.0f}"
              f" weighted {agg['cyc']['uf_weighted']['avg']:.0f} ai {agg['cyc']['ai']['avg']:.0f} | mismatches {agg['mism']}"
              f" ai {agg['ai_mism']} | ai all shots (cross-fitted) {ai_full}")
    if run_name and run_name != "-":
        (RUNS / f"results_{run_name}.json").write_text(json.dumps(results, indent=1))
    safe_bcall("qec_led_show", 0)
    safe_bcall("qec_beep", 880, 200)
    set_phase("done")



# ======================= Stage 2: real-time replay on the MCU =======================
RT_DECODERS = {"majority": 0, "greedy": 1, "uf_naive": 2, "uf_fast": 3, "uf_weighted": 4, "ai": 5}
rt_info = {"loaded": None}
live_stop = threading.Event()


def rt_load(req):
    """Bulk-load shots of one distance into the MCU's RAM (once), with weights for UF weighted
    and a trained AI decoder (if the distance fits the network)."""
    src, d, which = req.get("source", "noise"), int(req.get("d", 11)), req.get("state", "both")
    n_req = int(req.get("n", 4000))
    if src == "noise":
        rounds = int(req.get("rounds", DEFAULTS["rounds"]))
        rng = np.random.default_rng()
        p, q = float(req.get("p", DEFAULTS["p"])), float(req.get("q", DEFAULTS["q"]))
        raw = {(d, t): simulate(d, rounds, max(1, n_req // 2 + 1), p, q, t, rng) for t in (0, 1)}
        ai_extra = {t: simulate(d, rounds, 2000, p, q, t, rng) for t in (0, 1)}   # fresh training shots
        backend = f"noise model p={p:.3f} q={q:.3f}"
    else:
        raw, meta = qc.load_run(RUNS, src)
        rounds, backend = meta["rounds"], meta.get("backend", "?")
        ai_extra = None
        if (d, 0) not in raw:
            raise RuntimeError(f"distance {d} not in run {src}")
    states = {"both": (0, 1), "0": (0,), "1": (1,)}[which]
    parts = [(raw[(d, t)], t) for t in states]
    if len(parts) == 2:                       # interleave |0> and |1> shots
        m = min(len(parts[0][0]), len(parts[1][0]))
        rows = np.empty((2 * m, parts[0][0].shape[1]), dtype=np.uint8)
        rows[0::2], rows[1::2] = parts[0][0][:m], parts[1][0][:m]
        truth = np.tile(np.array([0, 1], dtype=np.uint8), m)
    else:
        rows, truth = parts[0][0], np.full(len(parts[0][0]), parts[0][1], dtype=np.uint8)
    rows, truth = rows[:n_req], truth[:n_req]
    set_phase(f"loading {len(rows)} shots of d={d} into the MCU")
    r = bcall("qec_buf_begin", d, rounds, len(rows))
    got, stride = r >> 16, r & 0xFFFF
    if got <= 0:
        raise RuntimeError("MCU could not allocate the buffer")
    rows, truth = rows[:got], truth[:got]
    # weights from the loaded shots' own error model (both states mixed if 'both')
    edges, B = qc.build_graph(d, rounds)
    probs = qc.estimate_edge_probs(qc.detection_events(rows, d, rounds), edges, B)
    cw = qc.pack_caps(qc.probs_to_caps(probs))
    for off in range(0, len(cw), 4):
        chunk = cw[off:off + 4] + [0] * (4 - len(cw[off:off + 4]))
        bcall("qec_weights", off, *chunk)
    # pack: shot bits + truth bit, little-endian bit order, `stride` bytes per shot
    full = np.concatenate([rows, truth[:, None]], axis=1)
    packed = np.packbits(full, axis=1, bitorder="little")
    blob = np.zeros((got, stride), dtype=np.uint8)
    blob[:, :packed.shape[1]] = packed
    data = blob.reshape(-1)
    data = np.concatenate([data, np.zeros((-len(data)) % 24, dtype=np.uint8)])
    vals = (data[0::3].astype(np.int64) | (data[1::3].astype(np.int64) << 8) | (data[2::3].astype(np.int64) << 16))
    t0 = time.time()
    ncalls = len(vals) // 8
    for off in range(ncalls):
        bcall("qec_buf_put", off, *[int(v) for v in vals[off * 8:(off + 1) * 8]])
        if off % 50 == 0:
            set_phase(f"loading d={d}: {100 * off // max(1, ncalls)}%")
            safe_bcall("qec_led_progress", 100 * off // max(1, ncalls))
    secs = time.time() - t0
    # transport check: replay with majority vote as fast as possible and compare with Python
    bcall("qec_rt_start", 0, 1, got)
    wait_rt()
    mcu_fails = bcall("qec_rt_get", 1)
    py_fails = int((qc.majority_logical(rows, d, rounds) != truth).sum())
    ai_info = rt_train_ai(raw, ai_extra, d, rounds, states, got, rows, truth)
    rt_info["loaded"] = {"source": src, "backend": backend, "d": d, "rounds": rounds, "state": which,
                         "shots": got, "stride": stride, "kb": round(got * stride / 1024, 1),
                         "load_s": round(secs, 1), "transport_ok": mcu_fails == py_fails,
                         "maj_fails_mcu": mcu_fails, "maj_fails_py": py_fails,
                         "p_data": qc.summarize_probs(probs, edges)["p_data"],
                         "p_meas": qc.summarize_probs(probs, edges)["p_meas"], "ai": ai_info}
    ui_send("rt_loaded", rt_info["loaded"])
    print("loaded:", rt_info["loaded"])
    safe_bcall("qec_led_show", 1)
    set_phase("done")


def rt_train_ai(raw, extra, d, rounds, states, got, rows, truth):
    """Train the AI decoder on shots that are NOT replayed (if there are enough), upload it and
    check that the MCU's network makes exactly the same decisions as Python on the loaded shots."""
    if not qec_ai.fits(d, rounds):
        return {"ok": False, "why": f"d={d} too large for the network ({qec_ai.n_inputs(d, rounds)} > {qec_ai.MAX_IN} inputs)"}
    set_phase(f"training AI decoder d={d}")
    if extra is not None:
        tr = [(extra[t], t) for t in (0, 1)]
    else:
        used = {t: (got + 1) // 2 if len(states) == 2 else (got if t in states else 0) for t in (0, 1)}
        tr = [(raw[(d, t)][used[t]:], t) for t in (0, 1)]
    in_sample = sum(len(r) for r, _ in tr) < 1000
    if in_sample:                                  # too few spare shots: train on everything
        tr = [(raw[(d, t)], t) for t in (0, 1)]
    tr_rows = np.concatenate([r for r, _ in tr])
    tr_truth = np.concatenate([np.full(len(r), t, dtype=np.uint8) for r, t in tr])
    t0 = time.time()
    model = qec_ai.train(tr_rows, tr_truth, d, rounds)
    train_s = time.time() - t0
    if not upload_ai(model):
        return {"ok": False, "why": "upload failed"}
    py_fails = int((qec_ai.predict(model, rows) != truth).sum())
    bcall("qec_rt_start", RT_DECODERS["ai"], 1, got)
    wait_rt()
    mcu_fails = bcall("qec_rt_get", 1)
    return {"ok": True, "train_shots": len(tr_rows), "in_sample": in_sample, "train_s": round(train_s, 1),
            "params": (qec_ai.n_inputs(d, rounds) + 2) * qec_ai.MAX_H + 1,
            "fails_mcu": mcu_fails, "fails_py": py_fails, "match": mcu_fails == py_fails}


def wait_rt(timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if bcall("qec_rt_status") == 3:
            return
        time.sleep(0.05)
    raise RuntimeError("MCU replay timed out")


def rt_sweep(req):
    if not rt_info["loaded"]:
        raise RuntimeError("load shots into the MCU first")
    L = rt_info["loaded"]
    decs = [d for d in req.get("decoders", ["uf_fast", "uf_weighted", "uf_naive"]) if d in RT_DECODERS
            and (d != "ai" or L.get("ai", {}).get("ok"))]          # no AI model for this distance: skip it
    if not decs:
        raise RuntimeError("no usable decoder selected (AI decoder not available for this distance?)")
    tmin, tmax = float(req.get("tau_min_ns", 50)), float(req.get("tau_max_ns", 50000))
    npts = int(req.get("points", 13))
    taus = [int(round(tmin * (tmax / tmin) ** (i / max(1, npts - 1)))) for i in range(npts)]
    n = int(req.get("n", min(L["shots"], 3000)))
    ui_send("rt_sweep_start", {"decoders": decs, "taus": taus, "loaded": L})
    total, done = len(decs) * len(taus), 0
    for dec in decs:
        for tau in reversed(taus):           # slow to fast
            set_phase(f"replay {dec} τ={tau / 1000:.2f} µs ({done + 1}/{total})")
            safe_bcall("qec_led_progress", 100 * done // total)
            bcall("qec_rt_start", RT_DECODERS[dec], tau, n)
            wait_rt()
            g = [bcall("qec_rt_get", i) for i in range(13)]
            series = [bcall("qec_rt_get", 16 + i) for i in range(0, 64, 4)]
            pt = {"decoder": dec, "tau_ns": tau, "rounds": L["rounds"], "shots": g[0], "fails": g[1],
                  "max_backlog": g[2], "p50_ns": g[3], "p90_ns": g[4], "p99_ns": g[5], "max_ns": g[6],
                  "mean_ns": g[7], "service_ns": g[8], "service_max_ns": g[9],
                  "first_ns": g[10], "last_ns": g[11], "duration_us": g[12], "series": series}
            pt["keeps_up"] = pt["max_backlog"] <= 8 or pt["last_ns"] < 2 * pt["first_ns"] + 4 * pt["service_ns"]
            ui_send("rt_point", pt)
            print(f"{dec:12s} tau={tau:7d} ns  mean decode {pt['service_ns']:7d} ns  p99 {pt['p99_ns']:10d} ns  "
                  f"max backlog {pt['max_backlog']:6d}  {'keeps up' if pt['keeps_up'] else 'FALLS BEHIND'}")
            done += 1
    safe_bcall("qec_led_show", 0)
    safe_bcall("qec_beep", 880, 150)
    set_phase("done")


def rt_live(req):
    if not rt_info["loaded"]:
        raise RuntimeError("load shots into the MCU first")
    dec = RT_DECODERS.get(req.get("decoder", "uf_fast"), 3)
    if dec == RT_DECODERS["ai"] and not rt_info["loaded"].get("ai", {}).get("ok"):
        raise RuntimeError("AI decoder not available for this distance")
    bcall("qec_live", 1, dec, int(req.get("tau_ns", 2000)))
    live_stop.clear()
    set_phase("live (turn the knob)")
    last = -1
    while not live_stop.is_set():
        try:
            w = [bcall("qec_live_get", i) for i in range(8)]
        except Exception as e:
            print("live poll failed:", e)
            time.sleep(0.5)
            continue
        if w[0] != last:
            last = w[0]
            ui_send("rt_live", {"seq": w[0], "tau_ns": w[1], "shots": w[2], "max_backlog": w[3],
                                "mean_ns": w[4], "max_ns": w[5], "fails": w[6], "knob": bool(w[7]),
                                "rounds": rt_info["loaded"]["rounds"]})
        time.sleep(0.2)
    bcall("qec_live", 0, dec, 0)
    set_phase("done")


# ---------------- request handling ----------------
def handle(req):
    kind = req.get("kind", "run")
    if kind == "rt_load":
        return rt_load(req)
    if kind == "rt_sweep":
        return rt_sweep(req)
    if kind == "rt_live":
        return rt_live(req)
    dshots = max(10, int(req.get("decode_shots", DEFAULTS["decode_shots"])))
    if kind == "redecode":
        set_phase(f"loading {req['name']}")
        raw, meta = qc.load_run(RUNS, req["name"])
        state["backend"] = meta.get("backend", "-")
        state["mode"] = "saved run"
        return analyze(raw, meta["rounds"], dshots, meta, req["name"])
    if kind == "import":
        raw, rounds, meta = import_job(req["job_id"].strip())
        name = qc.save_run(RUNS, raw, rounds, meta)
        ui_send("runs", qc.list_runs(RUNS))
        state["backend"], state["mode"] = meta["backend"], "imported job"
        return analyze(raw, rounds, dshots, meta, name)
    mode = req.get("mode", "sim")
    dists = sorted({int(d) for d in req.get("distances", DEFAULTS["distances"]) if 3 <= int(d) <= MAX_D})
    rounds = max(1, min(MAX_R, int(req.get("rounds", DEFAULTS["rounds"]))))
    shots = max(50, int(req.get("shots", DEFAULTS["shots"])))
    if mode == "hw":
        state["mode"] = "IBM hardware"
        raw, meta = run_hardware(dists, rounds, shots)
        name = qc.save_run(RUNS, raw, rounds, meta)
        ui_send("runs", qc.list_runs(RUNS))
    else:
        p = float(req.get("p", DEFAULTS["p"]))
        q = float(req.get("q", DEFAULTS["q"]))
        state["mode"], state["backend"] = f"noise model p={p:.3f} q={q:.3f}", "noise model"
        set_phase("simulating")
        rng = np.random.default_rng()
        raw = {(d, t): simulate(d, rounds, shots, p, q, t, rng) for d in dists for t in (0, 1)}
        meta, name = {"backend": "noise model", "mode": "sim", "p": p, "q": q}, "-"
    analyze(raw, rounds, dshots, meta, name)


def worker():
    global request
    time.sleep(5)
    read_timer()
    while True:
        with cv:
            while request is None:
                cv.wait()
            req, request = request, None
        try:
            handle(req)
        except Exception as e:
            print("Request failed:", e)
            set_phase(f"error: {e}")
            safe_bcall("qec_beep", 150, 400)


def _data(args):
    return args[-1] if args and isinstance(args[-1], dict) else {}


def on_hello(*args):
    push_status()
    ui_send("defaults", {**DEFAULTS, "pymatching": pymatching is not None})
    ui_send("runs", qc.list_runs(RUNS))
    ui_send("history", results)
    if rt_info["loaded"]:
        ui_send("rt_loaded", rt_info["loaded"])


def on_live_stop(*args):
    live_stop.set()


def on_request(*args):
    global request
    ph = state["phase"]
    if ph not in ("idle", "done") and not ph.startswith("error"):
        print("busy, ignoring request")
        return
    with cv:
        request = _data(args)
        cv.notify()


ui.on_message("hello", on_hello)
ui.on_message("run", on_request)
ui.on_message("rt_live_stop", on_live_stop)
threading.Thread(target=worker, daemon=True).start()

App.run()
