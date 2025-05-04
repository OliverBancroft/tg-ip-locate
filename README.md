# Telegram IP Locator

A tool to locate and test Telegram IP ranges.

## Features

- Downloads and processes Telegram's IP ranges
- Splits CIDR ranges into /24 subnets
- Tests subnet reachability using nmap
- Measures latency using ping and mtr
- Provides detailed logging and JSON output

## Installation

1. Clone the repository:
```bash
git clone https://github.com/oliverbancroft/tg-ip-locator.git
cd tg-ip-locator
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install system dependencies:
```bash
# For Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y nmap mtr

# For CentOS/RHEL
sudo yum install -y nmap mtr
```

## Usage

Run the script:
```bash
python split_cidr.py
```

The script will:
1. Download Telegram's IP ranges
2. Process and split them into /24 subnets
3. Test each subnet for reachability
4. Measure latency for reachable IPs
5. Save results to `telegram_ipv4_24.json`

## Output Format

The output JSON file contains:
- Original CIDR ranges
- Split /24 subnets
- Reachability status
- Latency measurements
- Test method used (ping/mtr)

## Docker Support

The project includes Docker support for easy deployment:

1. Build the Docker image:
```bash
docker build -t tg-ip-locator .
```

2. Run the container:
```bash
docker run -v $(pwd):/app tg-ip-locator
```

## API Endpoints

The service provides two HTTP endpoints:

1. Health Check:
```bash
curl http://localhost:8000/health
```

2. Latency Test:
```bash
curl http://localhost:8000/latency?ip=1.2.3.4
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

OliverBancroft
