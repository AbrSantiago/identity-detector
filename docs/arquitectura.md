# Arquitectura y decisiones de diseño

Documento vivo: se actualiza a medida que avanzan las fases. Registra las
decisiones tomadas y los supuestos asumidos cuando algo era ambiguo, para poder
defender el diseño.

## Componentes

- **Backend** (`backend/`, FastAPI, un solo worker). Estado en memoria: dict de
  identidades, buffer de chat con tope, historial de matches con tope. Expone el
  chat por WebSocket, la API de correlación y sirve el tracker.
- **Tracker** (`tracker/fp.js`). Un único script de terceros, servido por el
  backend e incluido en los dos frontends. Es el mismo observador en ambos
  sitios: esa es la idea central de la demo.
- **Frontend chat** (`frontends/chat/`) y **frontend detector**
  (`frontends/detector/`). JS vanilla, en orígenes distintos.

## Decisiones

- **Gestión de entorno con `uv`.** `pyproject.toml` como fuente única (deps +
  grupo dev + config de pytest) y `uv.lock` versionado. Se corre con `uv run`.
- **Python fijado en 3.12** (`backend/.python-version`, `requires-python <3.14`).
  Motivo: con 3.14 todavía no hay wheels de `pydantic-core` y `uv` intenta
  compilarlo desde Rust, lo que falla en Windows sin el linker de MSVC. `uv`
  descarga una 3.12 administrada automáticamente.
- **Despliegue con Cloudflare Tunnel en vez de Caddy** (decisión del grupo).
  Cloudflare aporta el HTTPS de borde y `cloudflared` expone `api.`, `chat.` y
  `detector.` sin abrir puertos. Se detalla en la fase 7.
- **Estado en memoria, un solo worker.** El estado vive en el proceso; con
  varios workers cada uno tendría su copia. Es intencional para la demo.

## Supuestos y límites (también son material para el informe)

- **Orden de headers:** solo es señal confiable con conexión directa. Detrás de
  un proxy (Cloudflare, Caddy, nginx) los headers se reescriben/normalizan, así
  que ese dato se pierde en producción. Se recolecta igual porque en local sí
  distingue implementaciones de cliente.
- **IP real detrás de proxy:** el backend solo lee `X-Forwarded-For` si la
  conexión viene de una IP en `TRUSTED_PROXIES`. Detrás de Cloudflare hay que
  cargar los rangos de Cloudflare (la IP real llega en `CF-Connecting-IP` /
  `X-Forwarded-For`). En local, conexión directa, `TRUSTED_PROXIES` vacío.
- **WebRTC:** hoy los navegadores ocultan las IPs locales detrás de nombres mDNS
  (`xxxx.local`); el tracker las ignora a propósito. Lo que sí se obtiene es la
  IP pública que revela el STUN, que es lo relevante para el caso de la VPN.
  Se usa un **STUN público** (`stun.l.google.com:19302`), documentado como el
  único tercero externo al que la demo contacta.
- **Client hints de alta entropía:** a un script de terceros no le llegan por
  header sin delegación de `Permissions-Policy`, así que se leen desde JS con
  `navigator.userAgentData.getHighEntropyValues()`. Los de baja entropía
  (`sec-ch-ua*`) sí se toman del header en el backend.
- **`fp_id` y "borrar mis datos":** el `fp_id` se calcula sobre los componentes
  NO volátiles (excluye la IP de WebRTC) para que la misma instalación de
  navegador dé el mismo id en el chat y en el detector. El borrado se hace por
  `fp_id`; si el navegador randomiza el fingerprint (Brave farbling), el id
  puede cambiar entre visitas y el borrado podría no encontrar datos viejos.
  Es un límite real y queda explícito.
- **`null` como información:** cada colector del tracker tiene timeout y
  `try/catch`; si una API no está o está bloqueada, el campo queda en `null`, y
  ese `null` también distingue (p. ej. un navegador que esconde el canvas).

## Algoritmo de correlación (`matching.py`)

- **Peso por dato = `-log2(frecuencia del valor)`** (bits de entropía, criterio
  EFF). Compartir una zona horaria común aporta ~0 bits; compartir un renderer
  de GPU raro aporta muchos.
- **Población chica.** Se combinan dos cosas: (1) suavizado de Laplace sobre la
  frecuencia observada, con la cardinalidad de cada atributo atada a sus bits a
  priori (`K = 2^prior_bits`), de modo que prior y suavizado sean coherentes; y
  (2) una mezcla con la **tabla de pesos a priori** (`PRIOR_BITS`, configurable)
  ponderada por el tamaño de la población: `w = N/(N+N0)`. Con N chico mandan los
  priors; con N grande, lo observado. Anda con 3 y con 300 identidades.
- **Comparaciones tolerantes:** User-Agent ignorando la versión menor (misma
  familia y versión mayor = 1.0; misma familia, otra mayor = 0.5); fuentes,
  idiomas, voces y WebRTC por solapamiento de Jaccard; IP con crédito parcial
  (IP exacta = 1.0; solo coincide la /24 o /64 = 0.6).
- **Puntaje por nivel = bits coincidentes / bits comparables** (0..1). Dos
  niveles: *navegador* (canvas, audio, UA, plugins, voces) y *dispositivo* (GPU,
  pantalla, fuentes, zona horaria, IP, etc.). El titular es
  `max(navegador, dispositivo)`: alcanza con que uno sea alto. El nivel
  dispositivo reconoce a la misma persona aunque cambie de navegador.
- **Umbral configurable** (`MATCH_THRESHOLD`): si ninguna candidata lo supera →
  "no te reconozco". Se devuelve la mejor, su porcentaje y el top 3.
- **Explicación:** por cada dato comparado se registra nivel, si coincidió y
  cuántos bits aportó. Ejemplo real (misma persona, Chrome en el chat y Firefox
  en el detector): navegador 0.15, dispositivo 1.00 — coinciden GPU (8.7 bits),
  fuentes (8.0), IP (6.7), pantalla, zona horaria…; difieren canvas, audio y UA
  (0 bits). Eso es exactamente "un seudónimo no es anonimato".

## Privacidad (implementación)

- Nada se escribe a disco ni se loguea la IP completa (el access log de uvicorn
  se desactiva en el arranque; ver fase 7).
- TTL de los datos en memoria (`DATA_TTL_HOURS`), barrido por tarea de fondo.
- CORS restringido a `ALLOWED_ORIGINS`. Sin cookies (no se usa `Domain=`); el
  `fp_id` viaja en el cuerpo, no en estado compartido entre frontends.
