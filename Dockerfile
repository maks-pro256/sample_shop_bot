FROM python:3.12-slim

# Не создавать .pyc и сразу выводить логи (иначе print/logging буферизуются)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: этот слой кэшируется и не пересобирается при правках кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запуск не от root
RUN useradd --create-home --shell /usr/sbin/nologin bot
USER bot

CMD ["python", "run.py"]
