"""AI decoder: a small neural network (MLP) trained on the device's own shots, pure numpy.

Input  (per shot, binary): detection events (R+1)*W  +  final data bits D
Output: flip = 1 if data qubit 0 must be flipped, i.e. decoded logical = data[0] ^ flip.
The prepared state (truth) is only used as the training label, never as an input.

Network: nin -> H (ReLU) -> 1. Trained in float (Adam, logistic loss), then quantised to
15-bit integers so the STM32 (sketch/qec_ai.h) and Python compute the SAME integer result:
  h_j = relu(b1[j] + sum_{i: x_i = 1} W1[i][j])         (int32, inputs are 0/1 -> adds only)
  z   = b2 + sum_j h_j * W2[j]                           (int64)      flip = z > 0
"""
import numpy as np
import qec_common as qc

MAX_IN, MAX_H = 128, 32          # must match sketch/qec_ai.h
QMAX = 16383                     # 15-bit signed weights (offset-packed, two per 30-bit word)


def n_inputs(d, rounds):
    return (rounds + 1) * (d - 1) + d


def fits(d, rounds):
    return n_inputs(d, rounds) <= MAX_IN


def features(rows, d, rounds):
    det = qc.detection_events(rows, d, rounds)
    return np.concatenate([det, rows[:, rounds * (d - 1):]], axis=1).astype(np.uint8)


def train(rows, truth, d, rounds, hidden=MAX_H, steps=2000, lr=3e-3, l2=1e-3, batch=128, seed=0):
    """rows: (n, nbits) uint8 shots of BOTH logical states, truth: (n,) labels. Returns an int model."""
    X = features(rows, d, rounds).astype(np.float32)
    y = (np.asarray(truth, dtype=np.uint8) ^ rows[:, rounds * (d - 1)]).astype(np.float32)
    rng = np.random.default_rng(seed)
    n, k = X.shape
    P = [rng.normal(0, 1 / np.sqrt(k), (k, hidden)).astype(np.float32), np.zeros(hidden, np.float32),
         rng.normal(0, 1 / np.sqrt(hidden), hidden).astype(np.float32), np.zeros(1, np.float32)]
    M = [np.zeros_like(p) for p in P]
    V = [np.zeros_like(p) for p in P]
    for t in range(1, steps + 1):
        j = rng.integers(0, n, min(batch, n))
        x, yy = X[j], y[j]
        h = np.maximum(0, x @ P[0] + P[1])
        z = np.clip(h @ P[2] + P[3][0], -30, 30)
        g = (1 / (1 + np.exp(-z)) - yy) / len(j)
        gh = np.outer(g, P[2]) * (h > 0)
        grads = [x.T @ gh + l2 * P[0], gh.sum(0), h.T @ g + l2 * P[2], np.array([g.sum()], np.float32)]
        for p, gr, m, v in zip(P, grads, M, V):
            m *= 0.9
            m += 0.1 * gr
            v *= 0.999
            v += 0.001 * gr * gr
            p -= lr * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
    return quantize(P, d, rounds)


def quantize(P, d, rounds):
    W1, b1, W2, b2 = P
    s1 = QMAX / max(1e-12, float(np.abs(np.concatenate([W1.ravel(), b1])).max()))
    s2 = QMAX / max(1e-12, float(np.abs(W2).max()))
    return {"d": d, "rounds": rounds, "nin": W1.shape[0], "hidden": W1.shape[1],
            "W1": np.rint(W1 * s1).astype(np.int64), "b1": np.rint(b1 * s1).astype(np.int64),
            "W2": np.rint(W2 * s2).astype(np.int64), "b2": int(np.rint(float(b2[0]) * s1 * s2))}


def predict_flip(model, rows):
    """Exact integer inference (same arithmetic as the MCU)."""
    X = features(rows, model["d"], model["rounds"]).astype(np.int64)
    h = np.maximum(0, X @ model["W1"] + model["b1"])
    return ((h @ model["W2"] + model["b2"]) > 0).astype(np.uint8)


def predict(model, rows):
    """Decoded logical value of every shot."""
    return rows[:, model["rounds"] * (model["d"] - 1)] ^ predict_flip(model, rows)


def pack(model):
    """-> (header, words). Values W1 (input-major), b1, W2, offset by 2^14, two per 30-bit word.
    header = (d, rounds, hidden, b2_hi, b2_lo) with b2 = (b2_hi - 2^20) * 2^30 + b2_lo, all non-negative."""
    vals = np.concatenate([model["W1"].ravel(), model["b1"], model["W2"]]) + (QMAX + 1)
    vals = np.concatenate([vals, np.zeros(len(vals) % 2, dtype=np.int64)])
    words = [int(a) | (int(b) << 15) for a, b in zip(vals[0::2], vals[1::2])]
    b2 = model["b2"]
    header = (model["d"], model["rounds"], model["hidden"], (b2 >> 30) + (1 << 20), b2 & ((1 << 30) - 1))
    return header, words


def upload(bcall, model):
    """Send a model to the MCU over Bridge (qec_ai_begin + qec_ai_put, 16 weights per call)."""
    header, words = pack(model)
    if bcall("qec_ai_begin", *header) != 1:
        raise RuntimeError("MCU rejected the AI model")
    for off in range(0, len(words), 8):
        chunk = words[off:off + 8]
        bcall("qec_ai_put", off // 8, *(chunk + [0] * (8 - len(chunk))))
    return bcall("qec_ai_check")


def checksum(model):
    """Sum of all weights mod 2^30 (compared with qec_ai_check on the MCU)."""
    _, words = pack(model)
    return int(sum(words) % (1 << 30))


def cross_val(rows, truth, d, rounds, folds=2, seed=1):
    """Held-out error: every shot is decoded by a model that never saw it. -> (fails, n)."""
    truth = np.asarray(truth, dtype=np.uint8)
    fold = np.random.default_rng(seed).permutation(len(rows)) % folds
    fails = 0
    for k in range(folds):
        m = train(rows[fold != k], truth[fold != k], d, rounds)
        fails += int((predict(m, rows[fold == k]) != truth[fold == k]).sum())
    return fails, len(rows)
