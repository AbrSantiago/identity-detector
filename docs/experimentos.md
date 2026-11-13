# Matriz de experimentos

Insumo para el informe. Cada fila se completa **con una corrida real** del
sistema; las columnas "Resultado" están vacías a propósito. Lo único cargado
son las **hipótesis** (lo que esperamos que pase y por qué), para poder
contrastarlas después con lo medido.

> Regla: no se anota ningún número que no salga de una corrida. Si un caso
> no se pudo probar (p. ej. falta el dispositivo), se deja "no probado" y se
> dice por qué.

## Cómo correr un experimento

1. Levantar el backend y los dos frontends (ver README, fase 7).
2. *(Opcional, para tener población)* sembrar identidades de ejemplo:
   `cd backend && uv run python scripts/seed.py`. Todas quedan en la red del
   que corre el script, así que el dato de IP aporta menos bits que en un caso
   real con personas en redes distintas.
3. **Entrar al chat** con la condición A (navegador/red/configuración base) y
   un nickname fácil de reconocer. Eso registra la identidad.
4. **Entrar al detector** con la condición B (la variación que se prueba) y
   aceptar el aviso.
5. Anotar en la tabla: quién dice que sos, puntajes por nivel y la tabla de
   "qué datos permitieron reconocerte" (qué coincidió, qué cambió).
6. Para repetir el caso, "Borrar mis datos" en el chat deja el estado limpio
   para ese navegador.

Datos a registrar en cada corrida:

| Campo | De dónde sale |
|---|---|
| Match | Veredicto del detector (nickname o "no te reconozco") |
| Puntaje navegador / dispositivo | Barras del detector (`browser_score`, `device_score`) |
| Coincidieron | Filas "sí" de la tabla de desglose, con sus bits |
| Cambiaron | Filas "no" de la tabla de desglose |

## Matriz

### 1. Mismo navegador: ventana normal vs. incógnito

- **Condición A:** ventana normal → chat. **B:** incógnito → detector.
- **Hipótesis:** se reconoce. Incógnito borra cookies y almacenamiento, pero
  canvas, audio, GPU, fuentes, pantalla y zona horaria son los mismos; no
  usamos cookies, así que no se pierde nada. Puede cambiar alguna señal
  menor (extensiones desactivadas, plugins).
- **Resultado:** _pendiente_

| Match | Navegador | Dispositivo | Coincidieron | Cambiaron |
|---|---|---|---|---|
| | | | | |

### 2. Mismo dispositivo: Chrome vs. Firefox

- **Condición A:** Chrome → chat. **B:** Firefox → detector.
- **Hipótesis:** se reconoce por el **nivel dispositivo** (GPU, pantalla,
  fuentes, zona horaria, IP) aunque el puntaje de navegador sea bajo
  (canvas, audio y User-Agent cambian). Es la razón de ser de los dos niveles.
- **Simulación previa (no es una medición):** con las identidades del seed, un
  visitante con el hardware de "ana" pero otro canvas y otro audio da
  `navegador 0.00 / dispositivo 1.00` y lo reconoce, con GPU 8.5 bits y fuentes
  8.0 bits como los datos de más peso. Sirve para validar el algoritmo, no
  como resultado del informe: falta la corrida con navegadores reales.
- **Resultado:** _pendiente_

| Match | Navegador | Dispositivo | Coincidieron | Cambiaron |
|---|---|---|---|---|
| | | | | |

### 3. Con y sin VPN

- **Condición A:** sin VPN → chat. **B:** con VPN → detector.
- **Hipótesis:** la IP cambia (y su /24), por lo que se pierden los bits de
  red, pero el resto del fingerprint no cambia y se reconoce igual. A
  verificar si WebRTC filtra la IP real por fuera de la VPN (mirar "IP pública
  por WebRTC" en "Esto sabemos de vos") y si la zona horaria delata el país
  real.
- **Resultado:** _pendiente_

| Match | Navegador | Dispositivo | IP cambió | WebRTC filtró IP real | Coincidieron | Cambiaron |
|---|---|---|---|---|---|---|
| | | | | | | |

### 4. Tor Browser / Firefox con `resistFingerprinting`

- **Condición A:** navegador normal → chat. **B:** Tor Browser, o Firefox con
  `privacy.resistFingerprinting = true` → detector.
- **Hipótesis:** no se reconoce o el puntaje cae mucho. El navegador
  **uniforma** los valores (pantalla, zona horaria en UTC, fuentes, canvas
  bloqueado o genérico), así que lo que el visitante comparte con cualquier
  otro Tor no distingue. Ojo: que muchos campos queden en `null` es en sí mismo
  una señal ("usa Tor/RFP").
- **Resultado:** _pendiente_

| Match | Navegador | Dispositivo | Campos en `null` | Coincidieron | Cambiaron |
|---|---|---|---|---|---|
| | | | | | |

### 5. Brave (farbling) y uBlock Origin bloqueando el tracker

- **5a. Brave:** A: Chrome → chat. B: Brave (escudos por defecto) → detector.
  **Hipótesis:** Brave aleatoriza canvas/audio/WebGL por sesión y sitio, así
  que esos datos no coinciden; el nivel dispositivo puede seguir reconociendo
  por lo que Brave no toca (pantalla, zona horaria, IP).
- **5b. uBlock Origin:** B: navegador con uBlock y la lista que bloquee el
  dominio del tracker. **Hipótesis:** si bloquea `tracker/fp.js`, el
  frontend no puede medir (hoy muestra "No se pudo cargar el tracker"). Vale
  anotar que el servidor igual ve IP y headers de la conexión.
- **Resultado:** _pendiente_

| Caso | Match | Navegador | Dispositivo | Qué se bloqueó o aleatorizó |
|---|---|---|---|---|
| 5a | | | | |
| 5b | | | | |

### 6. Dos personas con equipos iguales (falsos positivos)

- **Condición:** dos personas distintas con el mismo modelo de equipo, mismo
  sistema y navegador, y la misma red. Una entra al chat y la otra al detector.
- **Hipótesis:** el sistema probablemente las confunde (**falso positivo**).
  Es un límite real de la técnica: si el hardware y el software son idénticos y
  comparten IP, el fingerprint no las distingue. Los perfiles `lucas` y `mica`
  del seed existen para provocar este caso.
- **Resultado:** _pendiente_ (anotar qué dato las diferenció, si alguno).

| Match (¿confunde?) | Navegador | Dispositivo | Qué las distinguía |
|---|---|---|---|
| | | | |

### 7. Cambio de red del mismo dispositivo (wifi ↔ datos móviles)

- **Condición A:** wifi → chat. **B:** mismo dispositivo con datos móviles →
  detector.
- **Hipótesis:** cambia la IP y su red; se pierden esos bits, pero el nivel
  dispositivo y el navegador siguen coincidiendo, así que se reconoce. Con
  CGNAT la IP móvil puede compartirse con muchas personas: aporta poco.
- **Resultado:** _pendiente_

| Match | Navegador | Dispositivo | IP cambió | Coincidieron | Cambiaron |
|---|---|---|---|---|---|
| | | | | | |

## Lecturas para la discusión (completar con los datos)

- ¿Qué datos aportaron más bits de manera sistemática?
- ¿En qué casos se reconoció gracias al nivel dispositivo y no al navegador?
- ¿Qué defensa fue más efectiva (uniformar, aleatorizar, bloquear) y qué costo
  tuvo (sitios rotos, aviso de "usa Tor")?
- ¿Cuántos falsos positivos hubo y en qué condiciones?
