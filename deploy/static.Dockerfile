# Imagen de un frontend estático (chat o detector), elegido por el ARG SITE.
# nginx corre los scripts de /docker-entrypoint.d/ al arrancar: usamos uno para
# generar config.js con la URL del backend (o para que el frontend la derive).
FROM nginx:1.27-alpine
ARG SITE
COPY frontends/${SITE}/ /usr/share/nginx/html/
COPY deploy/static-entrypoint.sh /docker-entrypoint.d/40-apibase.sh
RUN chmod +x /docker-entrypoint.d/40-apibase.sh
EXPOSE 80
