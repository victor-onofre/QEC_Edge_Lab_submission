"""Shared repetition-code helpers (used on the board and by the laptop tool).

Bit layout of one shot (same as the MCU):  s[0][0..W-1], ..., s[R-1][0..W-1], final[0..D-1]
Detector graph (same edge order as qec_decoders.h::configure):
  space edges (t,i)-(t,i+1), then boundary edges (t,0)-B [left] and (t,W-1)-B [right],
  then time edges (t,i)-(t+1,i).
"""
import json, math
from datetime import datetime
from pathlib import Path
import numpy as np


# ---------------- graph ----------------
def build_graph(d, rounds):
    W, T = d - 1, rounds + 1
    B = T * W
    node = lambda t, i: t * W + i
    edges = []                       # (u, v, is_left_boundary, kind)
    for t in range(T):
        for i in range(W - 1):
            edges.append((node(t, i), node(t, i + 1), 0, "space"))
    for t in range(T):
        edges.append((node(t, 0), B, 1, "boundary"))
        edges.append((node(t, W - 1), B, 0, "boundary"))
    for t in range(T - 1):
        for i in range(W):
            edges.append((node(t, i), node(t + 1, i), 0, "time"))
    return edges, B


def detection_events(rows, d, rounds):
    """rows: (shots, R*W + D) uint8 -> (shots, (R+1)*W) detection events."""
    W = d - 1
    n = rows.shape[0]
    s = rows[:, :rounds * W].reshape(n, rounds, W)
    data = rows[:, rounds * W:]
    final = (data[:, :-1] ^ data[:, 1:])[:, None, :]
    layers = np.concatenate([s, final], axis=1)
    prev = np.concatenate([np.zeros((n, 1, W), dtype=rows.dtype), s], axis=1)
    return (layers ^ prev).reshape(n, -1)


def majority_logical(rows, d, rounds):
    data = rows[:, rounds * (d - 1):]
    return (data.sum(axis=1) * 2 > d).astype(np.uint8)


# ---------------- error model from the data ("p_ij" method) ----------------
def estimate_edge_probs(det, edges, B):
    """Estimate the probability of every graph edge from detection-event correlations."""
    x = det.astype(np.float64)
    m = x.mean(axis=0)
    p = np.full(len(edges), 0.01)
    for k, (u, v, _, _) in enumerate(edges):
        if v == B:
            continue
        xij = float(np.mean(x[:, u] * x[:, v]))
        num = 4 * (xij - m[u] * m[v])
        den = 1 - 2 * m[u] - 2 * m[v] + 4 * xij
        val = 1 - num / den if den > 1e-9 else 1.0
        p[k] = 0.5 - 0.5 * math.sqrt(min(1.0, max(0.0, val)))
    incident = {}
    for k, (u, v, _, _) in enumerate(edges):
        incident.setdefault(u, []).append(k)
        if v != B:
            incident.setdefault(v, []).append(k)
    for k, (u, v, _, _) in enumerate(edges):
        if v != B:
            continue
        prod = 1.0
        for k2 in incident[u]:
            if k2 != k:
                prod *= (1 - 2 * p[k2])
        val = (1 - 2 * m[u]) / prod if abs(prod) > 1e-9 else 1.0
        p[k] = 0.5 * (1 - min(1.0, max(-1.0, val)))
    return np.clip(p, 1e-4, 0.45)


def summarize_probs(p, edges):
    kinds = np.array([e[3] for e in edges])
    data_mask = kinds != "time"
    return {"p_data": float(p[data_mask].mean()),
            "p_meas": float(p[~data_mask].mean()) if (~data_mask).any() else 0.0}


def probs_to_caps(p):
    """Integer growth capacities for the weighted union-find (median edge -> 2, like unweighted)."""
    w = np.log((1 - p) / p)
    ref = float(np.median(w))
    return np.clip(np.rint(2 * w / ref), 1, 15).astype(int)


def pack_caps(caps):
    """7 x 4-bit capacities per 31-bit word, in edge order."""
    words = []
    for j in range(0, len(caps), 7):
        w = 0
        for b, c in enumerate(caps[j:j + 7]):
            w |= int(c) << (4 * b)
        words.append(w)
    return words


def pack_bits(row):
    """31 bits per word, LSB first (matches qec::loadWords)."""
    words = []
    for j in range(0, len(row), 31):
        w = 0
        for b, v in enumerate(row[j:j + 31]):
            w |= int(v) << b
        words.append(w)
    return words


# ---------------- run storage ----------------
def save_run(runs_dir, raw, rounds, meta):
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}_{meta.get('backend', 'sim')}_r{rounds}"
    arrays, nbits = {}, {}
    for (d, truth), rows in raw.items():
        key = f"d{d}_t{truth}"
        arrays[key] = np.packbits(rows, axis=1)
        nbits[key] = int(rows.shape[1])
    np.savez_compressed(runs_dir / f"{name}.npz", **arrays)
    (runs_dir / f"{name}.json").write_text(json.dumps(
        {"name": name, "rounds": rounds, "nbits": nbits, "created": stamp, **meta}, indent=1))
    return name


def load_run(runs_dir, name):
    runs_dir = Path(runs_dir)
    meta = json.loads((runs_dir / f"{name}.json").read_text())
    z = np.load(runs_dir / f"{name}.npz")
    raw = {}
    for key, nb in meta["nbits"].items():
        d, t = key[1:].split("_t")
        raw[(int(d), int(t))] = np.unpackbits(z[key], axis=1, count=nb)
    return raw, meta


def list_runs(runs_dir):
    runs_dir = Path(runs_dir)
    if not runs_dir.exists():
        return []
    out = []
    for f in sorted(runs_dir.glob("*.json"), reverse=True):
        if f.name.startswith("results_"):
            continue
        try:
            m = json.loads(f.read_text())
            ds = sorted({int(k[1:].split("_t")[0]) for k in m["nbits"]})
            out.append({"name": m["name"], "backend": m.get("backend", "?"), "rounds": m["rounds"],
                        "distances": ds, "job_id": m.get("job_id", "-"), "created": m.get("created", "")})
        except Exception:
            pass
    return out
