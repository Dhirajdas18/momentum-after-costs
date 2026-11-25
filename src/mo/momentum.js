// Momentum maths in the browser. Mirrors src/mo/momentum.py; tests compare the two through Node.
// Monthly inputs are arrays of rows (months), each an array of prices per stock, null for gaps.
// The volatility-adjusted score needs daily prices, which the page does not carry, so it is
// Python only.

const isNum = (v) => v !== null && v !== undefined && Number.isFinite(v);

// Total return from month t - lookback to month t - skip, known at month-end t (null if missing).
function momentum(monthly, lookback = 12, skip = 1) {
  if (!(skip >= 0 && skip < lookback)) throw new Error("need 0 <= skip < lookback");
  return monthly.map((row, t) => row.map((_, j) => {
    if (t < lookback) return null;
    const a = monthly[t - lookback][j], b = monthly[t - skip][j];
    return isNum(a) && isNum(b) ? b / a - 1 : null;
  }));
}

// Long-only top-N, equal weight, rebalanced every `every` months; see backtest in momentum.py.
function backtest(px, score, topN = 20, every = 1, costPerSide = 0.003) {
  const T = px.length, n = T ? px[0].length : 0;
  const valid = (i, j) => isNum(score[i][j]) && isNum(px[i][j]);
  let i0 = -1;
  for (let i = 0; i < T - 1 && i0 < 0; i++) for (let j = 0; j < n; j++) if (valid(i, j)) { i0 = i; break; }
  if (i0 < 0) throw new Error("no month with a valid score and price before the last month");
  let w = new Array(n).fill(0), pending = 0;
  const gross = [], net = [], turnover = [], cost = [], holdings = [], rebalances = [];
  const equityGross = [1], equityNet = [1];
  for (let i = i0; i < T; i++) {
    if (i > i0) {
      const r = new Array(n);
      for (let j = 0; j < n; j++) {
        const a = px[i - 1][j], b = px[i][j];
        r[j] = isNum(a) && isNum(b) ? b / a - 1 : 0;  // missing start or end price: cash at 0
      }
      let g = 0;
      for (let j = 0; j < n; j++) g += w[j] * r[j];
      gross.push(g);
      net.push((1 + g) * (1 - pending) - 1);
      equityGross.push(equityGross[equityGross.length - 1] * (1 + g));
      equityNet.push(equityNet[equityNet.length - 1] * (1 + net[net.length - 1]));
      pending = 0;
      if (1 + g !== 0) w = w.map((v, j) => v * (1 + r[j]) / (1 + g));  // weights drift with prices
    }
    if (i < T - 1 && (i - i0) % every === 0) {
      const cand = [];
      for (let j = 0; j < n; j++) if (valid(i, j)) cand.push(j);
      cand.sort((a, b) => score[i][b] - score[i][a]);  // stable: ties keep column order
      const pick = cand.slice(0, topN), target = new Array(n).fill(0);
      pick.forEach((j) => { target[j] = 1 / pick.length; });
      let tv = 0;
      for (let j = 0; j < n; j++) tv += Math.abs(target[j] - w[j]);
      turnover.push(tv); cost.push(costPerSide * tv); pending = costPerSide * tv;
      holdings.push(pick); rebalances.push(i);
      w = target;
    }
  }
  return { start: i0, gross, net, equityGross, equityNet, turnover, cost, holdings, rebalances };
}

// Compound annual growth by calendar time; dates are "YYYY-MM-DD" strings.
function cagr(equity, dates) {
  const days = (Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / 86400000;
  return Math.pow(equity[equity.length - 1] / equity[0], 365.25 / days) - 1;
}

// Sample standard deviation of period returns, annualised by sqrt(periods).
function annualVol(returns, periods = 12) {
  const m = returns.reduce((a, b) => a + b, 0) / returns.length;
  const v = returns.reduce((a, b) => a + (b - m) ** 2, 0) / (returns.length - 1);
  return Math.sqrt(v * periods);
}

// Worst fall from a running peak, as a negative fraction.
function maxDrawdown(equity) {
  let peak = -Infinity, worst = 0;
  for (const v of equity) { peak = Math.max(peak, v); worst = Math.min(worst, v / peak - 1); }
  return worst;
}

if (typeof module !== "undefined") {
  module.exports = { momentum, backtest, cagr, annualVol, maxDrawdown };
}
