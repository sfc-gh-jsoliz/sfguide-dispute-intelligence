/* Chargeback & Dispute Intelligence: hosted no-account example (Sample mode only).
   Renders the same five screens as app/streamlit_app.py from data/*.json, which
   scripts/capture_sample.py captured from a Live run. No external scripts. */
(function () {
  "use strict";
  var C = { lost: "#A33A12", primary: "#11757B", gold: "#7A6A2E", bench: "#6B5512", line: "#D3DCDD", muted: "#4E6064", ink: "#102326", ai: "#0E6E7E" };
  var CAT = { "Fraud": C.lost, "Consumer Disputes": C.primary, "Processing Errors": C.gold };
  var CATN = { DIGITAL: "Digital Goods", TRAVEL: "Travel", RETAIL: "Retail", GROCERY: "Grocery" };
  var SCOPES = { holiday: "Holiday spike: Nov 2025-Jan 2026 vs Aug-Oct 2025", book: "Book review: first vs latest month (Jul 2024 vs Jun 2026)" };
  var QUESTIONS = [
    "How did chargeback volume in Nov-Dec compare to the prior 3 months, by reason category?",
    "What is our win rate by reason code, and where are we losing the most dollars?",
    "How do our dispute trends compare to CFPB complaint volume for the same period?"
  ];
  var HEDGE = "Fraud disputes likely rose around 40% and could keep climbing into next season.";
  var cache = {}, state = { note: null, rv: null, chat: [], rFilter: null, mFilter: null };
  var view = document.getElementById("view"), tip = document.getElementById("tip");
  var MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function load(k) {
    if (!cache[k]) cache[k] = fetch("data/" + k + ".json").then(function (r) { if (!r.ok) throw new Error(k + ": HTTP " + r.status); return r.json(); });
    return cache[k];
  }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function usd(v) { v = +v || 0; return Math.abs(v) >= 1e6 ? "$" + (v / 1e6).toFixed(2) + "M" : Math.abs(v) >= 1e3 ? "$" + Math.round(v / 1e3) + "K" : "$" + v.toFixed(2); }
  function pct(v) { return v == null || isNaN(v) ? "n/d" : (v * 100).toFixed(1) + "%"; }
  function num(v) { return Math.round(v).toLocaleString("en-US"); }
  function mlabel(d) { var p = d.split("-"); return MON[+p[1] - 1] + " " + p[0].slice(2); }
  function mlong(d) { var p = d.split("-"); return MON[+p[1] - 1] + " " + p[0]; }
  function sum(a, f) { return a.reduce(function (s, x) { return s + (+f(x) || 0); }, 0); }
  function group(a, f) { var m = {}; a.forEach(function (x) { var k = f(x); (m[k] = m[k] || []).push(x); }); return m; }
  function pill(t, k) { return '<span class="pill p-' + k + '">' + esc(t) + "</span>"; }
  function powered(t) { return '<div class="powered"><i></i>' + esc(t) + "</div>"; }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function jitter(a, b) { return a + Math.random() * (b - a); }
  function kpi(l, v, n, trend, goodUp) {
    var t = "";
    if (trend != null) { var up = trend >= 0, good = up === goodUp; t = '<span class="' + (good ? "tw" : "tl") + '">' + (up ? "&#9650; " : "&#9660; ") + Math.abs(Math.round(trend * 100)) + "%</span>"; }
    return '<div class="kpi"><div class="kl">' + esc(l) + '</div><div class="kv" data-count="' + esc(v) + '">' + esc(v) + '</div><div class="kn">' + t + "<span>" + esc(n) + "</span></div></div>";
  }
  function animateCounts() {
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    view.querySelectorAll("[data-count]").forEach(function (el) {
      var txt = el.getAttribute("data-count"), m = txt.match(/^(\D*)([\d,.]+)(.*)$/);
      if (!m) return;
      var target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length, comma = m[2].indexOf(",") >= 0, t0 = performance.now();
      (function step(t) {
        var k = Math.min(1, (t - t0) / 900), e = 1 - Math.pow(1 - k, 3), v = target * e;
        var s = dec ? v.toFixed(dec) : Math.round(v).toString();
        if (comma) s = Number(s).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
        el.textContent = m[1] + s + m[3];
        if (k < 1) requestAnimationFrame(step);
      })(t0);
    });
  }
  function showTip(e, h) { tip.innerHTML = h; tip.hidden = false; var x = Math.min(e.clientX + 12, innerWidth - 250); tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px"; }
  function hideTip() { tip.hidden = true; }
  function bindTips(root) {
    root.querySelectorAll("[data-tip]").forEach(function (el) {
      el.addEventListener("mousemove", function (e) { showTip(e, el.getAttribute("data-tip")); });
      el.addEventListener("mouseleave", hideTip);
      el.addEventListener("click", function (e) { showTip(e, el.getAttribute("data-tip")); });
    });
  }
  function md(s) {
    s = esc(s);
    var lines = s.split("\n"), out = [], i = 0;
    function inline(t) { return t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\[(F\d+(?:\s*,\s*F\d+)*)\]/g, function (_, ids) { return ids.split(/\s*,\s*/).map(function (x) { return '<span class="cite">' + x + "</span>"; }).join(""); }); }
    while (i < lines.length) {
      var l = lines[i];
      if (/^\|/.test(l)) {
        var rows = []; while (i < lines.length && /^\|/.test(lines[i])) { rows.push(lines[i]); i++; }
        var cells = rows.filter(function (r) { return !/^\|[\s:|-]+\|$/.test(r); }).map(function (r) { return r.replace(/^\||\|$/g, "").split("|"); });
        out.push('<div class="scroll"><table>' + cells.map(function (c, j) { return "<tr>" + c.map(function (x) { return (j ? "<td>" : "<th>") + inline(x.trim()) + (j ? "</td>" : "</th>"); }).join("") + "</tr>"; }).join("") + "</table></div>");
        continue;
      }
      if (/^[-*] /.test(l)) { var it = []; while (i < lines.length && /^[-*] /.test(lines[i])) { it.push("<li>" + inline(lines[i].slice(2)) + "</li>"); i++; } out.push("<ul>" + it.join("") + "</ul>"); continue; }
      var h = l.match(/^(#{1,3}) (.*)$/);
      if (h) out.push("<h" + (h[1].length) + ">" + inline(h[2]) + "</h" + h[1].length + ">");
      else if (l.trim()) out.push("<p>" + inline(l) + "</p>");
      i++;
    }
    return out.join("");
  }

  /* ---------- data shaping (mirrors the Streamlit app) ---------- */
  function bookTotals(monthly, cm) {
    var by = group(monthly, function (r) { return r.month_end; }), proc = group(cm, function (r) { return r.month_end; });
    return Object.keys(by).sort().map(function (m) {
      var rs = by[m];
      return { m: m, disputes: sum(rs, function (r) { return r.total_disputes; }), usd: sum(rs, function (r) { return r.total_dispute_usd; }),
        won: sum(rs, function (r) { return r.total_won; }), resolved: sum(rs, function (r) { return r.total_resolved; }),
        lost: sum(rs, function (r) { return r.total_lost_usd; }), ff: sum(rs, function (r) { return r.total_friendly_fraud; }),
        cfpb: Math.max.apply(null, rs.map(function (r) { return r.cfpb_complaints; })), proc: sum(proc[m] || [], function (r) { return r.processed_txn; }),
        holiday: [11, 12, 1].indexOf(+m.split("-")[1]) >= 0 };
    });
  }
  function reasonTable(rm, dim) {
    var g = group(rm, function (r) { return r.reason_code; });
    return Object.keys(g).map(function (code) {
      var rs = g[code], d = dim.filter(function (x) { return x.reason_code === code; })[0] || {};
      var won = sum(rs, function (r) { return r.total_won; }), res = sum(rs, function (r) { return r.total_resolved; });
      return { code: code, network: rs[0].network, name: rs[0].reason_name, cat: rs[0].reason_category, disputes: sum(rs, function (r) { return r.total_disputes; }),
        usd: sum(rs, function (r) { return r.total_dispute_usd; }), won: won, resolved: res, lost: sum(rs, function (r) { return r.total_lost_usd; }),
        win: res ? won / res : null, root: d.typical_root_cause, desc: d.description, ff: d.is_friendly_fraud, months: rs };
    }).sort(function (a, b) { return b.disputes - a.disputes; });
  }
  function merchantTable(raw) {
    var g = group(raw, function (r) { return r.merchant_id; }), catMix = {};
    raw.forEach(function (r) { var k = r.merchant_category; catMix[k] = catMix[k] || {}; catMix[k][r.reason_code] = (catMix[k][r.reason_code] || 0) + r.disputes; });
    return Object.keys(g).map(function (id) {
      var rs = g[id], tot = sum(rs, function (r) { return r.disputes; }), st = {};
      rs.forEach(function (r) { st[r.status] = (st[r.status] || 0) + r.disputes; });
      var codes = {}; rs.forEach(function (r) { codes[r.reason_code] = (codes[r.reason_code] || 0) + r.disputes; });
      var cm = catMix[rs[0].merchant_category], ctot = Object.keys(cm).reduce(function (s, k) { return s + cm[k]; }, 0), hot = null;
      Object.keys(codes).sort().forEach(function (k) { var lift = (codes[k] / tot) / (cm[k] / ctot); if (!hot || lift > hot.lift) hot = { code: k, share: codes[k] / tot, cat: cm[k] / ctot, lift: lift }; });
      var w = st.won || 0, l = st.lost || 0;
      return { id: +id, name: rs[0].merchant_name, mcc: rs[0].mcc, catKey: rs[0].merchant_category, cat: CATN[rs[0].merchant_category], disputes: tot,
        usd: sum(rs, function (r) { return r.dispute_usd; }), lost: sum(rs.filter(function (r) { return r.status === "lost"; }), function (r) { return r.dispute_usd; }),
        win: w + l ? w / (w + l) : null, inflight: (st.open || 0) + (st["pre-arb"] || 0), hot: hot };
    }).sort(function (a, b) { return b.lost - a.lost; });
  }

  /* ---------- SVG charts ---------- */
  function trendChart(monthly, totals) {
    var W = 760, H = 300, L = 46, R = 52, T = 18, B = 30, months = totals.map(function (t) { return t.m; }), n = months.length;
    var cats = ["Fraud", "Consumer Disputes", "Processing Errors"], stack = {};
    months.forEach(function (m) { stack[m] = {}; });
    monthly.forEach(function (r) { stack[r.month_end][r.reason_category] = r.total_disputes; });
    var maxY = Math.ceil(Math.max.apply(null, totals.map(function (t) { return t.disputes; })) / 100) * 100;
    var cMax = Math.ceil(Math.max.apply(null, totals.map(function (t) { return t.cfpb; })) / 1000) * 1000;
    function x(i) { return L + (W - L - R) * i / (n - 1); }
    function y(v) { return T + (H - T - B) * (1 - v / maxY); }
    function y2(v) { return T + (H - T - B) * (1 - v / cMax); }
    var s = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Monthly disputes stacked by reason category with the CFPB complaint benchmark as a dashed line">';
    totals.forEach(function (t, i) { if (t.holiday) s += '<rect x="' + (x(i) - (W - L - R) / (n - 1) / 2) + '" y="' + T + '" width="' + (W - L - R) / (n - 1) + '" height="' + (H - T - B) + '" fill="#F3E9CC" opacity=".55"/>'; });
    [0, .25, .5, .75, 1].forEach(function (k) { var v = maxY * k; s += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="' + C.line + '"/><text x="' + (L - 6) + '" y="' + (y(v) + 4) + '" text-anchor="end">' + v + '</text><text x="' + (W - R + 6) + '" y="' + (y2(cMax * k) + 4) + '">' + num(cMax * k) + "</text>"; });
    var base = months.map(function () { return 0; });
    cats.forEach(function (c) {
      var top = months.map(function (m, i) { return base[i] + (stack[m][c] || 0); });
      var d = "M" + months.map(function (m, i) { return x(i) + "," + y(top[i]); }).join("L") + "L" + months.map(function (m, i) { return x(n - 1 - i) + "," + y(base[n - 1 - i]); }).join("L") + "Z";
      s += '<path d="' + d + '" fill="' + CAT[c] + '" opacity=".88"/>';
      base = top;
    });
    s += '<path d="M' + totals.map(function (t, i) { return x(i) + "," + y2(t.cfpb); }).join("L") + '" fill="none" stroke="' + C.bench + '" stroke-width="2" stroke-dasharray="5 4"/>';
    totals.forEach(function (t, i) {
      var tipH = "<b>" + mlong(t.m) + "</b><br>" + cats.map(function (c) { return c + ": " + num(stack[t.m][c] || 0); }).join("<br>") + "<br>Total: " + num(t.disputes) + " · " + usd(t.usd) + "<br>CFPB complaints: " + num(t.cfpb);
      s += '<circle cx="' + x(i) + '" cy="' + y2(t.cfpb) + '" r="2.6" fill="' + C.bench + '"/>';
      s += '<rect data-tip="' + esc(tipH) + '" x="' + (x(i) - (W - L - R) / (n - 1) / 2) + '" y="' + T + '" width="' + (W - L - R) / (n - 1) + '" height="' + (H - T - B) + '" fill="transparent"/>';
      if (i % 3 === 0) s += '<text x="' + x(i) + '" y="' + (H - 10) + '" text-anchor="middle">' + mlabel(t.m) + "</text>";
    });
    s += '<text x="' + (x(4) + 4) + '" y="' + (T + 12) + '" style="fill:' + C.bench + ';font-weight:600">Holiday</text>';
    return s + "</svg>";
  }
  function hbars(rows) {
    var W = 1100, rowH = 30, L = 300, H = rows.length * rowH + 26, max = Math.max.apply(null, rows.map(function (r) { return r.lost; }));
    var s = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Dollars lost by reason code">';
    rows.forEach(function (r, i) {
      var w = (W - L - 70) * r.lost / max, yy = i * rowH + 4;
      s += '<text x="' + (L - 8) + '" y="' + (yy + 16) + '" text-anchor="end" style="fill:' + C.ink + '">' + esc(r.network === "VISA" ? "Visa" : "Mastercard") + " " + esc(r.code) + " · " + esc(r.name) + "</text>";
      s += '<rect data-tip="' + esc("<b>" + r.code + " " + r.name + "</b><br>Lost " + usd(r.lost) + "<br>Win rate " + pct(r.win) + "<br>" + num(r.disputes) + " disputes") + '" x="' + L + '" y="' + yy + '" width="' + w + '" height="18" rx="4" fill="' + CAT[r.cat] + '"/>';
      s += '<text x="' + (L + w + 6) + '" y="' + (yy + 14) + '">' + usd(r.lost) + "</text>";
    });
    return s + "</svg>";
  }
  function heatmap(cm) {
    var cats = ["Digital Goods & Subscriptions", "Travel & Hospitality", "Retail & E-commerce", "Grocery & Essentials"];
    var months = Array.from(new Set(cm.map(function (r) { return r.month_end; }))).sort(), W = 760, L = 150, cw = (W - L) / months.length, ch = 30, H = cats.length * ch + 30;
    var vals = cm.map(function (r) { return r.total_disputes / r.processed_txn * 1e4; }), lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    function col(v) { var k = (v - lo) / (hi - lo), a = [234, 243, 243], b = [12, 59, 62]; return "rgb(" + a.map(function (x, i) { return Math.round(x + (b[i] - x) * Math.pow(k, .8)); }).join(",") + ")"; }
    var s = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Chargeback rate heatmap by merchant category and month">';
    cats.forEach(function (c, j) {
      s += '<text x="' + (L - 8) + '" y="' + (j * ch + 19) + '" text-anchor="end" style="fill:' + C.ink + '">' + esc(c.split(" &")[0].split(" ")[0] === "Digital" ? "Digital Goods" : c.split(" &")[0]) + "</text>";
      months.forEach(function (m, i) {
        var r = cm.filter(function (x) { return x.month_end === m && x.category_name === c; })[0]; if (!r) return;
        var v = r.total_disputes / r.processed_txn * 1e4;
        s += '<rect data-tip="' + esc("<b>" + c + "</b><br>" + mlong(m) + "<br>" + v.toFixed(1) + " bps · " + r.total_disputes + " disputes<br>" + num(r.processed_txn) + " processed txns") + '" x="' + (L + i * cw + 1) + '" y="' + (j * ch + 2) + '" width="' + (cw - 2) + '" height="' + (ch - 4) + '" rx="3" fill="' + col(v) + '"/>';
      });
    });
    months.forEach(function (m, i) { if (i % 3 === 0) s += '<text x="' + (L + i * cw + cw / 2) + '" y="' + (H - 8) + '" text-anchor="middle">' + mlabel(m) + "</text>"; });
    return s + "</svg>";
  }
  function bars(series, color, label) {
    var W = 600, H = 180, L = 36, B = 26, n = series.length, max = Math.max.apply(null, series.map(function (s) { return s.v; })) || 1, bw = (W - L) / n;
    var s = '<svg class="chart" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(label) + '">';
    [0, .5, 1].forEach(function (k) { var yy = 8 + (H - B - 8) * (1 - k); s += '<line x1="' + L + '" x2="' + W + '" y1="' + yy + '" y2="' + yy + '" stroke="' + C.line + '"/><text x="' + (L - 5) + '" y="' + (yy + 4) + '" text-anchor="end">' + Math.round(max * k) + "</text>"; });
    series.forEach(function (d, i) {
      var h = (H - B - 8) * d.v / max;
      s += '<rect data-tip="' + esc(d.tip) + '" x="' + (L + i * bw + bw * .18) + '" y="' + (H - B - h) + '" width="' + bw * .64 + '" height="' + h + '" rx="2" fill="' + color + '"/>';
      if (i % 3 === 0) s += '<text x="' + (L + i * bw + bw / 2) + '" y="' + (H - 8) + '" text-anchor="middle">' + mlabel(d.m) + "</text>";
    });
    return s + "</svg>";
  }

  /* ---------- sortable table ---------- */
  function table(cols, rows, onRow) {
    var id = "t" + Math.random().toString(36).slice(2, 8), sortK = null, dir = -1;
    function body() {
      var rs = rows.slice();
      if (sortK) rs.sort(function (a, b) { var x = a[sortK], y = b[sortK]; return (x > y ? 1 : x < y ? -1 : 0) * dir; });
      return rs.map(function (r) { return '<tr tabindex="0" data-k="' + esc(r._key) + '">' + cols.map(function (c) { return '<td class="' + (c.n ? "n" : "") + '">' + c.f(r) + "</td>"; }).join("") + "</tr>"; }).join("");
    }
    setTimeout(function () {
      var t = document.getElementById(id); if (!t) return;
      t.querySelectorAll("th").forEach(function (th, i) {
        th.addEventListener("click", function () {
          var k = cols[i].k; if (!k) return;
          dir = sortK === k ? -dir : -1; sortK = k;
          t.querySelectorAll("th").forEach(function (x) { x.removeAttribute("aria-sort"); });
          th.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
          t.tBodies[0].innerHTML = body(); wire();
        });
      });
      function wire() {
        t.querySelectorAll("tbody tr").forEach(function (tr) {
          tr.addEventListener("click", function () { onRow(tr.getAttribute("data-k")); });
          tr.addEventListener("keydown", function (e) { if (e.key === "Enter") onRow(tr.getAttribute("data-k")); });
        });
      }
      wire();
    });
    return '<div class="scroll"><table class="t" id="' + id + '"><thead><tr>' + cols.map(function (c) { return '<th class="' + (c.n ? "n" : "") + '" scope="col">' + esc(c.h) + "</th>"; }).join("") + "</tr></thead><tbody>" + body() + "</tbody></table></div>";
  }

  /* ---------- drawer ---------- */
  var drawer = document.getElementById("drawer"), dbody = document.getElementById("dbody"), lastFocus = null;
  function openDrawer(h) { lastFocus = document.activeElement; dbody.innerHTML = h; drawer.hidden = false; bindTips(dbody); drawer.querySelector(".x").focus(); document.body.style.overflow = "hidden"; }
  function closeDrawer() { drawer.hidden = true; document.body.style.overflow = ""; hideTip(); if (lastFocus) lastFocus.focus(); }
  drawer.addEventListener("click", function (e) { if (e.target.hasAttribute("data-close")) closeDrawer(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drawer.hidden) closeDrawer(); });

  /* ---------- staged AI ---------- */
  function stagedRun(box, steps, totalMs) {
    box.innerHTML = '<ul class="steps">' + steps.map(function (s) { return '<li><span class="spin"></span>' + esc(s) + "</li>"; }).join("") + "</ul>";
    var lis = box.querySelectorAll("li"), per = totalMs / steps.length, p = Promise.resolve();
    steps.forEach(function (_, i) { p = p.then(function () { lis[i].className = "on"; return sleep(per * jitter(.85, 1.15)); }).then(function () { lis[i].className = "done"; }); });
    return p;
  }
  function streamInto(el, text, wps) {
    var toks = text.split(/(\s+)/), acc = "", i = 0;
    return new Promise(function (res) {
      (function tick() {
        for (var k = 0; k < 3 && i < toks.length; k++) acc += toks[i++];
        el.innerHTML = md(acc) + '<span class="caret"></span>';
        if (i < toks.length) setTimeout(tick, 1000 / wps * 3); else { el.innerHTML = md(text); res(); }
      })();
    });
  }
  var SAMPLE_LABEL = '<div class="ailabel">Sample AI response · captured from a Live run, replayed with a simulated delay</div>';

  /* ---------- screens ---------- */
  var screens = {
    overview: function () {
      return Promise.all([load("monthly"), load("category_month"), load("reason_monthly"), load("reason_dim")]).then(function (d) {
        var t = bookTotals(d[0], d[1]), rt = reasonTable(d[2], d[3]);
        var hol = t.filter(function (x) { return x.holiday; }), oth = t.filter(function (x) { return !x.holiday; });
        var avg = function (a, f) { return sum(a, f) / a.length; };
        var holAvg = avg(hol, function (x) { return x.disputes; }), othAvg = avg(oth, function (x) { return x.disputes; });
        var last3 = t.slice(-3), prev3 = t.slice(-6, -3), wr = sum(t, function (x) { return x.won; }) / sum(t, function (x) { return x.resolved; });
        var wrT = (sum(last3, function (x) { return x.won; }) / sum(last3, function (x) { return x.resolved; })) / (sum(prev3, function (x) { return x.won; }) / sum(prev3, function (x) { return x.resolved; })) - 1;
        var bps = function (a) { return avg(a, function (x) { return x.disputes / x.proc * 1e4; }); };
        var worst = rt.slice().sort(function (a, b) { return a.win - b.win; })[0], topLoss = rt.slice().sort(function (a, b) { return b.lost - a.lost; })[0];
        var cats = group(d[1], function (r) { return r.category_name; }), crate = Object.keys(cats).map(function (k) { return { k: k, v: sum(cats[k], function (r) { return r.total_disputes; }) / sum(cats[k], function (r) { return r.processed_txn; }) * 1e4 }; }).sort(function (a, b) { return b.v - a.v; });
        return "<h1>Chargeback overview</h1><p class=\"sub\">Halvane Payments dispute book · 24 months to 30 Jun 2026 · benchmarked against monthly consumer complaints</p>" +
          '<div class="kpis">' + kpi("Disputes filed", num(sum(t, function (x) { return x.disputes; })), "Nov-Jan vs other months", holAvg / othAvg - 1, false) +
          kpi("Disputed amount", usd(sum(t, function (x) { return x.usd; })), "24 months, all networks") +
          kpi("Win rate", pct(wr), "won / resolved · last 3 vs prior 3 mo", wrT, true) +
          kpi("Dollars lost", usd(sum(t, function (x) { return x.lost; })), usd(sum(last3, function (x) { return x.lost; })) + " in the last 3 months") +
          kpi("Chargeback rate", Math.round(bps(t)) + " bps", "holiday " + Math.round(bps(hol)) + " vs " + Math.round(bps(oth)) + " bps", bps(hol) / bps(oth) - 1, false) + "</div>" +
          '<div class="grid"><section class="card"><h2>Disputes by reason category, with the complaint benchmark</h2>' + powered("Semantic View DISPUTE_SV · SEMANTIC_VIEW() query") +
          '<div class="legend"><span><b style="background:' + C.lost + '"></b>Fraud</span><span><b style="background:' + C.primary + '"></b>Consumer Disputes</span><span><b style="background:' + C.gold + '"></b>Processing Errors</span><span><b class="dash"></b>CFPB complaints (right axis)</span></div>' +
          trendChart(d[0], t) + '<p class="cap">Complaint counts are a market-wide monthly signal, joined by month only and never summed with disputes.</p></section>' +
          '<section class="card"><h2>What stands out</h2>' +
          '<div class="ins i-gold"><b>Holiday spike.</b> Nov-Jan averaged ' + num(holAvg) + " disputes a month vs " + num(othAvg) + " in other months (+" + Math.round((holAvg / othAvg - 1) * 100) + "%).</div>" +
          '<div class="ins i-lost"><b>Hardest to win: ' + (worst.network === "VISA" ? "Visa " : "Mastercard ") + esc(worst.code) + "</b> (" + esc(worst.name) + ") at " + pct(worst.win) + " vs " + pct(wr) + " for the book.</div>" +
          '<div class="ins i-lost"><b>Most dollars lost: ' + esc(topLoss.code) + "</b>, " + usd(topLoss.lost) + " over 24 months.</div>" +
          '<div class="ins i-won"><b>' + esc(crate[0].k) + "</b> runs " + Math.round(crate[0].v) + " bps, " + (crate[0].v / crate[crate.length - 1].v).toFixed(1) + "x " + esc(crate[crate.length - 1].k) + ".</div>" +
          '<div class="ins i-ai">Computed from the semantic view, not AI. Open <a href="#/notes"><b>Chargeback notes</b></a> for a verified write-up.</div></section></div>' +
          '<section class="card"><h2>Dollars lost by reason code</h2>' + hbars(rt.slice().sort(function (a, b) { return b.lost - a.lost; })) + "</section>";
      });
    },
    reasons: function () {
      return Promise.all([load("reason_monthly"), load("reason_dim"), load("reason_by_category")]).then(function (d) {
        var rt = reasonTable(d[0], d[1]), bookWr = sum(rt, function (r) { return r.won; }) / sum(rt, function (r) { return r.resolved; });
        var f = state.rFilter || (state.rFilter = { net: { VISA: 1, MASTERCARD: 1 }, cat: { "Fraud": 1, "Consumer Disputes": 1, "Processing Errors": 1 }, q: "" });
        var rows = rt.filter(function (r) { return f.net[r.network] && f.cat[r.cat] && (!f.q || (r.code + " " + r.name + " " + r.root).toLowerCase().indexOf(f.q.toLowerCase()) >= 0); });
        rows.forEach(function (r) { r._key = r.code; });
        function chip(group, k, label) { return '<button type="button" class="fchip" data-g="' + group + '" data-k="' + esc(k) + '" aria-pressed="' + (!!f[group][k]) + '">' + esc(label) + "</button>"; }
        var h = '<h1>Reason codes</h1><p class="sub">Every Visa and Mastercard reason code in the book. Click a row to open its detail panel; click a column header to sort.</p>' +
          '<div class="filters">' + chip("net", "VISA", "Visa") + chip("net", "MASTERCARD", "Mastercard") + "<span style=\"width:.6rem\"></span>" +
          chip("cat", "Fraud", "Fraud") + chip("cat", "Consumer Disputes", "Consumer Disputes") + chip("cat", "Processing Errors", "Processing Errors") +
          '<input class="search" type="search" placeholder="Search: recurring, 10.4" aria-label="Search reason codes" value="' + esc(f.q) + '"></div>';
        if (!rows.length) return h + '<div class="empty">No reason codes match these filters. Clear a filter or the search box.</div>';
        h += '<section class="card">' + powered("Book win rate " + pct(bookWr) + " · rows from SEMANTIC_VIEW(DISPUTE_SV)") + table([
          { h: "Network", k: "network", f: function (r) { return r.network === "VISA" ? "Visa" : "Mastercard"; } },
          { h: "Code", k: "code", f: function (r) { return "<b>" + esc(r.code) + "</b>"; } },
          { h: "Reason", k: "name", f: function (r) { return esc(r.name); } },
          { h: "Category", k: "cat", f: function (r) { return esc(r.cat); } },
          { h: "Disputes", k: "disputes", n: 1, f: function (r) { return num(r.disputes); } },
          { h: "Disputed", k: "usd", n: 1, f: function (r) { return usd(r.usd); } },
          { h: "Win rate", k: "win", f: function (r) { return '<span class="bar"><i style="width:' + (r.win * 100) + '%"></i></span>' + pct(r.win); } },
          { h: "Lost", k: "lost", n: 1, f: function (r) { return usd(r.lost); } },
          { h: "Status", k: "win", f: function (r) { return r.win < bookWr - .05 ? pill("Below book", "lost") : pill("At or above book", "won"); } }
        ], rows, function (code) { reasonDrawer(rt.filter(function (r) { return r.code === code; })[0], bookWr, d[2]); }) + "</section>";
        return h;
      });
    },
    merchants: function () {
      return Promise.all([load("category_month"), load("merchants")]).then(function (d) {
        var mt = merchantTable(d[1]), f = state.mFilter || (state.mFilter = { cat: { "Digital Goods": 1, "Travel": 1, "Retail": 1, "Grocery": 1 } });
        var rows = mt.filter(function (r) { return f.cat[r.cat]; }); rows.forEach(function (r) { r._key = r.id; r.hotLift = r.hot.lift; });
        var h = '<h1>Merchants</h1><p class="sub">Chargeback rate by merchant category and month, and every merchant in the book. Click a merchant to see its disputes in flight.</p>' +
          '<section class="card"><h2>Chargeback rate (bps of processed transactions)</h2>' + heatmap(d[0]) + powered("Semantic View DISPUTE_SV · processed volume is non-additive (MAX per category-month)") + "</section>" +
          '<div class="filters">' + Object.keys(f.cat).map(function (k) { return '<button type="button" class="fchip" data-g="cat" data-k="' + k + '" aria-pressed="' + (!!f.cat[k]) + '">' + k + "</button>"; }).join("") + "</div>";
        if (!rows.length) return h + '<div class="empty">No merchants in the selected categories.</div>';
        return h + '<section class="card">' + table([
          { h: "Merchant", k: "name", f: function (r) { return "<b>" + esc(r.name) + "</b>"; } },
          { h: "Category", k: "cat", f: function (r) { return esc(r.cat); } },
          { h: "MCC", k: "mcc", f: function (r) { return esc(r.mcc); } },
          { h: "Disputes", k: "disputes", n: 1, f: function (r) { return num(r.disputes); } },
          { h: "Win rate", k: "win", f: function (r) { return '<span class="bar"><i style="width:' + (r.win * 100) + '%"></i></span>' + pct(r.win); } },
          { h: "Lost", k: "lost", n: 1, f: function (r) { return usd(r.lost); } },
          { h: "In flight", k: "inflight", n: 1, f: function (r) { return num(r.inflight); } },
          { h: "Concentration", k: "hotLift", f: function (r) { return r.hot.lift >= 2 ? pill(r.hot.code + ": " + Math.round(r.hot.share * 100) + "% vs " + Math.round(r.hot.cat * 100) + "% category", "lost") : pill("In line with category mix", "open"); } }
        ], rows, function (id) { merchantDrawer(mt.filter(function (r) { return r.id === +id; })[0]); }) + '<p class="cap">Merchant rows come from DISPUTE_FACT (the semantic view stops at merchant category).</p></section>';
      });
    },
    notes: function () {
      return load("reports").then(function (reports) {
        var n = state.note;
        var h = '<h1>Chargeback notes</h1><p class="sub">A one-page note for a merchant review or the CFO: drafted by Cortex AI_COMPLETE from a fact pack, then fact-checked by a second AI_COMPLETE pass that refuses unsupported or hedged claims.</p>' +
          '<div class="two"><section class="card"><h2>Write a note</h2>' + Object.keys(SCOPES).map(function (k, i) { return '<label class="radio"><input type="radio" name="scope" value="' + k + '"' + ((n ? n.scope === k : i === 0) ? " checked" : "") + ">" + esc(SCOPES[k]) + "</label>"; }).join("") +
          powered("Cortex AI_COMPLETE · draft + verifier") + '<button class="btn" id="runNote" type="button">&#9654; Run dispute analysis</button><p class="cap">Live runs take about 8-11 s and cost two AI_COMPLETE calls.</p></section>' +
          '<div><div id="noteOut">' + (n ? noteHtml(n.res) : '<div class="empty"><b>No note yet.</b><br>Pick a scope and run the analysis. The draft streams in, then the verifier stamps it Verified or Needs review.</div>') + "</div>" +
          '<section class="card" id="breakCard"' + (n ? "" : " hidden") + '><h2>Try to break it</h2><p class="cap" style="margin-top:0">Add a hedged, unsupported sentence to the draft and run only the verifier again.</p><button class="btn ghost" id="runRv" type="button">Insert a hedge and re-verify</button><div id="rvOut">' + (state.rv && n && state.rv.scope === n.scope ? rvHtml(state.rv.rv) : "") + "</div></section></div></div>" +
          '<h2 style="margin-top:.4rem">Note gallery</h2><div class="gallery">' + reports.map(function (r, i) {
            var ok = r.status === "verified", title = (r.report_md || "").split("\n")[0].replace(/^#+\s*/, "") || r.subject;
            return '<button type="button" class="docket' + (ok ? "" : " bad") + '" data-rep="' + i + '">' + pill(ok ? "Verified" : "Needs review", ok ? "won" : "lost") + '<div class="dt">' + esc(title.slice(0, 90)) + '</div><div class="ds">' + esc(r.subject) + " · " + esc(r.created_at) + " · " + r.edits_applied + " flagged</div></button>";
          }).join("") + "</div>";
        setTimeout(function () {
          view.querySelectorAll("[data-rep]").forEach(function (b) { b.addEventListener("click", function () { var r = reports[+b.getAttribute("data-rep")]; openDrawer('<h2 id="dtitle">Saved chargeback note</h2>' + stamp(r.status === "verified") + '<div class="note">' + md(r.report_md) + "</div>" + factPack(JSON.parse(r.fact_pack || "[]"))); }); });
        });
        return h;
      });
    },
    ask: function () {
      var h = '<h1>Ask the desk</h1><p class="sub">Plain-English questions answered by a Cortex Agent that writes SQL with Cortex Analyst over the DISPUTE_SV semantic view. Every figure comes from a query you can inspect.</p>' +
        powered("Cortex Agent DISPUTE_AGENT · Cortex Analyst · Semantic View DISPUTE_SV") +
        '<div class="qs">' + QUESTIONS.map(function (q, i) { return '<button type="button" class="q" data-q="' + i + '">' + esc(q) + "</button>"; }).join("") + "</div>" +
        '<div id="chat">' + state.chat.map(function (c) { return msgU(c.q) + msgA(answerHtml(c.a)); }).join("") + "</div>" +
        '<form class="ask" id="askForm"><input id="askIn" placeholder="Sample mode answers the three questions above" aria-label="Ask a question"><button class="btn" type="submit">Ask</button></form><div id="askNote"></div>';
      return Promise.resolve(h);
    }
  };

  function stamp(ok) { return '<div style="margin:.5rem 0 .7rem"><span class="stamp ' + (ok ? "s-ok" : "s-bad") + '">' + (ok ? "Verified" : "Needs review") + "</span></div>"; }
  function factPack(fp) {
    if (!fp.length) return "";
    var cols = Object.keys(fp[0]);
    return "<details><summary>Sources: fact pack (" + fp.length + " rows, cited as F1-F" + fp.length + ')</summary><div class="scroll"><table class="t"><tr>' + cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr>" + fp.map(function (r) { return "<tr>" + cols.map(function (c) { return "<td>" + esc(r[c]) + "</td>"; }).join("") + "</tr>"; }).join("") + "</table></div></details>";
  }
  function flags(v) { return v.edits && v.edits.length ? '<div class="ins i-lost"><b>Verifier flags</b><ul style="margin:.2rem 0 0 1rem;padding:0">' + v.edits.map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("") + "</ul></div>" : ""; }
  function verdictLine(v) { return stamp(v.status === "verified").replace("</div>", '<span style="margin-left:.8rem;font-size:.8rem;color:' + C.muted + '">residual hedges: ' + v.residual_hedges + " · flagged: " + v.edits.length + "</span></div>"); }
  function noteHtml(res) { return '<section class="card">' + SAMPLE_LABEL + '<div class="note" id="noteBody">' + md(res.draft) + "</div>" + verdictLine(res.verdict) + flags(res.verdict) + factPack(res.fact_pack) + "</section>"; }
  function rvHtml(rv) { return SAMPLE_LABEL + '<div class="ins i-lost">Added: <i>' + esc(HEDGE) + "</i></div>" + verdictLine(rv.verdict) + flags(rv.verdict); }
  function msgU(q) { return '<div class="msg u"><div class="who">You</div><div class="body">' + esc(q) + "</div></div>"; }
  function msgA(h) { return '<div class="msg a"><div class="who">AI</div><div class="body">' + h + "</div></div>"; }
  function answerHtml(a) {
    return SAMPLE_LABEL + '<div class="note">' + md(a.text) + "</div>" + (a.tables || []).map(function (t) {
      return '<div class="scroll"><table class="t"><tr>' + t.columns.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr>" + t.rows.map(function (r) { return "<tr>" + r.map(function (x) { return "<td>" + esc(x) + "</td>"; }).join("") + "</tr>"; }).join("") + "</table></div>";
    }).join("") + (a.sql ? "<details><summary>Source: SQL generated by Cortex Analyst over DISPUTE_SV</summary><pre>" + esc(a.sql) + "</pre></details>" : "");
  }

  function reasonDrawer(r, bookWr, byCat) {
    var below = r.win < bookWr - .05, rows = byCat.filter(function (x) { return x.reason_code === r.code; });
    var series = r.months.map(function (m) { return { m: m.month_end, v: m.total_disputes, tip: "<b>" + mlong(m.month_end) + "</b><br>" + m.total_disputes + " disputes<br>Win rate " + pct(m.total_resolved ? m.total_won / m.total_resolved : null) }; });
    openDrawer('<h2 id="dtitle">' + (r.network === "VISA" ? "Visa " : "Mastercard ") + esc(r.code) + " · " + esc(r.name) + "</h2>" +
      '<div class="filters">' + pill(r.cat, "ai") + pill(r.ff ? "Friendly fraud" : "Cardholder claim", r.ff ? "lost" : "open") + pill((below ? "Below" : "At or above") + " book win rate", below ? "lost" : "won") + "</div>" +
      "<p>" + esc(r.desc) + '.</p><p class="cap">Typical root cause: <b>' + esc(r.root) + "</b></p>" +
      '<div class="kpis k4">' + kpi("Disputes", num(r.disputes), "24 months") + kpi("Disputed", usd(r.usd), "USD") + kpi("Win rate", pct(r.win), "book " + pct(bookWr)) + kpi("Lost", usd(r.lost), "status lost") + "</div>" +
      "<h2>Monthly disputes</h2>" + bars(series, CAT[r.cat], "Monthly disputes for reason code " + r.code) +
      '<div class="scroll"><table class="t"><tr><th>Merchant category</th><th class="n">Disputes</th><th class="n">Win rate</th><th class="n">Lost</th></tr>' + rows.map(function (x) { return "<tr><td>" + esc(x.category_name) + '</td><td class="n">' + num(x.total_disputes) + '</td><td class="n">' + pct(x.total_won / x.total_resolved) + '</td><td class="n">' + usd(x.total_lost_usd) + "</td></tr>"; }).join("") + "</table></div>" +
      powered("Semantic View DISPUTE_SV"));
  }
  var STATUS = { open: ["Open", "open"], "pre-arb": ["Pre-arbitration", "prearb"], won: ["Won", "won"], lost: ["Lost", "lost"] };
  function merchantDrawer(m) {
    load("merchant_detail_" + m.id).then(function (d) {
      var by = group(d.monthly, function (r) { return r.month_end; });
      var series = Object.keys(by).sort().map(function (k) { return { m: k, v: sum(by[k], function (r) { return r.disputes; }), tip: "<b>" + mlong(k) + "</b><br>" + by[k].map(function (r) { return r.reason_code + ": " + r.disputes; }).join("<br>") }; });
      openDrawer('<h2 id="dtitle">' + esc(m.name) + "</h2>" + '<div class="filters">' + pill(m.cat, "ai") + pill("MCC " + m.mcc, "open") + pill(m.inflight + " in flight", "prearb") + "</div>" +
        '<div class="kpis k4">' + kpi("Disputes", num(m.disputes), "24 months") + kpi("Win rate", pct(m.win), "won / resolved") + kpi("Lost", usd(m.lost), "USD") + kpi("Hot code", m.hot.code, Math.round(m.hot.share * 100) + "% vs " + Math.round(m.hot.cat * 100) + "% category") + "</div>" +
        "<h2>Monthly disputes</h2>" + bars(series, C.primary, "Monthly disputes for " + m.name) +
        "<h2>Disputes in flight</h2>" + (d.inflight.length ? '<div class="scroll"><table class="t"><tr><th>Dispute</th><th>Reason</th><th>Filed</th><th>Respond by</th><th>Status</th><th class="n">Amount</th></tr>' + d.inflight.map(function (x) {
          return "<tr><td>D-" + String(x.dispute_id).padStart(6, "0") + "</td><td>" + (x.network === "VISA" ? "Visa " : "Mastercard ") + esc(x.reason_code) + "</td><td>" + esc(x.date_filed) + "</td><td>" + esc(x.respond_by) + "</td><td>" + pill(STATUS[x.status][0], STATUS[x.status][1]) + '</td><td class="n">$' + (+x.dispute_amount).toFixed(2) + "</td></tr>";
        }).join("") + '</table></div><p class="cap">Up to 25 by respond-by date (30 days after filing), as of 30 Jun 2026.</p>' : '<div class="empty">No open or pre-arbitration disputes for this merchant.</div>'));
    });
  }

  /* ---------- page wiring ---------- */
  function wire(route) {
    bindTips(view); animateCounts();
    view.querySelectorAll(".fchip").forEach(function (b) {
      b.addEventListener("click", function () {
        var f = route === "reasons" ? state.rFilter : state.mFilter, g = b.getAttribute("data-g"), k = b.getAttribute("data-k");
        if (f[g][k]) delete f[g][k]; else f[g][k] = 1;
        render();
      });
    });
    var s = view.querySelector(".search");
    if (s) s.addEventListener("change", function () { state.rFilter.q = s.value; render(); });
    if (route === "notes") {
      var btn = document.getElementById("runNote");
      btn.addEventListener("click", function () {
        var scope = view.querySelector("input[name=scope]:checked").value, out = document.getElementById("noteOut");
        btn.disabled = true; out.innerHTML = '<section class="card"><div id="stg"></div></section>';
        Promise.all([load("generate_" + scope), load("fact_pack_" + scope)]).then(function (d) {
          var res = d[0];
          return stagedRun(document.getElementById("stg"), ["Reading the dispute book through DISPUTE_SV (24 months, 9,960 disputes)…", "Building the fact pack: " + d[1].length + " rows, the note's only allowed numbers…", "Drafting the note with AI_COMPLETE (claude-sonnet-4-5)…", "Verifying every figure against the fact pack and checking for hedges…", "Saving the note and verdict to DISPUTE_REPORTS…"], jitter(4000, 8000)).then(function () {
            out.innerHTML = '<section class="card">' + SAMPLE_LABEL + '<div class="note" id="noteBody"></div><div id="vd"></div></section>';
            return streamInto(document.getElementById("noteBody"), res.draft, 70);
          }).then(function () {
            document.getElementById("vd").innerHTML = verdictLine(res.verdict) + flags(res.verdict) + factPack(res.fact_pack);
            state.note = { scope: scope, res: res }; state.rv = null; btn.disabled = false;
            var bc = document.getElementById("breakCard"); bc.hidden = false; document.getElementById("rvOut").innerHTML = "";
          });
        }).catch(fail);
      });
      var rb = document.getElementById("runRv");
      if (rb) rb.addEventListener("click", function () {
        if (!state.note) return;
        var out = document.getElementById("rvOut"), scope = state.note.scope; rb.disabled = true;
        out.innerHTML = '<div id="stg2"></div>';
        load("reverify_" + scope).then(function (rv) {
          return stagedRun(document.getElementById("stg2"), ["Re-reading the fact pack…", "Checking each figure in the edited draft…", "Scanning for hedge words…"], jitter(4000, 6000)).then(function () {
            state.rv = { scope: scope, rv: rv }; out.innerHTML = rvHtml(rv); rb.disabled = false;
          });
        }).catch(fail);
      });
    }
    if (route === "ask") {
      function ask(i) {
        var chat = document.getElementById("chat"), q = QUESTIONS[i], wrap = document.createElement("div");
        wrap.innerHTML = msgU(q) + msgA('<div class="stg3"></div><div class="ans"></div>'); chat.appendChild(wrap);
        var stg = wrap.querySelector(".stg3"), ans = wrap.querySelector(".ans");
        wrap.scrollIntoView({ behavior: "smooth", block: "start" });
        load("ask_" + i).then(function (a) {
          return stagedRun(stg, ["Planning with the Cortex Agent…", "Generating SQL with Cortex Analyst over DISPUTE_SV…", "Running the query on SNOWPACK_DISPUTE_INTEL_WH…", "Writing the answer from the result set…"], jitter(5000, 8000)).then(function () {
            stg.innerHTML = ""; ans.innerHTML = SAMPLE_LABEL + '<div class="note"></div>';
            return streamInto(ans.querySelector(".note"), a.text, 80).then(function () { ans.innerHTML = answerHtml(a); state.chat.push({ q: q, a: a }); });
          });
        }).catch(fail);
      }
      view.querySelectorAll("[data-q]").forEach(function (b) { b.addEventListener("click", function () { ask(+b.getAttribute("data-q")); }); });
      document.getElementById("askForm").addEventListener("submit", function (e) {
        e.preventDefault(); var v = document.getElementById("askIn").value.trim(), i = QUESTIONS.indexOf(v);
        if (i >= 0) ask(i); else document.getElementById("askNote").innerHTML = '<div class="callout">Sample mode replays captured answers to the three sample questions. Run the app in Live mode to ask your own.</div>';
      });
    }
  }
  function fail(e) { view.innerHTML = '<div class="empty"><b>Could not load sample data.</b><br>' + esc(e.message) + "</div>"; }
  function render() {
    var route = (location.hash.replace(/^#\//, "") || "overview").split("?")[0];
    if (!screens[route]) route = "overview";
    document.querySelectorAll(".tabs a").forEach(function (a) { if (a.getAttribute("data-r") === route) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    document.title = document.querySelector('.tabs a[data-r="' + route + '"]').textContent + " · Chargeback & Dispute Intelligence (sample)";
    view.innerHTML = '<div class="card" style="height:120px;background:linear-gradient(90deg,#E3E9EA 25%,#F2F5F5 37%,#E3E9EA 63%);background-size:400% 100%"></div>';
    screens[route]().then(function (h) { view.innerHTML = h; wire(route); }).catch(fail);
  }
  document.getElementById("goLive").addEventListener("click", function () {
    view.insertAdjacentHTML("afterbegin", '<div class="callout"><b>Live mode runs in your Snowflake account.</b> This hosted example is always Sample mode. To see live inference, run <code>sql/setup.sql</code>, then deploy the Streamlit app or run it locally with key-pair auth. See <a href="https://github.com/sfc-gh-jsoliz/sfguide-dispute-intelligence#run-it-live">the repository guide</a>.</div>');
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  addEventListener("hashchange", function () { hideTip(); render(); });
  render();
})();
