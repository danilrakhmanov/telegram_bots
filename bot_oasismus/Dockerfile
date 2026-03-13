# Используем официальный Python образ
FROM python:3.9-slim

# Создаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY bot.py .

# Создаем папку для сессий (чтобы не потерять при перезапуске)
RUN mkdir -p /app/sessions

# Запускаем бота
CMD ["python", "bot.py"]