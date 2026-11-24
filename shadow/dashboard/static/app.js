/* SHADOW dashboard — live WS + self-registration */

const $ = (id) => document.getElementById(id);

let state = null;
let ws = null;
let regDismissed = sessionStorage.getItem("shadow_reg_skip") === "1";

function fmt(n, d = 5) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(d);
}

function money(n) {
  if (n == null) return "—";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    state = JSON.parse(ev.data);
    render(state);
  };
  ws.onclose = () => setTimeout(connect, 1500);
}

function setPill(el, text, cls) {
  el.textContent = text;
  el.className = `pill ${cls}`;
}

function showRegOverlay(show) {
  const el = $("regOverlay");
  if (!el) return;
  if (show) el.removeAttribute("hidden");
  else el.setAttribute("hidden", "");
}

function updateRegistrationUI(s) {
  const reg = s.registration || {};
  const registered = !!reg.registered;
  const connected = !!s.connected && !s.paper;

  $("regBadge").textContent = connected
    ? "Pieslēgts"
    : registered
      ? "Reģistrēts · nav savienots"
      : "Nav reģistrēts";
  $("regConnected").textContent = connected ? "LIVE/DEMO API" : s.paper ? "PAPER" : "OFF";
  $("regIdent").textContent = reg.identifier_masked || "—";
  $("regKey").textContent = reg.api_key_masked || "—";
  $("regEnv").textContent = (reg.connected_env || "demo").toUpperCase();

  // Auto-open registration if not registered and user hasn't skipped this session
  if (!registered && !regDismissed && !connected) {
    showRegOverlay(true);
  } else if (connected) {
    showRegOverlay(false);
  }
}

function render(s) {
  $("epic").textContent = s.epic || "EURUSD";
  $("price").textContent = fmt(s.last_price);
  $("bid").textContent = fmt(s.bid);
  $("ask").textContent = fmt(s.ask);
  $("spread").textContent = fmt(s.spread, 5);
  $("regime").textContent = s.regime || "—";
  $("structure").textContent = s.structure || "—";
  $("confluence").textContent = fmt(s.confluence, 3);
  $("message").textContent = s.message || "";
  $("barCount").textContent = `${(s.candles || []).length} bars`;

  const sig = s.signal || "HOLD";
  const sigEl = $("signal");
  sigEl.textContent = sig;
  sigEl.className = `signal ${sig}`;

  const mode = s.mode || "idle";
  if (mode === "waiting_handover") setPill($("modePill"), "WAITING HANDOVER", "wait");
  else if (mode === "paper") setPill($("modePill"), "PAPER ACTIVE", "paper");
  else if (mode === "active") setPill($("modePill"), "LIVE ACTIVE", "active");
  else setPill($("modePill"), mode.toUpperCase(), "dim");

  setPill(
    $("connPill"),
    s.connected ? "API CONNECTED" : s.paper ? "PAPER" : "OFFLINE",
    s.connected ? "active" : "dim"
  );
  setPill($("sessionPill"), (s.session || "off").toUpperCase(), s.session === "off" ? "dim" : "active");

  $("bal").textContent = money(s.account_balance);
  $("avail").textContent = money(s.account_available);
  $("pnl").textContent = money(s.account_pnl);
  $("winrate").textContent = s.stats?.winrate != null ? `${s.stats.winrate}%` : "—";
  $("net").textContent = money(s.stats?.net_pnl);
  $("openN").textContent = String(s.stats?.open ?? (s.open_positions || []).length);

  updateRegistrationUI(s);

  const gates = s.last_decision?.gates || [];
  $("gates").innerHTML = gates
    .map(
      (g) =>
        `<li class="${g.ok ? "ok" : "bad"}"><span><i class="dot ${g.ok ? "ok" : "bad"}"></i>${g.gate}</span><span class="mono muted">${g.detail || (g.ok ? "pass" : "fail")}</span></li>`
    )
    .join("");
  $("reasons").textContent = (s.last_decision?.reasons || []).join(" · ");

  const b = s.last_decision?.brackets;
  if (b) {
    $("brackets").className = "brackets";
    $("brackets").innerHTML = `
      <div class="row"><span>Direction</span><span>${b.direction}</span></div>
      <div class="row"><span>Entry</span><span>${fmt(b.entry)}</span></div>
      <div class="row"><span>SL</span><span>${fmt(b.sl)}</span></div>
      <div class="row"><span>TP</span><span>${fmt(b.tp)}</span></div>
      <div class="row"><span>R:R</span><span>${fmt(b.rr, 2)}</span></div>
      <div class="logic">${b.logic || ""}</div>`;
  } else {
    $("brackets").className = "brackets empty";
    $("brackets").textContent = "Nav aktīva setup";
  }

  const rows = (s.open_positions || [])
    .map((item) => {
      const p = item.position || item;
      return `<tr>
        <td class="mono">${p.dealId || "—"}</td>
        <td class="${p.direction || ""}">${p.direction || "—"}</td>
        <td class="mono">${fmt(p.level)}</td>
        <td class="mono">${p.size ?? "—"}</td>
        <td class="mono">${fmt(p.upl, 2)}</td>
        <td class="mono">${fmt(p.stopLevel)}</td>
        <td class="mono">${fmt(p.profitLevel)}</td>
      </tr>`;
    })
    .join("");
  $("positions").innerHTML = rows || `<tr><td colspan="7" class="muted">Nav atvērtu pozīciju</td></tr>`;

  $("zones").innerHTML =
    (s.zones || [])
      .slice(0, 8)
      .map(
        (z) => `<div class="zone ${z.kind}">
        <strong>${z.kind}</strong>
        <span class="mono">${fmt(z.bottom)} – ${fmt(z.top)}</span>
        <span class="mono">Q ${fmt(z.quality, 2)} · T${z.touches}</span>
      </div>`
      )
      .join("") || `<div class="muted">Nav zonu</div>`;

  const ind = s.indicators || {};
  $("indicators").innerHTML = [
    ["ATR", fmt(ind.atr)],
    ["RSI", fmt(ind.rsi, 1)],
    ["EMA9", fmt(ind.ema_fast)],
    ["EMA21", fmt(ind.ema_slow)],
    ["EMA50", fmt(ind.ema_trend)],
    ["News", s.news_risk || "ok"],
  ]
    .map(([k, v]) => `<div><span>${k}</span><b class="mono">${v}</b></div>`)
    .join("");

  const dec = (s.decisions || []).slice(-12).reverse();
  const trades = (s.trades || []).slice(-8).reverse();
  $("log").innerHTML =
    trades
      .map(
        (t) =>
          `<div>TRADE ${t.signal} @ ${fmt(t.brackets?.entry)} · ${t.regime} · conf ${fmt(t.confluence, 2)}</div>`
      )
      .join("") +
    dec
      .map(
        (d) =>
          `<div>${(d.ts || "").slice(11, 19)} ${d.signal} · ${d.regime} · ${fmt(d.confluence, 2)} · ${(d.reasons || []).slice(0, 3).join(",")}</div>`
      )
      .join("");

  $("handoverAt").textContent = s.handover_detected_at ? `Handover: ${s.handover_detected_at}` : "";

  drawChart(s);
}

function drawChart(s) {
  const canvas = $("chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 900;
  const cssH = 340;
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const candles = s.candles || [];
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.fillStyle = "#0a110e";
  ctx.fillRect(0, 0, cssW, cssH);

  if (candles.length < 2) {
    ctx.fillStyle = "#7f958c";
    ctx.font = "13px IBM Plex Sans";
    ctx.fillText("Gaida sveces…", 16, 28);
    return;
  }

  const padL = 8,
    padR = 56,
    padT = 12,
    padB = 18;
  const w = cssW - padL - padR;
  const h = cssH - padT - padB;
  const slice = candles.slice(-90);
  let lo = Math.min(...slice.map((c) => c.l));
  let hi = Math.max(...slice.map((c) => c.h));
  for (const z of s.zones || []) {
    lo = Math.min(lo, z.bottom);
    hi = Math.max(hi, z.top);
  }
  const span = Math.max(hi - lo, 1e-6);

  const xAt = (i) => padL + (i / (slice.length - 1)) * w;
  const yAt = (p) => padT + (1 - (p - lo) / span) * h;

  for (const z of s.zones || []) {
    const y1 = yAt(z.top);
    const y2 = yAt(z.bottom);
    ctx.fillStyle = z.kind === "demand" ? "rgba(62,207,142,0.12)" : "rgba(239,107,107,0.12)";
    ctx.fillRect(padL, Math.min(y1, y2), w, Math.abs(y2 - y1) || 2);
    ctx.strokeStyle = z.kind === "demand" ? "rgba(62,207,142,0.45)" : "rgba(239,107,107,0.45)";
    ctx.beginPath();
    ctx.moveTo(padL, y1);
    ctx.lineTo(padL + w, y1);
    ctx.moveTo(padL, y2);
    ctx.lineTo(padL + w, y2);
    ctx.stroke();
  }

  const cw = Math.max(2, (w / slice.length) * 0.65);
  slice.forEach((c, i) => {
    const x = xAt(i);
    const bull = c.c >= c.o;
    ctx.strokeStyle = bull ? "#3ecf8e" : "#ef6b6b";
    ctx.fillStyle = bull ? "#3ecf8e" : "#ef6b6b";
    ctx.beginPath();
    ctx.moveTo(x, yAt(c.h));
    ctx.lineTo(x, yAt(c.l));
    ctx.stroke();
    const yO = yAt(c.o);
    const yC = yAt(c.c);
    const top = Math.min(yO, yC);
    const bh = Math.max(1, Math.abs(yC - yO));
    ctx.fillRect(x - cw / 2, top, cw, bh);
  });

  if (s.last_price != null) {
    const y = yAt(s.last_price);
    ctx.strokeStyle = "rgba(232,184,74,0.7)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(padL, y);
    ctx.lineTo(padL + w, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "#e8b84a";
    ctx.font = "11px IBM Plex Mono";
    ctx.fillText(fmt(s.last_price), padL + w + 6, y + 4);
  }

  const br = s.last_decision?.brackets;
  if (br) {
    ctx.font = "10px IBM Plex Mono";
    [
      [br.sl, "#ef6b6b", "SL"],
      [br.tp, "#3ecf8e", "TP"],
    ].forEach(([p, col, lab]) => {
      if (p == null) return;
      const y = yAt(p);
      ctx.strokeStyle = col;
      ctx.globalAlpha = 0.7;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + w, y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = col;
      ctx.fillText(lab, padL + 4, y - 3);
    });
  }
}

async function post(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

function formPayload(form) {
  const fd = new FormData(form);
  return {
    api_key: String(fd.get("api_key") || "").trim(),
    identifier: String(fd.get("identifier") || "").trim(),
    password: String(fd.get("password") || "").trim(),
    env: fd.get("env") || "demo",
    epic: fd.get("epic") || "EURUSD",
    size: Number(fd.get("size") || 1000),
    persist: true,
  };
}

async function submitRegistration(form, statusEl) {
  const payload = formPayload(form);
  if (statusEl) statusEl.textContent = "Reģistrēju un pieslēdzos Capital.com…";
  $("message").textContent = "Reģistrēju un pieslēdzos Capital.com…";
  const res = await post("/api/register", payload);
  const msg =
    res.message ||
    (res.ok ? "Reģistrācija OK — pieslēgts." : res.error || "Reģistrācija neizdevās");
  if (statusEl) statusEl.textContent = msg;
  $("message").textContent = msg;
  $("credsHint").textContent = res.ok
    ? "Reģistrācija saglabāta .env. Atver pirmo treidu Capital.com app — robots pārņems."
    : msg + (res.error ? ` (${res.error})` : "");
  if (res.ok) {
    regDismissed = true;
    sessionStorage.setItem("shadow_reg_skip", "1");
    showRegOverlay(false);
  }
  return res;
}

$("btnHandoverBuy").onclick = async () => {
  $("message").textContent = "Simulē handover BUY…";
  const res = await post("/api/handover/simulate", { direction: "BUY" });
  if (!res.ok) $("message").textContent = res.message || res.error || "Handover jau aktīvs";
};
$("btnHandoverSell").onclick = async () => {
  $("message").textContent = "Simulē handover SELL…";
  const res = await post("/api/handover/simulate", { direction: "SELL" });
  if (!res.ok) $("message").textContent = res.message || res.error || "Handover jau aktīvs";
};
$("btnHandoverReset").onclick = async () => {
  $("message").textContent = "Reset handover…";
  await post("/api/handover/reset", {});
};

$("credsForm").onsubmit = async (e) => {
  e.preventDefault();
  await submitRegistration(e.target, $("credsHint"));
};

$("regForm").onsubmit = async (e) => {
  e.preventDefault();
  const btn = $("regSubmit");
  btn.disabled = true;
  try {
    await submitRegistration(e.target, $("regStatus"));
  } finally {
    btn.disabled = false;
  }
};

$("regSkip").onclick = () => {
  regDismissed = true;
  sessionStorage.setItem("shadow_reg_skip", "1");
  showRegOverlay(false);
  $("message").textContent = "Paper režīms — vari reģistrēties jebkurā laikā ar pogu «Reģistrācija».";
};

$("btnOpenReg").onclick = () => {
  regDismissed = false;
  showRegOverlay(true);
};

document.querySelectorAll("[data-news]").forEach((btn) => {
  btn.onclick = () => post("/api/news", { risk: btn.dataset.news });
});

function tickClock() {
  const now = new Date();
  $("clock").textContent = now.toISOString().slice(11, 19) + " UTC";
}
setInterval(tickClock, 1000);
tickClock();
connect();

setInterval(async () => {
  if (ws && ws.readyState === 1) return;
  try {
    const r = await fetch("/api/state");
    state = await r.json();
    render(state);
  } catch (_) {}
}, 2000);

window.addEventListener("resize", () => state && drawChart(state));
