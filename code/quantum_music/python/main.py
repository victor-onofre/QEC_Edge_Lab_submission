import json, math, threading, time
from datetime import datetime
from pathlib import Path
import numpy as np
from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.circuit.library import QFTGate
from qiskit.primitives import StatevectorSampler

CFG = json.loads((Path(__file__).parent / "ibm_config.json").read_text())
N_QUBITS = 5
N_BINS = 2 ** N_QUBITS                      # 32 possible notes
SHOTS = CFG.get("shots", 128)               # for statistics
MELODY = CFG.get("melody_notes", 16)        # how many notes are played
NOTE_MS = 150
KNOB_STEPS = CFG.get("knob_steps", 64)
MIN_INTERVAL = CFG.get("min_interval_s", 15)

PHI = Parameter("phi")
ui = WebUI()
state = {"hardware": bool(CFG.get("use_hardware")), "backend": "-", "depth": None,
         "twoq": None, "phase": "starting"}
history = []
runners = {}
latest = None
last_value = 0
cv = threading.Condition()


# ---------------- Quantum circuit ----------------
def build_circuit():
    """Phase estimation: H on all qubits, phase 2^k*phi on qubit k, inverse QFT."""
    qc = QuantumCircuit(N_QUBITS)
    qc.h(range(N_QUBITS))
    for k in range(N_QUBITS):
        qc.p((2 ** k) * PHI, k)
    qc.append(QFTGate(N_QUBITS).inverse(), range(N_QUBITS))
    qc.measure_all()
    return qc


QC = build_circuit()
CIRCUIT_TEXT = str(QC.draw(output="text", fold=-1))


def ideal_probs(phi):
    j = np.arange(N_BINS)
    k = np.arange(N_BINS)[:, None]
    amp = np.exp(1j * j * (phi - 2 * np.pi * k / N_BINS)).sum(axis=1) / N_BINS
    return np.abs(amp) ** 2


def make_runner(hw):
    if not hw:
        return {"hw": False, "name": "local simulator", "circuit": QC,
                "sampler": StatevectorSampler(), "depth": QC.decompose(reps=3).depth(),
                "twoq": None}
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
    from qiskit.transpiler import generate_preset_pass_manager
    svc = QiskitRuntimeService(channel="ibm_cloud", token=CFG["token"], instance=CFG["instance"])
    backend = svc.least_busy(operational=True, simulator=False)
    set_phase(f"transpiling for {backend.name}")
    isa = generate_preset_pass_manager(backend=backend, optimization_level=3).run(QC)
    ops = isa.count_ops()
    twoq = sum(v for k, v in ops.items() if k in ("cz", "ecr", "cx"))
    print(f"{backend.name}: depth {isa.depth()}, two-qubit gates {twoq}")
    return {"hw": True, "name": backend.name, "circuit": isa,
            "sampler": SamplerV2(mode=backend), "depth": isa.depth(), "twoq": twoq}


def get_runner():
    hw = state["hardware"]
    if hw not in runners:
        set_phase("connecting to IBM" if hw else "starting simulator")
        runners[hw] = make_runner(hw)
    r = runners[hw]
    state.update(backend=r["name"], depth=r["depth"], twoq=r["twoq"])
    return r


# ---------------- Web UI ----------------
def ui_send(event, data):
    try:
        ui.send_message(event, data)
    except Exception as e:
        print(f"UI send {event} failed: {e}")


def push_status():
    ui_send("status", {**state, "knob_steps": KNOB_STEPS, "n_bins": N_BINS,
                       "shots": SHOTS, "melody": MELODY, "min_interval": MIN_INTERVAL})


def set_phase(p):
    state["phase"] = p
    push_status()


def _data(args):
    return args[-1] if args and isinstance(args[-1], dict) else {}


def on_hello(*args):
    push_status()
    ui_send("circuit", {"text": CIRCUIT_TEXT})
    ui_send("history", history[-100:])
    ui_send("knob", {"value": last_value})


def on_ui_phase(*args):
    on_knob(int(_data(args).get("value", 0)))


def on_ui_rerun(*args):
    on_knob(last_value)


def on_ui_hardware(*args):
    state["hardware"] = bool(_data(args).get("on"))
    print("Mode:", "IBM hardware" if state["hardware"] else "simulator")
    push_status()


ui.on_message("hello", on_hello)
ui.on_message("set_phase", on_ui_phase)
ui.on_message("rerun", on_ui_rerun)
ui.on_message("set_hardware", on_ui_hardware)


# ---------------- Board (LED matrix + buzzer) ----------------
def freq(note):                      # 32 chromatic notes from A3 (220 Hz)
    return int(round(220 * 2 ** (note / 12)))


def safe_call(name, *args):
    try:
        Bridge.call(name, *args)
    except Exception as e:
        print(f"Bridge call {name} failed: {e}")


def show_histogram(counts, expected):
    top = max(counts) or 1
    for col in range(13):            # 13 columns centred on the expected note
        b = (expected - 6 + col) % N_BINS
        h = 0 if counts[b] == 0 else max(1, round(8 * counts[b] / top))
        safe_call("set_hist", col, h)
    safe_call("show_hist", 1)


def play(notes, expected):
    for i, n in enumerate(notes):
        if latest is not None:       # knob moved: stop and run the new position
            print("  knob moved - interrupting melody")
            return
        col = (n - expected + 6) % N_BINS
        ui_send("note", {"i": i, "note": n})
        safe_call("play_note", freq(n), NOTE_MS, col if col < 13 else -1)
        time.sleep(NOTE_MS / 1000 * 1.15)
    ui_send("note", {"i": -1, "note": -1})


# ---------------- Worker ----------------
def worker():
    global latest, last_value
    last_hw_run = 0.0
    while True:
        with cv:
            while latest is None:
                cv.wait()
        try:
            r = get_runner()
        except Exception as e:
            print("Setup failed:", e)
            set_phase(f"error: {e}")
            safe_call("show_error", 1)
            with cv:
                latest = None
            continue
        if r["hw"]:
            wait = MIN_INTERVAL - (time.time() - last_hw_run)
            if wait > 0:
                set_phase(f"rate limit {wait:.0f}s")
                time.sleep(wait)
        with cv:
            value, latest = latest, None
        last_value = value

        phi = 2 * math.pi * (value % KNOB_STEPS) / KNOB_STEPS
        ideal_bin = phi * N_BINS / (2 * math.pi)
        expected = round(ideal_bin) % N_BINS
        safe_call("set_waiting", 1)
        set_phase("submitting")
        t0 = time.time()
        try:
            job = r["sampler"].run([(r["circuit"], [phi])], shots=SHOTS)
            job_id = job.job_id() if r["hw"] else "-"
            if r["hw"]:
                print(f"  job {job_id} on {r['name']}")
                while not job.in_final_state():
                    set_phase(str(job.status()).lower())
                    time.sleep(2)
            bits = job.result()[0].data.meas.get_bitstrings()
        except Exception as e:
            print("Quantum job failed:", e)
            set_phase(f"error: {e}")
            safe_call("show_error", 1)
            continue
        if r["hw"]:
            last_hw_run = time.time()

        notes = [int(b, 2) for b in bits]
        counts = np.bincount(notes, minlength=N_BINS)
        ideal = ideal_probs(phi)
        hit = counts[expected] / SHOTS
        tvd = 0.5 * np.abs(counts / SHOTS - ideal).sum()
        result = {
            "run": len(history) + 1, "time": datetime.now().strftime("%H:%M:%S"),
            "hardware": r["hw"], "backend": r["name"], "knob": value,
            "phi_deg": round(math.degrees(phi), 2), "ideal_bin": round(ideal_bin, 3),
            "expected": expected, "notes": notes[:MELODY], "counts": counts.tolist(),
            "ideal": [round(float(p), 5) for p in ideal], "hit": round(float(hit), 4),
            "hit_ideal": round(float(ideal[expected]), 4), "tvd": round(float(tvd), 4),
            "seconds": round(time.time() - t0, 1), "job_id": job_id, "shots": SHOTS,
        }
        history.append(result)
        del history[:-200]
        ui_send("result", result)
        print(f"knob {value:4d} phi={result['phi_deg']:6.1f}° hit {hit:4.0%} "
              f"(ideal {ideal[expected]:4.0%}) TVD {tvd:.3f} [{r['name']}, {result['seconds']}s]")

        show_histogram(counts.tolist(), expected)
        set_phase("playing")
        play(notes[:MELODY], expected)
        set_phase("idle")


def on_knob(value):
    global latest
    with cv:
        latest = int(value)
        cv.notify()
    ui_send("knob", {"value": int(value)})


def on_press():
    on_knob(last_value)              # re-run the same position


def first_run():
    time.sleep(30)                   # wait for the boot logo
    on_knob(0)


Bridge.provide("knob_changed", on_knob)
Bridge.provide("knob_pressed", on_press)
threading.Thread(target=worker, daemon=True).start()
threading.Thread(target=first_run, daemon=True).start()

App.run()
