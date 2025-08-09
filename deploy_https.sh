#!/usr/bin/env bash
set -euo pipefail

echo "=== Настройка доменов и HTTPS через Caddy + Docker ==="

read -rp "Введи фронтовый домен (например, casino.example.com): " FRONT_DOMAIN
read -rp "Введи API домен для бекенда WS (например, api.casino.example.com): " API_DOMAIN
read -rp "Введи e-mail для Let's Encrypt уведомлений: " LE_EMAIL

# Структура каталогов
mkdir -p infra/caddy
mkdir -p infra/frontend
mkdir -p infra/backend

# Создаём Caddyfile, домены вписаны напрямую (никаких плейсхолдеров)
cat > infra/caddy/Caddyfile <<'EOF'
# Файл заполняется ниже скриптом — заглушка
EOF

# Перезапишем Caddyfile со вставкой доменов
cat > infra/caddy/Caddyfile <<EOF
{
  email ${LE_EMAIL}
  auto_https on
}

${FRONT_DOMAIN} {
  root * /srv/frontend
  file_server
  encode gzip zstd
}

${API_DOMAIN} {
  @ws {
    path /ws*
    header Connection *Upgrade*
    header Upgrade websocket
  }

  reverse_proxy @ws backend:8000
  reverse_proxy / backend:8000
}
EOF

# Dockerfile для фронта (отдаём статику через Caddy, но держим контейнер с удобным билдом)
cat > infra/frontend/Dockerfile <<'EOF'
FROM python:3.11-slim
WORKDIR /app
COPY social_casino_frontend /app
CMD ["python3", "-m", "http.server", "80"]
EOF

# Dockerfile для бэкенда (FastAPI + Uvicorn)
cat > infra/backend/Dockerfile <<'EOF'
FROM python:3.11-slim

WORKDIR /app
COPY social_casino_backend /app/social_casino_backend
COPY serve_frontend.py /app/serve_frontend.py
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

ENV TELEGRAM_BOT_TOKEN=""
CMD ["uvicorn", "social_casino_backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

# requirements.txt (в корне репозитория рядом с serve_frontend.py и social_casino_backend)
if [ ! -f requirements.txt ]; then
  cat > requirements.txt <<'EOF'
fastapi
uvicorn[standard]
httpx
EOF
fi

# docker-compose.yml — единая сеть, Caddy берёт фронтовую статику из volume
cat > docker-compose.yml <<EOF
version: "3.9"

networks:
  webnet:

services:
  backend:
    build:
      context: .
      dockerfile: infra/backend/Dockerfile
    environment:
      - TELEGRAM_BOT_TOKEN=\${TELEGRAM_BOT_TOKEN}
    expose:
      - "8000"
    networks:
      - webnet
    restart: unless-stopped

  frontend:
    build:
      context: .
      dockerfile: infra/frontend/Dockerfile
    volumes:
      - ./social_casino_frontend:/app:ro
    expose:
      - "80"
    networks:
      - webnet
    restart: unless-stopped

  caddy:
    image: caddy:2.7
    depends_on:
      - frontend
      - backend
    ports:
      - "80:80"
      - "443:443"
    volumes:
      # Статика фронта монтируется в каталог, откуда Caddy её отдаёт
      - ./social_casino_frontend:/srv/frontend:ro
      - ./infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    networks:
      - webnet
    restart: unless-stopped

volumes:
  caddy-data:
  caddy-config:
EOF

echo "=== Готово. Проверь docker-compose.yml, infra/caddy/Caddyfile. ==="
echo "1) Убедись, что DNS A-записи ${FRONT_DOMAIN} и ${API_DOMAIN} смотрят на IP сервера"
echo "2) Экспортируй TELEGRAM_BOT_TOKEN и запускай:"
echo "   export TELEGRAM_BOT_TOKEN='123456:ABC-DEF...'  # твой реальный токен"
echo "   docker compose up -d --build"
