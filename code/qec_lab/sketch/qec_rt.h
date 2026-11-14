// qec_rt.h - real-time replay of stored syndromes (Stage 2).
//
// Shots are bulk-loaded into RAM once. A replay then pretends that a new syndrome
// round arrives every `tau` clock ticks: shot k is complete at time (k+1) * R * tau.
// The decoder works through the shots in order (one server, first-in first-out),
// never before a shot has fully arrived, and we record for every shot
//   latency = time decoding finished - time the shot was complete
//   backlog = shots complete but not yet decoded, when its decoding starts.
// If the mean decode time exceeds R * tau, the backlog grows without limit.
//
// Plain C++ with a pluggable clock so the same code runs on the STM32 and on a laptop.
#pragma once
#include <stdlib.h>
#include "qec_decoders.h"
#include "qec_ai.h"

namespace rt {

static const int BUF_BYTES = 80 * 1024;
static const int MAX_SHOTS = 6000;
static uint8_t buf[BUF_BYTES];
static uint32_t lat[MAX_SHOTS];
static int stride = 0, nShots = 0;
static uint32_t (*now)() = nullptr;      // clock source (ticks)
static uint32_t ticksPerUs = 160;

// Prepare the buffer for `n` shots of a (d, r) repetition code. Returns how many fit.
static int begin(int d, int r, int n) {
  if (!qec::configure(d, r)) return 0;
  stride = (qec::NBITS + 1 + 7) / 8;     // shot bits + 1 truth bit, little-endian bit order
  int cap = BUF_BYTES / stride;
  if (cap > MAX_SHOTS) cap = MAX_SHOTS;
  nShots = n < cap ? n : cap;
  memset(buf, 0, (size_t)nShots * stride);
  return nShots;
}

// 8 values of 24 bits each = 24 bytes, written at byte offset off * 24.
static void put(int off, const int32_t* v, int count) {
  int limit = nShots * stride;
  for (int k = 0; k < count; k++)
    for (int j = 0; j < 3; j++) {
      int idx = (off * count + k) * 3 + j;
      if (idx < limit) buf[idx] = (uint8_t)((v[k] >> (8 * j)) & 0xFF);
    }
}

static inline uint8_t loadShot(int k) {
  const uint8_t* p = buf + (size_t)k * stride;
  for (int i = 0; i < qec::NBITS; i++) qec::bits[i] = (p[i >> 3] >> (i & 7)) & 1;
  return (p[qec::NBITS >> 3] >> (qec::NBITS & 7)) & 1;   // truth bit
}

static inline uint8_t decodeWith(int dec) {
  qec::computeDetectors();
  switch (dec) {
    case 0: return qec::decodeMajority();
    case 1: return qec::decodeGreedy();
    case 2: return qec::decodeUnionFind();
    case 3: return qec::decodeUnionFindFast(qec::capUniform);
    case 5: return ai::decode();
    default: return qec::decodeUnionFindFast(qec::capWeighted);
  }
}

struct Stats {
  uint32_t shots, fails, maxBacklog;
  uint32_t p50, p90, p99, maxLat;        // latency, ticks
  uint64_t sumLat, sumService;
  uint32_t maxService;
  uint32_t firstDecileLat, lastDecileLat; // mean latency of first / last 10% of shots
  uint32_t duration;
  uint16_t series[64];                    // max backlog in 64 time buckets
};
static Stats st;

static int cmpU32(const void* a, const void* b) {
  uint32_t x = *(const uint32_t*)a, y = *(const uint32_t*)b;
  return x < y ? -1 : (x > y ? 1 : 0);
}

// Replay `n` shots (cycling through the buffer) with round time tauTicks.
static void run(int dec, uint32_t tauTicks, int n) {
  if (n > MAX_SHOTS) n = MAX_SHOTS;
  memset(&st, 0, sizeof(st));
  const uint32_t period = tauTicks * (uint32_t)qec::R;
  const uint32_t t0 = now();
  for (int k = 0; k < n; k++) {
    const uint32_t arrival = (uint32_t)(k + 1) * period;
    uint32_t t;
    while ((t = now() - t0) < arrival) { }                 // idle until shot k is complete
    uint32_t backlog = t / period - (uint32_t)k;           // complete but not yet decoded
    uint8_t truth = loadShot(k % nShots);
    uint32_t a = now();
    uint8_t out = decodeWith(dec);
    uint32_t b = now();
    uint32_t service = b - a;
    uint32_t latency = (b - t0) - arrival;
    lat[k] = latency;
    st.sumLat += latency;
    st.sumService += service;
    if (service > st.maxService) st.maxService = service;
    if (backlog > st.maxBacklog) st.maxBacklog = backlog;
    int bucket = (int)((int64_t)k * 64 / n);
    if (backlog > st.series[bucket]) st.series[bucket] = backlog > 65535 ? 65535 : (uint16_t)backlog;
    st.fails += (out != truth);
  }
  st.duration = now() - t0;
  st.shots = n;
  int dec10 = n / 10 > 0 ? n / 10 : 1;
  uint64_t f = 0, l = 0;
  for (int k = 0; k < dec10; k++) { f += lat[k]; l += lat[n - 1 - k]; }
  st.firstDecileLat = (uint32_t)(f / dec10);
  st.lastDecileLat = (uint32_t)(l / dec10);
  qsort(lat, n, sizeof(uint32_t), cmpU32);
  st.p50 = lat[n / 2];
  st.p90 = lat[(n * 9) / 10];
  st.p99 = lat[(n * 99) / 100 < n ? (n * 99) / 100 : n - 1];
  st.maxLat = lat[n - 1];
}

// ---- live mode: short independent windows, so the knob can change tau between them ----
struct Window {
  uint32_t seq, tauNs, shots, maxBacklog, meanLatNs, maxLatNs, fails;
};
static Window lastWindow;
static int liveCursor = 0;

static void liveWindow(int dec, uint32_t tauTicks, uint32_t windowTicks) {
  const uint32_t period = tauTicks * (uint32_t)qec::R;
  const uint32_t t0 = now();
  uint32_t k = 0, maxB = 0, maxL = 0, fails = 0;
  uint64_t sumL = 0;
  for (;;) {
    const uint32_t arrival = (k + 1) * period;
    if (arrival > windowTicks) break;
    uint32_t t;
    while ((t = now() - t0) < arrival) { }
    uint32_t backlog = t / period - k;
    uint8_t truth = loadShot(liveCursor);
    liveCursor = (liveCursor + 1) % nShots;
    uint8_t out = decodeWith(dec);
    uint32_t latency = (now() - t0) - arrival;
    sumL += latency;
    if (latency > maxL) maxL = latency;
    if (backlog > maxB) maxB = backlog;
    fails += (out != truth);
    k++;
    if (now() - t0 > 4 * windowTicks) break;               // hopelessly behind: stop the window
  }
  // shots that arrived during the window but were never decoded also count as backlog
  uint32_t arrivedTotal = windowTicks / period;
  if (arrivedTotal > k && arrivedTotal - k > maxB) maxB = arrivedTotal - k;
  lastWindow.seq++;
  lastWindow.tauNs = (uint32_t)((uint64_t)tauTicks * 1000 / ticksPerUs);
  lastWindow.shots = k;
  lastWindow.maxBacklog = maxB;
  lastWindow.meanLatNs = k ? (uint32_t)((sumL / k) * 1000 / ticksPerUs) : 0;
  lastWindow.maxLatNs = (uint32_t)((uint64_t)maxL * 1000 / ticksPerUs);
  lastWindow.fails = fails;
}

static inline uint32_t toNs(uint64_t ticks) { return (uint32_t)(ticks * 1000 / ticksPerUs); }

}  // namespace rt
