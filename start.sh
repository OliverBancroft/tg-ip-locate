#!/bin/bash

# 检查数据目录是否存在
if [ ! -d "/app/data" ]; then
    mkdir -p /app/data
fi

# 检查JSON文件是否存在，不存在则运行扫描
if [ ! -f "/app/data/telegram_ipv4_24.json" ]; then
    echo "Initial scan file not found, running first scan..."
    python split_cidr.py
fi

# 启动定时任务
python -c "
import schedule
import time
import subprocess
import os
from datetime import datetime

def run_scan():
    print(f'[{datetime.now()}] Starting scheduled scan...')
    subprocess.run(['python', 'split_cidr.py'])

# 设置定时任务
schedule.every(${SCAN_INTERVAL}).seconds.do(run_scan)

# 在后台运行定时任务
import threading
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
scheduler_thread.start()
"

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