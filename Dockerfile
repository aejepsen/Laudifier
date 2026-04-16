# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build --configuration=production

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Non-root user (nginx official image já cria nginx user)
RUN mkdir -p /var/cache/nginx /var/run && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx

COPY --from=builder /app/dist/laudifier /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER nginx

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
