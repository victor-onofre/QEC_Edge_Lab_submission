# QEC Edge Lab: €60 Arduino that corrects real quantum computer errors

**Junction Finland 2026 · Best use of Arduino UNO Q** · tags: Junction Finland 2026, Arduino UNO Q, Modulino, Edge AI, Quantum computing

> **In one sentence:** quantum computers make mistakes all the time, and a fast classical computer has to fix them
> on the fly. We built that "error fixer" on an Arduino UNO Q, tested it on real IBM quantum computers, and taught it
> with on-device AI to fix errors up to 9.5× better than the standard method.

**No quantum background needed to read this page.** The first part explains everything in plain words; the
technical details for experts are at the end.

---

## In 30 seconds

- **Real quantum hardware:** the Arduino sends experiments to IBM's 156-qubit quantum computers over the internet (free account).
- **The Arduino fixes the errors:** its small real-time processor works out which quantum bits went wrong, and measures exactly how long that takes.
- **Edge AI:** a small neural network trained *on the Arduino* learns the personality of each quantum chip and makes **up to 9× fewer mistakes** (typically 2–3×) than the best classical method.
- **You can feel the limit:** turn a knob to speed up the stream of errors; the LED matrix fills up and a buzzer growls when the Arduino can no longer keep up.

---

## Quantum computing in one minute (no physics needed)

**Quantum bits are fragile.** A normal computer bit is a 0 or a 1 and stays that way. A quantum bit (*qubit*) is so
sensitive that heat, stray signals or simply time make it flip by accident, on today's machines, a few times in
every hundred operations. Left alone, errors pile up and the result is garbage.

**The fix: redundancy and voting.** Imagine whispering a message across a noisy room. To be safe you say it with
several people at once, and the listener takes the majority. Quantum error correction does the same: one "logical"
bit of information is spread over many physical qubits.

**The catch: you can't just look.** Looking at a qubit destroys its quantum information. So instead, helper qubits
ask indirect questions such as *"are these two neighbours still the same?"*, over and over, every few microseconds.
The answers are clues; we call them **syndromes**.

**The detective: the decoder.** A classical computer reads the stream of clues and works out *which* qubits most
likely flipped, so they can be corrected. This program is called the **decoder**. It has to be:

1. **Accurate:**a wrong guess makes things worse, and
2. **Fast:** new clues arrive every round (about every microsecond on IBM machines). Like a supermarket cashier:
   if customers arrive faster than the cashier serves them, the queue grows forever.

![How quantum error correction works](media/how_error_correction_works.png)

**This project builds that decoder on an Arduino**, checks how accurate and how fast it is on real IBM data, and
uses AI to make it smarter.

**Detecting or correcting?** As in Google's and IBM's error-correction experiments, the qubits are not physically
flipped back: the decoder works out which errors happened and **corrects the measured result in software** (experts
call this tracking the errors in the "Pauli frame"). The proof that this is correction and not just detection is that
the final answer gets *more* reliable as more qubits are added. Our decoding runs after each IBM job; the real-time
test replays the real data on the Arduino at realistic speed.

---

## Why this matters: the race to build fast decoders

Decoding is one of the hardest open engineering problems on the road to useful quantum computers. Riverlane, a
company that builds decoders, calls the decoder "the beating heart of QEC" [1]. The biggest players are all
building dedicated hardware for it:

| Who | What they built | How fast |
|---|---|---|
| **Google Quantum AI** (Nature, 2024) | First error correction "below threshold" on its Willow chip, with a real-time decoder [2] | 63 µs average decoder latency, for a 1.1 µs error-correction cycle |
| **Google DeepMind — AlphaQubit** (Nature, 2024) | A neural-network decoder that beat classical decoders on Google's real hardware [3]; a 2025 successor targets real-time speed [4] | Successor reported under 1 µs per cycle on commercial hardware [4] |
| **Riverlane — Deltaflow 2** | A decoder on FPGA chips, tested live with Rigetti's quantum computer [5][6] | 0.44–0.79 µs per round; about 16 µs end-to-end for the whole system [6] |
| **NVIDIA — CUDA-Q QEC + NVQLink** | GPU decoders wired to quantum control electronics, including an AI pre-decoder in front of a classical one [7] | 2.1 µs per round for the AI-assisted pipeline in a surface-code test; under 4 µs FPGA–GPU round trip [7] |
| **IBM — Relay-BP on FPGA** | A decoder for IBM's next-generation codes, built to keep up with a 1 µs measurement cycle [8] | 24 ns per algorithm iteration on an AMD FPGA [8] |

These numbers measure different things (per round, end-to-end, per iteration), so they are not directly
comparable. The message is the same everywhere: **decoders must be accurate, fast and small**, and the industry is
spending FPGAs, GPUs and custom chips to get there. Two trends stand out: **neural-network decoders** (AlphaQubit,
NVIDIA's AI pre-decoder) and **putting the decoder close to the quantum computer**.

**QEC Edge Lab explores the same two ideas on a €60 board:** a neural-network decoder trained on the device, running
on an embedded processor next to the experiment, measured against the same real-time limit. Our Arduino reaches about
**9 µs per round**: roughly 10× slower per round than the FPGA and GPU systems above, which is exactly why the
industry builds dedicated hardware, but achieved with a €60 microcontroller you can buy in a shop and fast enough
for trapped-ion and neutral-atom machines, whose rounds take roughly 100 µs to a few milliseconds.

---

## What we built

![Architecture](media/architecture.png)

The Arduino UNO Q is two computers on one board, and that is exactly how real quantum computers are controlled:

| Part of the Arduino | Its job here | In everyday terms |
|---|---|---|
| **Linux side** (Qualcomm processor) | Talks to IBM, stores results, trains the AI, serves the web dashboard | The office: planning and paperwork |
| **Microcontroller** (STM32, 160 MHz) | Runs the decoders and times every one of them to the clock cycle | The factory floor: fast, precise, no interruptions |
| **8×13 LED matrix** | Shows progress, results, and the "queue" of unsolved errors | A live scoreboard |
| **Modulino Knob** | Sets how fast new error clues arrive | The speed dial |
| **Modulino Buzzer** | Growls when the decoder falls behind | The alarm |

## What you see and hear in the demo

1. **The scoreboard:** the dashboard shows real IBM results — as we use more qubits, the error rate drops (that's error correction working).
2. **The AI:** a pink line on the chart, the neural network trained on the Arduino beats the classical decoders.
3. **The speed test:** we turn the knob to send clues faster and faster. The Arduino keeps up… until about **9 microseconds per round**. Past that point the LED matrix fills with bars, the dashboard turns red and the buzzer growls: the queue of unsolved errors is exploding.

## Results in plain words

![Logical error vs distance](media/logical_error_vs_distance_ibm_fez.png)

*How to read it:* left to right = more qubits protecting the information; down = fewer mistakes. The lines go
down, so error correction works on the real machine. **Blue** is the Arduino's classical decoder; **purple** is the
neural network trained on the Arduino. On small codes (5–13 qubits) the AI makes about 2× fewer mistakes (1.8–2.4×) than any
other decoder. On bigger codes it levels off at about 0.2–0.3%, where the classical decoders take over — so the best
design uses the AI for small codes and the classical decoder for large ones.

| What we found | Why it matters |
|---|---|
| **Error correction works on IBM's real chips:** spreading the information over 21 qubits instead of 5 cut mistakes from **4.8% to 0.075%** (64× fewer). | The core promise of quantum error correction, shown with a €60 board as the decoder. |
| **The AI decoder makes up to 9.5× fewer mistakes** (typically 2–3×) than the best classical decoder on small and medium codes (up to 17 qubits), on two different IBM chips. | Learning from data beats hand-written rules, and it runs on the Arduino itself. |
| **Why the AI wins:** on these chips a stored **1 fades into a 0 about 10–16× more often** than a 0 turns into a 1 (like a light bulb that dims, but never switches itself on). The AI learned this by itself from the data. | The Arduino doubles as a diagnostic tool: it discovered real physical behaviour of each chip, including one qubit that flips 31% of the time. |
| **Speed limit: about 9 microseconds per round** for the AI decoder on the Arduino, as fast as the fastest classical decoder we built. | Too slow for IBM's superconducting chips (~1 µs per round), but **fast enough for trapped-ion and neutral-atom quantum computers**, whose rounds take roughly 100 µs to a few milliseconds. |
| **We made the classical decoder 2.4–4× faster** on the microcontroller with identical answers. | Every microsecond counts in real-time control. |

## Why this could work on neutral-atom and trapped-ion quantum computers

There are several ways to build a qubit. IBM and Google use **superconducting circuits**: very fast, about one
error-correction round per microsecond, which is why our Arduino (about 9 µs per round) is too slow for them.
Two other leading approaches are much slower per round, and that changes the picture:

- **Neutral atoms** (single atoms held by laser "tweezers"; QuEra, Atom Computing, Pasqal) and
- **Trapped ions** (charged atoms held by electric fields; Quantinuum, IonQ).

Their qubits are very stable, but gates, measurements and moving atoms or ions around take much longer: roughly
**1 millisecond per round**, and trapped-ion design models assume 1–5 ms [9][10].

![Time budget by platform](media/time_budget_by_platform.png)

**1. There is time to spare.** At about 1 ms per round, the decoder has roughly **100 times more time** than our
Arduino needs. A €60 microcontroller could keep up, with room left for bigger codes or for decoding several
logical qubits at once.

**2. The industry is already using AI decoders on these machines.** Harvard, QuEra and MIT reached
"below-threshold" error correction on 448 neutral atoms using **machine-learning decoding** together with detection
of lost atoms (Nature, 2025) [11]. Quantinuum reports **neural-network decoders** for its Helios trapped-ion computer,
running at 0.2–0.5 ms per round on NVIDIA H100 GPUs [12]. Our project shows that this kind of decoder can also
run on a cheap, low-power embedded chip.

**3. Their errors have their own personality, which an AI decoder can learn.** On IBM chips, our AI decoder learned that
a stored 1 fades into a 0 far more often than the reverse. Atoms and ions have different quirks; for example, an
atom can simply disappear, which the hardware can detect [11][13]. A decoder trained on the device's own data, as
ours is, adapts to whatever the dominant quirk is, without hand-written rules.

**What we have not shown yet:**

- We have not run on an ion or atom machine. Our measured data come from IBM's superconducting chips.
- Those machines mostly use 2-D codes (surface and colour codes); our decoders handle the 1-D repetition code and
  would need extending.
- Round times are improving fast (Atom Computing reports up to 90 rounds of error correction with atom
  replacement [13]; other groups report large increases in cycle rate), so the 100× margin will shrink over time.
- Real control systems also need time to move data in and out; our numbers cover the decoding itself.

**Next steps on this path:** noise models that mimic atoms and ions (including lost atoms), a decoder that uses
"this atom is missing" flags (cheap to add to union-find), and tests with data from vendor emulators.

## Who it helps

- **Students and teachers:** see, hear and *touch* quantum error correction on real hardware for the price of an Arduino.
- **Engineers building quantum computers:** a cheap bench to test how fast and accurate a decoder is on small embedded chips.
- **Researchers:** real measurements of how individual qubits on IBM chips misbehave, from a free account.

## Glossary

| Word | Meaning |
|---|---|
| **Qubit** | A quantum bit. Fragile: it can flip by accident. |
| **Physical vs logical qubit** | Physical = one real qubit on the chip. Logical = one protected bit of information spread over many physical qubits. |
| **Error correction** | Spreading information redundantly and repairing it as errors happen. |
| **Repetition code** | The simplest error-correcting code: store the same bit many times and keep checking that neighbours agree. |
| **Code distance (d)** | How many copies protect the bit. Bigger d = more qubits = more protection. |
| **Syndrome** | A clue: the answer to "are these two neighbours still the same?" |
| **Decoder** | The program that turns clues into a decision about what went wrong. |
| **Logical error rate** | How often the decoder still gets the final answer wrong. Lower is better. |
| **Round / round time (τ)** | One cycle of checking all neighbours; τ is how often a new round of clues arrives. |
| **Backlog** | Clues waiting to be decoded. If it keeps growing, the decoder is too slow. |
| **Union-find, matching (PyMatching)** | Two well-known classical decoder algorithms. PyMatching is the accurate reference used by researchers. |
| **T1 decay** | A qubit holding 1 slowly "relaxes" to 0, like a ball rolling downhill. |
| **IBM ibm_fez / ibm_marrakesh** | Two of IBM's 156-qubit quantum computers, available free via the cloud. |

---

# For experts: technical details

## How it works

1. **Accuracy on real hardware.** Bit-flip repetition codes at distance 3–25 (up to 49 qubits), 3 rounds of
   mid-circuit syndrome measurement, logical |0⟩ and |1⟩. A line of qubits with no SWAP gates is found on the
   chip; all 16 circuits go to IBM as one job (~6 s of QPU time). Shots are streamed to the STM32 over Bridge RPC,
   which decodes them and counts CPU cycles per decoder (DWT cycle counter, interrupts masked).
2. **Faster, smarter decoders.** A lazy-reset union-find runs 2.4–4× faster on the STM32 with identical results.
   The Linux side learns an error probability for every edge of the decoding graph from the syndromes
   ("p_ij" method), per logical state, and the STM32 uses them as integer weights. Runs are saved; old IBM jobs can
   be re-imported by ID without QPU time.
3. **Real-time backlog test.** Syndromes are bulk-loaded into STM32 RAM, then replayed as if one round arrived
   every τ, with interrupts on. The STM32 decodes in order and records latency and backlog. A sweep finds each
   decoder's limit τ* = mean decode time / rounds; in live mode the knob sets τ.
4. **Edge AI decoder** (below).

| Component | Role |
|---|---|
| Linux side (Qualcomm QRB2210, Debian) | Qiskit 2.x, qiskit-ibm-runtime, numpy; IBM jobs, saved runs, error-model learning, AI training, WebUI dashboard |
| STM32U585 (Cortex-M33, 160 MHz) | Decoders (majority, greedy, union-find naive/fast/weighted, AI), real-time replay engine, DWT cycle counter |
| Bridge RPC | Linux ↔ STM32 (msgpack); bulk loads only, never inside a timing measurement |

## Edge AI decoder

- **Model:** one hidden layer (detection events + final data bits → 32 ReLU units → 1 output; 400–4,000 parameters),
  trained in pure numpy on the board's Linux side (~2.6 s per model on the board), on held-out shots.
- **Inference on the STM32:** weights quantised to 15-bit integers, sent over Bridge with a checksum (a d=5 model is
  47 calls); integer arithmetic, **bit-exact with Python on every shot tested**; ~8.5 KB RAM. The first layer is
  additions only, because the inputs are bits.
- **Why it wins:** IBM hardware noise is strongly asymmetric (T1 decay of |1⟩); the network learns it from data,
  matching and union-find cannot represent it. A control network given only detection events does worse than union-find.
- **Where it loses:** at d ≥ 11 on ibm_fez it has an error floor of 0.15–0.4% (too few training shots for ~120 inputs),
  while graph decoders reach < 0.05%. A practical design: AI up to d=9, matching above.
- **Honest test:** 2-fold cross-fitting; the prepared state is only the training label, never an input (valid
  because both logical states are equally likely in the experiment).
- **Libraries considered:** TensorFlow Lite Micro (compile failures reported on the UNO Q core), Edge Impulse
  (supported, but needs a Studio/west build), emlearn (needs scikit-learn/Keras); a hand-written C MLP was the most robust.

| ibm_marrakesh, d | Best graph decoder | AI decoder |
|---|---|---|
| 3 | 10.6% (PyMatching weighted) | **6.3%** |
| 5 | 3.6% (PyMatching, mixed weights) | **1.8%** |
| 7 | 1.7% (PyMatching weighted) | **0.22%** |
| 9 | 0.47% (PyMatching weighted) | **0.05%** |

STM32 cost per AI decode: 1,909 cycles (11.9 µs) at d=3, 2,686 (16.8 µs) at d=5 — about the same as fast union-find.
Real-time replay (ibm_marrakesh, d=5): AI limit **8.7 µs per round**, tied with weighted union-find, fast UF 10.4 µs,
naive UF 19.8 µs. Second ibm_fez run: AI 2.8–3.2× fewer errors than the best graph decoder at d = 3–7.

## Key measurements

| Finding | Measured |
|---|---|
| Data error per round, \|0⟩ vs \|1⟩ | 0.3–1.2% vs 4.1–5.8% on ibm_fez (median 0.18% vs 3.4%); consistent with T1 decay |
| Worst qubit found | Qubit 82 on ibm_marrakesh: 31% error per round in \|1⟩ |
| Weighted vs uniform union-find | Up to 36% fewer logical errors (d=9, ibm_fez) |
| Fast vs naive union-find on the STM32 | 2.4–4× fewer cycles, identical results |
| Real-time limit on the STM32 | d=11: ~15 µs/round (fast UF), 41 µs (naive); d=5: 8.7 µs/round (AI) |
| Microbenchmark vs real-time replay | Replay ~1.5× slower (detector computation, unpacking, interrupts) |
| QPU time per experiment | ~6 s for 16 circuits |

All tables, generated from the raw data: [`results/results_tables.md`](results/results_tables.md).

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
├── data/ibm_runs/            raw shots of the IBM runs (.npz + .json), board results, offline CSVs
├── results/results_tables.md all result tables, generated from data/
├── docs/                     demo script, submission checklist, background notes
└── media/                    architecture diagram, results chart, shot list for photos/video
```

## Build and run

1. Create a free IBM Quantum account (Open Plan); copy your API key and instance CRN. *(Optional: the
   "Noise model" mode works without any account.)*
2. **Easiest:** import `qec_lab_import.zip` (in the repository root) into Arduino App Lab; it contains `app.yaml`
   (with the WebUI brick) and `sketch/sketch.yaml` (with the Modulino library). **Manual alternative:** in Arduino App Lab 0.12,
   create an app `qec_lab`, add the **WebUI - HTML** brick and the **Modulino** sketch library.
3. Copy `code/qec_lab/{python,sketch,assets}` into the app. **Add the brick first, then copy** (adding the brick resets `assets/`).
   Don't overwrite App Lab's own `app.yaml` and `sketch/sketch.yaml`.
4. Copy `python/ibm_config.example.json` to `python/ibm_config.json` and fill in your token and instance. Never publish it.
5. Connect the Modulino Knob and Buzzer (Qwiic) and run the app.
6. Open the dashboard on port 7000. If the Wi-Fi blocks device-to-device traffic: `ssh -N -L 7000:127.0.0.1:7000 arduino@<board-ip>`.
7. **Accuracy tab:** noise model first, then IBM hardware. **Real-time tab:** load a saved run, sweep, then live mode with the knob.
8. Full statistics on a laptop: `pip install numpy pymatching`, copy `python/runs/` from the board, run
   `python3 tools/qec_offline.py ./runs`.

## Limitations

- **Emulated real time:** real hardware syndromes are replayed on the STM32; the timing is real, but the loop with
  the quantum computer is not closed (the network adds milliseconds).
- **Too slow for superconducting qubits** (~9–15 µs vs ~1 µs per round); likely fast enough for trapped-ion and
  neutral-atom machines (rounds of roughly 100 µs to a few ms).
- **Correction in software, after the run:** as in Google's and IBM's memory experiments, corrections are applied to the
  measured result (Pauli-frame tracking), not sent back to the qubits; decoding happens after each IBM job.
- **Repetition code only** (bit flips, not phase errors), so it does not protect an arbitrary quantum state; 2-D codes
  (surface or colour codes) are the next step.
- **STM32 statistics** use 400 shots per distance; full statistics (4,000) come from the laptop tool, which runs the
  same C decoder code.

## Credits and tools

Arduino UNO Q, Arduino App Lab, Modulino Knob and Buzzer; IBM Quantum (Qiskit, qiskit-ibm-runtime);
PyMatching (laptop reference decoder); socket.io client 4.7.5 (dashboard). Union-find decoding after
Delfosse & Nickerson; edge-probability estimation after the "p_ij" correlation method used in repetition-code
experiments.

## References

1. Riverlane — *Why the decoder is the beating heart of QEC*. https://www.riverlane.com/blog/why-the-decoder-is-the-beating-heart-of-qec
2. Google Quantum AI and collaborators — *Quantum error correction below the surface code threshold*, Nature 638, 920–926 (2025). arXiv: https://arxiv.org/abs/2408.13687
3. Bausch et al. (Google DeepMind & Google Quantum AI) — *Learning high-accuracy error decoding for quantum processors* (AlphaQubit), Nature (2024). Coverage: https://thedebrief.org/google-deepminds-breakthrough-alphaqubit-closing-in-on-the-holy-grail-of-quantum-computing/
4. Senior et al. — *A scalable and real-time neural decoder for topological quantum codes* (preprint, 2025). https://arxiv.org/abs/2512.07737
5. Riverlane — *Introducing the world's first low-latency QEC experiment*. https://www.riverlane.com/news/introducing-the-world-s-first-low-latency-qec-experiment
6. The Quantum Insider — *Riverlane publishes hardware decoder for real-time quantum error correction* (Dec 2025). https://thequantuminsider.com/2025/12/18/riverlane-hardware-decoder-real-time-qec/
7. NVIDIA — *CUDA-Q QEC 0.6 enables real-time QEC with NVQLink* (Apr 2026). https://nvidia.github.io/cuda-quantum/blogs/blog/2026/04/14/cudaq-qec-0.6/
8. IBM Quantum — *Real-time decoding of the gross code memory with FPGAs* (arXiv 2510.21600, 2025). https://arxiv.org/abs/2510.21600 ; algorithm: *Improved belief propagation is sufficient for real-time decoding of quantum memory*, https://arxiv.org/abs/2506.01779
9. IonQ real-time decoding study, modelling a trapped-ion architecture with a 1–5 ms cycle time (coverage). https://postquantum.com/engineering-news/ionq-real-time-decoder-cpu/
10. *The classical stack behind quantum error correction* (overview citing ~1 µs rounds for superconducting qubits and ~1 ms for trapped ions and neutral atoms). https://postquantum.com/quantum-computing/qec-classical-stack-infrastructure/
11. Bluvstein et al. (Harvard, QuEra, MIT) — *A fault-tolerant neutral-atom architecture for universal quantum computation*, Nature (Nov 2025). arXiv: https://arxiv.org/abs/2506.20661
12. Quantum Computing Report — *Quantinuum demonstrates 99.9995% logical memory fidelity on Helios trapped-ion processor*. https://quantumcomputingreport.com/quantinuum-demonstrates-99-9995-logical-memory-fidelity-on-helios-trapped-ion-processor/
13. Atom Computing — *Quantum error correction with toric code*. https://atom-computing.com/quantum-error-correction-with-toric-code/
