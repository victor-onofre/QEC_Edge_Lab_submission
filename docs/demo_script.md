# Demo script (2 minutes)

Run it **offline** from saved runs, so venue Wi-Fi and the IBM queue cannot break it.
Before you start: dashboard open on the **Real-time** tab, d=11 from a saved ibm_fez run already loaded, knob connected.

| Time | Say | Show |
|---|---|---|
| 0:00–0:20 | "Quantum computers make errors every microsecond. A classical computer has to catch them in real time, or the computation is lost." | The board, the LED matrix and the knob |
| 0:20–0:50 | "We ran error-correction codes on IBM's 156-qubit chips. Adding qubits pushes the logical error from 5% down to below 1 in 4,000, decoded here on the Arduino's microcontroller." | Accuracy tab: logical error vs distance |
| 0:50–1:15 | "The board also learned things about the chips: a 1 decays 10 to 16 times faster than a 0, and one qubit flips 31% of the time. Our AI decoder, trained on the board, learns these quirks by itself." | Highlights card; AI decoder line |
| 1:15–1:45 | "Now the hard part: speed. I shorten the time between rounds with this knob." Turn slowly past about 15 µs. | LED bars fill up, buzzer growls, dashboard turns red |
| 1:45–2:00 | "Here is the limit of a $50 microcontroller: 15 microseconds per round. Too slow for superconducting qubits, fast enough for ion traps and neutral atoms. A full quantum control bench in your hand." | Sweep chart with the limit line |

**Backup:** if the board fails, play the screen recording of the same steps.

## Likely judge questions
- *Is it really real time?* The timing is real (STM32 cycle counter, interrupts on); the syndromes are real IBM data
  replayed at a chosen rate. The loop with IBM is not closed — the network adds milliseconds.
- *Where is the AI?* Trained on the board's Linux side from the chip's own syndromes; inference runs on the STM32 and
  is timed and compared against classical decoders on held-out shots.
- *Why Arduino and not a laptop?* Deterministic timing: on the laptop a single clock read cost 1.3 µs and the OS
  interrupts the decoder; the STM32 gives cycle-exact numbers, like real control electronics.
