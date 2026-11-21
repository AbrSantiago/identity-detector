/* Configuración del frontend del chat.
 * apiBase: origen del backend (sirve el tracker, el WebSocket y la API).
 * Es el ÚNICO lugar donde se cambia la URL del backend.
 *
 * En local (run_local.py) el backend queda en api.localhost:8000.
 * En producción, p. ej.: https://api.tudominio.ar
 */
window.IDENTITY_CONFIG = {
  apiBase: "http://localhost:8000",
};
