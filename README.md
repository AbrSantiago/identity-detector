# identity-detector

Demostración práctica de un trabajo universitario de seguridad informática (TP3):
**la correlación de identidades digitales mediante fingerprinting del navegador
y datos de red. Un seudónimo no es anonimato.**

La idea central: un mismo tercero (el script `tracker/fp.js`) presente en dos
sitios distintos es **el mismo observador**, y puede reconocerte sin cookies ni
estado compartido entre los sitios.

> **Uso pedagógico y consentido.** Participan solo integrantes del grupo e
> invitados informados, sobre servicios propios. Cada frontend muestra un aviso
> de qué se recolecta y exige aceptarlo antes de enviar nada. Hay un botón
> "Borrar mis datos". Todo vive en memoria, con TTL; nada se escribe a disco ni
> se loguea la IP completa. No hay analytics ni terceros, salvo el servidor STUN
> público de Google (`stun.l.google.com:19302`) que usa WebRTC para ver tu IP
> pública.

## Cómo funciona

| Servicio | Qué hace |
|---|---|
| **Chat** (`frontends/chat`) | Chat anónimo en tiempo real. Al entrar con un nickname, el tracker mide el navegador y el backend guarda nickname + fingerprint + datos de red. |
| **Detector** (`frontends/detector`) | Otro sitio, otro origen, mismo tracker. Mide al visitante y el backend devuelve la identidad más parecida **y qué datos permitieron reconocerla**. Incluye un historial de consultas en vivo. |
| **Backend** (`backend/`, FastAPI) | Estado en memoria, chat por WebSocket, API de correlación y sirve el tracker. Un solo worker. |

La correlación pesa cada dato por su entropía (`-log2` de la frecuencia del
valor), con suavizado y pesos a priori para que ande con 3 o con 300
identidades, y puntúa en dos niveles: **navegador** (canvas, audio, UA) y
**dispositivo** (GPU, pantalla, fuentes, zona horaria, IP). Detalle y
supuestos en [docs/arquitectura.md](docs/arquitectura.md).

## Correrlo en local (un comando)

Requisitos: [uv](https://docs.astral.sh/uv/) (descarga solo Python 3.12).

```bash
uv run --project backend python run_local.py
```

| URL | Qué es |
|---|---|
| http://chat.localhost:8000 | Frontend del chat |
| http://detector.localhost:8000 | Frontend del detector |
| http://localhost:8000/docs | API (Swagger) |

Los navegadores resuelven `*.localhost` a tu máquina, así que el chat y el
detector son **orígenes distintos**, como en producción. Con otro puerto:
`--port 8080`.

### Probar que te reconoce

1. Entrá al **chat**, aceptá el aviso y elegí un nickname.
2. Abrí el **detector** en otra pestaña (o en otro navegador) y aceptá el aviso.
3. Tiene que decir quién sos y mostrar la tabla de datos coincidentes.

Probá también el detector en Firefox con el chat en Chrome (reconoce por el
nivel dispositivo) y "Borrar mis datos" en el chat.

### Población de prueba (seed)

Para probar sin varias personas conectadas, con el backend corriendo:

```bash
cd backend
uv run python scripts/seed.py
```

Carga 5 perfiles inventados (incluye un par casi idéntico para provocar un
falso positivo). Viven en memoria: si reiniciás el backend, hay que volver a
correrlo. Sus fingerprints son inventados, así que **no te van a reconocer a
vos**; sirven de población alrededor para ver el top 3.

## Desplegar / exponer

Con Docker, y pensado para exponerlo por **Dev Tunnels** de VS Code (que un
profe lo abra desde afuera sin perder el estado en memoria):

```bash
cd deploy
docker compose up -d --build
```

Paso a paso del forward por Dev Tunnels y la alternativa hosteada en
[deploy/README.md](deploy/README.md).

## Tests

```bash
cd backend
uv run pytest
```

## Configuración

Por variables de entorno (ver [deploy/.env.example](deploy/.env.example)):
`ALLOWED_ORIGINS`, `TRUSTED_PROXIES`, `DATA_TTL_HOURS`, `MATCH_THRESHOLD`,
`CHAT_HISTORY_LIMIT`, `MATCH_HISTORY_LIMIT`. `run_local.py` fija
`ALLOWED_ORIGINS` solo; el resto tiene defaults.

## Estructura

```
backend/app/        main · api · chat · matching · network · store · models · config
backend/tests/      tests del backend
backend/scripts/    seed.py
tracker/fp.js       script tracker compartido (servido por el backend)
frontends/chat/     chat anónimo         (JS vanilla)
frontends/detector/ detector de identidad (JS vanilla)
run_local.py        levanta todo en local
deploy/             .env.example
docs/               arquitectura · experimentos · notas para el informe
```

## Documentación

- [docs/arquitectura.md](docs/arquitectura.md): decisiones, supuestos y límites.
- [docs/experimentos.md](docs/experimentos.md): matriz de experimentos (a completar con corridas reales).
- [docs/notas-informe.md](docs/notas-informe.md): material para el informe IEEE.

## Estado

Implementado: backend, tracker, chat, correlación, detector con historial en
vivo, borrado de datos, tests, seed, ejecución local y **despliegue con
`docker compose` + Dev Tunnels** (ver [deploy/README.md](deploy/README.md)).
**Pendiente:** completar la matriz de experimentos con corridas reales.
