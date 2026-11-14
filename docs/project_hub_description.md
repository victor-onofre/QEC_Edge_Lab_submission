TITLE
QEC Edge Lab: a €60 Arduino that corrects real quantum-computer errors

SHORT DESCRIPTION (one line)
An Arduino UNO Q decodes errors from IBM's real quantum computers in real time, with an on-device AI decoder that makes up to 9× fewer mistakes.

TAGS
Junction Finland 2026, Arduino UNO Q, Modulino, Edge AI, Quantum computing

---------------------------------------------------------------------------

STORY

In one sentence
Quantum computers make mistakes all the time, and a fast classical computer has to fix them on the fly. We built that "error fixer" on an Arduino UNO Q, tested it on real IBM quantum computers, and taught it with on-device AI to fix errors up to 9× better than the standard method. No quantum background is needed to follow this project.

In 30 seconds
- Real quantum hardware: the Arduino sends experiments to IBM's 156-qubit quantum computers over the internet (free account).
- The Arduino fixes the errors: its real-time microcontroller works out which quantum bits went wrong, and measures exactly how long that takes.
- Edge AI: a small neural network trained on the Arduino learns the "personality" of each quantum chip and makes up to 9× fewer mistakes (typically 2–3×) than the best classical method.
- You can feel the limit: turn the Modulino Knob to speed up the stream of errors; the LED matrix fills up and the Modulino Buzzer growls when the Arduino can no longer keep up.

Quantum computing in one minute
Quantum bits (qubits) are fragile: heat, stray signals or simply time make them flip by accident. Quantum error correction spreads one bit of information over many qubits, like whispering a message with several people at once in a noisy room. You cannot look at the qubits directly, so helper qubits keep asking "are these two neighbours still the same?". The answers are clues. A classical program, the decoder, reads the clues and works out which qubit flipped so it can be fixed. The decoder must be accurate and fast: new clues arrive about every microsecond on IBM machines. Like a supermarket cashier, if customers arrive faster than they are served, the queue grows forever.

Detecting or correcting? As in Google's and IBM's error-correction experiments, the qubits are not physically flipped back: the decoder works out which errors happened and corrects the measured result in software. The proof that this is correction and not just detection is that the final answer gets more reliable as more qubits are added. Our decoding runs after each IBM job; the real-time test replays the real data on the Arduino at realistic speed.

Why it matters
Decoding is one of the hardest engineering problems on the road to useful quantum computers. Google, Google DeepMind (AlphaQubit), Riverlane, NVIDIA and IBM are all building dedicated FPGA, GPU or neural-network decoders for it. QEC Edge Lab explores the same two ideas, neural-network decoding and putting the decoder close to the experiment, on a €60 board.

What we built
The Arduino UNO Q is two computers on one board, exactly like the control system of a real quantum computer:
- Linux side ("the office"): talks to IBM, collects the clues, learns how each chip misbehaves, trains the AI decoder (about 2.6 s on the board) and serves a live web dashboard.
- Microcontroller ("the factory floor", STM32 at 160 MHz): runs the decoders in real time (classical union-find and the AI) and times every decode to the clock cycle.
- 8×13 LED matrix: progress, results, and the live queue of unsolved errors.
- Modulino Knob: sets how fast new clues arrive.
- Modulino Buzzer: growls when the decoder falls behind.

How it works
1. The Arduino builds error-correction experiments with 5 to 49 qubits and sends them to IBM as one job (about 6 seconds of quantum computer time).
2. The clues come back; the Linux side learns the chip's noise and trains the neural network.
3. The microcontroller decodes every shot with several decoders, including the AI (integer-only neural network, bit-exact with the Python version, about 8.5 KB of RAM).
4. Real-time test: thousands of real clue sets are loaded into the microcontroller's memory and replayed at a chosen speed. The knob sets the speed; the LED matrix and buzzer show when the decoder can no longer keep up.

Results on real IBM quantum computers
- Error correction works on the real chips: spreading the information over 21 qubits instead of 5 cut mistakes from 4.8% to 0.075% (64× fewer).
- The AI decoder makes up to 9.5× fewer mistakes (typically 2–3×) than the best classical decoder on codes of up to 17 qubits, on two different IBM chips.
- Why the AI wins: on these chips a stored 1 fades into a 0 about 10–16× more often than a 0 turns into a 1. The AI learned this by itself from the data. The Arduino also found one qubit that flips 31% of the time.
- Speed: the AI decoder keeps up down to about 9 microseconds per round, as fast as the fastest classical decoder we built. We also made the classical decoder 2.4–4× faster on the microcontroller with identical answers.

Why this could work on neutral-atom and trapped-ion quantum computers
IBM's superconducting qubits need a decoder every ~1 microsecond, which is too fast for a microcontroller. Neutral-atom and trapped-ion quantum computers run much slower rounds, roughly 1 millisecond, giving the decoder about 100× more time than our Arduino needs. These machines already use AI decoders today (Harvard/QuEra/MIT on neutral atoms, Quantinuum on trapped ions), so a cheap, low-power decoder that learns each device's noise could be a practical building block. We have not tested on those machines yet.

Who it helps
- Students and teachers: see, hear and touch quantum error correction on real hardware for the price of an Arduino.
- Engineers building quantum computers: a cheap bench to test decoder speed and accuracy on embedded chips.
- Researchers: real measurements of how individual qubits on IBM chips misbehave, from a free account.

Honest limitations
- The real-time test replays real IBM data on the Arduino; the timing is real, but the loop with the quantum computer is not closed (the internet adds milliseconds).
- About 9 µs per round is too slow for superconducting qubits; it would likely be fast enough for neutral-atom and trapped-ion machines.
- Corrections are applied in software to the measured result (as in Google's and IBM's experiments), not sent back to the qubits, and decoding happens after each IBM job.
- Repetition code only: it protects against bit flips, not phase errors, so it does not protect an arbitrary quantum state; 2-D codes are the next step.
- On large codes the AI decoder hits an accuracy floor of about 0.2–0.3%, where the classical decoder is better, so the best design combines both.

Hardware
- Arduino UNO Q (2 GB)
- Modulino Knob
- Modulino Buzzer
- USB-C cable and power supply

Software
- Arduino App Lab (Python app + Arduino sketch + WebUI brick)
- IBM Quantum (free Open Plan), Qiskit
- numpy (AI training on the board)

Code and full results
https://github.com/victor-onofre/QEC_Edge_Lab_submission
(Import qec_lab_import.zip into Arduino App Lab, add your IBM key to python/ibm_config.json, connect the Knob and Buzzer, and run.)
