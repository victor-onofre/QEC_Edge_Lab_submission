// QEC Decoder Lab - Stage 1
// The STM32 decodes repetition-code syndromes (from IBM hardware or a noise model)
// with five classical decoders and a small neural network (AI decoder, qec_ai.h)
// and measures how many CPU cycles each one needs.
#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
#include <Modulino.h>
#include "qec_decoders.h"
#include "qec_ai.h"
#include "qec_rt.h"

// ---- cycle-accurate timing --------------------------------------------------
// If the sketch does not compile, set QEC_USE_DWT and/or QEC_USE_ZEPHYR to 0:
// timing then falls back to micros() (1 us resolution, averaged over many shots).
#define QEC_USE_DWT 1
#define QEC_USE_ZEPHYR 1

#if QEC_USE_DWT && __has_include(<cmsis_core.h>)
  #include <cmsis_core.h>
  #define QEC_HAVE_DWT 1
#endif
#if QEC_USE_ZEPHYR && __has_include(<zephyr/kernel.h>)
  #include <zephyr/kernel.h>
  #define QEC_HAVE_ZEPHYR 1
#endif

int timerMode = 0;            // 0 = micros, 1 = zephyr hw cycles, 2 = DWT cycle counter
uint32_t timerHz = 1000000;   // ticks per second of the active timer
uint32_t cpuHz = 160000000;

static inline uint32_t ticks() {
#ifdef QEC_HAVE_DWT
  if (timerMode == 2) return DWT->CYCCNT;
#endif
#ifdef QEC_HAVE_ZEPHYR
  if (timerMode == 1) return k_cycle_get_32();
#endif
  return micros();
}

uint32_t ticksFn() { return ticks(); }

void setupTimer() {
#ifdef QEC_HAVE_DWT
  #if defined(DCB)
    DCB->DEMCR |= DCB_DEMCR_TRCENA_Msk;
  #else
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
  #endif
  DWT->CYCCNT = 0;
  DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
  uint32_t a = DWT->CYCCNT; delayMicroseconds(50); uint32_t b = DWT->CYCCNT;
  if (b - a > 1000) {
    timerMode = 2;
    cpuHz = SystemCoreClock ? SystemCoreClock : 160000000;
    timerHz = cpuHz;
    return;
  }
#endif
#ifdef QEC_HAVE_ZEPHYR
  uint32_t hz = sys_clock_hw_cycles_per_sec();
  if (hz >= 1000000) { timerMode = 1; timerHz = hz; return; }
#endif
  timerMode = 0; timerHz = 1000000;
}

// ---- statistics per decoder --------------------------------------------------
// 0 = majority, 1 = greedy, 2 = union-find (naive), 3 = union-find (fast), 4 = union-find (fast, weighted),
// 5 = AI (neural network; majority vote if no model for this distance is loaded)
const int NDEC = 6;
uint64_t sumTicks[NDEC];
uint32_t maxTicks[NDEC];
uint32_t nShots = 0;
bool configured = false;
int truthBit = 0;

// ---- Bridge functions ----------------------------------------------------------
int qec_config(int d, int r, int truth) {
  configured = qec::configure(d, r);
  truthBit = truth & 1;
  for (int k = 0; k < NDEC; k++) { sumTicks[k] = 0; maxTicks[k] = 0; }
  nShots = 0;
  return configured ? qec::NBITS : 0;
}

// Edge capacities for the weighted decoder: 7 x 4-bit values per word, in edge order.
int qec_weights(int off, int w0, int w1, int w2, int w3) {
  int32_t w[4] = {w0, w1, w2, w3};
  qec::loadWeights(off, w, 4);
  return qec::E;
}

int qec_load(int off, int w0, int w1, int w2, int w3) {
  int32_t w[4] = {w0, w1, w2, w3};
  qec::loadWords(off, w, 4);
  return 0;
}

// Returns: bits 0..5 = failure of each decoder, bits 8.. = number of defects
int qec_decode() {
  if (!configured) return -1;
  uint8_t out[NDEC];
  uint32_t t[NDEC + 1];
  noInterrupts();                      // clean cycle counts, decoding takes only microseconds
  t[0] = ticks();
  int defects = qec::computeDetectors();
  out[0] = qec::decodeMajority();
  t[1] = ticks();
  out[1] = qec::decodeGreedy();
  t[2] = ticks();
  out[2] = qec::decodeUnionFind();
  t[3] = ticks();
  out[3] = qec::decodeUnionFindFast(qec::capUniform);
  t[4] = ticks();
  out[4] = qec::decodeUnionFindFast(qec::capWeighted);
  t[5] = ticks();
  out[5] = ai::decode();
  t[6] = ticks();
  interrupts();
  // detector computation is counted in the majority time (it is shared by all)
  int mask = 0;
  for (int k = 0; k < NDEC; k++) {
    uint32_t dt = t[k + 1] - t[k];
    sumTicks[k] += dt;
    if (dt > maxTicks[k]) maxTicks[k] = dt;
    if (out[k] != truthBit) mask |= (1 << k);
  }
  nShots++;
  return mask | (defects << 8);
}

// ---- AI decoder model (trained in python/qec_ai.py) ----
int qec_ai_begin(int d, int r, int nh, int b2Hi, int b2Lo) { return ai::begin(d, r, nh, b2Hi, b2Lo); }

// 8 words x two 15-bit weights, at word offset off * 8
int qec_ai_put(int off, int w0, int w1, int w2, int w3, int w4, int w5, int w6, int w7) {
  int32_t w[8] = {w0, w1, w2, w3, w4, w5, w6, w7};
  ai::put(off, w, 8);
  return 0;
}

// checksum of the stored model, -1 if no model, -2 if it does not match the configured code
int qec_ai_check() {
  if (!ai::ready) return -1;
  if (!ai::usable()) return -2;
  return ai::checksum();
}

// what: 0 = average ticks, 1 = max ticks, 2 = shots
int qec_stat(int dec, int what) {
  if (dec < 0 || dec >= NDEC) return -1;
  if (what == 0) return nShots ? (int)(sumTicks[dec] / nShots) : 0;
  if (what == 1) return (int)maxTicks[dec];
  return (int)nShots;
}

int qec_timer(int what) {               // 0 = mode, 1 = timer Hz, 2 = CPU Hz
  if (what == 0) return timerMode;
  if (what == 1) return (int)timerHz;
  return (int)cpuHz;
}

// ---- LED matrix + buzzer ------------------------------------------------------
Arduino_LED_Matrix matrix;
ModulinoBuzzer buzzer;
ModulinoKnob knob;
uint8_t frame[104];
volatile int ledMode = 0;              // 0 idle, 1 progress, 2 bars
volatile int progressPct = 0;
volatile int bars[13];
volatile bool ledDirty = true;
volatile int beepFreq = 0, beepMs = 0;

void px(int r, int c, uint8_t v) { if (r >= 0 && r < 8 && c >= 0 && c < 13) frame[r * 13 + c] = v; }

int qec_led_progress(int pct) { progressPct = pct; ledMode = 1; ledDirty = true; return 0; }
int qec_led_bar(int col, int h) { if (col >= 0 && col < 13) bars[col] = h; return 0; }
int qec_led_show(int clear) {
  if (clear) for (int c = 0; c < 13; c++) bars[c] = 0;
  ledMode = 2; ledDirty = true; return 0;
}
int qec_beep(int f, int ms) { beepFreq = f; beepMs = ms; return 0; }

void drawProgress() {
  memset(frame, 0, sizeof(frame));
  int cols = progressPct * 13 / 100;
  for (int c = 0; c < 13; c++) px(7, c, c < cols ? 7 : 1);
  // little "syndrome rain" above the bar
  for (int i = 0; i < 6; i++) px(random(0, 6), random(0, 13), random(1, 5));
  matrix.draw(frame);
}

void drawBars() {
  memset(frame, 0, sizeof(frame));
  for (int c = 0; c < 13; c++)
    for (int i = 0; i < bars[c] && i < 8; i++) px(7 - i, c, (c % 2 == 0) ? 7 : 3);
  matrix.draw(frame);
}


// ---- Stage 2: bulk buffer + real-time replay ---------------------------------
volatile int rtState = 0;            // 0 idle, 1 pending, 2 running, 3 done
volatile int rtDec = 3, rtN = 0;
volatile uint32_t rtTauTicks = 160;
volatile bool liveOn = false;
volatile int liveDec = 3;
volatile uint32_t liveTauNs = 2000;
int16_t knobBase = 0;
uint32_t knobTauBase = 2000;
bool knobControl = false;
uint8_t liveHist[13];

static uint32_t nsToTicks(uint32_t ns) {
  uint64_t t = (uint64_t)ns * rt::ticksPerUs / 1000;
  return t < 1 ? 1 : (uint32_t)t;
}

int qec_buf_begin(int d, int r, int n) {
  liveOn = false;
  rtState = 0;
  configured = false;
  int got = rt::begin(d, r, n);
  return got > 0 ? got * 65536 + rt::stride : 0;   // shots << 16 | stride
}

int qec_buf_put(int off, int v0, int v1, int v2, int v3, int v4, int v5, int v6, int v7) {
  int32_t v[8] = {v0, v1, v2, v3, v4, v5, v6, v7};
  rt::put(off, v, 8);
  return 0;
}

int qec_rt_start(int dec, int tauNs, int n) {
  if (rtState == 1 || rtState == 2 || rt::nShots == 0) return 0;
  liveOn = false;
  rtDec = dec; rtN = n; rtTauTicks = nsToTicks((uint32_t)tauNs);
  rtState = 1;
  return 1;
}

int qec_rt_status() { return rtState; }

// 0 shots, 1 fails, 2 maxBacklog, 3 p50, 4 p90, 5 p99, 6 max latency, 7 mean latency,
// 8 mean decode time, 9 max decode time, 10 first-decile latency, 11 last-decile latency (all ns),
// 12 duration (us), 16..79 backlog series
int qec_rt_get(int i) {
  const rt::Stats& s = rt::st;
  uint32_t n = s.shots ? s.shots : 1;
  switch (i) {
    case 0: return s.shots;
    case 1: return s.fails;
    case 2: return s.maxBacklog;
    case 3: return rt::toNs(s.p50);
    case 4: return rt::toNs(s.p90);
    case 5: return rt::toNs(s.p99);
    case 6: return rt::toNs(s.maxLat);
    case 7: return rt::toNs(s.sumLat / n);
    case 8: return rt::toNs(s.sumService / n);
    case 9: return rt::toNs(s.maxService);
    case 10: return rt::toNs(s.firstDecileLat);
    case 11: return rt::toNs(s.lastDecileLat);
    case 12: return (int)(s.duration / (rt::ticksPerUs ? rt::ticksPerUs : 1));
  }
  if (i >= 16 && i < 80) return s.series[i - 16];
  return -1;
}

int qec_live(int on, int dec, int tauNs) {
  if (on && rt::nShots == 0) return 0;
  liveDec = dec;
  if (tauNs > 0) { liveTauNs = tauNs; knobControl = false; }
  knobBase = knob.get(); knobTauBase = liveTauNs;
  memset(liveHist, 0, sizeof(liveHist));
  liveOn = on != 0;
  if (liveOn) rtState = 0;
  return 1;
}

// 0 seq, 1 tau ns, 2 shots, 3 max backlog, 4 mean latency ns, 5 max latency ns, 6 fails, 7 knob control
int qec_live_get(int i) {
  const rt::Window& w = rt::lastWindow;
  switch (i) {
    case 0: return w.seq; case 1: return w.tauNs; case 2: return w.shots; case 3: return w.maxBacklog;
    case 4: return w.meanLatNs; case 5: return w.maxLatNs; case 6: return w.fails; case 7: return knobControl;
  }
  return -1;
}

void drawLive() {
  for (int c = 0; c < 12; c++) liveHist[c] = liveHist[c + 1];
  uint32_t b = rt::lastWindow.maxBacklog;
  uint8_t h = 0;
  while (b > 0 && h < 8) { h++; b >>= 1; }              // log2 scale: 1, 2, 4 ... 128+
  liveHist[12] = h;
  memset(frame, 0, sizeof(frame));
  for (int c = 0; c < 13; c++)
    for (int i = 0; i < liveHist[c]; i++) px(7 - i, c, liveHist[c] > 2 ? 7 : 3);
  if (liveHist[12] == 0) px(7, 12, 2);                   // keeping up: one dim dot
  matrix.draw(frame);
}

void serviceStage2() {
  if (rtState == 1) {
    rtState = 2;
    rt::run(rtDec, rtTauTicks, rtN);
    rtState = 3;
  }
  if (liveOn) {
    int16_t k = knob.get();
    if (k != knobBase) {                                  // knob turned: it takes over tau
      knobControl = true;
      float f = powf(2.0f, (k - knobBase) / 4.0f);         // 4 clicks = factor 2
      uint32_t t = (uint32_t)(knobTauBase * f);
      liveTauNs = t < 20 ? 20 : (t > 500000 ? 500000 : t);
    }
    rt::liveWindow(liveDec, nsToTicks(liveTauNs), rt::ticksPerUs * 100000);   // 100 ms window
    drawLive();
    if (rt::lastWindow.maxBacklog > 64) buzzer.tone(220, 15);                 // falling behind
    delay(2);                                                                 // let Bridge run
  }
}

void setup() {
  Serial.begin(115200);
  matrix.begin();
  Modulino.begin();
  buzzer.begin();
  setupTimer();
  knob.begin();
  rt::now = ticksFn;
  rt::ticksPerUs = timerHz / 1000000 ? timerHz / 1000000 : 1;
  randomSeed(analogRead(A5));

  Bridge.begin();
  Bridge.provide("qec_config", qec_config);
  Bridge.provide("qec_load", qec_load);
  Bridge.provide("qec_weights", qec_weights);
  Bridge.provide("qec_decode", qec_decode);
  Bridge.provide("qec_stat", qec_stat);
  Bridge.provide("qec_timer", qec_timer);
  Bridge.provide("qec_ai_begin", qec_ai_begin);
  Bridge.provide("qec_ai_put", qec_ai_put);
  Bridge.provide("qec_ai_check", qec_ai_check);
  Bridge.provide("qec_led_progress", qec_led_progress);
  Bridge.provide("qec_led_bar", qec_led_bar);
  Bridge.provide("qec_led_show", qec_led_show);
  Bridge.provide("qec_beep", qec_beep);
  Bridge.provide("qec_buf_begin", qec_buf_begin);
  Bridge.provide("qec_buf_put", qec_buf_put);
  Bridge.provide("qec_rt_start", qec_rt_start);
  Bridge.provide("qec_rt_status", qec_rt_status);
  Bridge.provide("qec_rt_get", qec_rt_get);
  Bridge.provide("qec_live", qec_live);
  Bridge.provide("qec_live_get", qec_live_get);

  Serial.print("QEC lab ready, timer mode "); Serial.print(timerMode);
  Serial.print(", "); Serial.print(timerHz); Serial.println(" Hz");
}

void loop() {
  serviceStage2();
  if (liveOn) return;
  if (beepMs > 0) { buzzer.tone(beepFreq, beepMs); beepMs = 0; }
  if (ledMode == 1) { drawProgress(); delay(80); }
  else if (ledDirty) { ledDirty = false; if (ledMode == 2) drawBars(); }
  delay(10);
}
