// qec_ai.h - AI decoder: small neural network (MLP) trained on the Linux side (python/qec_ai.py).
// Integer-only inference, static memory, bit-exact with the Python model.
//
// Inputs (0/1): detection events det[0..B-1], then final data bits  -> nin = (R+1)*W + D
//   h[j] = relu(b1[j] + sum over inputs that are 1 of W1[i][j])   (adds only, no multiplies)
//   z    = b2 + sum_j h[j] * W2[j]                                 flip = z > 0
// Decoded logical = data qubit 0 ^ flip.
#pragma once
#include <stdint.h>
#include "qec_decoders.h"

namespace ai {

static const int MAX_IN = 128, MAX_H = 32;      // 8 KB of first-layer weights
static int16_t W1[MAX_IN * MAX_H];             // input-major: row i = weights of input i
static int16_t b1[MAX_H], W2[MAX_H];
static int64_t b2 = 0;
static int nin = 0, nh = 0, mD = 0, mR = 0;     // model shape and the code it was trained for
static bool ready = false;
static int32_t h[MAX_H];

// Header of a new model for a (d, r) code. b2 = (b2Hi - 2^20) * 2^30 + b2Lo. Returns 1 if it fits.
static int begin(int d, int r, int nHid, int32_t b2Hi, int32_t b2Lo) {
  ready = false;
  int nIn = (r + 1) * (d - 1) + d;
  if (d < 3 || r < 1 || nIn > MAX_IN || nHid < 1 || nHid > MAX_H) return 0;
  nin = nIn; nh = nHid; mD = d; mR = r;
  b2 = (int64_t)(b2Hi - (1 << 20)) * (1LL << 30) + b2Lo;
  memset(W1, 0, sizeof(W1)); memset(b1, 0, sizeof(b1)); memset(W2, 0, sizeof(W2));
  return 1;
}

static inline int count() { return nin * nh + 2 * nh; }

static inline void setVal(int idx, int v) {
  int16_t q = (int16_t)(v - 16384);
  int a = nin * nh;
  if (idx < a) W1[idx] = q;
  else if (idx < a + nh) b1[idx - a] = q;
  else if (idx < a + 2 * nh) W2[idx - a - nh] = q;
}
static inline int getVal(int idx) {
  int a = nin * nh;
  if (idx < a) return W1[idx] + 16384;
  if (idx < a + nh) return b1[idx - a] + 16384;
  if (idx < a + 2 * nh) return W2[idx - a - nh] + 16384;
  return 0;
}

// `count` 30-bit words (two 15-bit values each) at word offset off * count.
static void put(int off, const int32_t* w, int n) {
  for (int k = 0; k < n; k++) {
    int idx = 2 * ((off * n) + k);
    setVal(idx, w[k] & 0x7FFF);
    setVal(idx + 1, (w[k] >> 15) & 0x7FFF);
  }
  ready = true;
}

// Sum of the packed words mod 2^30 (Python: qec_ai.checksum).
static int32_t checksum() {
  uint32_t s = 0;
  int n = count();
  for (int i = 0; i < n; i += 2) s += (uint32_t)getVal(i) | ((uint32_t)getVal(i + 1) << 15);
  return (int32_t)(s & 0x3FFFFFFF);
}

// Model matches the configured code (qec::configure)?
static inline bool usable() { return ready && mD == qec::D && mR == qec::R; }

static inline void addRow(int i) {
  const int16_t* w = W1 + i * nh;
  for (int j = 0; j < nh; j++) h[j] += w[j];
}

// Needs qec::computeDetectors() first. Falls back to majority vote if no model fits.
static uint8_t decode() {
  if (!usable()) return qec::decodeMajority();
  for (int j = 0; j < nh; j++) h[j] = b1[j];
  for (int i = 0; i < qec::B; i++) if (qec::det[i]) addRow(i);
  for (int k = 0; k < qec::D; k++) if (qec::dataBit(k)) addRow(qec::B + k);
  int64_t z = b2;
  for (int j = 0; j < nh; j++) if (h[j] > 0) z += (int64_t)h[j] * W2[j];
  return (uint8_t)(qec::dataBit(0) ^ (z > 0 ? 1 : 0));
}

}  // namespace ai
