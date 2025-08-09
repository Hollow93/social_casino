# serve_frontend.py (ИСПРАВЛЕННАЯ ВЕРСИЯ)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

# --- Конфигурация ---
# Убедитесь, что этот скрипт находится в корневой папке social_casino_2.0
FRONTEND_DIR = "social_casino_frontend" 

app = FastAPI()

# --- Middleware для добавления заголовка ---
# Этот middleware перехватывает все ответы от сервера и добавляет к ним нужные заголовки
@app.middleware("http")
async def add_custom_headers(request: Request, call_next):
    response = await call_next(request)
    # Добавляем заголовок для пропуска экрана ngrok
    response.headers["ngrok-skip-browser-warning"] = "true"
    # Добавляем заголовки, чтобы браузер не кэшировал старые (сломанные) файлы
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- Подача статических файлов ---
# Эта одна строка монтирует всю папку фронтенда в корень сайта.
# FastAPI автоматически найдет index.html для запроса "/"
# и правильно отдаст style.css, app.js и другие файлы.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static_files")


if __name__ == "__main__":
    print(f"Запуск сервера для фронтенда из папки: {FRONTEND_DIR}")
    print("Сервер будет доступен по адресу http://127.0.0.1:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)