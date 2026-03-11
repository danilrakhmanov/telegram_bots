# Используем docker-compose как базовый образ
FROM docker/compose:latest

# Создаём рабочую директорию
WORKDIR /app

# Копируем файлы
COPY . .

# Запускаем docker-compose
CMD ["docker-compose", "up", "-d"]
