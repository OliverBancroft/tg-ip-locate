import requests
import ipaddress
import sys
import json
import nmap
import time
import subprocess
import re
from datetime import datetime
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
        # 使用python-nmap扫描整个网段
        nm = nmap.PortScanner()
        nm.scan(hosts=subnet, arguments='-sn')
        
        # 提取所有可达的IP
        reachable_ips = []
        for host in nm.all_hosts():
            if nm[host].state() == 'up':
                reachable_ips.append(host)
        
        if not reachable_ips:
            logger.warning(f"子网 {subnet} 没有发现可达IP，尝试使用mtr")
            # 如果nmap没有发现可达IP，使用mtr测试
            test_ip = str(ipaddress.ip_network(subnet).network_address + 1)
            mtr_result = get_mtr_latency(test_ip)
            if mtr_result is not None:
                logger.info(f"子网 {subnet} 通过mtr发现可达: {test_ip}, 延迟: {mtr_result:.2f}ms")
                return {
                    'subnet': subnet,
                    'reachable': True,
                    'latency': mtr_result,
                    'method': 'mtr',
                    'test_ip': test_ip
                }
            return {
                'subnet': subnet,
                'reachable': False,
                'latency': None,
                'method': None,
                'test_ip': None
            }
        
        # 使用第一个可达IP进行ping测试
        test_ip = reachable_ips[0]
        logger.info(f"子网 {subnet} 选择可达IP {test_ip} 进行ping测试")
        
        # 对选中的IP进行3次ping测试，取最低延迟
        best_latency = float('inf')
        for _ in range(3):
            ping_result = get_ping_latency(test_ip)
            if ping_result is not None and ping_result < best_latency:
                best_latency = ping_result
        
        # 如果ping测试成功（有任何一个ping成功），返回结果
        if best_latency != float('inf'):
            logger.info(f"子网 {subnet} ping测试成功: {test_ip}, 最低延迟: {best_latency:.2f}ms")
            return {
                'subnet': subnet,
                'reachable': True,
                'latency': best_latency,
                'method': 'ping',
                'test_ip': test_ip
            }
        
        # 如果ping测试失败，使用mtr
        logger.info(f"子网 {subnet} ping测试失败，尝试mtr")
        mtr_result = get_mtr_latency(test_ip)
        if mtr_result is not None:
            logger.info(f"子网 {subnet} mtr测试成功: {test_ip}, 延迟: {mtr_result:.2f}ms")
            return {
                'subnet': subnet,
                'reachable': True,
                'latency': mtr_result,
                'method': 'mtr',
                'test_ip': test_ip
            }
        
        # 如果mtr也失败（这种情况不应该发生），尝试其他可达IP
        logger.warning(f"子网 {subnet} 选中的IP {test_ip} mtr测试失败，尝试其他IP")
        for ip in reachable_ips[1:]:  # 跳过已经测试过的IP
            mtr_result = get_mtr_latency(ip)
            if mtr_result is not None:
                logger.info(f"子网 {subnet} 通过mtr发现可达: {ip}, 延迟: {mtr_result:.2f}ms")
                return {
                    'subnet': subnet,
                    'reachable': True,
                    'latency': mtr_result,
                    'method': 'mtr',
                    'test_ip': ip
                }
        
        # 如果所有方法都失败（这种情况不应该发生），返回失败
        logger.error(f"子网 {subnet} 所有测试方法都失败，这不应该发生")
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
    
    # 顺序扫描子网
    logger.info("开始扫描子网")
    results = []
    for subnet in subnets:
        try:
            result = scan_subnet(subnet)
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