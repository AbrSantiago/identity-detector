/* chat.js — lógica del frontend del chat.
 *
 * Secuencia: aceptar aviso -> elegir nickname/avatar -> recolectar fingerprint
 * (tracker/fp.js, cargado desde el backend) -> abrir WebSocket y mandar hello.
 */
(function () {
  "use strict";

  const API = window.IDENTITY_CONFIG.apiBase;
  const WS_URL = API.replace(/^http/, "ws") + "/ws/chat";

  const AVATARS = ["🦊", "🐢", "🦉", "🐙", "🦔", "🐳", "🦎", "🐝", "🦇", "🦜"];

  const el = {
    consent: document.getElementById("consent"),
    accept: document.getElementById("accept"),
    join: document.getElementById("join"),
    joinForm: document.getElementById("join-form"),
    nickname: document.getElementById("nickname"),
    avatars: document.getElementById("avatars"),
    joinStatus: document.getElementById("join-status"),
    chat: document.getElementById("chat"),
    mePill: document.getElementById("me-pill"),
    messages: document.getElementById("messages"),
    sayForm: document.getElementById("say-form"),
    say: document.getElementById("say"),
    forget: document.getElementById("forget"),
  };

  const state = {
    nickname: null,
    avatar: AVATARS[0],
    fpId: null,
    ws: null,
  };

  function show(screen) {
    for (const s of [el.consent, el.join, el.chat]) s.hidden = s !== screen;
  }

  // --- Avatares ---
  AVATARS.forEach((a, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = a;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", i === 0 ? "true" : "false");
    b.addEventListener("click", () => {
      state.avatar = a;
      el.avatars.querySelectorAll("button").forEach((x) =>
        x.setAttribute("aria-checked", x === b ? "true" : "false")
      );
    });
    el.avatars.appendChild(b);
  });

  // --- Consentimiento ---
  el.accept.addEventListener("click", () => show(el.join));

  // --- Join: recolectar fingerprint y conectar ---
  el.joinForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nick = el.nickname.value.trim();
    if (!nick) return;
    state.nickname = nick;
    el.joinStatus.textContent = "Midiendo tu navegador…";

    let fp;
    try {
      fp = await window.IdentityTracker.collect();
      state.fpId = fp.fp_id;
    } catch (err) {
      el.joinStatus.textContent = "No se pudo recolectar el fingerprint.";
      return;
    }
    connect(fp);
  });

  function connect(fp) {
    el.joinStatus.textContent = "Conectando…";
    const ws = new WebSocket(WS_URL);
    state.ws = ws;

    ws.addEventListener("open", () => {
      ws.send(
        JSON.stringify({
          type: "hello",
          nickname: state.nickname,
          avatar: state.avatar,
          fingerprint: fp,
        })
      );
      el.mePill.textContent = state.avatar + " " + state.nickname;
      show(el.chat);
      el.say.focus();
    });

    ws.addEventListener("message", (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch (_e) {
        return;
      }
      if (data.type === "history") {
        data.messages.forEach(renderMessage);
      } else if (data.type === "msg") {
        renderMessage(data);
      } else if (data.type === "system") {
        renderSystem(data.text);
      } else if (data.type === "error") {
        renderSystem("Error: " + data.text);
      }
      scrollDown();
    });

    ws.addEventListener("close", () => renderSystem("Te desconectaste de la sala."));
    ws.addEventListener("error", () => {
      el.joinStatus.textContent = "No se pudo conectar al chat.";
    });
  }

  // --- Render ---
  function renderMessage(m) {
    const li = document.createElement("li");
    li.className = "msg" + (m.nickname === state.nickname ? " mine" : "");
    const av = document.createElement("div");
    av.className = "av";
    av.textContent = m.avatar || "🙂";
    const body = document.createElement("div");
    body.className = "body";
    const who = document.createElement("div");
    who.className = "who";
    who.textContent = m.nickname;
    const text = document.createElement("div");
    text.className = "text";
    text.textContent = m.text;
    body.append(who, text);
    li.append(av, body);
    el.messages.appendChild(li);
  }

  function renderSystem(text) {
    const li = document.createElement("li");
    li.className = "sys";
    li.textContent = text;
    el.messages.appendChild(li);
  }

  function scrollDown() {
    el.messages.scrollTop = el.messages.scrollHeight;
  }

  // --- Enviar mensaje ---
  el.sayForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = el.say.value.trim();
    if (!text || !state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ type: "msg", text }));
    el.say.value = "";
  });

  // --- Borrar mis datos (se completa en la fase 6) ---
  el.forget.addEventListener("click", async () => {
    if (!state.fpId) return;
    if (!confirm("¿Borrar del servidor todos los datos de este navegador?")) return;
    try {
      const r = await fetch(API + "/api/me", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fp_id: state.fpId }),
      });
      if (r.ok) {
        const data = await r.json();
        renderSystem("Datos borrados (" + (data.removed ?? 0) + " identidades).");
      } else {
        renderSystem("El borrado todavía no está disponible (fase 6).");
      }
    } catch (_e) {
      renderSystem("No se pudo contactar al backend para borrar.");
    }
  });
})();
