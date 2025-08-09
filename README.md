# Social Casino Telegram WebApp

## Описание проекта
Этот проект — это Telegram WebApp-игра «Crash» с интеграцией Telegram Stars, бэкендом на FastAPI, WebSocket-реалтаймом и фронтендом, оптимизированным под Telegram. Пользователи могут заходить через Telegram Mini App, делать ставки, наблюдать за ростом множителя и забирать выигрыш до краша.

## Основной стек
- **Backend**: Python 3.11, FastAPI, Uvicorn, WebSockets
- **Frontend**: HTML/CSS/JavaScript (Telegram WebApp API)
- **База данных**: SQLite (в dev), можно заменить на PostgreSQL
- **Логирование событий**: ClickHouse
- **Веб-сервер**: Caddy (HTTPS + автосертификаты Let’s Encrypt)
- **Контейнеризация**: Docker Compose
- **Интеграция**: Telegram Bot API, Telegram Stars

## Основные функции
1. **Авторизация через Telegram WebApp**
   - Без регистрации/логина — используется `initData` от Telegram.
   - Проверка подписи HMAC для защиты от подмены.

2. **Игровая логика "Crash"**
   - Раунды с обратным отсчетом.
   - Множитель растёт до случайного "краша".
   - Автоматические ставки и автокэшаут.

3. **Система ставок и балансов**
   - Баланс хранится в базе данных.
   - Пополнение через Telegram Stars (`createInvoiceLink`).
   - Мгновенное обновление баланса через WebSocket.

4. **Логирование в ClickHouse**
   - Запись всех действий пользователей: подключение, ставки, кэшаут, платежи.

5. **Реалтайм через WebSocket**
   - Обновления состояния игры, баланса, истории множителей.

## Структура репозитория
```
social_casino-main/
├── backend/               # Бэкенд (FastAPI + WS)
│   ├── app/
│   │   ├── main.py        # Точка входа API и WS
│   │   ├── game_logic.py  # Логика игры Crash
│   │   ├── ws_manager.py  # Управление WebSocket-сессиями
│   │   ├── db.py          # Работа с базой данных
│   │   └── clickhouse_logger.py # Логирование
│   └── requirements.txt
├── frontend/              # Фронтенд Telegram WebApp
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── docker-compose.yml     # Оркестрация сервисов
├── Caddyfile              # Конфигурация веб-сервера Caddy
└── README.md              # Этот файл
```

## Как запустить
1. **Клонируем репозиторий**
```bash
git clone https://github.com/your-repo/social_casino.git
cd social_casino
```

2. **Создаём `.env` файл**
```env
TELEGRAM_BOT_TOKEN=токен_бота
CLICKHOUSE_URL=http://clickhouse:8123
```

3. **Запускаем в Docker**
```bash
docker compose up --build
```

4. **Подключаем в Telegram**
   - В `BotFather` включаем `Menu Button` → `Web App` с URL фронтенда.
   - Запускаем бот, переходим в игру.

## Управление сервисами
- **Перезапуск**
```bash
docker compose restart
```
- **Логи**
```bash
docker compose logs -f backend
```

Запуск локально:
cp .env.example .env   # и заполни значения
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# фронт+api будут доступны через Caddy на http://localhost:8080

Включаем с clickhouse
# в .env поставь CLICKHOUSE_ENABLED=1
docker compose -f docker-compose.yml -f docker-compose.clickhouse.yml up -d --build

## Автор
Разработано anvaesiDev и Hollow в 2025 году.
