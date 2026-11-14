// qec_decoders.h - repetition-code decoders for a microcontroller.
// Plain C++ (no Arduino dependencies), static memory only, so the same file
// is compiled on the STM32 and in the laptop test harness.
//
// Layout of one shot (bits[]):
//   syndrome rounds  s[t][i]  t = 0..R-1, i = 0..W-1   (W = D-1)  -> bits[t*W + i]
//   final data bits  x[k]     k = 0..D-1                          -> bits[R*W + k]
//
// Detector graph (space x time):
//   node(t,i) = t*W + i for t = 0..R (layer R uses the final data parities)
//   one boundary node B. Space edge between detector i-1 and i  = X error on data qubit i.
//   Edge (t,0)-B is data qubit 0 ("left"), edge (t,W-1)-B is data qubit D-1 ("right").
//   Time edge (t,i)-(t+1,i) = measurement error on ancilla i.
// Logical observable = final value of data qubit 0, so a correction flips it
// once for every "left" boundary edge it contains.
#pragma once
#include <stdint.h>
#include <string.h>

namespace qec {

static const int MAX_D = 25;
static const int MAX_R = 10;
static const int MAX_W = MAX_D - 1;
static const int MAX_T = MAX_R + 1;
static const int MAX_N = MAX_T * MAX_W + 1;
static const int MAX_E = MAX_T * (MAX_W - 1) + 2 * MAX_T + (MAX_T - 1) * MAX_W;
static const int MAX_BITS = MAX_R * MAX_W + MAX_D;

// ---------------- graph ----------------
static int D = 3, R = 1, W = 2, T = 2, N = 5, E = 0, B = 4, NBITS = 5;
static int16_t eu[MAX_E], ev[MAX_E];
static uint8_t eLeft[MAX_E];
static int16_t adjStart[MAX_N + 1], adjEdge[2 * MAX_E];

static uint8_t bits[MAX_BITS];
static uint8_t det[MAX_N];
static int lastDefects;
static void setUniformWeights();

static inline int node(int t, int i) { return t * W + i; }

static void addEdge(int u, int v, uint8_t left) { eu[E] = u; ev[E] = v; eLeft[E] = left; E++; }

// Returns false if d / r are out of range.
static bool configure(int d, int r) {
  if (d < 3 || d > MAX_D || r < 1 || r > MAX_R) return false;
  D = d; R = r; W = d - 1; T = r + 1; B = T * W; N = B + 1; E = 0;
  NBITS = R * W + D;
  for (int t = 0; t < T; t++)
    for (int i = 0; i < W - 1; i++) addEdge(node(t, i), node(t, i + 1), 0);
  for (int t = 0; t < T; t++) {
    addEdge(node(t, 0), B, 1);
    addEdge(node(t, W - 1), B, 0);
  }
  for (int t = 0; t < T - 1; t++)
    for (int i = 0; i < W; i++) addEdge(node(t, i), node(t + 1, i), 0);
  // CSR adjacency
  int16_t deg[MAX_N];
  memset(deg, 0, sizeof(deg));
  for (int e = 0; e < E; e++) { deg[eu[e]]++; deg[ev[e]]++; }
  adjStart[0] = 0;
  for (int v = 0; v < N; v++) adjStart[v + 1] = adjStart[v] + deg[v];
  int16_t fill[MAX_N];
  for (int v = 0; v < N; v++) fill[v] = adjStart[v];
  for (int e = 0; e < E; e++) { adjEdge[fill[eu[e]]++] = e; adjEdge[fill[ev[e]]++] = e; }
  memset(bits, 0, sizeof(bits));
  setUniformWeights();
  return true;
}

static inline uint8_t synd(int t, int i) { return bits[t * W + i]; }
static inline uint8_t dataBit(int k) { return bits[R * W + k]; }

// Detection events from raw measurements. Returns number of defects.
static int computeDetectors() {
  int count = 0;
  for (int t = 0; t < T; t++) {
    for (int i = 0; i < W; i++) {
      uint8_t cur = (t < R) ? synd(t, i) : (uint8_t)(dataBit(i) ^ dataBit(i + 1));
      uint8_t prev = (t == 0) ? 0 : synd(t - 1, i);
      det[node(t, i)] = cur ^ prev;
      count += det[node(t, i)];
    }
  }
  det[B] = 0;
  lastDefects = count;
  return count;
}

// ---------------- decoder 1: majority vote of the final data ----------------
static uint8_t decodeMajority() {
  int ones = 0;
  for (int k = 0; k < D; k++) ones += dataBit(k);
  return ones * 2 > D ? 1 : 0;
}

// ---------------- decoder 2: greedy nearest-neighbour matching ----------------
static int16_t gT[MAX_N], gI[MAX_N];
static uint8_t gAlive[MAX_N];

static uint8_t decodeGreedy() {
  int n = 0;
  for (int t = 0; t < T; t++)
    for (int i = 0; i < W; i++)
      if (det[node(t, i)]) { gT[n] = t; gI[n] = i; gAlive[n] = 1; n++; }
  uint8_t flip = 0;
  int remaining = n;
  while (remaining > 0) {
    // costs are doubled; boundary matches get +1 so a pair wins ties against a boundary
    int best = 0x7fff, ba = -1, bb = -1;  // bb: -1 left boundary, -2 right boundary, else partner
    for (int a = 0; a < n; a++) {
      if (!gAlive[a]) continue;
      int dl = 2 * (gI[a] + 1) + 1, dr = 2 * (W - gI[a]) + 1;
      if (dl < best) { best = dl; ba = a; bb = -1; }
      if (dr < best) { best = dr; ba = a; bb = -2; }
      for (int b = a + 1; b < n; b++) {
        if (!gAlive[b]) continue;
        int dd = 2 * ((gI[a] > gI[b] ? gI[a] - gI[b] : gI[b] - gI[a]) + (gT[a] > gT[b] ? gT[a] - gT[b] : gT[b] - gT[a]));
        if (dd < best) { best = dd; ba = a; bb = b; }
      }
    }
    gAlive[ba] = 0; remaining--;
    if (bb >= 0) { gAlive[bb] = 0; remaining--; }
    else if (bb == -1) flip ^= 1;
  }
  return (uint8_t)(dataBit(0) ^ flip);
}

// ---------------- decoder 3: union-find (Delfosse-Nickerson) + peeling ----------------
static int16_t ufParent[MAX_N], ufSize[MAX_N];
static uint8_t ufPar[MAX_N], ufBnd[MAX_N], growth[MAX_E];
static int16_t fullList[MAX_E];
static int16_t pEdge[MAX_N], pNode[MAX_N], order[MAX_N], queueBuf[MAX_N];
static uint8_t visited[MAX_N], dloc[MAX_N];

static int ufFind(int v) {
  while (ufParent[v] != v) { ufParent[v] = ufParent[ufParent[v]]; v = ufParent[v]; }
  return v;
}
static void ufUnion(int a, int b) {
  a = ufFind(a); b = ufFind(b);
  if (a == b) return;
  if (ufSize[a] < ufSize[b]) { int t = a; a = b; b = t; }
  ufParent[b] = a; ufSize[a] += ufSize[b];
  ufPar[a] ^= ufPar[b]; ufBnd[a] |= ufBnd[b];
}
static inline bool ufActive(int root) { return ufPar[root] && !ufBnd[root]; }

static uint8_t decodeUnionFind() {
  for (int v = 0; v < N; v++) { ufParent[v] = v; ufSize[v] = 1; ufPar[v] = det[v]; ufBnd[v] = (v == B); }
  memset(growth, 0, E);
  // --- growth ---
  for (int iter = 0; iter < 4 * N; iter++) {
    bool any = false;
    for (int v = 0; v < N; v++) if (ufParent[v] == v && ufActive(v)) { any = true; break; }
    if (!any) break;
    int nf = 0;
    for (int e = 0; e < E; e++) {
      if (growth[e] >= 2) continue;
      int inc = (ufActive(ufFind(eu[e])) ? 1 : 0) + (ufActive(ufFind(ev[e])) ? 1 : 0);
      if (!inc) continue;
      int g = growth[e] + inc;
      if (g >= 2) { growth[e] = 2; fullList[nf++] = e; } else growth[e] = (uint8_t)g;
    }
    for (int k = 0; k < nf; k++) ufUnion(eu[fullList[k]], ev[fullList[k]]);
  }
  // --- peeling on a spanning forest of fully grown edges (boundary tree first) ---
  memset(visited, 0, N);
  memcpy(dloc, det, N);
  int nOrder = 0;
  for (int pass = 0; pass <= N; pass++) {
    int root = (pass == 0) ? B : pass - 1;
    if (visited[root]) continue;
    visited[root] = 1; pEdge[root] = -1; pNode[root] = -1;
    int qh = 0, qt = 0;
    queueBuf[qt++] = root;
    while (qh < qt) {
      int v = queueBuf[qh++];
      order[nOrder++] = v;
      for (int k = adjStart[v]; k < adjStart[v + 1]; k++) {
        int e = adjEdge[k];
        if (growth[e] != 2) continue;
        int w = (eu[e] == v) ? ev[e] : eu[e];
        if (visited[w]) continue;
        visited[w] = 1; pEdge[w] = e; pNode[w] = v;
        queueBuf[qt++] = w;
      }
    }
  }
  uint8_t flip = 0;
  for (int k = nOrder - 1; k >= 0; k--) {
    int v = order[k];
    if (pEdge[v] < 0 || !dloc[v]) continue;
    if (eLeft[pEdge[v]]) flip ^= 1;
    dloc[v] ^= 1;
    dloc[pNode[v]] ^= 1;
  }
  return (uint8_t)(dataBit(0) ^ flip);
}

// ---------------- decoder 4/5: fast union-find with integer edge weights ----------------
// Same growth rule as decodeUnionFind (each active endpoint adds 1 per step, edge is
// "fully grown" when growth reaches its capacity), but:
//   * returns immediately when there are no defects,
//   * only visits edges next to members of active clusters (member linked lists),
//   * peels only the trees that contain defects.
// cap[e] = 2 for every edge reproduces the unweighted decoder exactly.
static uint8_t capUniform[MAX_E], capWeighted[MAX_E];
static int16_t memHead[MAX_N], memNext[MAX_N], memTail[MAX_N];
static int16_t actList[MAX_N], actNext[MAX_N];
static uint8_t actMark[MAX_N];

static void setUniformWeights() {
  memset(capUniform, 2, MAX_E);
  memset(capWeighted, 2, MAX_E);
}

static void ufUnionFast(int a, int b) {
  a = ufFind(a); b = ufFind(b);
  if (a == b) return;
  if (ufSize[a] < ufSize[b]) { int t = a; a = b; b = t; }
  ufParent[b] = a; ufSize[a] += ufSize[b];
  ufPar[a] ^= ufPar[b]; ufBnd[a] |= ufBnd[b];
  memNext[memTail[a]] = memHead[b];
  memTail[a] = memTail[b];
}

// Lazy per-shot reset: a node/edge is (re)initialised the first time it is touched in a shot.
static uint16_t nodeEpoch[MAX_N], edgeEpoch[MAX_E];
static uint16_t epoch = 0;
static int16_t defList[MAX_N];

static inline void touchNode(int v) {
  if (nodeEpoch[v] == epoch) return;
  nodeEpoch[v] = epoch;
  ufParent[v] = v; ufSize[v] = 1; ufPar[v] = det[v]; ufBnd[v] = (v == B);
  memHead[v] = v; memTail[v] = v; memNext[v] = -1;
  visited[v] = 0; dloc[v] = det[v];
}
static inline uint8_t getGrowth(int e) { return edgeEpoch[e] == epoch ? growth[e] : 0; }

static uint8_t decodeUnionFindFast(const uint8_t* cap) {
  if (lastDefects == 0) return dataBit(0);
  if (++epoch == 0) { memset(nodeEpoch, 0, sizeof(nodeEpoch)); memset(edgeEpoch, 0, sizeof(edgeEpoch)); epoch = 1; }
  int nAct = 0, nDef = 0;
  for (int v = 0; v < B; v++)
    if (det[v]) { touchNode(v); actList[nAct++] = v; defList[nDef++] = v; }
  for (int iter = 0; iter < 16 * N && nAct > 0; iter++) {
    int nf = 0;
    for (int a = 0; a < nAct; a++) {
      for (int v = memHead[actList[a]]; v >= 0; v = memNext[v]) {
        for (int k = adjStart[v]; k < adjStart[v + 1]; k++) {
          int e = adjEdge[k];
          uint8_t g = getGrowth(e);
          if (g >= cap[e]) continue;
          edgeEpoch[e] = epoch;
          growth[e] = ++g;
          if (g >= cap[e]) fullList[nf++] = e;
        }
      }
    }
    for (int k = 0; k < nf; k++) {
      int e = fullList[k];
      touchNode(eu[e]); touchNode(ev[e]);
      ufUnionFast(eu[e], ev[e]);
    }
    int nNew = 0;
    for (int a = 0; a < nAct; a++) {
      int r = ufFind(actList[a]);
      if (ufActive(r) && !actMark[r]) { actMark[r] = 1; actNext[nNew++] = r; }
    }
    for (int a = 0; a < nNew; a++) { actMark[actNext[a]] = 0; actList[a] = actNext[a]; }
    nAct = nNew;
  }
  // peeling: tree rooted at the boundary first (if reached), then trees rooted at defects
  int nOrder = 0;
  for (int s = -1; s < nDef; s++) {
    int root = (s < 0) ? B : defList[s];
    if (nodeEpoch[root] != epoch || visited[root]) continue;
    visited[root] = 1; pEdge[root] = -1; pNode[root] = -1;
    int qh = 0, qt = 0;
    queueBuf[qt++] = root;
    while (qh < qt) {
      int v = queueBuf[qh++];
      order[nOrder++] = v;
      for (int k = adjStart[v]; k < adjStart[v + 1]; k++) {
        int e = adjEdge[k];
        if (getGrowth(e) < cap[e]) continue;
        int w = (eu[e] == v) ? ev[e] : eu[e];
        if (visited[w]) continue;          // both ends of a full edge are touched
        visited[w] = 1; pEdge[w] = e; pNode[w] = v;
        queueBuf[qt++] = w;
      }
    }
  }
  uint8_t flip = 0;
  for (int k = nOrder - 1; k >= 0; k--) {
    int v = order[k];
    if (pEdge[v] < 0 || !dloc[v]) continue;
    if (eLeft[pEdge[v]]) flip ^= 1;
    dloc[v] ^= 1;
    dloc[pNode[v]] ^= 1;
  }
  return (uint8_t)(dataBit(0) ^ flip);
}

// Weighted capacities: each 31-bit word carries 7 x 4-bit capacities (1..15).
static void loadWeights(int off, const int32_t* w, int count) {
  for (int k = 0; k < count; k++) {
    for (int j = 0; j < 7; j++) {
      int idx = (off + k) * 7 + j;
      if (idx < E) {
        uint8_t c = (uint8_t)((w[k] >> (4 * j)) & 15);
        capWeighted[idx] = c ? c : 1;
      }
    }
  }
}

// Unpack 31-bit words (LSB first) into bits[] starting at word offset `off`.
static void loadWords(int off, const int32_t* w, int count) {
  for (int k = 0; k < count; k++) {
    for (int b = 0; b < 31; b++) {
      int idx = (off + k) * 31 + b;
      if (idx < NBITS) bits[idx] = (uint8_t)((w[k] >> b) & 1);
    }
  }
}

}  // namespace qec
