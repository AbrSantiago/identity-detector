/* detector.js — lógica del frontend del detector.
 *
 * Secuencia: aceptar aviso -> recolectar fingerprint (tracker/fp.js, el mismo
 * script que usa el chat) -> POST /api/identify -> mostrar match + explicación.
 * En paralelo mantiene el historial de consultas en vivo (GET + WS /ws/matches).
 *
 * Todo texto que viene del servidor (nicknames, valores) entra con textContent,
 * nunca con innerHTML: un nickname hostil no puede inyectar HTML.
 */
(function () {
  "use strict";

  const API = window.IDENTITY_CONFIG.apiBase;
  const WS_URL = API.replace(/^http/, "ws") + "/ws/matches";
  const HISTORY_HOURS = 6;
  const HISTORY_MAX = 50;

  const $ = (id) => document.getElementById(id);
  const el = {
    consent: $("consent"), accept: $("accept"), app: $("app"),
    verdict: $("verdict"), scores: $("scores"), top3: $("top3"),
    explainCard: $("explain-card"), breakdown: $("breakdown").tBodies[0],
    knownCard: $("known-card"), known: $("known"),
    history: $("history"), liveDot: $("live-dot"), liveText: $("live-text"),
  };

  const LEVEL_LABEL = { browser: "navegador", device: "dispositivo" };
  const ATTR_LABEL = {
    canvas: "Canvas", audio: "Audio", user_agent: "User-Agent", plugins: "Plugins",
    voices: "Voces de síntesis", do_not_track: "Do Not Track",
    webgl_renderer: "GPU (renderer)", webgl_vendor: "GPU (vendor)", fonts: "Fuentes",
    screen: "Pantalla", cores: "Núcleos", memory: "Memoria", touch: "Touch",
    timezone: "Zona horaria", languages: "Idiomas", platform: "Plataforma",
    media_queries: "Preferencias (tema, puntero…)", ip: "IP / red",
    webrtc_public: "IP pública (WebRTC)",
  };

  const pct = (x) => Math.round((x || 0) * 100) + "%";

  function node(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }

  // --- Arranque ---
  el.accept.addEventListener("click", async () => {
    el.consent.hidden = true;
    el.app.hidden = false;
    startHistory();
    await runIdentify();
  });

  async function runIdentify() {
    let fp;
    try {
      fp = await window.IdentityTracker.collect();
    } catch (_e) {
      el.verdict.replaceChildren(node("p", "muted", "No se pudo medir tu navegador."));
      return;
    }
    el.verdict.replaceChildren(node("p", "muted", "Comparando con las identidades del chat…"));
    try {
      const r = await fetch(API + "/api/identify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fp),
      });
      if (!r.ok) throw new Error("HTTP " + r.status);
      renderResult(await r.json());
    } catch (_e) {
      el.verdict.replaceChildren(node("p", "muted", "No se pudo contactar al backend."));
    }
  }

  // --- Resultado ---
  function renderResult(res) {
    // Veredicto
    const v = node("div");
    if (res.recognized && res.best) {
      v.append(
        node("div", "big-avatar", res.best.avatar),
        node("p", "who-label", "Te reconocemos como"),
        node("p", "who-name", res.best.nickname),
        node("p", "muted", "Coincidencia " + pct(res.best.combined_score) +
          " (umbral " + pct(res.threshold) + ")")
      );
    } else {
      v.append(
        node("p", "who-name", "No te reconocemos"),
        node("p", "muted", res.top.length
          ? "Ninguna identidad supera el umbral de " + pct(res.threshold) + "."
          : "Todavía no hay identidades registradas en el chat.")
      );
    }
    el.verdict.replaceChildren(v);

    // Puntajes por nivel (de la mejor candidata, aunque no supere el umbral)
    const lead = res.best || res.top[0];
    el.scores.replaceChildren();
    el.scores.hidden = !lead;
    if (lead) {
      el.scores.append(
        scoreBar("Navegador", lead.browser_score, "canvas, audio, UA"),
        scoreBar("Dispositivo", lead.device_score, "GPU, pantalla, fuentes, zona, IP")
      );
    }

    // Top 3
    el.top3.replaceChildren();
    el.top3.hidden = res.top.length === 0;
    if (res.top.length) {
      el.top3.append(node("h3", null, "Candidatas más parecidas"));
      res.top.forEach((c) => {
        const row = node("div", "cand");
        row.append(node("span", "cand-av", c.avatar), node("span", "cand-nick", c.nickname),
          node("span", "cand-score", pct(c.combined_score)));
        el.top3.append(row);
      });
    }

    // Explicación
    el.breakdown.replaceChildren();
    el.explainCard.hidden = res.breakdown.length === 0;
    res.breakdown.forEach((r) => {
      const tr = document.createElement("tr");
      tr.className = r.matched ? "hit" : "miss";
      tr.append(
        node("td", null, ATTR_LABEL[r.attribute] || r.attribute),
        node("td", null, LEVEL_LABEL[r.level] || r.level),
        node("td", null, r.matched ? "sí" : "no"),
        node("td", "num", r.bits.toFixed(1)),
        node("td", "muted", r.detail || "")
      );
      el.breakdown.append(tr);
    });

    renderKnown(res.observed_network, res.observed_fingerprint);
  }

  function scoreBar(label, value, hint) {
    const wrap = node("div", "score");
    const head = node("div", "score-head");
    head.append(node("span", null, label), node("span", "num", pct(value)));
    const bar = node("div", "bar");
    const fill = node("div", "fill");
    fill.style.width = pct(value);
    bar.append(fill);
    wrap.append(head, bar, node("div", "muted small-text", hint));
    return wrap;
  }

  // --- "Esto sabemos de vos" ---
  function renderKnown(net, fp) {
    const rows = [
      ["IP (vista por el servidor)", net.ip],
      ["Red", net.ip_network],
      ["User-Agent", net.user_agent],
      ["Accept-Language", net.accept_language],
      ["Client hints", [net.sec_ch_ua, net.sec_ch_ua_platform].filter(Boolean).join(" · ")],
      ["Canvas", fp.canvas_hash],
      ["GPU", [fp.webgl_vendor, fp.webgl_renderer].filter(Boolean).join(" / ")],
      ["Audio", fp.audio_hash],
      ["Fuentes detectadas", fp.fonts ? fp.fonts.length + " (" + fp.fonts.slice(0, 6).join(", ") + (fp.fonts.length > 6 ? "…" : "") + ")" : null],
      ["Pantalla", fp.screen_width ? fp.screen_width + "×" + fp.screen_height + " @" + fp.device_pixel_ratio + "x" : null],
      ["Núcleos / memoria", [fp.hardware_concurrency, fp.device_memory && fp.device_memory + " GB"].filter(Boolean).join(" / ")],
      ["Zona horaria", fp.timezone],
      ["Idiomas", fp.languages && fp.languages.join(", ")],
      ["IP pública por WebRTC", fp.webrtc_public_ips && fp.webrtc_public_ips.join(", ")],
    ];
    el.known.replaceChildren();
    rows.forEach(([k, val]) => {
      const row = node("div", "kv");
      // Un dato ausente (null) también es información: se muestra como tal.
      row.append(node("span", "k", k), node("span", val ? "v" : "v nul", val || "no disponible"));
      el.known.append(row);
    });
    el.knownCard.hidden = false;
  }

  // --- Historial en vivo ---
  const seen = [];

  async function startHistory() {
    try {
      const r = await fetch(API + "/api/matches?hours=" + HISTORY_HOURS);
      if (r.ok) {
        const events = await r.json(); // más nuevo primero
        seen.push(...events);
        renderHistory();
      }
    } catch (_e) { /* el WS igual puede funcionar */ }
    connectWs();
  }

  function connectWs() {
    const ws = new WebSocket(WS_URL);
    ws.addEventListener("open", () => setLive(true));
    ws.addEventListener("message", (ev) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.type === "match") {
          seen.unshift(m);
          if (seen.length > HISTORY_MAX) seen.length = HISTORY_MAX;
          renderHistory();
        }
      } catch (_e) { /* mensaje ajeno */ }
    });
    ws.addEventListener("close", () => {
      setLive(false);
      setTimeout(connectWs, 3000); // reintento simple
    });
  }

  function setLive(on) {
    el.liveDot.className = "dot" + (on ? " on" : "");
    el.liveText.textContent = on ? "en vivo" : "reconectando…";
  }

  function renderHistory() {
    el.history.replaceChildren();
    if (!seen.length) {
      el.history.append(node("li", "muted", "Sin consultas todavía."));
      return;
    }
    seen.slice(0, HISTORY_MAX).forEach((e) => {
      const li = node("li", "h-row");
      const when = new Date(e.at).toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      li.append(
        node("span", "h-time", when),
        node("span", "h-who", e.recognized ? (e.best_avatar || "") + " " + e.best_nickname : "no reconocido"),
        node("span", "h-score", pct(e.combined_score)),
        node("span", "h-net muted", e.visitor_ip_network || "")
      );
      if (!e.recognized) li.classList.add("none");
      el.history.append(li);
    });
  }
})();
