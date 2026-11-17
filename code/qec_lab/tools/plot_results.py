#!/usr/bin/env python3
"""Plot logical error vs code distance for one saved run, including the readout-only baselines.

Graph decoders and the MLP come from the offline CSV (tools/qec_offline.py). The two baselines that use only the final
data bits (threshold on the number of 1s; per-qubit naive Bayes) are computed here from the raw shots, with the same
2-fold split as qec_ai.cross_val (seed 1).

Usage (repo root):
  python3 code/qec_lab/tools/plot_results.py data/ibm_runs <run-name> media/out.png "<label>"
"""
import csv, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python"))
import qec_common as qc  # noqa: E402

runs, name, dest, label = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
DS = (3, 5, 7, 9, 11)
rows = {int(r["d"]): r for r in csv.DictReader(open(runs / f"offline_{name}.csv"))}
raw, meta = qc.load_run(runs, name)
R = meta["rounds"]
N = int(rows[DS[0]]["shots"])
FLOOR = 0.5 / N                                     # where "0 failures" is drawn


def readout_baselines(d):
    """Failures of the threshold and naive-Bayes rules on the final data bits (cross-fitted)."""
    al = np.concatenate([raw[(d, 0)], raw[(d, 1)]])
    truth = np.repeat([0, 1], [len(raw[(d, 0)]), len(raw[(d, 1)])])
    X = al[:, R * (d - 1):].astype(float)
    ones = X.sum(1)
    fold = np.random.default_rng(1).permutation(len(al)) % 2
    thr = nb = 0
    for k in (0, 1):
        tr, te = fold != k, fold == k
        best = min(range(d + 2), key=lambda th: ((ones[tr] >= th).astype(int) != truth[tr]).sum())
        thr += int(((ones[te] >= best).astype(int) != truth[te]).sum())
        ll = np.zeros((te.sum(), 2))
        for c in (0, 1):
            sel = tr & (truth == c)
            p = (X[sel].sum(0) + 1) / (sel.sum() + 2)
            ll[:, c] = (X[te] * np.log(p) + (1 - X[te]) * np.log(1 - p)).sum(1) + np.log(sel.sum() / tr.sum())
        nb += int((ll.argmax(1) != truth[te]).sum())
    return thr / len(al), nb / len(al)


col = lambda k: [float(rows[d][k]) for d in DS]
base = [readout_baselines(d) for d in DS]
series = [  # values, label, colour, linestyle, marker, width
    (col("majority"), "Majority vote", "#222222", ":", "o", 3.0),
    (col("uf_weighted"), "Weighted union-find, per-state weights (STM32)", "#0b2a78", "-", "o", 4.5),
    (col("pm_w_mixed"), "MWPM, mixed weights (PyMatching)", "#9a3b00", "--", "D", 3.0),
    ([b[1] for b in base], "Naive Bayes on final data bits (no syndromes)", "#0f6b3a", "-", "v", 4.5),
    ([b[0] for b in base], "Threshold on final data bits (no syndromes)", "#58b97f", "--", "s", 2.6),
    (col("ai"), "MLP: syndromes + final data bits (STM32)", "#7a0a50", "-", "^", 4.5),
]
fig, ax = plt.subplots(figsize=(10, 7.2), dpi=200)
for vals, lab, c, ls, m, lw in series:
    y = [v if v > 0 else FLOOR for v in vals]
    ax.plot(DS, y, ls=ls, color=c, lw=lw, zorder=3 if lw > 4 else 2)
    for d, v in zip(DS, vals):                       # hollow marker = 0 failures
        ax.plot([d], [v if v > 0 else FLOOR], marker=m, ms=9, color=c, mfc=c if v > 0 else "white", mec=c if v == 0 else "white",
                mew=1.6, zorder=4)
    ax.plot([], [], ls=ls, marker=m, color=c, lw=lw, ms=8, mec="white", label=lab)
ax.set_yscale("log")
ax.axhspan(FLOOR / 1.35, FLOOR * 1.35, color="#e9e9e9", zorder=0)
ax.text(DS[0] - 0.25, FLOOR, f"0 of {N:,}", va="center", ha="left", fontsize=10, color="#555")
ax.set_ylim(FLOOR / 1.35, None)
ax.set_xticks(DS); ax.set_xticklabels([f"d={k}\n({2 * k - 1} qubits)" for k in DS], fontsize=13)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{100 * v:g}%"))
ax.tick_params(axis="y", labelsize=13)
ax.grid(True, which="major", color="#c8c8c8", lw=1)
for s in ("top", "right"): ax.spines[s].set_visible(False)
for s in ("left", "bottom"): ax.spines[s].set_linewidth(1.6)
ax.set_xlabel("Code distance", fontsize=13, fontweight="bold")
ax.set_ylabel(f"Logical error per shot ({R} rounds)", fontsize=13, fontweight="bold")
ax.set_title(f"{label}: logical error vs distance, with readout-only baselines", fontsize=15, fontweight="bold", pad=12)
ax.legend(fontsize=10.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
fig.text(0.5, 0.012, f"job {meta.get('job_id', '-')} · {N:,} shots per distance · learned decoders cross-fitted on two halves · "
         "hollow marker = 0 failures", ha="center", fontsize=9.5, color="#444")
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(dest, bbox_inches="tight"); print("wrote", dest, [tuple(round(x * N) for x in b) for b in base])
