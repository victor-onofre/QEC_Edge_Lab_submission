#!/usr/bin/env python3
"""Offline full-statistics analysis of saved QEC Lab runs (runs on your laptop).

For every saved run it decodes ALL shots with:
  * majority vote
  * the board's own C decoders (union-find uniform / weighted), compiled here from
    ../sketch/qec_decoders.h, so the numbers are exactly what the STM32 would compute
  * PyMatching (minimum-weight perfect matching) uniform and weighted  - the reference
    (pm_weighted: weights per logical state, like the board; pm_w_mixed: one model for both states)
  * the AI decoder (python/qec_ai.py, a small neural network) - cross-fitted on two halves of the
    shots (both states mixed, label never an input), inference run with the board's C code (qec_ai.h)

Usage:
  pip install numpy pymatching
  scp -r arduino@10.0.34.98:~/ArduinoApps/qec_lab/python/runs ./runs
  python3 tools/qec_offline.py ./runs            # all runs
  python3 tools/qec_offline.py ./runs <run-name> # one run
Writes <runs>/offline_<run>.csv next to the data.
"""
import ctypes, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
import qec_common as qc  # noqa: E402
import qec_ai  # noqa: E402

try:
    import pymatching
except ImportError:
    pymatching = None
    print("note: pymatching not installed -> `pip install pymatching` for the MWPM reference")

SHIM = r"""
#include "%s"
#include "%s"
extern "C" int decode_batch(int d, int r, int truth, const unsigned char* rows, int nshots, int nbits,
                            const unsigned char* caps, int weighted) {
  qec::configure(d, r);
  for (int e = 0; e < qec::E; e++) qec::capWeighted[e] = caps[e];
  int fails = 0;
  for (int s = 0; s < nshots; s++) {
    for (int b = 0; b < nbits; b++) qec::bits[b] = rows[s * nbits + b];
    qec::computeDetectors();
    unsigned char out = qec::decodeUnionFindFast(weighted ? qec::capWeighted : qec::capUniform);
    fails += (out != truth);
  }
  return fails;
}
// AI decoder: load a packed model, decode all shots (decoded logical -> out), return active inputs
extern "C" long ai_batch(int d, int r, const int* hdr, const int* words, int nwords,
                         const unsigned char* rows, int nshots, int nbits, unsigned char* out) {
  qec::configure(d, r);
  ai::begin(hdr[0], hdr[1], hdr[2], hdr[3], hdr[4]);
  ai::put(0, words, nwords);
  long active = 0;
  for (int s = 0; s < nshots; s++) {
    for (int b = 0; b < nbits; b++) qec::bits[b] = rows[s * nbits + b];
    active += qec::computeDetectors();
    for (int k = 0; k < qec::D; k++) active += qec::dataBit(k);
    out[s] = ai::decode();
  }
  return active;
}
"""


def build_lib():
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "shim.cpp"
    src.write_text(SHIM % (HERE.parent / "sketch" / "qec_decoders.h", HERE.parent / "sketch" / "qec_ai.h"))
    lib = tmp / "libqecshim.so"
    subprocess.run(["g++", "-O2", "-shared", "-fPIC", "-w", "-o", str(lib), str(src)], check=True)
    so = ctypes.CDLL(str(lib))
    so.decode_batch.restype = ctypes.c_int
    so.ai_batch.restype = ctypes.c_long
    return so


def c_fails(so, rows, d, rounds, truth, caps, weighted):
    rows = np.ascontiguousarray(rows, dtype=np.uint8)
    caps = np.ascontiguousarray(caps, dtype=np.uint8)
    return so.decode_batch(d, rounds, truth, rows.ctypes.data_as(ctypes.c_void_p), rows.shape[0], rows.shape[1],
                           caps.ctypes.data_as(ctypes.c_void_p), int(weighted))


def ai_c(so, model, rows):
    """Board C inference of `model` on rows -> (decoded logicals, ns per shot, mean active inputs)."""
    hdr, words = qec_ai.pack(model)
    hdr = np.array(hdr, dtype=np.int32)
    words = np.array(words, dtype=np.int32)
    rows = np.ascontiguousarray(rows, dtype=np.uint8)
    out = np.zeros(len(rows), dtype=np.uint8)
    p = lambda a: a.ctypes.data_as(ctypes.c_void_p)
    t0 = time.perf_counter()
    active = so.ai_batch(model["d"], model["rounds"], p(hdr), p(words), len(words), p(rows), rows.shape[0], rows.shape[1], p(out))
    ns = (time.perf_counter() - t0) * 1e9 / max(1, len(rows))
    return out, ns, active / max(1, len(rows))


def pm_fails(det, rows, d, rounds, truth, edges, B, weights):
    m = pymatching.Matching()
    for (u, v, left, _), w in zip(edges, weights):
        fid = {0} if left else set()
        if v == B:
            m.add_boundary_edge(u, fault_ids=fid, weight=float(w))
        else:
            m.add_edge(u, v, fault_ids=fid, weight=float(w))
    flip = m.decode_batch(det)[:, 0]
    return int(((rows[:, rounds * (d - 1)] ^ flip) != truth).sum())


def fmt(f, n):
    p = f / n
    return f"{p:8.2e}" if p else f"<{1 / n:7.1e}"


def analyze_run(so, runs, name):
    raw, meta = qc.load_run(runs, name)
    R = meta["rounds"]
    dists = sorted({d for d, _ in raw})
    cols = ["d", "shots", "p_data", "p_meas", "majority", "uf", "uf_weighted"] + (["pm", "pm_weighted", "pm_w_mixed"] if pymatching else []) + ["ai", "ai_ns", "ai_adds"]
    print(f"\n== {name}  ({meta.get('backend')}, job {meta.get('job_id', '-')}, {R} rounds) ==")
    print("  ".join(f"{c:>11}" for c in cols))
    lines = [",".join(cols)]
    for d in dists:
        edges, B = qc.build_graph(d, R)
        dets = {t: qc.detection_events(raw[(d, t)], d, R) for t in (0, 1)}
        model = qc.summarize_probs(qc.estimate_edge_probs(np.concatenate([dets[0], dets[1]]), edges, B), edges)
        n = sum(len(raw[(d, t)]) for t in (0, 1))
        f = {"majority": 0, "uf": 0, "uf_weighted": 0, "pm": 0, "pm_weighted": 0, "pm_w_mixed": 0, "ai": 0}
        for t in (0, 1):
            rows = raw[(d, t)]
            f["majority"] += int((qc.majority_logical(rows, d, R) != t).sum())
            if pymatching:
                f["pm"] += pm_fails(dets[t], rows, d, R, t, edges, B, np.ones(len(edges)))
            # weights per logical state (|1> decays far more on hardware), cross-fitted on two halves
            half = len(rows) // 2
            for part, other in ((slice(0, half), slice(half, None)), (slice(half, None), slice(0, half))):
                pr = qc.estimate_edge_probs(dets[t][other], edges, B)
                caps = qc.probs_to_caps(pr)
                f["uf"] += c_fails(so, rows[part], d, R, t, caps, False)
                f["uf_weighted"] += c_fails(so, rows[part], d, R, t, caps, True)
                if pymatching:
                    f["pm_weighted"] += pm_fails(dets[t][part], rows[part], d, R, t, edges, B, np.log((1 - pr) / pr))
        # label-free baselines: one error model / one network for both states, cross-fitted on two halves
        rows_all = np.concatenate([raw[(d, 0)], raw[(d, 1)]])
        truth_all = np.repeat(np.array([0, 1], dtype=np.uint8), [len(raw[(d, 0)]), len(raw[(d, 1)])])
        det_all = np.concatenate([dets[0], dets[1]])
        fold = np.random.default_rng(1).permutation(len(rows_all)) % 2
        ns_sum, act_sum = 0.0, 0.0
        if not qec_ai.fits(d, R):
            f["ai"] = None
        for k in (0, 1):
            te, trn = fold == k, fold != k
            if pymatching:
                pr = qc.estimate_edge_probs(det_all[trn], edges, B)
                w = np.log((1 - pr) / pr)
                for t in (0, 1):
                    sel = te & (truth_all == t)
                    f["pm_w_mixed"] += pm_fails(det_all[sel], rows_all[sel], d, R, t, edges, B, w)
            if f["ai"] is not None:
                m = qec_ai.train(rows_all[trn], truth_all[trn], d, R)
                out, ns, act = ai_c(so, m, rows_all[te])
                assert (out == qec_ai.predict(m, rows_all[te])).all(), "C and Python AI inference disagree"
                f["ai"] += int((out != truth_all[te]).sum())
                ns_sum += ns / 2
                act_sum += act / 2
        f["ai_ns"], f["ai_adds"] = ns_sum, act_sum * qec_ai.MAX_H
        num = lambda c, v: (f"{v:.0f}" if c in ("ai_ns", "ai_adds") else fmt(v, n)) if v is not None else "-"
        vals = [str(d), str(n), f"{model['p_data']:.4f}", f"{model['p_meas']:.4f}"] + [num(c, f[c]) for c in cols[4:]]
        print("  ".join(f"{v:>11}" for v in vals))
        csv = lambda c, v: "" if v is None else (f"{v:.1f}" if c in ("ai_ns", "ai_adds") else str(v / n))
        lines.append(",".join([str(d), str(n), f"{model['p_data']:.5f}", f"{model['p_meas']:.5f}"] + [csv(c, f[c]) for c in cols[4:]]))
    out = Path(runs) / f"offline_{name}.csv"
    out.write_text("\n".join(lines) + "\n")
    print(f"saved {out}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    runs = Path(sys.argv[1])
    names = sys.argv[2:] or [r["name"] for r in qc.list_runs(runs)]
    if not names:
        print(f"no runs found in {runs}")
        sys.exit(1)
    so = build_lib()
    for name in names:
        analyze_run(so, runs, name)


if __name__ == "__main__":
    main()
