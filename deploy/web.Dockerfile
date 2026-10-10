# Production web console: built Vue app served by nginx, which also proxies
# the API and WebSocket to the backend so everything is same-origin.
FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Empty API base = same origin (nginx proxies /api, /ws, /health)
ENV VITE_API_BASE_URL=
RUN npm run build

FROM nginx:1.29-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/40-basic-auth.sh /docker-entrypoint.d/40-basic-auth.sh
RUN chmod +x /docker-entrypoint.d/40-basic-auth.sh
COPY --from=build /app/dist /usr/share/nginx/html
