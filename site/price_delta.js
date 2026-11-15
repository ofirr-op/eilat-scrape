// Change of the latest price versus the lowest price ever recorded on the
// same date and the same line (regular or mhot). The current point is part
// of the history, so the difference is never negative.

function lowestPoint(series) {
  let best = null;
  for (const point of series || []) {
    if (point.price == null || !(point.price > 0)) continue;
    if (!best || point.price < best.price - 0.005) {
      best = point;
      continue;
    }
    if (Math.abs(point.price - best.price) < 0.5 && Date.parse(point.at) < Date.parse(best.at)) {
      best = point;
    }
  }
  return best;
}

function money(n) {
  return Math.round(n).toLocaleString("en-US");
}

function versusLow(series) {
  const low = lowestPoint(series);
  if (!low) return null;
  const last = series[series.length - 1];
  if (!last) return null;
  if (last.price == null || !(last.price > 0)) {
    return { kind: "unavailable", low: low, last: last, delta: null, pct: null };
  }
  const delta = last.price - low.price;
  const flat = Math.abs(delta) < 0.5;
  return {
    kind: flat ? "flat" : "up",
    low: low,
    last: last,
    delta: flat ? 0 : delta,
    pct: flat || !(low.price > 0) ? 0 : (delta / low.price) * 100,
  };
}

function formatVersusLow(series) {
  const cmp = versusLow(series);
  if (!cmp) return "אין עדיין מחיר להשוואה.";
  if (cmp.kind === "unavailable") {
    return "בסריקה האחרונה (" + cmp.last.label + ") לא זמין. המחיר הנמוך ביותר: " +
      money(cmp.low.price) + " ₪ (" + cmp.low.label + ").";
  }
  const recorded = money(cmp.low.price) + " ₪, " + cmp.low.label;
  if (cmp.kind === "flat") {
    return "המחיר הנמוך ביותר (0 ₪, 0%) — " + recorded + ".";
  }
  return "+₪" + money(cmp.delta) + " (+" + cmp.pct.toFixed(1) + "%) מהמחיר הנמוך ביותר (" + recorded + ")";
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { lowestPoint: lowestPoint, versusLow: versusLow, formatVersusLow: formatVersusLow };
}
