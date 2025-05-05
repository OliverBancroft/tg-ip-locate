from flask import Flask, jsonify
import json
import os
from datetime import datetime
import threading
import time
import subprocess
import sys

app = Flask(__name__)

# Global variable to store the last update time
last_update_time = None
latency_data = None
location = os.getenv('LOCATION', 'SG')

def run_split_cidr():
    """Run split_cidr.py script"""
    try:
        print(f"Running split_cidr.py at {datetime.now()}")
        result = subprocess.run([sys.executable, 'split_cidr.py'], 
                              capture_output=True, 
                              text=True)
        if result.returncode == 0:
            print("split_cidr.py completed successfully")
            return True
        else:
            print(f"split_cidr.py failed with error: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error running split_cidr.py: {e}")
        return False

def load_latency_data():
    """Load latency data from JSON file"""
    global latency_data, last_update_time
    try:
        if os.path.exists('data/telegram_ipv4_24.json'):
            with open('data/telegram_ipv4_24.json', 'r') as f:
                latency_data = json.load(f)
            last_update_time = datetime.now()
            print(f"Latency data loaded at {last_update_time}")
        else:
            print("telegram_ipv4_24.json not found, running split_cidr.py")
            if run_split_cidr():
                # Try loading again after running split_cidr.py
                if os.path.exists('data/telegram_ipv4_24.json'):
                    with open('data/telegram_ipv4_24.json', 'r') as f:
                        latency_data = json.load(f)
                    last_update_time = datetime.now()
                    print(f"Latency data loaded at {last_update_time}")
    except Exception as e:
        print(f"Error loading latency data: {e}")
        latency_data = None

def monitor_latency_file():
    """Monitor the latency file for changes"""
    while True:
        try:
            # Check for file changes
            if os.path.exists('data/telegram_ipv4_24.json'):
                current_mtime = os.path.getmtime('data/telegram_ipv4_24.json')
                if last_update_time is None or current_mtime > last_update_time.timestamp():
                    load_latency_data()
            
            time.sleep(60)  # Check every minute
        except Exception as e:
            print(f"Error in monitor thread: {e}")
            time.sleep(60)

@app.route('/health')
def health_check():
    """Health check endpoint"""
    global last_update_time
    if last_update_time is None:
        return jsonify({
            "status": "error",
            "message": "Latency data not loaded",
            "timestamp": datetime.now().isoformat()
        }), 503
    
    # Check if data is stale (older than 24 hours)
    if (datetime.now() - last_update_time).total_seconds() > 86400:
        return jsonify({
            "status": "warning",
            "message": "Latency data is stale",
            "last_update": last_update_time.isoformat(),
            "timestamp": datetime.now().isoformat()
        }), 200
    
    return jsonify({
        "status": "ok",
        "message": "Service is healthy",
        "last_update": last_update_time.isoformat(),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/latency')
def get_latency():
    """Latency data endpoint"""
    global latency_data, last_update_time
    if latency_data is None:
        return jsonify({
            "status": "error",
            "message": "Latency data not available",
            "timestamp": datetime.now().isoformat()
        }), 503
    
    return jsonify({
        "status": "ok",
        "data": latency_data,
        "last_update": last_update_time.isoformat(),
        "timestamp": datetime.now().isoformat(),
        "location": location
    })

def main():
    # Load initial data
    load_latency_data()
    
    # Start file monitoring in a separate thread
    monitor_thread = threading.Thread(target=monitor_latency_file, daemon=True)
    monitor_thread.start()
    
    # Start the Flask server
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    main() 