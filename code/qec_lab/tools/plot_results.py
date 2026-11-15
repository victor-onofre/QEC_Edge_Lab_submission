#!/usr/bin/env python3
"""Plot logical error vs code distance from an offline CSV (tools/qec_offline.py output).
Usage: python3 code/qec_lab/tools/plot_results.py data/ibm_runs/offline_<run>.csv media/out.png "<backend> job <id>"
"""
import csv, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

src, dest, label = sys.argv[1], sys.argv[2], sys.argv[3]
rows = [r for r in csv.DictReader(open(src)) if int(r["d"]) <= 11]
d = [int(r["d"]) for r in rows]
col = lambda k: [float(r[k]) for r in rows]
series = [("majority", "Majority vote", "#222222", ":", "o", 3.5),
          ("uf", "Union-find", "#5a5a5a", "-", "s", 3.5),
          ("pm_weighted", "PyMatching weighted (reference)", "#9a3b00", "--", "D", 3.5),
          ("uf_weighted", "Weighted union-find (Arduino, classical)", "#0b2a78", "-", "o", 5.5),
          ("ai", "Neural-network decoder (Arduino, AI)", "#7a0a50", "-", "^", 5.5)]
fig, ax = plt.subplots(figsize=(10, 5.8), dpi=200)
for key, name, c, ls, m, lw in series:
    ax.plot(d, col(key), ls=ls, marker=m, color=c, lw=lw, ms=9 if lw > 4 else 7, mec="white", mew=1.2, label=name,
            zorder=3 if lw > 4 else 2)
ax.set_yscale("log")
ax.set_xticks(d); ax.set_xticklabels([f"d={k}\n({2 * k - 1} qubits)" for k in d], fontsize=13)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{100 * v:g}%"))
ax.tick_params(axis="y", labelsize=13)
ax.grid(True, which="major", color="#c8c8c8", lw=1)
for s in ("top", "right"): ax.spines[s].set_visible(False)
for s in ("left", "bottom"): ax.spines[s].set_linewidth(1.6)
ax.set_xlabel("Code distance (more qubits →)", fontsize=13, fontweight="bold")
ax.set_ylabel("Logical error per shot", fontsize=13, fontweight="bold")
ax.set_title("More qubits, fewer errors — and the AI decoder makes the fewest", fontsize=16, fontweight="bold", pad=14)
ai, best = col("ai"), [min(float(r[k]) for k in ("uf", "uf_weighted", "pm_weighted", "pm_w_mixed")) for r in rows]
i = max(range(len(d)), key=lambda k: best[k] / ai[k])
ax.annotate(f"AI {100 * ai[i]:.2g}% vs {100 * best[i]:.2g}%\n({best[i] / ai[i]:.1f}× fewer errors)", (d[i], ai[i]),
            xytext=(-150, -6), textcoords="offset points", fontsize=13, fontweight="bold", color="#7a0a50", va="center")
ax.legend(fontsize=11.5, frameon=False, loc="lower left")
fig.text(0.5, 0.012, f"{label} · 3 rounds · 4,000 shots per distance · AI scored on held-out shots", ha="center", fontsize=9.5, color="#444")
fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(dest); print("wrote", dest)
