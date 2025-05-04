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

def download_cidr_list(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text.splitlines()
    except requests.RequestException as e:
        print(f"Error downloading CIDR list: {e}")
        sys.exit(1)

def extract_ipv4_cidrs(lines):
    ipv4_cidrs = []
    for line in lines:
        line = line.strip()
        if not line or ':' in line:  # Skip empty lines and IPv6 addresses
            continue
        try:
            network = ipaddress.ip_network(line)
            if network.version == 4:  # Only keep IPv4 addresses
                ipv4_cidrs.append(network)
        except ValueError as e:
            print(f"Warning: Invalid CIDR format '{line}': {e}")
    return ipv4_cidrs

def get_ping_latency(ip):
    try:
        # Run ping with -c 3 (3 packets), -W 1 (1 second timeout)
        cmd = ['ping', '-c', '3', '-W', '1', ip]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return None
            
        # Parse ping output to get min latency
        lines = result.stdout.split('\n')
        for line in lines:
            if 'min/avg/max' in line:
                try:
                    # Extract min latency from output like "min/avg/max = 1.234/2.345/3.456"
                    min_latency = float(line.split('=')[1].split('/')[0].strip())
                    return min_latency
                except (IndexError, ValueError):
                    return None
        return None
    except Exception as e:
        print(f"Error running ping for {ip}: {e}")
        return None

def get_mtr_latency(ip):
    try:
        # Run mtr with -n (no DNS), -c 3 (3 cycles), --json output
        cmd = ['mtr', '-n', '-c', '3', '--json', ip]
        print(f"Running mtr command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"mtr command failed for {ip} with return code {result.returncode}")
            print(f"Error output: {result.stderr}")
            return None
            
        # Parse JSON output
        try:
            print(f"mtr raw output for {ip}: {result.stdout[:200]}...")  # Print first 200 chars
            mtr_data = json.loads(result.stdout)
            if not mtr_data or 'report' not in mtr_data:
                print(f"No report data in mtr output for {ip}")
                return None
                
            # Get the last two hops' latencies
            hubs = mtr_data['report']['hubs']
            if not hubs:
                print(f"No hops found in mtr output for {ip}")
                return None
                
            print(f"Found {len(hubs)} hops for {ip}")
            
            # Get latencies from the last two hops
            latencies = []
            for hub in reversed(hubs):
                # Skip hops with 100% loss
                if hub.get('Loss%', 0) >= 100:
                    print(f"Skipping hop {hub.get('host', 'unknown')} due to 100% loss")
                    continue
                    
                # Check if the hub has valid latency data
                if 'Avg' in hub and isinstance(hub['Avg'], (int, float)) and hub['Avg'] > 0:
                    latencies.append(hub['Avg'])
                    print(f"Found latency {hub['Avg']}ms for hop {hub.get('host', 'unknown')}")
                elif 'Avg' in hub:
                    print(f"Invalid latency value for hop {hub.get('host', 'unknown')}: {hub['Avg']}")
                if len(latencies) >= 2:
                    break
            
            # If we found any valid latencies, use the first one
            if latencies:
                selected_latency = latencies[0]
                print(f"Selected latency {selected_latency}ms for {ip}")
                return selected_latency
                    
            print(f"No valid latency found for {ip}")
            # Print the full hub data for debugging
            print("Hub data:")
            for hub in hubs:
                print(f"  Host: {hub.get('host', 'unknown')}, Loss%: {hub.get('Loss%', 'N/A')}, Avg: {hub.get('Avg', 'N/A')}")
            return None
        except json.JSONDecodeError as e:
            print(f"Error parsing mtr JSON output for {ip}: {e}")
            print(f"Raw output: {result.stdout}")
            return None
            
    except Exception as e:
        print(f"Error running mtr for {ip}: {e}")
        return None

def scan_subnet(subnet):
    try:
        # First try nmap ping scan
        nm = nmap.PortScanner()
        result = nm.scan(hosts=subnet, arguments='-sn -T5 --min-parallelism 100 --max-retries 1 --host-timeout 2s')
        
        ping_result = None
        # Check if any hosts are up
        for host in nm.all_hosts():
            if nm[host].state() == 'up':
                # Found a reachable IP, now test its latency with ping
                latency = get_ping_latency(host)
                if latency is not None:
                    ping_result = {
                        "ip": host,
                        "latency": latency,
                        "method": "ping",
                        "timestamp": datetime.now().isoformat()
                    }
                    print(f"Found ping result for {subnet}: {host} with latency {latency}ms")
                    break
        
        # If ping scan failed or no latency found, try mtr on .55 IP
        if ping_result is None:
            print(f"No ping result found for {subnet}, trying mtr...")
            network = ipaddress.ip_network(subnet)
            test_ip = str(network.network_address + 55)
            latency = get_mtr_latency(test_ip)
            
            if latency is not None:
                mtr_result = {
                    "ip": test_ip,
                    "latency": latency,
                    "method": "mtr",
                    "timestamp": datetime.now().isoformat()
                }
                print(f"Found mtr result for {subnet}: {test_ip} with latency {latency}ms")
                return mtr_result
            else:
                print(f"No mtr result found for {subnet}")
        
        return ping_result
            
    except Exception as e:
        print(f"Error scanning subnet {subnet}: {e}")
        return None

def split_to_24(ipv4_cidrs):
    all_subnets = []
    for network in ipv4_cidrs:
        original_cidr = str(network)
        if network.prefixlen <= 24:
            # Split into /24 subnets
            for subnet in network.subnets(new_prefix=24):
                all_subnets.append({
                    "original_cidr": original_cidr,
                    "subnet": str(subnet)
                })
        else:
            # If already smaller than /24, keep as is
            all_subnets.append({
                "original_cidr": original_cidr,
                "subnet": original_cidr
            })
    return all_subnets

def scan_all_subnets(subnets):
    print("Starting subnet scanning...")
    results = {}
    print_lock = Lock()
    
    def process_result(future):
        try:
            result = future.result()
            if result:
                with print_lock:
                    print(f"[{result['timestamp']}] Found {result['method']} result for subnet {future.subnet}:")
                    print(f"  IP: {result['ip']}")
                    print(f"  Latency: {result['latency']:.2f}ms")
                    print(f"  Method: {result['method']}")
                
                if future.original_cidr not in results:
                    results[future.original_cidr] = {
                        "original_cidr": future.original_cidr,
                        "subnets": [],
                        "reachable_ips": []
                    }
                
                # Add subnet information
                subnet_info = {
                    "subnet": future.subnet,
                    "reachable": result is not None
                }
                if subnet_info not in results[future.original_cidr]["subnets"]:
                    results[future.original_cidr]["subnets"].append(subnet_info)
                
                # Add reachable IP information
                if result:
                    results[future.original_cidr]["reachable_ips"].append({
                        "subnet": future.subnet,
                        "reachable_ip": result["ip"],
                        "latency": result["latency"],
                        "method": result["method"],
                        "timestamp": result["timestamp"]
                    })
        except Exception as e:
            print(f"Error processing result for subnet {future.subnet}: {e}")

    # Increase max_workers for more parallel scanning
    with ThreadPoolExecutor(max_workers=100) as executor:
        futures = []
        for subnet_info in subnets:
            future = executor.submit(scan_subnet, subnet_info["subnet"])
            future.subnet = subnet_info["subnet"]
            future.original_cidr = subnet_info["original_cidr"]
            future.add_done_callback(process_result)
            futures.append(future)
        
        # Wait for all futures to complete
        for future in futures:
            future.result()
    
    return list(results.values())

def main():
    url = "https://core.telegram.org/resources/cidr.txt"
    output_file = "telegram_ipv4_24.json"
    
    print("Downloading CIDR list...")
    cidr_lines = download_cidr_list(url)
    
    print("Extracting IPv4 addresses...")
    ipv4_cidrs = extract_ipv4_cidrs(cidr_lines)
    
    print("Splitting into /24 subnets...")
    subnets = split_to_24(ipv4_cidrs)
    
    print("Scanning subnets for reachable IPs...")
    result = scan_all_subnets(subnets)
    
    print(f"Writing results to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    
    print("Done!")

if __name__ == "__main__":
    main() 