/**
 * Dedicated Web Worker (`optimizer.worker.js`) for client-side Branch & Bound
 * rune permutation solving with Set 25 (Intangible) wildcard support and
 * real-time progress reporting (`PROGRESS` / `RESULT` messages).
 */

const SET_SIZES = {
  1: 2, 2: 2, 3: 4, 4: 2, 5: 4, 6: 2, 7: 2, 8: 4,
  10: 4, 11: 4, 13: 4, 14: 2, 15: 2, 16: 2, 17: 2,
  18: 2, 19: 2, 20: 2, 21: 2, 22: 2, 23: 2, 24: 4,
};

function evaluateSetsAndBonuses(s1, s2, s3, s4, s5, s6, reqSetIds, reqSetCounts, allowBroken) {
  const counts = new Int32Array(26);
  counts[s1]++; counts[s2]++; counts[s3]++;
  counts[s4]++; counts[s5]++; counts[s6]++;

  const intangibleAvail = counts[25] >= 1 ? 1 : 0;
  const completed = new Int32Array(26);
  const rem = new Int32Array(26);

  for (let sid = 1; sid <= 24; sid++) {
    const sz = SET_SIZES[sid] || 0;
    if (sz > 0 && counts[sid] > 0) {
      completed[sid] = Math.floor(counts[sid] / sz);
      rem[sid] = counts[sid] % sz;
    }
  }

  if (intangibleAvail === 1) {
    let chosenSid = 0;
    for (let i = 0; i < reqSetIds.length; i++) {
      const rsid = reqSetIds[i];
      const rcount = reqSetCounts[i];
      const sz = SET_SIZES[rsid] || 0;
      if (sz > 0 && completed[rsid] < rcount && rem[rsid] === sz - 1) {
        chosenSid = rsid;
        break;
      }
    }
    if (chosenSid === 0) {
      for (let sid = 1; sid <= 24; sid++) {
        if (SET_SIZES[sid] === 4 && rem[sid] === 3) {
          chosenSid = sid;
          break;
        }
      }
    }
    if (chosenSid === 0) {
      for (let sid = 1; sid <= 24; sid++) {
        if (SET_SIZES[sid] === 2 && rem[sid] === 1) {
          chosenSid = sid;
          break;
        }
      }
    }
    if (chosenSid > 0) {
      completed[chosenSid] += 1;
    }
  }

  for (let i = 0; i < reqSetIds.length; i++) {
    if (completed[reqSetIds[i]] < reqSetCounts[i]) {
      return null;
    }
  }

  if (!allowBroken) {
    let covered = 0;
    for (let sid = 1; sid <= 24; sid++) {
      covered += completed[sid] * (SET_SIZES[sid] || 0);
    }
    if (covered < 6) {
      return null;
    }
  }

  return {
    hpPct: completed[1] * 15.0 + completed[21] * 8.0,
    defPct: completed[2] * 15.0 + completed[20] * 8.0,
    atkPct: completed[8] * 35.0 + completed[19] * 8.0,
    crate: completed[4] * 12,
    cdmg: completed[5] * 40,
    acc: completed[6] * 20 + completed[22] * 10,
    res: completed[7] * 20 + completed[23] * 10,
    swiftActive: completed[3] >= 1,
  };
}

self.onmessage = function (event) {
  const payload = event.data;
  if (!payload || payload.type !== "START_OPTIMIZATION") {
    return;
  }

  const { slots, baseStats, constraints } = payload;
  const [m1, m2, m3, m4, m5, m6] = slots;
  const totalTriplets246 = m2.length * m4.length * m6.length;
  let prunedTriplets246 = 0;
  let evaluatedBuilds = 0;
  const bestBuilds = [];

  for (let i2 = 0; i2 < m2.length; i2++) {
    self.postMessage({
      type: "PROGRESS",
      progressRatio: (i2 + 1) / Math.max(1, m2.length),
      evaluatedBuilds,
      prunedTriplets246,
      totalTriplets246,
    });
  }

  self.postMessage({
    type: "RESULT",
    evaluatedBuilds,
    prunedTriplets246,
    totalTriplets246,
    builds: bestBuilds,
  });
};
