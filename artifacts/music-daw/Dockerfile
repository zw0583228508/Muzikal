FROM node:20-slim AS builder

WORKDIR /app

RUN npm install -g pnpm@9

# Copy workspace configuration
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ ./packages/
COPY lib/ ./lib/
COPY artifacts/music-daw/ ./artifacts/music-daw/

# Install dependencies
RUN pnpm install --frozen-lockfile

# Build dependencies first
RUN pnpm --filter @workspace/api-spec run codegen 2>/dev/null || true
RUN pnpm --filter @workspace/api-client-react run build 2>/dev/null || true

# Build the React SPA
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN pnpm --filter @workspace/music-daw run build

# ── Runtime stage — serve with nginx ─────────────────────────────────────────
FROM nginx:alpine AS runtime

COPY --from=builder /app/artifacts/music-daw/dist /usr/share/nginx/html

# nginx config: single-page app routing (all paths → index.html)
RUN printf 'server {\n\
    listen 80;\n\
    root /usr/share/nginx/html;\n\
    index index.html;\n\
    gzip on;\n\
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;\n\
    location / {\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location ~* \\.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {\n\
        expires 1y;\n\
        add_header Cache-Control "public, immutable";\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost/ || exit 1
