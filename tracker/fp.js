/* tracker/fp.js — el "script tracker" compartido.
 *
 * Este es el corazón conceptual de la demo: un ÚNICO script de terceros,
 * servido por el backend (GET /tracker/fp.js) e incluido tanto en el chat
 * como en el detector con <script src="https://<api>/tracker/fp.js">.
 * El mismo tercero presente en dos sitios distintos es el mismo observador.
 *
 * Diseño:
 *   - Cada colector está aislado en su propia función, con timeout y try/catch.
 *     Si una API no existe o está bloqueada (Brave, uBlock, resistFingerprinting),
 *     el campo queda en null. Y un null también es información: "este navegador
 *     esconde X" es, en sí mismo, una señal.
 *   - collect() corre todos los colectores en paralelo y arma un objeto cuyos
 *     nombres de campo coinciden con el modelo Fingerprint del backend (Pydantic).
 *   - fp_id es un hash estable derivado de los componentes NO volátiles. No
 *     incluye la IP de WebRTC (cambia de red) para que la misma instalación de
 *     navegador produzca el mismo fp_id en el chat y en el detector.
 *
 * Sin librerías externas: todo el fingerprinting es propio (requisito del TP).
 */
(function (global) {
  "use strict";

  const VERSION = "2.0";

  // --- utilidades -----------------------------------------------------------

  // Corre fn (sync o async) con un tope de tiempo. Ante error o timeout: null.
  // Que un colector cuelgue (p. ej. WebRTC sin respuesta) no debe frenar al resto.
  function safe(fn, ms) {
    ms = ms || 1500;
    return new Promise((resolve) => {
      let done = false;
      const finish = (v) => {
        if (!done) {
          done = true;
          resolve(v);
        }
      };
      const timer = setTimeout(() => finish(null), ms);
      Promise.resolve()
        .then(fn)
        .then((v) => {
          clearTimeout(timer);
          finish(v === undefined ? null : v);
        })
        .catch(() => {
          clearTimeout(timer);
          finish(null);
        });
    });
  }

  // Hash hex. Preferimos SHA-256 (crypto.subtle); si no hay contexto seguro,
  // caemos a un hash propio de 53 bits (suficiente para una huella estable).
  async function hashHex(str) {
    try {
      if (global.crypto && global.crypto.subtle) {
        const data = new TextEncoder().encode(str);
        const buf = await global.crypto.subtle.digest("SHA-256", data);
        return Array.from(new Uint8Array(buf))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
      }
    } catch (_e) {
      /* cae al fallback */
    }
    // Fallback determinístico (variación de cyrb53).
    let h1 = 0xdeadbeef ^ 0,
      h2 = 0x41c6ce57 ^ 0;
    for (let i = 0; i < str.length; i++) {
      const ch = str.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    const n = 4294967296 * (2097151 & h2) + (h1 >>> 0);
    return n.toString(16).padStart(14, "0");
  }

  // --- colectores -----------------------------------------------------------

  // Canvas: dibujamos texto y formas y leemos los píxeles. Pequeñas diferencias
  // de GPU, drivers y antialiasing dan una huella bastante estable por equipo.
  async function canvas() {
    const cv = document.createElement("canvas");
    cv.width = 240;
    cv.height = 60;
    const ctx = cv.getContext("2d");
    if (!ctx) return null;
    ctx.textBaseline = "top";
    ctx.font = "16px 'Arial'";
    ctx.fillStyle = "#f60";
    ctx.fillRect(10, 10, 100, 30);
    ctx.fillStyle = "#069";
    ctx.fillText("Identity 🎭 détector", 12, 14);
    ctx.strokeStyle = "rgba(0,120,200,0.8)";
    ctx.beginPath();
    ctx.arc(80, 30, 20, 0, Math.PI * 2);
    ctx.stroke();
    return await hashHex(cv.toDataURL());
  }

  // WebGL: vendor/renderer "unmasked" (el modelo real de GPU) más algunos
  // parámetros del contexto. El renderer suele ser muy distintivo.
  function webgl() {
    const cv = document.createElement("canvas");
    const gl = cv.getContext("webgl") || cv.getContext("experimental-webgl");
    if (!gl) return { webgl_vendor: null, webgl_renderer: null, webgl_params: null };
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    const vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null;
    const renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null;
    const params = {
      version: gl.getParameter(gl.VERSION),
      shading: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
      max_texture_size: gl.getParameter(gl.MAX_TEXTURE_SIZE),
      max_viewport: gl.getParameter(gl.MAX_VIEWPORT_DIMS),
      max_vertex_attribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS),
      aliased_line: gl.getParameter(gl.ALIASED_LINE_WIDTH_RANGE),
      extensions_count: (gl.getSupportedExtensions() || []).length,
    };
    return { webgl_vendor: vendor, webgl_renderer: renderer, webgl_params: params };
  }

  // Audio: renderizamos una señal con un compresor en un OfflineAudioContext.
  // La suma de la salida varía sutilmente según la implementación de audio.
  async function audio() {
    const AC = global.OfflineAudioContext || global.webkitOfflineAudioContext;
    if (!AC) return null;
    const ctx = new AC(1, 44100, 44100);
    const osc = ctx.createOscillator();
    osc.type = "triangle";
    osc.frequency.value = 10000;
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -50;
    comp.knee.value = 40;
    comp.ratio.value = 12;
    comp.attack.value = 0;
    comp.release.value = 0.25;
    osc.connect(comp);
    comp.connect(ctx.destination);
    osc.start(0);
    const buffer = await ctx.startRendering();
    const data = buffer.getChannelData(0);
    let acc = 0;
    for (let i = 4500; i < 5000; i++) acc += Math.abs(data[i]);
    return await hashHex(acc.toString());
  }

  // Fuentes: medimos el ancho de un texto con fuentes de respaldo conocidas y
  // vemos cuáles candidatas cambian ese ancho (están instaladas).
  function fonts() {
    const base = ["monospace", "sans-serif", "serif"];
    const candidates = [
      "Arial", "Arial Black", "Calibri", "Cambria", "Comic Sans MS", "Consolas",
      "Courier New", "Georgia", "Helvetica", "Impact", "Lucida Console",
      "Segoe UI", "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
      "Roboto", "Ubuntu", "DejaVu Sans", "Liberation Sans", "Noto Sans",
      "Menlo", "Monaco", "SF Pro", "Cantarell", "Fira Sans",
    ];
    const text = "mmmmmmmmmmlli WWWW 0123456789";
    const size = "72px";
    const span = document.createElement("span");
    span.style.cssText =
      "position:absolute;left:-9999px;top:-9999px;visibility:hidden;font-size:" + size + ";";
    span.textContent = text;
    document.body.appendChild(span);

    const baseline = {};
    for (const b of base) {
      span.style.fontFamily = b;
      baseline[b] = { w: span.offsetWidth, h: span.offsetHeight };
    }
    const detected = [];
    for (const font of candidates) {
      let matched = false;
      for (const b of base) {
        span.style.fontFamily = "'" + font + "'," + b;
        if (span.offsetWidth !== baseline[b].w || span.offsetHeight !== baseline[b].h) {
          matched = true;
          break;
        }
      }
      if (matched) detected.push(font);
    }
    document.body.removeChild(span);
    return detected;
  }

  // Pantalla y hardware básico.
  function hardware() {
    const touch =
      (navigator.maxTouchPoints || 0) > 0 ||
      "ontouchstart" in global ||
      (navigator.msMaxTouchPoints || 0) > 0;
    return {
      screen_width: screen.width,
      screen_height: screen.height,
      device_pixel_ratio: global.devicePixelRatio || null,
      color_depth: screen.colorDepth || null,
      hardware_concurrency: navigator.hardwareConcurrency || null,
      device_memory: navigator.deviceMemory || null,
      touch_support: touch,
    };
  }

  // Localización: zona horaria, idiomas y "quirks" de formato de Intl.
  function localization() {
    const intl = {};
    try {
      const dtf = new Intl.DateTimeFormat();
      const ro = dtf.resolvedOptions();
      intl.locale = ro.locale;
      intl.calendar = ro.calendar;
      intl.numbering = ro.numberingSystem;
      intl.sample_date = new Intl.DateTimeFormat(undefined, {
        dateStyle: "full",
        timeStyle: "long",
      }).format(new Date(0));
      intl.sample_number = new Intl.NumberFormat().format(1234567.891);
    } catch (_e) {
      /* intl queda parcial */
    }
    let tz = null;
    try {
      tz = Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch (_e) {
      tz = null;
    }
    return {
      timezone: tz,
      languages: navigator.languages ? Array.from(navigator.languages) : (navigator.language ? [navigator.language] : null),
      intl_formats: Object.keys(intl).length ? intl : null,
    };
  }

  // Voces de síntesis de voz. El catálogo se puebla async, así que esperamos
  // un toque el evento voiceschanged.
  function voices() {
    return new Promise((resolve) => {
      if (!global.speechSynthesis) return resolve(null);
      const read = () => {
        const list = global.speechSynthesis.getVoices() || [];
        return list.map((v) => v.name + " (" + v.lang + ")");
      };
      let got = read();
      if (got.length) return resolve(got);
      const handler = () => {
        got = read();
        resolve(got.length ? got : null);
      };
      global.speechSynthesis.onvoiceschanged = handler;
      setTimeout(() => resolve(read().length ? read() : null), 500);
    });
  }

  // Media queries: preferencias del sistema expuestas al navegador.
  function mediaQueries() {
    const q = (s) => {
      try {
        return global.matchMedia(s).matches;
      } catch (_e) {
        return null;
      }
    };
    return {
      dark: q("(prefers-color-scheme: dark)"),
      reduced_motion: q("(prefers-reduced-motion: reduce)"),
      pointer_fine: q("(pointer: fine)"),
      pointer_coarse: q("(pointer: coarse)"),
      hover: q("(hover: hover)"),
      high_contrast: q("(prefers-contrast: more)"),
    };
  }

  // Plugins (hoy casi vacío en Chrome/Firefox, pero su ausencia también informa).
  function plugins() {
    try {
      const list = Array.from(navigator.plugins || []).map((p) => p.name);
      return list.length ? list : [];
    } catch (_e) {
      return null;
    }
  }

  function doNotTrack() {
    return (
      navigator.doNotTrack || global.doNotTrack || navigator.msDoNotTrack || null
    );
  }

  // Client hints de alta entropía, leídos por JS (no llegan por header a un
  // tercero sin delegación de Permissions-Policy).
  async function uaData() {
    if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) {
      return null;
    }
    const hints = await navigator.userAgentData.getHighEntropyValues([
      "architecture", "bitness", "model", "platform", "platformVersion",
      "uaFullVersion", "fullVersionList", "wow64",
    ]);
    return hints;
  }

  // WebRTC/STUN: abrimos una conexión contra un STUN público y leemos los
  // candidatos ICE. De ahí sacamos la IP pública (relevante para el caso VPN)
  // y las IPs locales si el navegador no las oculta tras mDNS (.local).
  // El uso de STUN público es intencional y queda documentado.
  function webrtc() {
    return new Promise((resolve) => {
      const RTC = global.RTCPeerConnection || global.webkitRTCPeerConnection || global.mozRTCPeerConnection;
      const out = { webrtc_public_ips: [], webrtc_local_ips: [] };
      if (!RTC) return resolve({ webrtc_public_ips: null, webrtc_local_ips: null });

      const isPrivate = (ip) =>
        /^10\./.test(ip) ||
        /^192\.168\./.test(ip) ||
        /^172\.(1[6-9]|2\d|3[0-1])\./.test(ip) ||
        /^169\.254\./.test(ip) ||
        /^fe80:/i.test(ip) ||
        /^f[cd][0-9a-f]{2}:/i.test(ip) ||
        ip === "127.0.0.1" ||
        ip === "::1";

      const addPublic = (ip) => {
        if (!out.webrtc_public_ips.includes(ip)) out.webrtc_public_ips.push(ip);
      };
      const addLocal = (ip) => {
        if (!out.webrtc_local_ips.includes(ip)) out.webrtc_local_ips.push(ip);
      };

      let pc;
      try {
        pc = new RTC({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
      } catch (_e) {
        return resolve({ webrtc_public_ips: null, webrtc_local_ips: null });
      }

      const IP_RE = /([0-9]{1,3}(?:\.[0-9]{1,3}){3}|[a-f0-9]{0,4}(?::[a-f0-9]{0,4}){2,7})/i;
      const handle = (cand) => {
        if (!cand) return;
        // Ignoramos nombres mDNS (xxxx.local): el navegador oculta la IP local a propósito.
        if (/\.local/i.test(cand)) return;
        const m = cand.match(IP_RE);
        if (!m) return;
        const ip = m[1];
        if (ip.indexOf(":") === -1 && ip.split(".").length !== 4) return;
        if (isPrivate(ip)) addLocal(ip);
        else addPublic(ip);
      };

      pc.onicecandidate = (e) => {
        if (e.candidate) handle(e.candidate.candidate);
      };
      try {
        pc.createDataChannel("probe");
        pc.createOffer().then((o) => pc.setLocalDescription(o)).catch(() => {});
      } catch (_e) {
        /* seguimos: puede llegar algún candidato igual */
      }

      // Damos tiempo a juntar candidatos y cerramos.
      setTimeout(() => {
        try {
          pc.close();
        } catch (_e) {}
        resolve({
          webrtc_public_ips: out.webrtc_public_ips.length ? out.webrtc_public_ips : null,
          webrtc_local_ips: out.webrtc_local_ips.length ? out.webrtc_local_ips : null,
        });
      }, 1800);
    });
  }

  // --- orquestación ---------------------------------------------------------

  async function collect() {
    const [
      canvasHash,
      gl,
      audioHash,
      fontList,
      hw,
      loc,
      voiceList,
      mq,
      pluginList,
      ua,
      rtc,
    ] = await Promise.all([
      safe(canvas, 1500),
      safe(webgl, 1200),
      safe(audio, 2500),
      safe(fonts, 1500),
      safe(hardware, 500),
      safe(localization, 500),
      safe(voices, 1200),
      safe(mediaQueries, 500),
      safe(plugins, 500),
      safe(uaData, 1500),
      safe(webrtc, 2500),
    ]);

    const g = gl || {};
    const h = hw || {};
    const l = loc || {};
    const r = rtc || {};

    const fp = {
      canvas_hash: canvasHash,
      webgl_vendor: g.webgl_vendor || null,
      webgl_renderer: g.webgl_renderer || null,
      webgl_params: g.webgl_params || null,
      audio_hash: audioHash,
      fonts: fontList,
      screen_width: h.screen_width || null,
      screen_height: h.screen_height || null,
      device_pixel_ratio: h.device_pixel_ratio || null,
      color_depth: h.color_depth || null,
      hardware_concurrency: h.hardware_concurrency || null,
      device_memory: h.device_memory || null,
      touch_support: h.touch_support != null ? h.touch_support : null,
      timezone: l.timezone || null,
      languages: l.languages || null,
      intl_formats: l.intl_formats || null,
      voices: voiceList,
      media_queries: mq,
      plugins: pluginList,
      do_not_track: doNotTrack(),
      webrtc_public_ips: r.webrtc_public_ips || null,
      webrtc_local_ips: r.webrtc_local_ips || null,
      ua_data: ua,
    };

    // fp_id: hash estable de los componentes NO volátiles. Deja afuera WebRTC
    // (la IP cambia de red) para que la misma instalación dé el mismo id en el
    // chat y en el detector.
    const stable = JSON.stringify({
      canvas: fp.canvas_hash,
      audio: fp.audio_hash,
      glv: fp.webgl_vendor,
      glr: fp.webgl_renderer,
      fonts: fp.fonts ? fp.fonts.slice().sort() : null,
      sw: fp.screen_width,
      sh: fp.screen_height,
      dpr: fp.device_pixel_ratio,
      cd: fp.color_depth,
      cores: fp.hardware_concurrency,
      mem: fp.device_memory,
      tz: fp.timezone,
      langs: fp.languages,
      plat: (fp.ua_data && fp.ua_data.platform) || navigator.platform || null,
    });
    fp.fp_id = await hashHex(stable);

    return fp;
  }

  global.IdentityTracker = { collect: collect, version: VERSION };
})(window);
