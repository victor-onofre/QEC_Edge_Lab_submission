# Arduino UNO Q × IBM Quantum — Session Notes

*Session date: 2026-11-14 · Board hostname: `QuantumGravity` · App Lab 0.12.0 (Linux x86-64)*

---

## 1. Status summary

| Step | Status |
|---|---|
| Python virtual environment with Qiskit on the UNO Q | ✅ Done (`~/qenv`) |
| IBM Quantum API key + instance CRN stored as environment variables | ✅ Done (`~/.qiskit_env`) |
| Account test: connected, backends listed | ✅ Done |
| Bell-state job on real IBM hardware (`test_ibm.py --run`) | ✅ Works |
| QFT spectrum script (`qft_spectrum.py`) | 📝 Written, ready to run |
| App Lab LED-matrix app (`quantum-bell-bars`) | 📝 Written, not yet tested on the board |
| Microphone input → quantum circuit | 💡 Planned |
| 3-microphone sound localization | 💡 Planned |

---

## 2. Facts learned about the board

### UNO Q architecture
- **Two processors:**
  - **MPU** – Qualcomm QRB2210 (quad Cortex-A53, `aarch64`) running **Debian Linux**. Runs Python, networking, Qiskit.
  - **MCU** – STM32U585 (Cortex-M33) running the Arduino core on **Zephyr**. Real-time GPIO, ADC, sensors, the LED matrix.
- They talk over the **Router Bridge** (RPC).

### Measured on this board
```
Python 3.13.5
uname -m          → aarch64
/home/arduino     → 3.6 G total, 2.5 G free (before installing Qiskit)
RAM               → 1.7 Gi total, ~1.2 Gi available, 868 Mi swap
```

### App Lab facts (from App Lab 0.12.0's built-in reference text)
- **App layout:** `app.yaml` (name, icon, description, bricks), `python/main.py` (entry point, **must end with `App.run()`**; nothing after it runs), optional `sketch/` (`sketch.ino` + `sketch.yaml`, both required together), optional `assets/`. Folder names are fixed.
- **`python/requirements.txt`** (optional) lists pip packages for the app. They're installed into the app's container.
- **Python apps run in a container**, so they don't see `~/.bashrc` or `~/.qiskit_env`.
- **Secrets** officially go in *Brick Configuration*. That only exists for bricks, and there is no IBM brick, so for a private test the key goes in a config file inside the app (don't share or export the app).
- **Bridge:**
  - The receiving side registers a function with `Bridge.provide("name", fn)`.
  - The other side calls it with `Bridge.call("name", ...)` (synchronous, returns a value) or `Bridge.notify("name", ...)` (fire-and-forget).
  - Names must match exactly on both sides. **A mismatched `notify` fails silently.**
  - Python's `Bridge.call` returns the value directly. The sketch's `Bridge.call(...).result(out)` returns a bool, so check it.
  - Sketch side: `#include <Arduino_RouterBridge.h>`, call `Bridge.begin()` in `setup()`, log with `Serial.println`.
- **LED matrix** (MCU, `Arduino_LED_Matrix.h`): **8 rows × 13 columns, 3-bit grayscale (0–7)**.
  - Per-pixel frame: `uint8_t[104]` → `matrix.draw()`; index = `row * 13 + col`.
  - On/off frame: `uint32_t[4]` → `matrix.loadFrame()`.
  - Sequences: `loadSequence()` + `playSequence()` (blocks).
  - Don't drive it during the **~20–30 s boot logo**.
- **On-board RGB LEDs are active-low**: `digitalWrite(pin, LOW)` = ON (including `LED_BUILTIN`).
- Only one app runs at a time. A running app doesn't pick up file changes until it's restarted.

---

## 3. IBM Quantum account

- Platform: **https://quantum.cloud.ibm.com**, free **Open Plan** (about **10 min of quantum time per month**).
- **API key:** home dashboard → *API key* box → **Create +** → name it → **Copy**. It's shown only once.
- **Instance CRN:** *Instances* page (https://quantum.cloud.ibm.com/instances) → copy the CRN (`crn:v1:bluemix:public:quantum-computing:...`).
- Sessions are probably not available on the Open Plan, but **batch mode** is. Use it to group many jobs.

### Backends visible from the board (at time of test)
```
ibm_fez          156 qubits   pending jobs: 1
ibm_kingston     156 qubits   pending jobs: 237
ibm_marrakesh    156 qubits   pending jobs: 0
```

---

## 4. Setup steps that worked (and the problems hit along the way)

### 4.1 Install pip / venv
`pip: command not found` → Debian doesn't ship pip, and it also blocks system-wide `pip install` ("externally-managed-environment"). Fix:
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv
python3 -m venv ~/qenv
source ~/qenv/bin/activate
pip install --upgrade pip
pip install --no-cache-dir qiskit qiskit-ibm-runtime
pip install --no-cache-dir qiskit-aer        # optional local simulator
```
Tips:
- `--no-cache-dir` saves disk space (only 2.5 GB free).
- If you get "No space left on device" while unpacking: `mkdir -p ~/tmp && export TMPDIR=~/tmp`.
- If `qiskit-aer` starts "Building wheel…", press Ctrl-C and skip it. `StatevectorSampler` is enough for small circuits.
- Run `source ~/qenv/bin/activate` again in every new SSH session.

Quick local test:
```bash
python -c "
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler
qc = QuantumCircuit(2); qc.h(0); qc.cx(0,1); qc.measure_all()
print(StatevectorSampler().run([qc], shots=1000).result()[0].data.meas.get_counts())
"
```

### 4.2 Store the API key as an environment variable
**Problem:** `read -rsp` (hidden input) reported `got 0 characters`. The paste never reached the hidden prompt, and with an empty token Qiskit raised:
```
AccountNotFoundError: "Unable to find account. Please make sure an account with the channel name 'ibm_cloud' is saved."
```
(An *empty* token makes Qiskit look for a saved account, so the error mentions a missing account rather than a missing token.)

**What worked:** edit the file with nano, where you can see what you paste:
```bash
nano ~/.qiskit_env
```
```bash
export QISKIT_IBM_TOKEN="paste-your-api-key-here"
export QISKIT_IBM_INSTANCE="crn:v1:bluemix:public:quantum-computing:..."
```
Save with Ctrl+O, Enter, then Ctrl+X. Then:
```bash
chmod 600 ~/.qiskit_env
echo '[ -f ~/.qiskit_env ] && source ~/.qiskit_env' >> ~/.bashrc
source ~/.qiskit_env
echo "token length: ${#QISKIT_IBM_TOKEN}"   # expect ~44
echo "$QISKIT_IBM_INSTANCE"                  # expect crn:v1:...
clear
```
Paste in Linux terminals with **Ctrl+Shift+V** (or right-click → Paste).

Alternative: `QiskitRuntimeService.save_account(channel="ibm_cloud", token=..., instance=..., set_as_default=True)` writes `~/.qiskit/qiskit-ibm.json` (plain text, so `chmod 600` it).

Harmless warning seen when it worked:
```
WARNING: Loading account with the given token. A saved account will not be used.
```

### 4.3 Each new session
```bash
source ~/qenv/bin/activate
source ~/.qiskit_env
cd ~/quantum
```

---

## 5. Scripts

### 5.1 `~/quantum/test_ibm.py` — account test + Bell state on hardware ✅
```python
import os, sys, time
from qiskit import QuantumCircuit
from qiskit.transpiler import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

# 1) Connect
service = QiskitRuntimeService(
    channel="ibm_cloud",
    token=os.environ["QISKIT_IBM_TOKEN"],
    instance=os.environ["QISKIT_IBM_INSTANCE"],
)
print("Connected. Available backends:")
for b in service.backends(simulator=False, operational=True):
    s = b.status()
    print(f"  {b.name:15} {b.num_qubits:4} qubits   pending jobs: {s.pending_jobs}")

if "--run" not in sys.argv:
    print("\nAccount OK. Re-run with --run to send a Bell-state job to real hardware.")
    sys.exit(0)

# 2) Bell state on the least busy real device
backend = service.least_busy(operational=True, simulator=False)
print(f"\nUsing {backend.name}")

qc = QuantumCircuit(2)
qc.h(0); qc.cx(0, 1); qc.measure_all()
isa = generate_preset_pass_manager(backend=backend, optimization_level=1).run(qc)

job = SamplerV2(mode=backend).run([isa], shots=1024)
print("Job ID:", job.job_id())

t0 = time.time()
while not job.in_final_state():
    print(f"  status: {job.status()}  ({time.time()-t0:.0f}s)")
    time.sleep(10)

counts = job.result()[0].data.meas.get_counts()
print("\nCounts:", dict(sorted(counts.items())))
good = counts.get("00", 0) + counts.get("11", 0)
print(f"Bell fidelity estimate: {good/1024:.1%}  (ideal 100%, noise causes 01/10)")
```
```bash
python test_ibm.py          # account check, uses no quantum time
python test_ibm.py --run    # real hardware, a few seconds of quota
```
If you press Ctrl-C while waiting, the job keeps running at IBM. Find it under **Workloads** on quantum.cloud.ibm.com.

### 5.2 `~/quantum/qft_spectrum.py` — quantum spectrum analyser 📝
Amplitude-encodes 16 audio samples into 4 qubits, applies the QFT, and compares the measured probabilities with a classical FFT.
Expected: P(k) = |FFT(amp)[k]|² / N.
```python
"""
Quantum spectrum analyser: amplitude-encode 16 audio samples into 4 qubits,
apply the QFT, and compare measured probabilities with a classical FFT.
  python qft_spectrum.py               # 750 Hz tone, simulator only
  python qft_spectrum.py 500 1250      # two tones
  python qft_spectrum.py 750 --run     # also run on IBM hardware
"""
import os, sys, json, time
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import StatePreparation, QFTGate
from qiskit.primitives import StatevectorSampler
from qiskit.transpiler import generate_preset_pass_manager

N_QUBITS = 4
N = 2 ** N_QUBITS          # 16 samples
FS = 4000                  # sample rate in Hz -> 250 Hz per frequency bin
SHOTS = 4000

freqs = [float(a) for a in sys.argv[1:] if not a.startswith("--")] or [750.0]
run_hw = "--run" in sys.argv

# 1) The "audio" signal (later: replace with microphone samples)
t = np.arange(N) / FS
x = sum(np.sin(2 * np.pi * f * t) for f in freqs)
x = x + 0.05 * np.random.default_rng(0).standard_normal(N)
amp = x / np.linalg.norm(x)                      # quantum states must have norm 1

# 2) Classical reference: what the QFT should give
expected = np.abs(np.fft.fft(amp)) ** 2 / N

# 3) Quantum circuit: load the samples, then QFT
qc = QuantumCircuit(N_QUBITS)
qc.append(StatePreparation(amp), range(N_QUBITS))
qc.append(QFTGate(N_QUBITS), range(N_QUBITS))
qc.measure_all()

def to_probs(counts):
    p = np.zeros(N)
    for bits, c in counts.items():
        p[int(bits, 2)] = c / SHOTS
    return p

# 4) Ideal simulator on the UNO Q
sim = StatevectorSampler().run([qc], shots=SHOTS).result()[0].data.meas.get_counts()
results = {"expected": expected, "simulator": to_probs(sim)}

# 5) Real IBM hardware
if run_hw:
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    service = QiskitRuntimeService(channel="ibm_cloud",
                                   token=os.environ["QISKIT_IBM_TOKEN"],
                                   instance=os.environ["QISKIT_IBM_INSTANCE"])
    backend = service.least_busy(operational=True, simulator=False)
    print(f"Transpiling for {backend.name} (can take a little while on the board)...")
    isa = generate_preset_pass_manager(backend=backend, optimization_level=3).run(qc)
    ops = isa.count_ops()
    twoq = sum(v for k, v in ops.items() if k in ("cz", "ecr", "cx"))
    print(f"  circuit depth {isa.depth()}, two-qubit gates {twoq}")

    sampler = SamplerV2(mode=backend)
    sampler.options.dynamical_decoupling.enable = True   # reduces idle-qubit errors
    job = sampler.run([isa], shots=SHOTS)
    print("  job ID:", job.job_id())
    while not job.in_final_state():
        print("  status:", job.status()); time.sleep(5)
    results["hardware"] = to_probs(job.result()[0].data.meas.get_counts())

# 6) Report
tvd = lambda p, q: 0.5 * np.abs(p - q).sum()
cols = list(results)
print(f"\nTones {freqs} Hz | fs {FS} Hz | bin width {FS/N:.0f} Hz | {SHOTS} shots\n")
print(" bin   freq" + "".join(f"{c:>11}" for c in cols) + f"   bars = {cols[-1]}")
for k in range(N):
    f = k * FS / N if k <= N // 2 else (k - N) * FS / N   # bins above 8 = negative freqs
    print(f" {k:3} {f:6.0f}" + "".join(f"{results[c][k]:11.3f}" for c in cols)
          + "   " + "#" * int(round(results[cols[-1]][k] * 40)))
print()
for c in cols[1:]:
    print(f"Total variation distance, expected vs {c}: {tvd(expected, results[c]):.3f}")

json.dump({k: v.tolist() for k, v in results.items()} | {"freqs": freqs},
          open("qft_result.json", "w"), indent=1)
```
Expected results:
- **Simulator:** 750 Hz → peaks of about 0.5 at bin 3 (+750 Hz) and bin 13 (−750 Hz), mirror images because the signal is real. TVD (total variation distance) about 0.01–0.03, which is shot noise.
- **Hardware:** the same peaks plus a noise floor; TVD probably 0.1–0.3. Most of the circuit is spent loading the data (`StatePreparation`), so there's no quantum speedup.

Experiments:
1. A tone between bins (`875`) → spectral leakage.
2. `N_QUBITS = 3` vs `4` vs `5` → see how noise grows with circuit depth.
3. Dynamical decoupling on vs off → compare TVD.

---

## 6. App Lab app: `quantum-bell-bars` (LED matrix) 📝

On a button press (D2 → GND), or once 30 s after start, it runs a Bell circuit and shows **4 bars for 00/01/10/11** on the LED matrix, using grayscale for partial heights. While waiting it shows a random "superposition" shimmer; an error shows an X. It starts on the simulator; `"use_hardware": true` switches to IBM.

Create it in App Lab with **Create new app** (this generates `app.yaml` and `sketch.yaml`), then add the files below.

### `python/main.py`
```python
import json, threading, time
from pathlib import Path
from arduino.app_utils import App, Bridge
from qiskit import QuantumCircuit
from qiskit.primitives import StatevectorSampler

CFG = json.loads((Path(__file__).parent / "ibm_config.json").read_text())
SHOTS = 1024
busy = threading.Lock()


def bell_circuit():
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def run_simulator(qc):
    return StatevectorSampler().run([qc], shots=SHOTS).result()[0].data.meas.get_counts()


def run_hardware(qc):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    from qiskit.transpiler import generate_preset_pass_manager
    svc = QiskitRuntimeService(channel="ibm_cloud", token=CFG["token"], instance=CFG["instance"])
    backend = svc.least_busy(operational=True, simulator=False)
    isa = generate_preset_pass_manager(backend=backend, optimization_level=1).run(qc)
    job = SamplerV2(mode=backend).run([isa], shots=SHOTS)
    print(f"Job {job.job_id()} sent to {backend.name}, waiting...")
    return job.result()[0].data.meas.get_counts()


def to_levels(counts):
    """Bar level 0..56 = 8 rows x 7 brightness steps, scaled to the tallest bar."""
    vals = [counts.get(k, 0) for k in ("00", "01", "10", "11")]
    top = max(vals) or 1
    return [round(56 * v / top) for v in vals]


def quantum_job():
    if not busy.acquire(blocking=False):
        print("Job already running, ignoring trigger")
        return
    try:
        Bridge.call("set_waiting", 1)
        qc = bell_circuit()
        counts = run_hardware(qc) if CFG.get("use_hardware") else run_simulator(qc)
        print("Counts:", dict(sorted(counts.items())))
        Bridge.call("show_bars", *to_levels(counts))
    except Exception as e:
        print("Quantum job failed:", e)
        Bridge.call("show_error", 1)
    finally:
        busy.release()


def on_trigger():
    # Called by the sketch when the button is pressed. Run in a thread so the Bridge isn't blocked.
    threading.Thread(target=quantum_job, daemon=True).start()


def first_run():
    time.sleep(30)  # wait for the board's boot logo to finish
    on_trigger()


Bridge.provide("quantum_trigger", on_trigger)
threading.Thread(target=first_run, daemon=True).start()

App.run()
```

### `python/ibm_config.json` (⚠️ contains the key, so don't share or export the app)
```json
{
  "use_hardware": false,
  "token": "PASTE-YOUR-API-KEY",
  "instance": "crn:v1:bluemix:public:quantum-computing:..."
}
```

### `python/requirements.txt`
```
qiskit
qiskit-ibm-runtime
```
The first start takes several minutes while Qiskit installs into the container.

### `sketch/sketch.ino`
```cpp
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;
uint8_t frame[104];          // 8 rows x 13 cols, brightness 0-7

const int BUTTON_PIN = 2;    // button between D2 and GND
unsigned long lastPress = 0;

// State shared with Bridge callbacks; drawing happens only in loop()
volatile int mode = 0;       // 0 idle, 1 waiting, 2 show bars, 3 error
volatile int levels[4] = {0, 0, 0, 0};
volatile bool dirty = true;

void px(int r, int c, uint8_t v) {
  if (r >= 0 && r < 8 && c >= 0 && c < 13) frame[r * 13 + c] = v;
}

// ---- Called from Python ----
void set_waiting(int on) { mode = on ? 1 : 0; dirty = true; }
void show_error(int on)  { mode = 3; dirty = true; }
void show_bars(int a, int b, int c, int d) {
  levels[0] = a; levels[1] = b; levels[2] = c; levels[3] = d;
  mode = 2; dirty = true;
}

// ---- Drawing ----
void drawBars() {
  memset(frame, 0, sizeof(frame));
  for (int b = 0; b < 4; b++) {
    int full = levels[b] / 7, part = levels[b] % 7;
    int c0 = 1 + b * 3;                       // bars at columns 1-2, 4-5, 7-8, 10-11
    for (int i = 0; i < full && i < 8; i++) { px(7 - i, c0, 7); px(7 - i, c0 + 1, 7); }
    if (part && full < 8) { px(7 - full, c0, part); px(7 - full, c0 + 1, part); }
  }
  matrix.draw(frame);
}

void drawSuperposition() {                    // random shimmer while the job runs
  for (int i = 0; i < 104; i++) frame[i] = (random(10) < 3) ? random(1, 8) : 0;
  matrix.draw(frame);
}

void drawError() {                            // an "X"
  memset(frame, 0, sizeof(frame));
  for (int i = 0; i < 8; i++) { px(i, 2 + i, 7); px(i, 10 - i, 7); }
  matrix.draw(frame);
}

void setup() {
  Serial.begin(115200);
  matrix.begin();
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  randomSeed(analogRead(A5));

  Bridge.begin();
  Bridge.provide("set_waiting", set_waiting);
  Bridge.provide("show_bars", show_bars);
  Bridge.provide("show_error", show_error);
}

void loop() {
  // Button -> ask Python to run a quantum job
  if (digitalRead(BUTTON_PIN) == LOW && millis() - lastPress > 500) {
    lastPress = millis();
    Serial.println("Button: quantum_trigger");
    Bridge.notify("quantum_trigger");
  }

  if (mode == 1) {                 // animate continuously while waiting
    drawSuperposition();
    delay(80);
  } else if (dirty) {
    dirty = false;
    if (mode == 2) drawBars();
    else if (mode == 3) drawError();
  }
  delay(10);
}
```

### Troubleshooting
| Symptom | Likely cause |
|---|---|
| Missing `Arduino_RouterBridge.h` / `Arduino_LED_Matrix.h` | Add the library in App Lab's sketch **Libraries** panel |
| No dim noise pixels | Add `matrix.setGrayscaleBits(3);` after `matrix.begin();` |
| Button does nothing | Check the `quantum_trigger` name on both sides (a mismatched notify fails without an error) |
| X on the matrix | Python exception; check the log (token, CRN, network) |
| `ModuleNotFoundError: qiskit` | `requirements.txt` not in `python/`, or the install failed |

---

## 7. Project ideas explored

### 7.1 Original proof of concept: UNO Q + IBM Quantum
```
[Button / LED matrix] ⇄ STM32 sketch ⇄ Bridge ⇄ Python app (Linux) ⇄ HTTPS ⇄ IBM Quantum (Qiskit Runtime)
```
- Demos: a quantum random number generator ("quantum dice") and a Bell-state visualizer.
- Design rules: load Qiskit once at startup; **submit jobs without blocking** (background thread); keep a **stock of random bits** to hide queue waits; have a simulator mode for offline demos; never hard-code the key.
- Phases: 0 accounts → 1 Qiskit on the board ✅ → 2 first hardware job ✅ → 3 App Lab app → 4 test and harden → 5 demo and write-up.
- Fallback if the board can't run Qiskit: run Qiskit on a laptop or VM and have the board call it over HTTP or MQTT. (Not needed, since Qiskit runs on the board.)

### 7.2 Sound localization with 3 microphones (TDOA)
- Speed of sound ≈ 343 m/s. **3 mics in a triangle → 360° direction in 2D**; position (x, y) needs mics several meters apart (harder).
- **All 3 channels must be sampled from the same clock** (separate USB mics drift apart).
- Hardware: 3× MAX9814 electret modules on A0–A2, equilateral triangle with 15–25 cm sides, sampling ≥ 40 kS/s per channel.
- Numbers (d = 20 cm, fs = 48 kS/s): largest delay ≈ 0.58 ms ≈ **±28 samples**; 1 sample ≈ 7 mm ≈ 2° near broadside; parabolic peak fit gives sub-sample precision.
- Split: **MCU** detects the sound and cross-correlates only over ±28 lags (cheap) → sends `(τ12, τ13, τ23, confidence)` over Bridge. **Linux** solves the angle by least squares, smooths it and displays it. Streaming raw audio (~290 kB/s) over Bridge probably wouldn't keep up.
- Consistency check: τ12 + τ23 + τ31 ≈ 0.
- Phases: 0 laptop simulation (GCC-PHAT, a noise-robust correlation method, plus the solver) → 1 check that the ADC sampling is even enough (timer + DMA; fallback: a multichannel USB array such as ReSpeaker) → 2 MCU detection and delays → 3 angle and display → 4 accuracy measurements (every 30°, echoey vs. quiet room).
- Risks: uneven ADC timing, echoes (use GCC-PHAT and only the first ~5 ms), mismatched mics, small triangle.

### 7.3 Adding IBM Quantum to the localization project
Quantum gives no speed or accuracy benefit here, so it runs **alongside** the classical solver as a comparison (batch mode, asynchronous).
- **Option A (recommended): QAOA direction search.** Encode 16 or 32 directions in 4–5 qubits with **Gray code** (a bit-flip error lands on a nearby direction). Cost = squared TDOA residual, converted to a sum of Z-products with the Walsh–Hadamard transform:
  ```python
  terms = []
  for S in range(1, K):
      c = np.mean([cost[k] * (-1)**bin(k & S).count("1") for k in range(K)])
      if abs(c) > 0.02:
          terms.append(("".join("Z" if (S >> i) & 1 else "I" for i in reversed(range(n))), c))
  H = SparsePauliOp.from_list(terms)
  ansatz = QAOAAnsatz(H, reps=2)
  ```
  Train the parameters on the simulator; send only the final sampling run to hardware.
- **Option B:** a variational quantum classifier (3 qubits) for the source quadrant, compared with logistic regression.
- **Option C:** mic placement as a QUBO optimization problem (offline, so queue waits don't matter).

### 7.4 Microphone as input to the quantum computer
Audio must be reduced to a few numbers first:
- **Angle encoding:** n features → n qubit rotations (shallow).
- **Amplitude encoding:** 2ⁿ values → n qubits (deeper; fine up to about 4 qubits).

Ideas:
1. **Quantum spectrum (recommended):** amplitude-encode 16 samples → QFT → power spectrum, compared with an FFT. Whistle at the board and see the spectrum on the LED matrix. (`qft_spectrum.py` is the first step.)
2. **Sound classifier:** 4 band energies → 4 qubits, quantum kernel SVM vs. classical SVM (clap / snap / whistle / voice).
3. **"Quantum theremin":** pitch/loudness → rotation angles → measured results drive the buzzer or LEDs.
4. **Classical mic noise vs. quantum randomness:** randomness test comparison.

Practical: one MAX9814 on A0 is enough; send only features or 16-sample windows over Bridge; live demo on the simulator, hardware in batches; readout error correction (e.g. TREX) helps.

### 7.5 Other ideas
- CHSH Bell-inequality test: 4 small circuits, shows S > 2 on real hardware.
- Quantum-seeded sensor art; a small QAOA routing or scheduling problem driving actuators.

---

## 8. Next steps
1. Run `python qft_spectrum.py`, then `python qft_spectrum.py 750 --run`.
2. Build and test the `quantum-bell-bars` App Lab app (simulator first, then `use_hardware: true`).
3. Swap the Bell circuit in the app for the QFT spectrum and display it on the 13 matrix columns.
4. Add a microphone on A0 and feed real 16-sample windows into the QFT.
5. Optionally, the 3-mic localization simulator (Phase 0), with the QAOA comparison.

## 9. Security reminders
- Never paste the API key into source code you share; `~/.qiskit_env` is `chmod 600`.
- If the key is ever exposed, delete it on quantum.cloud.ibm.com and create a new one.
- Keep an eye on monthly quota usage (Open Plan ≈ 10 min/month).
