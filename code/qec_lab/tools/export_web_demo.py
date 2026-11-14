#!/usr/bin/env python3
"""Export real QEC Lab data for the interactive web demo (docs/demo/data.js).

Everything in the web demo comes from real runs:
  * error rates per decoder and distance: the offline CSVs (tools/qec_offline.py, all 4,000 shots per distance)
  * individual shots: real IBM shots; decoded here with majority vote, the board's own weighted union-find
    (compiled from ../sketch/qec_decoders.h, weights per logical state from the other half of that state's shots)
    and the AI decoder (cross-fitted on two halves: every shot decoded by a network that never saw it)
  * timing: STM32 measurements from results/results_tables.md (sections 2 and 6)

Usage (from the repo root):  python3 code/qec_lab/tools/export_web_demo.py data/ibm_runs docs/demo/data.js
"""
import csv, ctypes, json, subprocess, sys, tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "python"))
import qec_common as qc  # noqa: E402
import qec_ai  # noqa: E402

RUNS = [  # (run name, label)
    ("20261114-171154_ibm_marrakesh_r3", "ibm_marrakesh"),
    ("20261114-181148_ibm_fez_r3", "ibm_fez (run 3)"),
    ("20261114-163126_ibm_fez_r3", "ibm_fez (run 2)"),
    ("20261114-162418_ibm_fez_r3", "ibm_fez (run 1)"),
]
SHOT_RUNS = RUNS[:2]
SHOT_DS = (3, 5, 7)
N_RANDOM, N_PICKED = 300, 60

SHIM = r"""
#include "%s"
extern "C" void uf_outputs(int d, int r, const unsigned char* rows, int nshots, int nbits,
                           const unsigned char* caps, unsigned char* out) {
  qec::configure(d, r);
  for (int e = 0; e < qec::E; e++) qec::capWeighted[e] = caps[e];
  for (int s = 0; s < nshots; s++) {
    for (int b = 0; b < nbits; b++) qec::bits[b] = rows[s * nbits + b];
    qec::computeDetectors();
    out[s] = qec::decodeUnionFindFast(qec::capWeighted);
  }
}
"""

# STM32 measurements (results/results_tables.md section 6: ibm_marrakesh, d=5, 3 rounds, interrupts on)
TIMING = {
    "d": 5, "rounds": 3, "backend": "ibm_marrakesh",
    "decoders": [
        {"key": "ai", "name": "AI (neural net)", "mean_us": 26.0, "limit_us": 8.7, "kept_up": [10, 30], "fell_behind": [5.6, 2214]},
        {"key": "ufw", "name": "Union-find weighted", "mean_us": 25.9, "limit_us": 8.6, "kept_up": [10, 47], "fell_behind": [5.6, 2219]},
        {"key": "uff", "name": "Union-find fast", "mean_us": 31.0, "limit_us": 10.4, "kept_up": [17.8, 15], "fell_behind": [10, 456]},
        {"key": "ufn", "name": "Union-find naive", "mean_us": 59.3, "limit_us": 19.8, "kept_up": [31.6, 8], "fell_behind": [17.8, 523]},
    ],
}


def build_lib():
    tmp = Path(tempfile.mkdtemp())
    (tmp / "s.cpp").write_text(SHIM % (HERE.parent / "sketch" / "qec_decoders.h"))
    subprocess.run(["g++", "-O2", "-shared", "-fPIC", "-w", "-o", str(tmp / "s.so"), str(tmp / "s.cpp")], check=True)
    return ctypes.CDLL(str(tmp / "s.so"))


def uf_out(so, rows, d, R, caps):
    rows = np.ascontiguousarray(rows, dtype=np.uint8)
    caps = np.ascontiguousarray(caps, dtype=np.uint8)
    out = np.zeros(len(rows), dtype=np.uint8)
    p = lambda a: a.ctypes.data_as(ctypes.c_void_p)
    so.uf_outputs(d, R, p(rows), rows.shape[0], rows.shape[1], p(caps), p(out))
    return out


def rates(runs_dir, name):
    out = {}
    with open(runs_dir / f"offline_{name}.csv") as f:
        for r in csv.DictReader(f):
            g = lambda k: float(r[k]) if r.get(k) not in (None, "") else None
            out[int(r["d"])] = {"shots": int(r["shots"]), "majority": g("majority"), "ufw": g("uf_weighted"),
                                "pm": min(g("pm_weighted"), g("pm_w_mixed")), "ai": g("ai")}
    return [dict(d=d, **v) for d, v in sorted(out.items())]


def shots_for(so, raw, d, R, rng):
    edges, B = qc.build_graph(d, R)
    rows_all = np.concatenate([raw[(d, 0)], raw[(d, 1)]])
    truth = np.repeat(np.array([0, 1], dtype=np.uint8), [len(raw[(d, 0)]), len(raw[(d, 1)])])
    maj = qc.majority_logical(rows_all, d, R)
    # weighted union-find: weights per state from the other half of that state's shots (as tools/qec_offline.py)
    ufw = np.zeros(len(rows_all), dtype=np.uint8)
    off = 0
    for t in (0, 1):
        rows = raw[(d, t)]
        det = qc.detection_events(rows, d, R)
        half = len(rows) // 2
        for (a, b), other in (((0, half), slice(half, None)), ((half, len(rows)), slice(0, half))):
            caps = qc.probs_to_caps(qc.estimate_edge_probs(det[other], edges, B))
            ufw[off + a:off + b] = uf_out(so, rows[a:b], d, R, caps)
        off += len(rows)
    # AI: 2-fold cross-fitting, same split as qec_ai.cross_val
    ai = np.zeros(len(rows_all), dtype=np.uint8)
    fold = np.random.default_rng(1).permutation(len(rows_all)) % 2
    for k in (0, 1):
        m = qec_ai.train(rows_all[fold != k], truth[fold != k], d, R)
        ai[fold == k] = qec_ai.predict(m, rows_all[fold == k])
    full = {"majority": float((maj != truth).mean()), "ufw": float((ufw != truth).mean()), "ai": float((ai != truth).mean()),
            "n": int(len(truth))}
    rand = rng.choice(len(rows_all), N_RANDOM, replace=False)
    disagree = np.flatnonzero((ai != ufw) | (maj != ufw))
    disagree = np.setdiff1d(disagree, rand)
    picked = rng.choice(disagree, min(N_PICKED, len(disagree)), replace=False) if len(disagree) else np.array([], int)
    out = []
    for idx, flag in [(i, 0) for i in rand] + [(i, 1) for i in picked]:
        r = rows_all[idx]
        out.append({"b": "".join(map(str, r)), "t": int(truth[idx]), "m": int(maj[idx]), "u": int(ufw[idx]),
                    "a": int(ai[idx]), "p": flag})
    return {"d": d, "rounds": R, "full": full, "shots": out}


def main():
    runs_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/ibm_runs")
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/demo/data.js")
    so = build_lib()
    rng = np.random.default_rng(2026)
    data = {"runs": [], "shots": {}, "timing": TIMING}
    for name, label in RUNS:
        meta = json.loads((runs_dir / f"{name}.json").read_text())
        data["runs"].append({"key": name, "label": label, "backend": meta["backend"], "job": meta.get("job_id"),
                             "rounds": meta["rounds"], "rates": rates(runs_dir, name)})
    for name, label in SHOT_RUNS:
        raw, meta = qc.load_run(runs_dir, name)
        data["shots"][name] = {"label": label, "sets": [shots_for(so, raw, d, meta["rounds"], rng) for d in SHOT_DS]}
        for s in data["shots"][name]["sets"]:
            print(f"{label} d={s['d']}: full-stat errors maj {s['full']['majority']:.4f} ufw {s['full']['ufw']:.4f} "
                  f"ai {s['full']['ai']:.4f}  exported {len(s['shots'])} shots")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("// generated by code/qec_lab/tools/export_web_demo.py from real IBM runs\nwindow.QEC_DATA = "
                    + json.dumps(data, separators=(",", ":")) + ";\n")
    print(f"wrote {dest} ({dest.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
