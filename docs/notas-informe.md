# Notas para el informe IEEE

Material ordenado según el informe. Se actualiza con lo que sale del
desarrollo y de los experimentos. Convención:

- **[Medido]**: sale de una corrida o de un test de este repo.
- **[Diseño]**: decisión de implementación.
- **[A verificar]**: afirmación que hay que confirmar contra una fuente antes de citarla.
- **[Pendiente]**: depende de experimentos que todavía no se corrieron (ver `experimentos.md`).

## 1. Situación analizada

- Una persona usa un seudónimo en un chat y entra a otro sitio sin relación
  aparente. Un **mismo tercero** (script incluido en ambos) puede asociar las
  dos visitas sin cookies, sin login y sin estado compartido entre los sitios.
- La demo reproduce eso con tres piezas: chat (sitio A), detector (sitio B) y
  un backend que sirve el tracker y correlaciona. Los dos sitios son orígenes
  distintos y **no comparten cookies ni almacenamiento**. [Diseño]
- Pregunta del trabajo: ¿alcanza con elegir un nickname para ser anónimo? No.

## 2. Protocolos y tecnologías

| Tecnología | Qué aporta al fingerprint | Notas de implementación |
|---|---|---|
| **HTTP / headers** | IP de origen, `User-Agent`, `Accept-Language`, `Accept-Encoding`, client hints de baja entropía (`sec-ch-ua*`), orden de los headers. | El servidor los observa del propio request; el cliente no los puede falsear en el cuerpo. [Diseño] |
| **WebSocket** (RFC 6455) | El chat entra por `WS /ws/chat`; el handshake HTTP trae los mismos headers. | Los navegadores **no aplican CORS a WebSocket**: se valida `Origin` a mano. [Diseño] |
| **WebRTC / STUN / ICE** (RFC 8489, RFC 8445) | IP pública vista por el STUN: revela la IP real aunque haya VPN o proxy HTTP. | Los navegadores modernos ocultan las IPs locales tras nombres mDNS; el tracker las ignora. Único tercero externo: STUN público de Google. [Diseño] |
| **APIs del navegador** | Canvas, WebGL (vendor/renderer), AudioContext, medición de fuentes por ancho de texto, pantalla, núcleos, memoria, zona horaria, idiomas, voces de síntesis, media queries, plugins, DNT. | Cada colector tiene timeout y `try/catch`; si falla devuelve `null`, y **ese `null` también es información**. [Diseño] |
| **Client hints de alta entropía** | `navigator.userAgentData.getHighEntropyValues()`. | A un script de terceros no le llegan por header sin delegación de `Permissions-Policy`, por eso se leen desde JS. [Diseño] |
| **Reverse proxy** | La IP real llega en `X-Forwarded-For`. | Solo se confía en ese header si la conexión viene de `TRUSTED_PROXIES`; si no, cualquiera falsearía su IP. El orden de headers se pierde detrás de un proxy. [Diseño] |

## 3. Cómo y por qué es posible

- **Entropía.** Cada dato aporta `-log2(frecuencia del valor)` bits. Una zona
  horaria común aporta casi 0 bits; un renderer de GPU raro aporta muchos. Los
  bits de datos independientes se suman. [Diseño; criterio de la EFF, A verificar la cita]
- **Cuántos bits distinguen a una persona.** Entre 8.000 millones de personas
  alcanzan ~33 bits (log₂ 8×10⁹ ≈ 32,9). [Cálculo]
- **Población chica.** Con 3 usuarios la frecuencia observada es ruido. El
  algoritmo mezcla un suavizado de Laplace con una tabla de pesos a priori por
  atributo, ponderada por el tamaño de la población (`w = N/(N+N0)`): con pocos
  usuarios mandan los priors, con muchos lo observado. [Diseño]
- **Comparación tolerante.** UA ignorando la versión menor, fuentes por
  Jaccard, IP con crédito parcial si coincide la /24 o /64. [Diseño]
- **Dos niveles de puntaje.** *Navegador* (canvas, audio, UA) y *dispositivo*
  (GPU, pantalla, fuentes, zona horaria, IP). El nivel dispositivo reconoce a la
  misma persona aunque cambie de navegador. [Diseño] En una simulación con
  perfiles inventados, mismo hardware con otro canvas y otro audio dio
  navegador 0,00 / dispositivo 1,00 y fue reconocido; el algoritmo funciona,
  la corrida con navegadores reales sigue **[Pendiente]**.
- **El vector es el script de terceros.** El mismo `fp.js` incluido en dos
  sitios es un único observador: no hace falta que los sitios cooperen.

### Límites y hallazgos honestos

- **Falsos positivos.** Equipos iguales (mismo modelo, mismo software, misma
  red) son indistinguibles. En la simulación, un visitante con otro hardware
  igual obtuvo **0,42** contra dos perfiles de notebook común, por encima del
  umbral actual (0,35). [Medido en simulación] Hay que calibrar el umbral con
  los experimentos y discutir el equilibrio entre falsos positivos y negativos.
- **`fp_id` y borrado.** Si el navegador aleatoriza su fingerprint (Brave), el
  `fp_id` cambia entre visitas y el borrado solo alcanza al actual. [Diseño]
- **Histórico no atribuible.** El historial de consultas no guarda `fp_id` ni IP
  completa (solo resultado y red /24 o /64); por eso no se puede borrar por
  visitante y expira por TTL. [Diseño]
- **Lo que no se compara.** `header_order` y `Accept-Language` se recolectan pero
  no entran al puntaje. [Diseño]

## 4. Defensas y su costo

| Defensa | Cómo actúa | Costo / límite |
|---|---|---|
| **Uniformar** (Tor Browser, `resistFingerprinting`) | Todos los usuarios devuelven los mismos valores: no distingue. | Puede romper sitios (zona horaria, tamaño de ventana, canvas). Que muchos campos den `null` delata que se usa esa defensa. [Pendiente: caso 4] |
| **Aleatorizar** (farbling de Brave) | Ruido distinto por sesión y por sitio en canvas, audio y WebGL: dos sitios ven valores distintos. | Rompe la correlación por esos datos, no por el resto (pantalla, zona horaria, IP). [Pendiente: caso 5a] |
| **Bloquear terceros** (uBlock Origin) | El tracker no carga. | Depende de listas; el servidor igual ve IP y headers. [Pendiente: caso 5b] |
| **Perfiles separados** | Identidades que no deben cruzarse usan navegadores o perfiles distintos. | Disciplina del usuario; mismo dispositivo y misma IP siguen siendo señal. |
| **VPN** | Cambia la IP. | No cambia el resto del fingerprint y WebRTC puede filtrar la IP real. [Pendiente: caso 3] |
| **Cookies / incógnito** | Borra estado. | No alcanza: el fingerprint no usa estado. [Pendiente: caso 1] |

Todas pueden romper funcionalidad de sitios legítimos.

## 5. Recomendaciones técnicas

- Para usuarios: perfiles separados por identidad, navegador con protección
  contra fingerprinting, bloqueo de terceros, cuidado con WebRTC en VPN.
- Para sitios: no incluir scripts de terceros que no hacen falta; auditar a
  quién se le cede el contexto de la página; aviso y consentimiento.
- Para nuestro diseño (buenas prácticas de la demo): confiar en
  `X-Forwarded-For` solo desde proxies declarados; no guardar IP completa; TTL
  corto; borrado funcional; sin analytics.

## 6. Conclusiones (a respaldar con los experimentos)

1. **Un seudónimo no es anonimato.** El nickname es lo único que el usuario
   decide; el resto lo mide el tercero.
2. ~33 bits distinguen a una persona entre 8.000 millones; un fingerprint
   típico reúne bastantes más. [A verificar con fuentes]
3. **Borrar cookies o usar incógnito no alcanza.** [Pendiente: caso 1]
4. **Una VPN cambia la IP, no el resto**, y WebRTC puede filtrar la IP real.
   [Pendiente: caso 3]
5. **Lo raro te hace más rastreable:** un renderer de GPU o un set de fuentes
   poco común aporta más bits.
6. **Los scripts de terceros son el vector.**
7. **Límite de la técnica:** equipos iguales generan falsos positivos. [Pendiente: caso 6]

## 7. Aspectos legales y éticos

> No es asesoramiento legal. Todo lo de esta sección está **[A confirmar]**.

- **Unión Europea:** la Directiva ePrivacy (2002/58/CE, art. 5.3) exige
  consentimiento para acceder o almacenar información en el dispositivo, lo que
  alcanza al fingerprinting; el RGPD (2016/679) regula los datos personales
  resultantes. [A confirmar artículos y alcance]
- **Argentina:** Ley 25.326 de Protección de Datos Personales; Ley 26.388
  (delitos informáticos, acceso no autorizado). [A confirmar aplicabilidad]
- **Usos legítimos:** detección de fraude y seguridad de cuentas, con las
  mismas obligaciones de transparencia.
- **Cómo lo resolvimos en la demo:** participan solo integrantes e invitados
  informados; aviso previo y aceptación antes de enviar datos; borrado a pedido;
  TTL; sin IP completa; sin terceros salvo el STUN documentado; sin pruebas
  sobre sistemas ajenos.

## 8. Fuentes candidatas (formato IEEE)

**No se verificaron las referencias contra los originales.** Ninguna está lista
para citar hasta confirmar autores, año, venue y páginas/DOI.

| # | Fuente | Estado |
|---|---|---|
| 1 | I. Fette y A. Melnikov, "The WebSocket Protocol," RFC 6455, IETF, 2011. | Número y título conocidos; **a verificar** datos |
| 2 | M. Petit-Huguenin et al., "Session Traversal Utilities for NAT (STUN)," RFC 8489, IETF, 2020. | **A verificar** autores |
| 3 | A. Keränen, C. Holmberg y J. Rosenberg, "Interactive Connectivity Establishment (ICE)," RFC 8445, IETF, 2018. | **A verificar** autores |
| 4 | EFF, "Cover Your Tracks" (antes Panopticlick), sitio web. | **A verificar** URL y fecha de acceso |
| 5 | P. Eckersley, "How Unique Is Your Web Browser?," PETS 2010. | **A verificar** |
| 6 | P. Laperdrix, N. Bielova, B. Baudry y G. Avoine, "Browser Fingerprinting: A Survey," ACM Trans. Web, 2020. | **A verificar** |
| 7 | A. Gómez-Boix, P. Laperdrix y B. Baudry, "Hiding in the Crowd: an Analysis of the Effectiveness of Browser Fingerprinting at Large Scale," WWW 2018. | **A verificar** |
| 8 | G. Acar et al., "The Web Never Forgets: Persistent Tracking Mechanisms in the Wild," ACM CCS 2014. | **A verificar** |
| 9 | K. Mowery y H. Shacham, "Pixel Perfect: Fingerprinting Canvas in HTML5," W2SP 2012. | **A verificar** |
| 10 | Directiva 2002/58/CE (ePrivacy) y Reglamento (UE) 2016/679 (RGPD). | **A verificar** artículos |
| 11 | Ley 25.326 y Ley 26.388 (Argentina). | **A verificar** texto vigente |
