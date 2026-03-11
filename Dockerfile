FROM python:3.9-slim

# Установка supervisor для управления процессами
RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости и устанавливаем
COPY bot_findkzn/requirements.txt /app/bot_findkzn/requirements.txt
RUN pip install --no-cache-dir -r /app/bot_findkzn/requirements.txt

COPY bot_oasismus/requirements.txt /app/bot_oasismus/requirements.txt
RUN pip install --no-cache-dir -r /app/bot_oasismus/requirements.txt

# Копируем код ботов
COPY bot_findkzn/ /app/bot_findkzn/
COPY bot_oasismus/ /app/bot_oasismus/

# Создаём папки для сессий
RUN mkdir -p /app/bot_findkzn/sessions /app/bot_oasismus/sessions

# Создаём конфигурацию supervisor
RUN echo "[supervisord]" > /etc/supervisor/conf.d/supervisord.conf && \
    echo "nodaemon=true" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "[program:bot_findkzn]" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "directory=/app/bot_findkzn" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "command=python bot.py" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stdout_logfile=/dev/stdout" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stdout_logfile_maxbytes=0" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stderr_logfile=/dev/stderr" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stderr_logfile_maxbytes=0" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "[program:bot_oasismus]" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "directory=/app/bot_oasismus" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "command=python bot.py" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stdout_logfile=/dev/stdout" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stdout_logfile_maxbytes=0" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stderr_logfile=/dev/stderr" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "stderr_logfile_maxbytes=0" >> /etc/supervisor/conf.d/supervisord.conf && \
    echo "autorestart=true" >> /etc/supervisor/conf.d/supervisord.conf

# Запускаем supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
