#!/bin/bash

# 检查JSON文件是否存在，不存在则运行扫描
if [ ! -f "/app/data/telegram_ipv4_24.json" ]; then
    echo "Initial scan file not found, running first scan..."
    python split_cidr.py
fi

# 在后台启动调度器
python scheduler.py &
SCHEDULER_PID=$!

# 启动Gunicorn
exec gunicorn --bind 0.0.0.0:8080 \
    --workers ${GUNICORN_WORKERS} \
    --threads ${GUNICORN_THREADS} \
    --timeout ${GUNICORN_TIMEOUT} \
    --worker-class=sync \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    server:app 