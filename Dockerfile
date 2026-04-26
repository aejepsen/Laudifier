# ─── Stage 1: builder ────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build --configuration=production

# ─── Stage 2: runtime ────────────────────────────────────────────────────────
# Imagem oficial unprivileged — roda como uid 101, listen 8080, pid /tmp
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=builder /app/dist/laudifier /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
