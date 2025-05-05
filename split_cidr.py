import requests
import ipaddress
import sys
import json
import nmap
import time
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from queue import Queue
from threading import Lock
import os
import logging

# 创建data目录（如果不存在）
os.makedirs('data', exist_ok=True)

# 配置日志
log_filename = os.path.join('data', f'scan_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def download_cidr_list(url):
    """下载CIDR列表"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"下载CIDR列表失败: {str(e)}")
        raise

def extract_ipv4_cidrs(text):
    """提取IPv4 CIDR"""
    cidrs = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            try:
                network = ipaddress.ip_network(line)
                if network.version == 4:
                    cidrs.append(str(network))
            except ValueError:
                continue
    return cidrs

def split_cidr_to_24(cidr):
    """将CIDR分割成/24子网"""
    try:
        network = ipaddress.ip_network(cidr)
        if network.prefixlen >= 24:
            return [str(network)]
        return [str(subnet) for subnet in network.subnets(new_prefix=24)]
    except Exception as e:
        logger.error(f"分割CIDR {cidr} 失败: {str(e)}")
        return []

def get_ping_latency(ip):
    """使用ping测试延迟"""
    try:
        result = subprocess.run(['ping', '-c', '3', '-W', '1', ip], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            # 提取平均延迟
            for line in result.stdout.splitlines():
                if 'avg' in line:
                    try:
                        avg = float(line.split('/')[-3])
                        return avg
                    except (IndexError, ValueError):
                        continue
    except Exception as e:
        logger.error(f"Ping测试 {ip} 失败: {str(e)}")
    return None

def get_mtr_latency(ip):
    """使用mtr测试延迟"""
    try:
        result = subprocess.run(['mtr', '--json', '-c', '3', ip], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if 'report' in data and 'hubs' in data['report']:
                    # 获取所有跳的延迟
                    latencies = []
                    for hub in data['report']['hubs']:
                        # 跳过丢包率100%的跳
                        if hub.get('Loss%', 0) >= 100:
                            continue
                        # 检查是否有有效的延迟数据
                        if 'Avg' in hub and isinstance(hub['Avg'], (int, float)) and hub['Avg'] > 0:
                            latencies.append(hub['Avg'])
                    
                    # 如果有有效的延迟数据，返回最后一个有效延迟
                    if latencies:
                        logger.info(f"MTR测试 {ip} 成功，找到 {len(latencies)} 个有效延迟")
                        return latencies[-1]
                    else:
                        logger.warning(f"MTR测试 {ip} 未找到有效延迟")
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error(f"解析mtr结果失败: {str(e)}")
    except Exception as e:
        logger.error(f"MTR测试 {ip} 失败: {str(e)}")
    return None

def scan_subnet(subnet):
    """扫描子网并测试延迟"""
    try:
        # 使用nmap扫描整个网段
        nmap_cmd = ['nmap', '-sn', subnet]
        result = subprocess.run(nmap_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.warning(f"子网 {subnet} nmap扫描失败")
            return {
                'subnet': subnet,
                'reachable': False,
                'latency': None,
                'method': None,
                'test_ip': None
            }
        
        # 提取所有可达的IP
        reachable_ips = []
        for line in result.stdout.splitlines():
            if 'Nmap scan report for' in line:
                # 从输出中提取IP地址
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if ip_match:
                    reachable_ips.append(ip_match.group(1))
        
        if not reachable_ips:
            logger.warning(f"子网 {subnet} 没有发现可达IP")
            return {
                'subnet': subnet,
                'reachable': False,
                'latency': None,
                'method': None,
                'test_ip': None
            }
        
        # 测试所有可达IP的延迟
        best_latency = float('inf')
        best_ip = None
        best_method = None
        
        for ip in reachable_ips:
            # 尝试ping
            ping_result = get_ping_latency(ip)
            if ping_result is not None and ping_result < best_latency:
                best_latency = ping_result
                best_ip = ip
                best_method = 'ping'
            
            # 如果ping失败或延迟较高，尝试mtr
            if ping_result is None or ping_result > 100:
                mtr_result = get_mtr_latency(ip)
                if mtr_result is not None and mtr_result < best_latency:
                    best_latency = mtr_result
                    best_ip = ip
                    best_method = 'mtr'
        
        if best_ip is not None:
            logger.info(f"子网 {subnet} 最佳延迟: {best_ip}, {best_method}: {best_latency:.2f}ms")
            return {
                'subnet': subnet,
                'reachable': True,
                'latency': best_latency,
                'method': best_method,
                'test_ip': best_ip
            }
        
        logger.warning(f"子网 {subnet} 所有IP延迟测试失败")
        return {
            'subnet': subnet,
            'reachable': False,
            'latency': None,
            'method': None,
            'test_ip': None
        }
    except Exception as e:
        logger.error(f"扫描子网 {subnet} 时发生错误: {str(e)}")
        return {
            'subnet': subnet,
            'reachable': False,
            'latency': None,
            'method': None,
            'test_ip': None
        }

def main():
    """主函数"""
    start_time = time.time()
    logger.info("开始执行IP扫描任务")
    
    # 下载CIDR列表
    url = "https://core.telegram.org/resources/cidr.txt"
    logger.info(f"正在从 {url} 下载CIDR列表")
    cidr_text = download_cidr_list(url)
    
    # 提取IPv4 CIDR
    logger.info("正在提取IPv4 CIDR")
    ipv4_cidrs = extract_ipv4_cidrs(cidr_text)
    logger.info(f"找到 {len(ipv4_cidrs)} 个IPv4 CIDR")
    
    # 分割成/24子网
    logger.info("正在分割CIDR为/24子网")
    subnets = []
    for cidr in ipv4_cidrs:
        subnets.extend(split_cidr_to_24(cidr))
    logger.info(f"分割得到 {len(subnets)} 个/24子网")
    
    # 并行扫描子网
    logger.info("开始扫描子网")
    results = []
    # 使用10个线程并行扫描，每个线程负责一个子网
    # 考虑到每个子网扫描都会使用nmap、ping和mtr，所以不要设置太多线程
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_subnet = {executor.submit(scan_subnet, subnet): subnet for subnet in subnets}
        for future in as_completed(future_to_subnet):
            subnet = future_to_subnet[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"处理子网 {subnet} 时发生错误: {str(e)}")
    
    # 整理结果
    output = {
        'original_cidrs': ipv4_cidrs,
        'subnets': results,
        'scan_time': time.time() - start_time,
        'total_subnets': len(subnets),
        'reachable_subnets': len([r for r in results if r['reachable']]),
        'scan_timestamp': datetime.now().isoformat()
    }
    
    # 保存结果到JSON文件
    output_file = os.path.join('data', 'telegram_ipv4_24.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    logger.info(f"扫描完成，结果已保存到 {output_file}")
    logger.info(f"总扫描时间: {time.time() - start_time:.2f} 秒")
    logger.info(f"总子网数: {len(subnets)}")
    logger.info(f"可达子网数: {len([r for r in results if r['reachable']])}")

if __name__ == "__main__":
    main() 