#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Modulino.h>

Arduino_LED_Matrix matrix;
ModulinoBuzzer buzzer;
ModulinoKnob knob;
uint8_t frame[104];                    // 8 x 13, brightness 0-7

const int KNOB_STEPS = 64;             // keep equal to "knob_steps" in ibm_config.json
const unsigned long SETTLE_MS = 350;   // knob must rest this long before a job is sent

// mode: 0 idle, 1 waiting (shimmer), 2 histogram, 3 error, 4 turning (dial)
volatile int mode = 0;
volatile int hist[13];
volatile bool dirty = false, notePending = false;
volatile int nFreq, nMs, nCol;

int16_t lastKnob = 0, sentKnob = 0;
unsigned long lastChange = 0, lastPress = 0;
bool moved = false;

void px(int r, int c, uint8_t v) { if (r>=0 && r<8 && c>=0 && c<13) frame[r*13+c] = v; }

// ---- Called from Python (store state only; loop() draws) ----
void set_waiting(int on)               { mode = on ? 1 : 0; dirty = true; }
void set_hist(int col, int h)          { if (col >= 0 && col < 13) hist[col] = h; }
void show_hist(int on)                 { mode = 2; nCol = -1; dirty = true; }
void show_error(int on)                { mode = 3; dirty = true; }
void play_note(int f, int ms, int col) { nFreq = f; nMs = ms; nCol = col; notePending = true; }

// ---- Drawing ----
void drawHist(int highlight) {
  memset(frame, 0, sizeof(frame));
  for (int c = 0; c < 13; c++) {
    uint8_t v = (c == highlight) ? 7 : (c == 6 ? 4 : 2);   // centre = expected note
    for (int i = 0; i < hist[c] && i < 8; i++) px(7 - i, c, v);
  }
  matrix.draw(frame);
}

void drawDial(int value) {             // vertical needle = knob position
  memset(frame, 0, sizeof(frame));
  int pos = ((value % KNOB_STEPS) + KNOB_STEPS) % KNOB_STEPS;
  int col = pos * 13 / KNOB_STEPS;
  for (int r = 0; r < 8; r++) px(r, col, 7);
  matrix.draw(frame);
}

void drawSuperposition() {
  for (int i = 0; i < 104; i++) frame[i] = (random(10) < 3) ? random(1, 8) : 0;
  matrix.draw(frame);
}

void drawError() {
  memset(frame, 0, sizeof(frame));
  for (int i = 0; i < 8; i++) { px(i, 2+i, 7); px(i, 10-i, 7); }
  matrix.draw(frame);
  buzzer.tone(150, 400);
}

void setup() {
  Serial.begin(115200);
  matrix.begin();
  Modulino.begin();
  buzzer.begin();
  knob.begin();
  randomSeed(analogRead(A5));
  lastKnob = sentKnob = knob.get();

  Bridge.begin();
  Bridge.provide("set_waiting", set_waiting);
  Bridge.provide("set_hist", set_hist);
  Bridge.provide("show_hist", show_hist);
  Bridge.provide("show_error", show_error);
  Bridge.provide("play_note", play_note);
}

void loop() {
  // --- Knob: show dial while turning, send position once it settles ---
  int16_t v = knob.get();
  if (v != lastKnob) {
    lastKnob = v;
    lastChange = millis();
    moved = true;
    mode = 4;
    drawDial(v);
    buzzer.tone(2000, 5);                     // tiny click per step
  }
  if (moved && millis() - lastChange > SETTLE_MS) {
    moved = false;
    if (v != sentKnob) {
      sentKnob = v;
      Serial.print("knob -> "); Serial.println(v);
      Bridge.notify("knob_changed", (int)v);
    } else {
      mode = 2; dirty = true;                 // returned to same spot: redraw histogram
    }
  }
  if (knob.isPressed() && millis() - lastPress > 600) {
    lastPress = millis();
    Bridge.notify("knob_pressed");
  }

  // --- Output ---
  if (notePending) {
    notePending = false;
    buzzer.tone(nFreq, nMs);
    drawHist(nCol);
  } else if (mode == 1) {
    drawSuperposition();
    delay(60);
  } else if (dirty) {
    dirty = false;
    if (mode == 2) drawHist(-1);
    else if (mode == 3) drawError();
  }
  delay(10);
}
