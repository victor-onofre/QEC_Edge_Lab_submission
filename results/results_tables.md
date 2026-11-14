# QEC Edge Lab — results

All numbers come from the files in `data/ibm_runs/` (generated, not retyped). IBM hardware: 156-qubit Heron processors, bit-flip repetition codes, 3 syndrome rounds, 2,000 shots per logical state (|0⟩ and |1⟩) per distance.

## 1. Logical error rate per shot (all 4,000 shots per distance)

Decoded on a laptop with the exact C decoder code that runs on the STM32 (`tools/qec_offline.py`), plus PyMatching as the reference. Decoder weights are learned per logical state from held-out shots.

### ibm_fez, run 1 (job dbs8m78k09pc73avsgh0)

| d | qubits | p_data | p_meas | majority | uf | uf_weighted | pm | pm_weighted |
|---|---|---|---|---|---|---|---|---|
| 3 | 5 | 3.12% | 7.01% | 5.03% | 4.62% | 5.22% | 5.30% | 4.23% |
| 5 | 9 | 2.78% | 6.26% | 2.75% | 2.30% | 2.08% | 2.23% | 1.90% |
| 7 | 13 | 2.59% | 6.18% | 1.07% | 0.55% | 0.35% | 0.53% | 0.30% |
| 9 | 17 | 2.55% | 5.40% | 0.38% | 0.35% | 0.30% | 0.30% | 0.27% |
| 11 | 21 | 2.30% | 4.64% | 0.30% | 2.5e-04 | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |
| 15 | 29 | 2.31% | 4.59% | 5.0e-04 | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |
| 21 | 41 | 2.21% | 4.21% | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |
| 25 | 49 | 2.14% | 4.19% | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |

### ibm_fez, run 2 (job dbs8pivv5hds73dim45g)

| d | qubits | p_data | p_meas | majority | uf | uf_weighted | pm | pm_weighted |
|---|---|---|---|---|---|---|---|---|
| 3 | 5 | 3.18% | 6.66% | 5.15% | 4.85% | 4.83% | 5.55% | 4.52% |
| 5 | 9 | 2.57% | 6.56% | 2.00% | 1.52% | 1.07% | 1.52% | 1.10% |
| 7 | 13 | 2.37% | 6.41% | 0.80% | 0.65% | 0.57% | 0.70% | 0.40% |
| 9 | 17 | 2.46% | 5.64% | 0.47% | 0.27% | 0.18% | 0.22% | 0.10% |
| 11 | 21 | 2.25% | 4.80% | 0.25% | 7.5e-04 | 7.5e-04 | 0.10% | 7.5e-04 |
| 15 | 29 | 2.16% | 4.68% | 7.5e-04 | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |
| 21 | 41 | 2.24% | 4.19% | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |
| 25 | 49 | 2.24% | 4.12% | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |

### ibm_marrakesh (job dbs9cg9abdes73fqsuu0)

| d | qubits | p_data | p_meas | majority | uf | uf_weighted | pm | pm_weighted |
|---|---|---|---|---|---|---|---|---|
| 3 | 5 | 10.77% | 5.66% | 18.25% | 16.12% | 12.20% | 16.93% | 10.57% |
| 5 | 9 | 7.80% | 4.25% | 9.78% | 5.03% | 4.15% | 5.17% | 3.80% |
| 7 | 13 | 6.70% | 4.29% | 6.50% | 2.23% | 1.88% | 2.45% | 1.68% |
| 9 | 17 | 5.84% | 3.56% | 3.05% | 0.73% | 0.53% | 0.65% | 0.47% |
| 11 | 21 | 5.34% | 3.14% | 1.68% | 0.47% | 0.50% | 0.43% | 0.25% |
| 15 | 29 | 5.32% | 3.46% | 1.80% | 0.15% | 0.43% | 0.15% | 0.18% |
| 21 | 41 | 4.74% | 3.35% | 0.68% | 5.0e-04 | 5.0e-04 | 0 (<2.5e-4) | 2.5e-04 |
| 25 | 49 | 4.53% | 3.52% | 0.33% | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) | 0 (<2.5e-4) |

Columns: majority = majority vote of the final data qubits; uf = union-find (uniform weights); uf_weighted = union-find with learned weights (the board's decoder); pm / pm_weighted = PyMatching minimum-weight matching. p_data / p_meas = estimated data and measurement error per round.

## 2. Decoder cost on the STM32 (Cortex-M33 @ 160 MHz, DWT cycle counter)

Average cycles per shot over 400 shots per distance, measured on the board with interrupts masked.

### ibm_fez, run 1 (job dbs8m78k09pc73avsgh0)

| d | majority | greedy | uf_naive | uf_fast | uf_weighted | uf_fast µs | speed-up fast vs naive |
|---|---|---|---|---|---|---|---|
| 3 | 411 | 293 | 3034 | 1266 | 1504 | 7.9 | ×2.4 |
| 5 | 689 | 582 | 6159 | 2522 | 2986 | 15.8 | ×2.4 |
| 7 | 967 | 930 | 9437 | 3590 | 4454 | 22.4 | ×2.6 |
| 9 | 1245 | 1254 | 12468 | 4159 | 5349 | 26.0 | ×3.0 |
| 11 | 1523 | 1618 | 15702 | 4788 | 5950 | 29.9 | ×3.3 |
| 15 | 2079 | 3002 | 22379 | 6336 | 8103 | 39.6 | ×3.5 |
| 21 | 2913 | 5896 | 32459 | 8710 | 11097 | 54.4 | ×3.7 |
| 25 | 3469 | 8554 | 40294 | 10043 | 13482 | 62.8 | ×4.0 |

### ibm_fez, run 2 (job dbs8pivv5hds73dim45g)

| d | majority | greedy | uf_naive | uf_fast | uf_weighted | uf_fast µs | speed-up fast vs naive |
|---|---|---|---|---|---|---|---|
| 3 | 411 | 283 | 3008 | 1232 | 1192 | 7.7 | ×2.4 |
| 5 | 689 | 570 | 5951 | 2280 | 2214 | 14.2 | ×2.6 |
| 7 | 967 | 870 | 9016 | 3140 | 3108 | 19.6 | ×2.9 |
| 9 | 1245 | 1259 | 12328 | 4022 | 3824 | 25.1 | ×3.1 |
| 11 | 1523 | 1640 | 15480 | 4636 | 4732 | 29.0 | ×3.3 |
| 15 | 2079 | 2917 | 22497 | 6368 | 6438 | 39.8 | ×3.5 |
| 21 | 2913 | 5466 | 32728 | 8300 | 8391 | 51.9 | ×3.9 |
| 25 | 3469 | 7714 | 39642 | 9902 | 10247 | 61.9 | ×4.0 |

### ibm_marrakesh (job dbs9cg9abdes73fqsuu0)

| d | majority | greedy | uf_naive | uf_fast | uf_weighted | uf_fast µs | speed-up fast vs naive |
|---|---|---|---|---|---|---|---|
| 3 | 453 | 412 | 4042 | 2518 | 1933 | 15.7 | ×1.6 |
| 5 | 721 | 650 | 7061 | 3288 | 2631 | 20.5 | ×2.1 |
| 7 | 989 | 1309 | 10598 | 4851 | 4316 | 30.3 | ×2.2 |
| 9 | 1257 | 1670 | 13568 | 5224 | 4686 | 32.6 | ×2.6 |
| 11 | 1525 | 2128 | 17178 | 6224 | 5686 | 38.9 | ×2.8 |
| 15 | 2061 | 5096 | 24560 | 9144 | 9348 | 57.1 | ×2.7 |
| 21 | 2865 | 9832 | 35441 | 11529 | 11918 | 72.1 | ×3.1 |
| 25 | 3401 | 13824 | 42073 | 13166 | 14334 | 82.3 | ×3.2 |

All runs: 0 transport mismatches (MCU vs Python majority vote) and 0 disagreements between naive and fast union-find.

## 3. Real-time backlog test on the STM32 (Stage 2)

ibm_fez run 2, d=11, 4,000 shots loaded into STM32 RAM (23.4 KB, 10.2 s over Bridge), transport check passed. Shots replayed as if one syndrome round arrives every τ; interrupts on (realistic). Limit τ* = mean decode time / 3 rounds.

| Decoder | Mean decode per shot | Limit τ* | Last τ that kept up (max backlog) | First τ that fell behind (max backlog) |
|---|---|---|---|---|
| UF fast | 44.4 µs | 14.8 µs/round | 17.8 µs (24) | 10 µs (1,992) |
| UF weighted | 46.5 µs | 15.5 µs/round | 17.8 µs (25) | 10 µs (2,188) |
| UF naive | 124 µs | 41 µs/round | 56 µs (5) | 31.6 µs (1,096) |

At τ = 100 ns the backlog reached 496,233 (fast), 515,835 (weighted) and 1,290,718 shots (naive). Near the limit (17.8 µs, ~83% busy) the p99 latency was already 1.2 ms. In-replay decode time (44 µs) is ~1.5× the isolated measurement (29 µs at d=11) because of detector computation, shot unpacking and interrupts.

## 4. Device findings (per-qubit error, from the d=25 syndromes)

### ibm_fez run 2

Median data qubit error per round: |0⟩ 0.18%, |1⟩ 3.35% (|1⟩ 19× worse, consistent with T1 decay). Median measurement error 3.86%.

| Worst data qubits | physical qubit | \|0⟩ | \|1⟩ |
|---|---|---|---|
| data #20 | 14 | 0.2% | 8.6% |
| data #0 | 82 | 1.6% | 6.5% |
| data #8 | 4 | 0.2% | 6.4% |
| data #15 | 50 | 0.1% | 5.7% |
| data #22 | 18 | 0.0% | 5.7% |

### ibm_marrakesh

Median data qubit error per round: |0⟩ 0.37%, |1⟩ 6.04% (|1⟩ 16× worse, consistent with T1 decay). Median measurement error 1.87%.

| Worst data qubits | physical qubit | \|0⟩ | \|1⟩ |
|---|---|---|---|
| data #0 | 82 | 7.2% | 31.2% |
| data #11 | 26 | 0.4% | 24.3% |
| data #5 | 36 | 0.4% | 12.1% |
| data #18 | 34 | 0.1% | 11.7% |
| data #1 | 76 | 2.9% | 8.8% |

Both chips have the same coupling map, so the same line of physical qubits (82, 81, 76, …) was used on both; its quality differs a lot between the chips.

