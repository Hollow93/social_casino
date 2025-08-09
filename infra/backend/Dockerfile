FROM python:3.11-slim

WORKDIR /app/social_casino_backend

COPY social_casino_backend /app/social_casino_backend
COPY serve_frontend.py /app/serve_frontend.py
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r /app/requirements.txt

ENV TELEGRAM_BOT_TOKEN="8111352574:AAGC-ax46qx_JEkG1inM375Cz-BXTbc-fPw"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

