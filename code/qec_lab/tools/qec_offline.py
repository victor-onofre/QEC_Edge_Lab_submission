#!/usr/bin/env python3
"""Offline full-statistics analysis of saved QEC Lab runs (runs on your laptop).

For every saved run it decodes ALL shots with:
  * majority vote
  * the board's own C decoders (union-find uniform / weighted), compiled here from
    ../sketch/qec_decoders.h, so the numbers are exactly what the STM32 would compute
  * PyMatching (minimum-weight perfect matching) uniform and weighted  - the reference

Usage:
  pip install numpy pymatching
  scp -r arduino@10.0.34.98:~/ArduinoApps/qec_lab/python/runs ./runs
  python3 tools/qec_offline.py ./runs            # all runs
  python3 tools/qec_offline.py ./runs <run-name> # one run
Writes <runs>/offline_<run>.csv next to the data.
"""
import ctypes, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
import qec_common as qc  # noqa: E402

try:
    import pymatching
except ImportError:
    pymatching = None
    print("note: pymatching not installed -> `pip install pymatching` for the MWPM reference")

SHIM = r"""
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
"""


def build_lib():
    tmp = Path(tempfile.mkdtemp())
    src = tmp / "shim.cpp"
    src.write_text(SHIM % (HERE.parent / "sketch" / "qec_decoders.h"))
    lib = tmp / "libqecshim.so"
    subprocess.run(["g++", "-O2", "-shared", "-fPIC", "-w", "-o", str(lib), str(src)], check=True)
    so = ctypes.CDLL(str(lib))
    so.decode_batch.restype = ctypes.c_int
    return so


def c_fails(so, rows, d, rounds, truth, caps, weighted):
    rows = np.ascontiguousarray(rows, dtype=np.uint8)
    caps = np.ascontiguousarray(caps, dtype=np.uint8)
    return so.decode_batch(d, rounds, truth, rows.ctypes.data_as(ctypes.c_void_p), rows.shape[0], rows.shape[1],
                           caps.ctypes.data_as(ctypes.c_void_p), int(weighted))


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
    cols = ["d", "shots", "p_data", "p_meas", "majority", "uf", "uf_weighted"] + (["pm", "pm_weighted"] if pymatching else [])
    print(f"\n== {name}  ({meta.get('backend')}, job {meta.get('job_id', '-')}, {R} rounds) ==")
    print("  ".join(f"{c:>11}" for c in cols))
    lines = [",".join(cols)]
    for d in dists:
        edges, B = qc.build_graph(d, R)
        dets = {t: qc.detection_events(raw[(d, t)], d, R) for t in (0, 1)}
        model = qc.summarize_probs(qc.estimate_edge_probs(np.concatenate([dets[0], dets[1]]), edges, B), edges)
        n = sum(len(raw[(d, t)]) for t in (0, 1))
        f = {"majority": 0, "uf": 0, "uf_weighted": 0, "pm": 0, "pm_weighted": 0}
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
        vals = [str(d), str(n), f"{model['p_data']:.4f}", f"{model['p_meas']:.4f}"] + [fmt(f[c], n) for c in cols[4:]]
        print("  ".join(f"{v:>11}" for v in vals))
        lines.append(",".join([str(d), str(n), f"{model['p_data']:.5f}", f"{model['p_meas']:.5f}"] + [str(f[c] / n) for c in cols[4:]]))
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
