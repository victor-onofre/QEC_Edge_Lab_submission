#!/usr/bin/env python3
"""Draw the memory-experiment circuits of a saved run, as the app builds them.

The circuit builder is taken verbatim from python/main.py (rep_code_circuit), and the physical qubits come from the
run's metadata ("line"), so the pictures show what was submitted for that job before IBM-specific compilation.
One extra picture shows a local re-compilation to Heron-style native gates (cz, rz, sx, x): an illustration, not the
stored job circuit.

Usage (repo root):  python3 code/qec_lab/tools/draw_circuits.py data/ibm_runs/<run>.json media/
Needs: qiskit, matplotlib, pylatexenc.
"""
import ast, json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile

HERE = Path(__file__).resolve().parent
src = (HERE.parent / "python" / "main.py").read_text()
fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "rep_code_circuit")
ns = {}
exec(compile(ast.Module([fn], []), "main.py", "exec"), ns)
rep_code_circuit = ns["rep_code_circuit"]


def labelled(d, rounds, truth, line):
    """Same circuit, with one named register per qubit: role and physical qubit."""
    base = rep_code_circuit(d, rounds, truth)
    qregs = [QuantumRegister(1, (f"data {k // 2}" if k % 2 == 0 else f"check {k // 2}") + f"  (Q{line[k]})") for k in range(2 * d - 1)]
    cregs = [ClassicalRegister(c.size, {"final": "final readout"}.get(c.name, c.name.replace("s", "round ") )) for c in base.cregs]
    out = QuantumCircuit(*qregs, *cregs)
    out.compose(base, qubits=range(2 * d - 1), clbits=range(base.num_clbits), inplace=True)
    return out


def main():
    meta = json.loads(Path(sys.argv[1]).read_text())
    dest = Path(sys.argv[2]); line, R, be = meta["line"], meta["rounds"], meta["backend"]
    style = {"backgroundcolor": "#ffffff", "dpi": 150}
    jobs = [(3, 1, f"circuit_{be}_d3_logical1.png"), (5, 0, f"circuit_{be}_d5_logical0.png")]
    for d, truth, name in jobs:
        c = labelled(d, R, truth, line)
        fig = c.draw("mpl", fold=-1, cregbundle=True, style=style, scale=0.8)
        fig.suptitle(f"{be} job {meta.get('job_id', '-')}: distance {d}, logical |{truth}>, {R} rounds, "
                     f"{2 * d - 1} qubits ({c.depth()} layers before compilation)", fontsize=11, y=1.0)
        fig.savefig(dest / name, bbox_inches="tight", dpi=150); print("wrote", dest / name, c.count_ops())
    # one round at d=3, re-compiled locally to Heron-style native gates
    c = transpile(rep_code_circuit(3, 1, 1), basis_gates=["cz", "rz", "sx", "x", "measure", "reset"],
                  coupling_map=[[i, i + 1] for i in range(4)] + [[i + 1, i] for i in range(4)], optimization_level=1)
    fig = c.draw("mpl", fold=-1, cregbundle=True, style=style, scale=0.8, idle_wires=False)
    fig.suptitle("Distance 3, logical |1>, one round, re-compiled to native gates (cz, rz, sx, x): illustration", fontsize=11, y=1.0)
    fig.savefig(dest / "circuit_d3_native_gates.png", bbox_inches="tight", dpi=150); print("wrote native", c.count_ops())
    print(rep_code_circuit(3, 1, 1).draw("text", fold=-1, cregbundle=True))


if __name__ == "__main__":
    main()
