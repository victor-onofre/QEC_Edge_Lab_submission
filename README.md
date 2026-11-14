# QEC Edge Lab — a $50 Arduino that corrects real quantum-computer errors

**Junction Finland 2026 · Best use of Arduino UNO Q** · tags: Junction Finland 2026, Arduino UNO Q, Modulino, Edge AI, Quantum computing

The Arduino UNO Q runs error-correction codes on IBM quantum computers, decodes the errors on its own
microcontroller, learns each chip's quirks with an on-device AI decoder (up to 9.5× fewer logical errors than the best classical decoder), and shows with a knob, lights and
sound where real-time decoding breaks.

Live write-up (editable, with diagram and chart): https://claude.ai/artifact/RcepXDPrf9ZojUqimkgxvN

---

## The problem and who it helps

Quantum computers make errors constantly. A classical computer has to find and correct them in real time,
often within about a microsecond per round. Real machines use FPGAs and custom chips next to the cryostat,
so this classical side of quantum computing is expensive and invisible to most people.

QEC Edge Lab puts it on a board you can hold:

- **Students and educators:** see and hear error correction working on real quantum hardware.
- **Quantum-software and control engineers:** a cheap bench for decoder speed and accuracy under embedded limits.
- **Researchers:** real device data (per-qubit error maps, drift between runs) from a free IBM Quantum account.

## Architecture

![Architecture](media/architecture.png)

The UNO Q's two processors split the work like a real quantum control stack:

| Part | Role |
|---|---|
| Linux side (Qualcomm, Debian) | Qiskit, IBM jobs, saved runs, error-model learning, AI training, web dashboard (the host computer) |
| STM32U585 (Cortex-M33, 160 MHz) | Decoders (majority, greedy, union-find naive/fast/weighted, AI), real-time replay, DWT cycle counter (the real-time controller) |
| Bridge RPC | Linux ↔ STM32; used for bulk loads, never inside a timing measurement |
| 8×13 LED matrix | Progress, results as bars, live decoder backlog |
| Modulino Knob | Sets the round time τ in live mode (4 clicks = ×2) |
| Modulino Buzzer | Growls when the decoder falls behind, beeps when a run ends |

## How it works

1. **Accuracy on real hardware.** Bit-flip repetition codes at distance 3–25 (up to 49 qubits), 3 rounds of
   mid-circuit syndrome measurement, logical |0⟩ and |1⟩. A line of qubits with no SWAP gates is found on the
   chip; all 16 circuits go to IBM as one job (~6 s of QPU time). Shots are streamed to the STM32, which decodes
   them and counts CPU cycles per decoder.
2. **Faster, smarter decoders.** A lazy-reset union-find runs 2.4–4× faster on the STM32 with identical results.
   The Linux side learns an error probability for every edge of the decoding graph from the syndromes
   ("p_ij" method), per logical state, and the STM32 uses them as weights. Runs are saved; old IBM jobs can be
   re-imported by ID without QPU time.
3. **Real-time backlog test.** Syndromes are bulk-loaded into STM32 RAM, then replayed as if one round arrived
   every τ. The STM32 decodes in order and records latency and backlog. A sweep finds each decoder's limit;
   in live mode the knob sets τ and the LED matrix and buzzer show the queue filling.
4. **Edge AI decoder** — see below.

## Results (real IBM hardware)

![Logical error vs distance](media/logical_error_vs_distance_ibm_fez.png)

On ibm_fez, going from 5 to 21 qubits cut the logical error from **4.8% to 0.075%** with the board's weighted
union-find decoder. Full tables: [`results/results_tables.md`](results/results_tables.md).

| Finding | Measured |
|---|---|
| Data error per round, \|0⟩ vs \|1⟩ | 0.3–1.2% vs 4.1–5.8% on ibm_fez: \|1⟩ is 10–16× worse, consistent with T1 decay |
| Worst qubit found | Qubit 82 on ibm_marrakesh: 31% error per round in \|1⟩ |
| Weighted vs uniform union-find | Up to 36% fewer logical errors (d=9, ibm_fez) |
| Fast vs naive union-find on the STM32 | 2.4–4× fewer cycles, identical results |
| Real-time limit at d=11 on the STM32 | ~15 µs per round (fast UF), 41 µs (naive UF); IBM rounds take ~1 µs |
| QPU time per experiment | ~6 s for 16 circuits |

## Edge AI: a decoder that learns each chip

A small neural network learns each chip's real noise on the board and decodes on the STM32. On ibm_marrakesh it
makes **1.7–9.5× fewer logical errors than the best graph decoder** (d = 3–11).

- **Training on the board:** the Linux side trains a 1-hidden-layer network (detection events + final data bits →
  32 ReLU units → 1 output, 400–4,000 parameters) in pure numpy on held-out shots, in about 0.2 s per model on a laptop.
- **Inference on the microcontroller:** weights are quantised to 15-bit integers and sent over Bridge (a d=5 model
  is 47 calls, ~0.2 s, verified by a checksum). The STM32 runs it in integer arithmetic, **bit-exact with Python on
  every shot tested**, as decoder #6 in the accuracy comparison and in the real-time backlog sweep. About 8.5 KB RAM.
- **Why it wins:** on IBM hardware a |1⟩ decays (T1) far more often than a |0⟩ flips. The network learns this
  asymmetric noise from the data; matching and union-find cannot represent it. A control network given only the
  detection events does worse than union-find, so the gain comes from learning the device's real noise.
- **Where it loses:** on ibm_fez at d ≥ 11 it has an error floor of 0.2–0.4% (too few training shots for ~120
  inputs), while graph decoders reach < 0.075%.
- **Honest test:** trained and scored on separate shots (2-fold cross-fitting). The prepared state is only the
  training label, never an input. This works because both logical states are equally likely in the experiment.

| ibm_marrakesh, d | Best graph decoder | AI decoder |
|---|---|---|
| 3 | 10.6% (PyMatching weighted) | **6.3%** |
| 5 | 3.6% (PyMatching, mixed weights) | **1.8%** |
| 7 | 1.7% (PyMatching weighted) | **0.22%** |
| 9 | 0.47% (PyMatching weighted) | **0.05%** |

Full tables for all runs: [`results/results_tables.md`](results/results_tables.md), section 5. STM32 cycles per AI
decode are measured on the board (DWT counter) and shown on the dashboard; laptop estimate ≈ 6 µs at d=5.

Libraries considered: TensorFlow Lite Micro (reported compile failures on the UNO Q core), Edge Impulse (supports
the UNO Q but needs a Studio/west build), emlearn (needs scikit-learn/Keras for training). A hand-written C MLP whose
first layer is additions only (inputs are bits) was the simplest robust choice.

## Repository layout

```
QEC_Edge_Lab_submission/
├── README.md                 this file
├── make_export.sh            refreshes code/ from the working app folders (never copies the API key)
├── code/
│   ├── qec_lab/              the main App Lab app
│   │   ├── python/           main.py (app), qec_common.py (graph, error model, run storage), qec_ai.py (AI decoder),
│   │   │                     requirements.txt, ibm_config.example.json
│   │   ├── sketch/           sketch.ino, qec_decoders.h (decoders), qec_rt.h (real-time replay), qec_ai.h (AI inference)
│   │   ├── assets/           web dashboard (index.html, app.js, style.css, libs/)
│   │   └── tools/            qec_offline.py (laptop: full statistics + PyMatching)
│   └── quantum_music/        earlier experiment: knob-controlled 5-qubit phase-estimation synth with dashboard
├── data/ibm_runs/            raw shots of the 3 IBM runs (.npz + .json), board results, offline CSVs
├── results/results_tables.md all result tables, generated from data/
├── docs/                     demo script, submission checklist, background notes
└── media/                    architecture diagram, results chart, shot list for photos/video
```

## Build and run

1. Create a free IBM Quantum account (Open Plan); copy your API key and instance CRN.
2. In Arduino App Lab 0.12, create an app `qec_lab`, add the **WebUI - HTML** brick and the **Modulino** sketch library.
3. Copy `code/qec_lab/{python,sketch,assets}` into the app. **Add the brick first, then copy** (adding the brick resets `assets/`).
   Don't overwrite App Lab's own `app.yaml` and `sketch/sketch.yaml`.
4. Copy `python/ibm_config.example.json` to `python/ibm_config.json` and fill in your token and instance. Never publish it.
5. Connect the Modulino Knob and Buzzer (Qwiic) and run the app.
6. Open the dashboard on port 7000. If the Wi-Fi blocks device-to-device traffic: `ssh -N -L 7000:127.0.0.1:7000 arduino@<board-ip>`.
7. **Accuracy tab:** noise model first, then IBM hardware. **Real-time tab:** load a saved run, sweep, then live mode with the knob.
8. Full statistics on a laptop: `pip install numpy pymatching`, copy `python/runs/` from the board, run
   `python3 tools/qec_offline.py ./runs`.

## Limitations

- **Emulated real time:** real hardware syndromes are replayed on the STM32; the timing is real, the loop with the
  quantum computer is not closed (the network adds milliseconds).
- **Too slow for superconducting qubits** (~15 µs vs ~1 µs per round at d=11); trapped-ion and neutral-atom machines
  run rounds of roughly 100 µs to a few ms, where the same decoder would probably keep up.
- **Repetition code only** (bit flips, not phase errors); 2-D codes are the next step.
- **STM32 statistics** use 400 shots per distance; full statistics (4,000) come from the laptop tool, which runs the
  same C decoder code.

## Credits and tools

Arduino UNO Q, Arduino App Lab, Modulino Knob and Buzzer; IBM Quantum (Qiskit, qiskit-ibm-runtime);
PyMatching (laptop reference decoder); socket.io client 4.7.5 (dashboard). Union-find decoding after
Delfosse & Nickerson; edge-probability estimation after the "p_ij" correlation method used in repetition-code
experiments.

Open questions before publishing: team names, licence for the code, GitHub repo or zip.
