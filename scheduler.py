import schedule
import time
import subprocess
import os
import logging
from datetime import datetime
import pytz

# 配置日志
log_filename = os.path.join('data', f'scheduler_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_scan():
    """执行扫描任务"""
    try:
        logger.info("开始执行定时扫描任务")
        start_time = time.time()
        
        # 运行扫描脚本
        result = subprocess.run(['python', 'split_cidr.py'], 
                              capture_output=True, 
                              text=True)
        
        # 记录扫描结果
        if result.returncode == 0:
            logger.info("扫描任务完成")
            logger.info(f"扫描耗时: {time.time() - start_time:.2f} 秒")
            if result.stdout:
                logger.info(f"扫描输出: {result.stdout}")
        else:
            logger.error(f"扫描任务失败: {result.stderr}")
            
    except Exception as e:
        logger.error(f"执行扫描任务时发生错误: {str(e)}")

def run_scheduler():
    """运行调度器"""
    try:
        # 设置时区为 UTC+8
        tz = pytz.timezone('Asia/Shanghai')
        schedule.every().thursday.at("22:00", tz).do(run_scan)
        
        logger.info(f"调度器启动，设置为每周四 22:00 (UTC+8/Asia/Shanghai) 执行扫描")
        logger.info(f"当前时区时间: {datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # 运行调度器
        while True:
            schedule.run_pending()
            time.sleep(1)
            
    except Exception as e:
        logger.error(f"调度器运行错误: {str(e)}")
        raise

if __name__ == "__main__":
    # 确保数据目录存在
    os.makedirs('data', exist_ok=True)
    
    # 启动调度器
    logger.info("启动调度器...")
    run_scheduler() 