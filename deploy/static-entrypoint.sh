#!/bin/sh
# Genera config.js al arrancar el contenedor estático.
# - Si API_BASE está seteado (dominio propio), se usa tal cual.
# - Si está vacío, el frontend DERIVA la URL del backend del host actual:
#   Dev Tunnels incrusta el puerto en el subdominio
#   (https://<id>-8080.<cluster>.devtunnels.ms), así que apunta al -8000 del
#   mismo túnel. En localhost, al :8000.
set -e
cat > /usr/share/nginx/html/config.js <<'JSEOF'
(function () {
  var explicit = "__API_BASE__";
  var o = location.origin;
  var api = explicit;
  if (!api) {
    api = o.replace("-8080.", "-8000.").replace("-8081.", "-8000.");
    if (api === o) { api = o.replace(/:\d+$/, ":8000"); }
  }
  window.IDENTITY_CONFIG = { apiBase: api };
})();
JSEOF
sed -i "s|__API_BASE__|${API_BASE:-}|g" /usr/share/nginx/html/config.js
echo "[static] config.js -> apiBase: ${API_BASE:-auto (derivado del host)}"
