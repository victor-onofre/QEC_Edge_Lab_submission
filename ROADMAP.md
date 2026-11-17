# QEC Edge Lab: what next

Written 2026-11-16, after Junction Finland 2026. The goal is no longer to win anything; it is to do the most
interesting and most honest work one person can do with this hardware.

## 1. First, a correction to the headline AI claim

A check on the saved shots (same 2-fold split as `qec_ai.cross_val`) shows that a **one-parameter rule that ignores
every syndrome** does as well as, or better than, the neural network on ibm_fez for d ≥ 5 (at d = 3 the network is still ahead). The rule: count the 1s in the final
data readout and compare with a threshold chosen on the training half ("if enough 1s survived, it was a 1").

Failures out of 4,000 shots:

| Chip (run) | Qubits (d) | Majority vote | Threshold rule | Naive Bayes (final bits) | Neural network | Best graph decoder |
|---|---|---|---|---|---|---|
| ibm_fez (fez-2) | 9 (5) | 80 | **4** | **4** | 20 | 39 |
| ibm_fez (fez-2) | 13 (7) | 32 | **0** | **0** | 9 | 16 |
| ibm_fez (fez-2) | 17 (9) | 19 | **0** | **0** | 9 | 4 |
| ibm_fez (fez-2) | 21 (11) | 10 | **0** | **0** | 12 | 3 |
| ibm_marrakesh | 9 (5) | 391 | 181 | 104 | **72** | 144 |
| ibm_marrakesh | 13 (7) | 260 | 65 | 20 | **9** | 67 |
| ibm_marrakesh | 17 (9) | 122 | 13 | **2** | **2** | 19 |

"Best graph decoder" is the lowest of union-find, weighted union-find and the three PyMatching variants. Run names as in the README.

What it means:

- The "2–9.5× fewer errors than classical" ratio mostly measures a **missing prior** in the graph decoders (they are
  never told that a stored 1 decays and a stored 0 does not), not learning by the network.
- On ibm_fez, for d ≥ 5, the network is **worse** than the trivial rule; its "error floor" at d ≥ 11 is a training weakness.
- On ibm_marrakesh the network beats the threshold rule, but a per-qubit naive-Bayes rule on the final bits gets most of
  the way there and matches it at d = 9. On that chip data qubit 0 (physical qubit 82), which is the logical observable,
  is nearly uninformative, so the comparison mostly measures how decoders cope with one dead qubit.
- Not affected: decoder timings, the union-find work, the real-time replay, error suppression with distance.

The README on `main` and its two result charts are corrected (section 5.3; charts drawn by `tools/plot_results.py`, which
now computes the threshold and naive-Bayes baselines). The slides, the video, the demo page and
`results/results_tables.md` still state the old claim.

Related published work: a neural repetition-code decoder on IBM hardware with ~700× more data (FiLM, arXiv:2601.16123).

## 2. Directions

Effort in evenings (ev) or weeks (wk). QPU time in seconds; the current 16-circuit job takes about 6 s.

| # | Direction | Why it is interesting | First evening | Effort / cost / QPU | Main risk |
|---|---|---|---|---|---|
| 1 | **What does the network really learn?** Threshold and naive-Bayes baselines are done (in `tools/plot_results.py` and the README). Still to do: move them into `tools/qec_offline.py`, add an exact maximum-likelihood decoder, Wilson error bars, a final-bits-only MLP and a per-state failure split, then regenerate `results/results_tables.md` | Decides what everything else builds on | Port the baselines into the offline tool | 1–2 ev / €0 / 0 | The headline deflates (it already has) |
| 2 | **State-independent memory experiment:** hide a random, known X-frame on the data qubits (undone before decoding), or add a mid-circuit X echo | Separates learned correlations from a state prior | Add random `x()` and frame bookkeeping to `rep_code_circuit` | 3 ev / €0 / ~15 s | Any AI advantage vanishes (still a result) |
| 3 | **Phase-flip code** next to the bit-flip code | T2 instead of T1; symmetric noise | H-conjugate the circuit | 2 ev / €0 / ~10 s | Dephasing swamps the suppression |
| 4 | **Many rounds, real statistics:** R = 3…30, 20,000+ shots, error per round | Syndromes finally matter; no more "handful of failures" | Raise `MAX_R` and shots; fit error per round | 1 wk / €0 / 1–2 min | MCU RAM for long shots |
| 5 | **General-graph union-find on the MCU from a Stim detector error model;** surface code d=3, 5 (simulated data) | Leaves 1-D; reusable core. FPGA/ASIC versions exist, no Cortex-M one found | Stim + PyMatching on the laptop; emit a rep-code model; diff against the current decoder | 2–3 wk / €0 / 0 | Peeling and boundaries in 2-D are fiddly |
| 6 | **Embedded decoder benchmark suite:** cycles, RAM, µJ per decode across microcontrollers | Appears to be a gap | JSON result schema; run on the UNO Q | 3–4 wk after #5 / €10–20 / 0 | Nobody uses it |
| 7 | **Power measurement** | Closes a stated hole | Idle / decode / train on a USB meter; later a shunt on the MCU rail | 1–2 ev / €5–15 / 0 | Linux side dominates the reading |
| 8 | **Hardware-in-the-loop "fake QPU":** a second MCU streams syndromes over SPI at hardware-timed τ; the Arduino returns corrections by a deadline pin | A real closed loop with measurable jitter, no Bridge | A Pico bit-bangs stored shots; scope the deadline | 2 wk / €15–25 / 0 | Zephyr interrupt latency |
| 9 | **Sliding-window streaming decoder** with a worst-case time bound | Unbounded rounds in fixed RAM; "fixed latency" becomes a real claim | Window over the existing union-find on a simulated R=100 run | 2 wk / €0 / 0 | Seams between windows |
| 10 | **Erasure- and loss-aware union-find;** how many logical qubits per board at 1 ms rounds | Matches neutral atoms; turns "100× headroom" into a number | Stim circuit with heralded erasure, zero-weight edges | 2–3 wk / €0 / 0 | Simulation only |
| 11 | **Soft-information decoding** with 8-bit IQ values | Per-shot weights instead of fixed ones | Check whether the Open Plan returns kerneled data | 1–2 wk / €0 / ~30 s | Access unverified; already published (arXiv:2411.16228) |
| 12 | **Feed-forward on IBM** (`if_test`) | Real active correction | Reproduce IBM's repetition-code tutorial at d=3 | 3 ev / €0 / ~1 min | The decoder runs in IBM's controller, not the Arduino |
| 13 | **"Chip weather station":** a daily 6 s job, on-board retrain, per-qubit drift log | Honest use of on-device training; a long time series | Cron job + CSV append | 2 ev then passive / €0 / ~3 min per month | Queue times |
| 14 | **FPGA port** (Tang Nano / iCE40) | Learn HDL; reach ~1 µs | Lookup-table decoder for d=3 | 4+ wk / €15–30 / 0 | Time sink; heavily trodden |
| 15 | **Short write-up:** "What a neural decoder learns in a repetition-code memory experiment" (from #1–4) | A clarifying result is useful | Outline + the table above | 1 wk / €0 / 0 | Needs care |
| 16 | **Calibration-aware qubit selection and run metadata:** choose the line of qubits from IBM's calibration data (T1, readout error, CZ error) instead of a random walk; avoid putting the logical observable on a bad qubit; save T1/T2, readout error and gate, measurement and reset durations with every run | On ibm_marrakesh the observable sat on a nearly dead qubit (physical 82), which dominates that run; and the T1 explanation of the state-dependent noise cannot be checked without durations | Score candidate lines from `backend.properties()` / `backend.target` in `find_line`; write the calibration snapshot into the run's JSON | 1–2 ev / €0 / 0 (needs one new job to show the effect, ~6 s) | Calibration data can be stale; the best line changes from day to day |

## 3. Ranked by interest per hour

1. #1: free, and it changes the story.
2. #16: one or two evenings, and it removes the largest known flaw in the data before any new QPU time is spent.
3. #2 and #3 together: one IBM job, under 30 s of QPU time.
4. #4: makes every number defensible.
5. #5: unlocks #6, #9 and #10.
6. #7: one evening, removes a caveat.

## 4. Suggested roadmap (5–6 weeks)

- **Week 1:** #1 with error bars, and #16. Output: corrected results tables; a calibration-aware `find_line` that stores a calibration snapshot with each run.
- **Week 2:** one IBM job covering #2, #3 and #4 on two chips, on qubit lines chosen by #16. Output: AI vs threshold vs matching, state-dependent vs state-independent.
- **Weeks 3–4:** #5, surface code d=3, 5 on the MCU against PyMatching. Output: cycles vs distance for a 2-D code.
- **Week 5:** #7, and a start on #8 or #10. Output: µJ per decode; logical qubits per board at 1 ms.
- **Week 6:** #15.

## 5. Not worth doing

- Bigger networks, CMSIS-NN or TFLite Micro: 737 parameters, a first layer that is already additions, and 4,000 shots cannot feed more.
- Chasing 1 µs per round on a Cortex-M: that is FPGA territory.
- The Arduino in a live loop with a cloud quantum computer: network milliseconds, and no external-controller hook.
- Paid neutral-atom or ion QPU time for QEC: no free public route found; simulate with Stim.
- More repetition-code neural results without #1 and #2.

## 6. Access facts to verify

- IBM Open Plan: 10 minutes per 28 days; dynamic circuits reported available on all backends.
- IQM Resonance: a free Starter tier was announced in 2025; confirm it still exists.
- AWS Braket: the free tier is simulator only.

## 7. Hardware: which pack for which idea

Checked 2026-11-16 on store.arduino.cc. The UNO Q 2GB, Modulino Knob and Modulino Buzzer used so far were on loan from the
hackathon organisers, so continuing on hardware means buying a board. Recommended: the SBC Controller Bundle (€82,73) plus a
Modulino Buzzer (€7,30), about €90: it costs €14 more than a 2GB board with a Knob and Buzzer (€76,20) and adds the 4GB/32GB
board, Pixels, Joystick and Buttons. Roadmap steps 1–4 can start on a laptop without a board (decoders compile on the laptop;
IBM jobs can be sent from it); the board is needed for on-chip timing, the real-time replay and the demos.

### What the Arduino packs contain

| Pack | Contents | Price | Parts bought separately |
|---|---|---|---|
| Arcade Bundle | UNO Q 4GB, Modulino Buttons, Joystick, Movement | €78,29 | €120,45 |
| DIY Synth Bundle | UNO Q 4GB, Modulino Knob, Buttons, Movement, Distance | €82,35 | €126,80 |
| SBC Controller Bundle | UNO Q 4GB, Modulino Buttons, Joystick, Knob, Pixels | €82,73 | €127,25 |
| UNO Q 4GB alone | – | €82,90 | – |
| UNO Q 2GB alone | – | €59,90 | – |

Only the SBC Controller contents were read from its product page; Arcade and Synth come from search snippets and from
the part prices adding up exactly to the "was" price (the store rate-limited the other pages). Every bundle costs less
than a bare 4GB board, so a bare 4GB board is never the right purchase. The discounts look promotional; no end date found.

### What each direction needs

| Directions | Extra hardware | Best part | Arduino pack useful? |
|---|---|---|---|
| 1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 15 | Nothing | – | No |
| 6 Benchmark suite | Other microcontrollers | Raspberry Pi Pico 2 (~€6), Pico (~€5), ESP32-C3 (~€4) | No: a second UNO Q has the same STM32 |
| 7 Power | Current measurement | USB-C meter (€10–35) for the whole board; INA226 breakout (~€4) | No |
| 8 Fake QPU | Second MCU, wires, a way to see the deadline pin | Pico 2 (~€6), 24 MHz logic analyser (~€10), jumpers (~€4) | A second UNO Q works, but a Pico is cheaper and gives an independent clock |
| 14 FPGA | FPGA board | Tang Nano 9K (~€20) | No |
| Demos and outreach | Display and inputs | Modulino Pixels, Buttons, Joystick | Yes: SBC Controller Bundle, or the three loose (€35,35) |

Non-Arduino prices are typical EU figures, not checked on the day.

UNO Q pitfalls (from the datasheet; not tested):

- **Power (#7):** the 3.3 V rail feeds the STM32 together with the Wi-Fi domain and other chips, with no documented
  isolation jumper, so the microcontroller's own power probably cannot be measured on this board, only the whole board's.
  For true µJ per decode, a same-family board with a current jumper (NUCLEO-U545RE-Q, ~€18, to be verified) is a proxy.
- **Fake QPU (#8):** header pins are STM32 pins at 3.3 V, so a Pico connects directly; D3, A0 and A1 are not 5 V tolerant.
  SPI slave mode on the Zephyr-based core is unverified: make the UNO Q the SPI master with a data-ready pin, or use the UART.
- **Benchmarks (#6):** the timing uses the DWT cycle counter, which Cortex-M0+ and RISC-V boards do not have.
- **Many rounds (#4):** `MAX_R = 10` in `qec_decoders.h`; buffers need resizing.

### Shopping lists

| Goal | Items | Total | Arduino pack? |
|---|---|---|---|
| Science first (#1, #2+#3, #4, #5, #7) | USB-C meter, INA226, jumpers | ~€18 | No |
| Closed-loop hardware (#6–8) | 2× Pico 2, logic analyser, breadboard and wires, INA226 | ~€34 | No |
| Fun and outreach | Modulino Pixels + Buttons + Joystick | €35,35 | Only if a second board is wanted: then the SBC Controller Bundle (€82,73) |

Not worth buying: a bare UNO Q 4GB; the Synth Bundle (duplicate Knob; Movement and Distance unused); the SPE, relay,
motor or proto shields; Modulino Thermo (cycle counts do not depend on temperature, and it reads room temperature);
a Nordic PPK2; an FPGA board before #5 is done.

### Ideas the packs would enable

| Idea | Part | Effort | Value |
|---|---|---|---|
| Decoder microscope: the knob single-steps union-find growth and peeling; Pixels show the current round's checks | Pixels | 2 ev | Medium: a real debugging aid for #5 and #9 |
| Human versus decoder: people decode displayed syndromes with Buttons; log accuracy and latency | Buttons + Pixels | 2–3 ev | Toy to medium; good outreach |
| Adversarial error hunt: place errors with the Joystick to find patterns where union-find fails and matching does not | Joystick | 3 ev | Medium |
| Twin boards: identical firmware on a second UNO Q for board-to-board timing spread, then use it as the fake QPU | A bundle | 2 ev | Medium |
| Live threshold dial: hand distance sets the physical error rate | Distance | 1 ev | Toy |
| Deadline cliff by ear: the Buzzer clicks on each missed deadline | Already owned | 1 ev | Toy; a sanity check for #8 |

## 8. References

- FiLM neural repetition-code decoder on IBM hardware: https://arxiv.org/abs/2601.16123
- Soft information, "one byte suffices": https://arxiv.org/abs/2411.16228
- FPGA union-find decoder: https://arxiv.org/abs/2406.08491
- Riverlane decoder ASIC: https://arxiv.org/abs/2309.05558
- Hardware decoder: https://arxiv.org/abs/2411.10343
- Sliding-window decoding: https://arxiv.org/abs/2209.09219
- IBM repetition-codes tutorial: https://quantum.cloud.ibm.com/docs/tutorials/repetition-codes
