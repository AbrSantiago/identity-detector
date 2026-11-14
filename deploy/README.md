# Despliegue

Tres servicios en puertos distintos, para que el chat y el detector sean
**orígenes distintos** (es la gracia de la demo):

| Servicio | Puerto | Qué es |
|---|---|---|
| `backend`  | 8000 | FastAPI: API, WebSocket, tracker, `/docs` |
| `chat`     | 8080 | Frontend del chat (nginx, estático) |
| `detector` | 8081 | Frontend del detector (nginx, estático) |

El estado vive en memoria, así que el backend corre con **un solo worker**.

## Levantar con Docker

Requisito: Docker Desktop. Desde la carpeta `deploy/`:

```bash
cd deploy
docker compose up -d --build
```

- chat → http://localhost:8080
- detector → http://localhost:8081
- API/docs → http://localhost:8000/docs

Para ver los valores de entorno ya resueltos (útil para chequear el regex de
CORS): `docker compose config`. Para los logs: `docker compose logs -f backend`.
Para bajar todo: `docker compose down`.

## Exponerlo por Dev Tunnels (VS Code)

Para que lo abran desde afuera (otra compu, otro navegador, un profe) sin
dormirse ni perder el estado en memoria. **No hay que configurar URLs a mano.**

1. Levantá el compose (arriba).
2. En VS Code, panel **PORTS** → **Forward a Port** → agregá **8000**, **8080**
   y **8081** (los tres).
3. En cada uno: click derecho → **Port Visibility → Public**. Es necesario para
   que lo abran sin loguearse y para que el detector pueda llamar a la API.
4. Copiá la URL del **8080** (chat) y la del **8081** (detector) y abrilas. La
   URL es del tipo `https://<id>-8080.<cluster>.devtunnels.ms`.

### Por qué funciona sin configurar nada

- Dev Tunnels incrusta el puerto en el subdominio (`<id>-8080...`), así que el
  frontend **deriva** la URL de la API cambiando `-8080`/`-8081` por `-8000`
  (`deploy/static-entrypoint.sh`).
- El backend acepta cualquier origen `*.devtunnels.ms` por CORS y en el chequeo
  de Origin del WebSocket (default `ALLOWED_ORIGIN_REGEX` en el compose).

> **Límite conocido (bueno para el informe):** detrás del túnel, el backend ve
> la IP del borde de Dev Tunnels, no la del visitante. La correlación por IP
> pierde precisión; el resto del fingerprint (y la IP pública vía WebRTC/STUN)
> sigue andando. En local directo (`run_local.py`) la IP real sí se observa.

## Con dominio propio (opcional)

Si algún día lo ponés en un dominio: en `deploy/.env` fijá
`API_BASE=https://api.tudominio` y
`ALLOWED_ORIGINS=https://chat.tudominio,https://detector.tudominio`, apuntá esos
hostnames con un proxy inverso (o Cloudflare Tunnel) a los puertos 8080/8081/8000
y recreá con `docker compose up -d`.

## Alternativa hosteada (sin tu PC prendida)

De los tiers gratuitos, **Render** (Docker) es el único viable, pero **se duerme
a los 15 min de inactividad y al reiniciar pierde el estado en memoria**
(identidades y historial). Sirve si lo despertás y recorrés el seed
(`backend/scripts/seed.py`) justo antes de mostrarlo. Fly.io ya no tiene free
tier (2026) y Cloudflare no hostea bien un backend con estado + WebSockets.
Para la defensa, Dev Tunnels desde tu máquina es más confiable.
