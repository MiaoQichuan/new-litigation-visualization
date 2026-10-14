/* 磁吸网格规则（编辑器用）。与 scripts/grid.py 是同一套规则的两份写法：
 * 常数一律从服务器给的 rules 里取，不在这里另写；回归里的「规则对照」用 node 跑这份，与 Python 逐项比对。
 * 只算几何，不碰 DOM。 */
(function (root) {
  "use strict";

  /* 版面：铺满全屏 / 预留位置（与 grid.py 的 geom 同一套算法）。base 是默认网格，frame 是课件的版面设定 */
  function geom(base, frame) {
    const full = !frame || (frame.mode || "full") === "full";
    const [t, r, b, l] = full ? [base.MY0 ?? base.MY, base.MX0 ?? base.MX, base.MY0 ?? base.MY, base.MX0 ?? base.MX]
                              : [frame.top, frame.right, frame.bottom, frame.left].map(Number);
    return Object.assign({}, base, {
      MX0: base.MX0 ?? base.MX, MY0: base.MY0 ?? base.MY, MX: l, MY: t,
      COL: (base.W - l - r - (base.COLS - 1) * base.GUT) / base.COLS,
      ROW: (base.H - t - b - (base.ROWS - 1) * base.GUT) / base.ROWS,
      BLEED: full ? [0, 0, base.W, base.H] : [l, t, base.W - l - r, base.H - t - b],
    });
  }
  function px(R, m) {
    const g = R.grid;
    if (m.bleed) return (g.BLEED || [0, 0, g.W, g.H]).slice();
    return [g.MX + m.x * (g.COL + g.GUT), g.MY + m.y * (g.ROW + g.GUT),
            m.w * g.COL + (m.w - 1) * g.GUT, m.h * g.ROW + (m.h - 1) * g.GUT];
  }

  function toneOf(R, m) {
    if (m.bleed) return "bare";
    return m.tone || R.types[m.type].tone;
  }

  function overlaps(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  }

  function fits(R, m) {
    const g = R.grid, t = R.types[m.type];
    if (!t) return false;
    if (m.x < 0 || m.y < 0 || m.x + m.w > g.COLS || m.y + m.h > g.ROWS) return false;
    if (m.w < t.min[0] || m.h < t.min[1]) return false;
    if (m.h > (t.maxh || g.ROWS)) return false;
    return true;
  }

  function joinable(R, a, b) {
    const fa = R.types[a.type].family, fb = R.types[b.type].family;
    return !!(fa && fa === fb && toneOf(R, a) === toneOf(R, b) && toneOf(R, a) !== "bare"
      && a.join !== false && b.join !== false);
  }

  /* 每个模块哪几条边与邻居连成一组：{id: ["l","r","t","b"] 的子集（按 lrtb 排序）} */
  function fusion(R, mods) {
    const sides = {};
    for (const m of mods) sides[m.id] = new Set();
    for (const a of mods) for (const b of mods) {
      if (a === b || !joinable(R, a, b)) continue;
      if (a.y === b.y && a.h === b.h && a.x + a.w === b.x) { sides[a.id].add("r"); sides[b.id].add("l"); }
      if (a.x === b.x && a.w === b.w && a.y + a.h === b.y) { sides[a.id].add("b"); sides[b.id].add("t"); }
    }
    const out = {};
    for (const k in sides) out[k] = ["l", "r", "t", "b"].filter((s) => sides[k].has(s));
    return out;
  }

  function cardRect(R, m, fused) {
    const g = R.grid;
    let [x, y, w, h] = px(R, m);
    const e = (g.GUT - g.FUSE_GAP) / 2;
    if (fused.includes("l")) { x -= e; w += e; }
    if (fused.includes("r")) { w += e; }
    if (fused.includes("t")) { y -= e; h += e; }
    if (fused.includes("b")) { h += e; }
    return [x, y, w, h];
  }

  /* 四角半径（左上、右上、右下、左下） */
  function corners(fused, outer, inner) {
    const has = (a, b) => fused.includes(a) || fused.includes(b);
    return [has("t", "l") ? inner : outer, has("t", "r") ? inner : outer,
            has("b", "r") ? inner : outer, has("b", "l") ? inner : outer];
  }

  function freeSpot(R, mods, w, h, x0, y0, skip) {
    const g = R.grid;
    const others = mods.filter((m) => m.id !== skip);
    let best = null;
    for (let y = 0; y <= g.ROWS - h; y++) for (let x = 0; x <= g.COLS - w; x++) {
      const c = { x, y, w, h };
      if (others.some((o) => overlaps(c, o))) continue;
      const d = (x - x0) ** 2 + (y - y0) ** 2 * 1.5;
      if (best === null || d < best[0]) best = [d, x, y];
    }
    return best === null ? null : [best[1], best[2]];
  }

  /* 放一个模块：先按要的尺寸找空位，放不下就逐步缩到最小尺寸。返回 [x, y, w, h] 或 null。 */
  function place(R, mods, type, x0, y0, w, h, skip) {
    const t = R.types[type];
    const [mw, mh] = t.min, [dw, dh] = t.default;
    w = w || dw; h = h || dh;
    const tries = [];
    for (let ww = w; ww >= mw; ww--) for (let hh = h; hh >= mh; hh--) tries.push([ww * hh, ww, hh, tries.length]);
    tries.sort((a, b) => b[0] - a[0] || a[3] - b[3]);          /* 与 Python 的稳定排序一致 */
    for (const [, ww, hh] of tries) {
      const s = freeSpot(R, mods, ww, hh, x0 || 0, y0 || 0, skip);
      if (s) return [s[0], s[1], ww, hh];
    }
    return null;
  }

  /* 页面坐标 → 最近的格子（左上角）。 */
  function cellAt(R, X, Y) {
    const g = R.grid;
    return [Math.round((X - g.MX) / (g.COL + g.GUT)), Math.round((Y - g.MY) / (g.ROW + g.GUT))];
  }

  function clampTo(R, m) {
    const g = R.grid;
    return Object.assign({}, m, {
      x: Math.max(0, Math.min(g.COLS - m.w, m.x)),
      y: Math.max(0, Math.min(g.ROWS - m.h, m.y)),
    });
  }

  /* 吸进一组（借 M3E Canvas 的连接件）：卡片拖到同类卡片旁边，就按那一组的高（并排）或宽（上下叠）落下，
   * 落下即连成一组。c 是拖动中的候选（含 type / tone / join）；离 c 最近、在 reach 格以内、放得下的那个位置胜出。
   * 只在编辑器里用：deck.json 里写的是落定后的格子，拼页不需要这一步。 */
  function runSnap(R, mods, c, skip, reach) {
    const t = R.types[c.type];
    if (!t || !t.family) return null;
    reach = reach == null ? 2 : reach;
    const others = mods.filter((m) => m.id !== skip);
    const opts = [];
    for (const n of others) {
      if (!joinable(R, n, c)) continue;
      for (let w = c.w; w >= t.min[0]; w--) {
        opts.push({ x: n.x + n.w, y: n.y, w, h: n.h }, { x: n.x - w, y: n.y, w, h: n.h });
      }
      for (let h = c.h; h >= t.min[1]; h--) {
        opts.push({ x: n.x, y: n.y + n.h, w: n.w, h }, { x: n.x, y: n.y - h, w: n.w, h });
      }
    }
    let best = null;
    for (const o of opts) {
      const cand = Object.assign({}, c, o);
      if (!fits(R, cand) || others.some((m) => overlaps(cand, m))) continue;
      const d = Math.hypot(o.x - c.x, o.y - c.y);
      if (d > reach) continue;
      const score = d - o.w * o.h * 0.001;          /* 同样近时取大的 */
      if (!best || score < best[0]) best = [score, cand];
    }
    return best ? best[1] : null;
  }

  const api = { geom, px, toneOf, overlaps, fits, joinable, fusion, cardRect, corners, freeSpot, place, cellAt, clampTo, runSnap };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.NLVGrid = api;
})(typeof window !== "undefined" ? window : globalThis);
