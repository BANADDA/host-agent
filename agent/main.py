# host-agent/agent/main.py
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict

import yaml

from .core.database import (cleanup_database, create_deployment,
                            get_expired_deployments, get_gpu_status,
                            init_database, store_gpu_metrics, store_gpu_status,
                            store_health_check, update_deployment_status,
                            update_gpu_status)
from .core.deployment import deploy_container, terminate_deployment
from .core.hardware import (calculate_health_scores, collect_gpu_metrics,
                            collect_system_metrics,
                            get_comprehensive_system_info, get_gpu_info,
                            get_host_info, get_uptime_info)
from .core.monitoring import (start_command_polling, start_duration_monitor,
                              start_gpu_monitoring, start_health_monitoring,
                              start_health_push, start_heartbeat,
                              start_metrics_push)
from .core.registration import register_with_server

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/taolie-host-agent/agent.log')
    ]
)
logger = logging.getLogger(__name__)

class TAOLIEHostAgent:
    def __init__(self):
        self.config = None
        self.agent_id = None
        self.gpu_uuid = None
        self.running = False
        
    def load_config(self):
        """Load configuration from YAML file."""
        config_path = "/etc/taolie-host-agent/config.yaml"
        if not os.path.exists(config_path):
            config_path = "config.yaml"  # Fallback for development
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        logger.info("Configuration loaded successfully")
        
    def validate_config(self):
        """Validate configuration settings."""
        required_fields = [
            'agent.api_key',
            'network.public_ip',
            'network.ports.ssh',
            'network.ports.rental_port_1',
            'network.ports.rental_port_2'
        ]
        
        for field in required_fields:
            keys = field.split('.')
            value = self.config
            for key in keys:
                if key not in value:
                    raise ValueError(f"Missing required configuration: {field}")
                value = value[key]
            
            if not value or value == "your-api-key-here" or value == "123.45.67.89":
                raise ValueError(f"Configuration {field} must be set to a valid value")
        
        logger.info("Configuration validation passed")
        
    def generate_agent_id(self):
        """Generate or load agent ID."""
        if not self.config['agent']['id']:
            import secrets
            self.agent_id = f"agent-{secrets.token_hex(6)}"
            
            # Update config file
            self.config['agent']['id'] = self.agent_id
            config_path = "/etc/taolie-host-agent/config.yaml"
            if not os.path.exists(config_path):
                config_path = "config.yaml"
            
            with open(config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            
            logger.info(f"Generated new agent ID: {self.agent_id}")
        else:
            self.agent_id = self.config['agent']['id']
            logger.info(f"Using existing agent ID: {self.agent_id}")
    
    async def test_network_config(self):
        """Test network configuration and port availability."""
        import socket

        # Test public IP
        current_ip = None
        try:
            import requests
            current_ip = requests.get('https://ifconfig.me', timeout=5).text.strip()
        except:
            pass
        
        configured_ip = self.config['network']['public_ip']
        if current_ip and current_ip != configured_ip:
            logger.warning(f"Your current IP ({current_ip}) doesn't match configured IP ({configured_ip})")
            logger.warning(f"Renters will try to connect to: {configured_ip}")
        
        # Test port availability
        ports = [
            self.config['network']['ports']['ssh'],
            self.config['network']['ports']['rental_port_1'],
            self.config['network']['ports']['rental_port_2']
        ]
        
        for port in ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result == 0:
                logger.error(f"Port {port} is already in use")
                raise ValueError(f"Port {port} is already in use")
            else:
                logger.info(f"Port {port} is available")
    
    async def collect_system_info(self):
        """Collect GPU and host information."""
        gpu_info = get_gpu_info()
        host_info = get_host_info()
        
        return {
            'gpu': gpu_info,
            'host': host_info
        }
    
    async def register_gpu(self):
        """Register GPU with central server."""
        # Check if already registered
        gpu_status = await get_gpu_status()
        if gpu_status and gpu_status.get('gpu_uuid'):
            self.gpu_uuid = gpu_status['gpu_uuid']
            logger.info(f"Already registered with UUID: {self.gpu_uuid}")
            return
        
        # Collect comprehensive system info
        comp_info = get_comprehensive_system_info()
        
        # Prepare comprehensive registration payload
        payload = {
            "host_agent_id": self.agent_id,
            
            # GPU Information
            "gpu_name": comp_info['gpu_name'],
            "gpu_memory_mb": comp_info['gpu_memory_mb'],
            "gpu_count": comp_info['gpu_count'],
            "driver_version": comp_info['driver_version'],
            "cuda_version": comp_info['cuda_version'],
            
            # Host Information
            "hostname": comp_info['hostname'],
            "os": comp_info['os'],
            "cpu_count": comp_info['cpu_count'],
            "cpu_cores": comp_info['cpu_cores'],
            "total_ram_gb": comp_info['total_ram_gb'],
            "total_vram_gb": comp_info['total_vram_gb'],
            
            # Storage Information
            "storage_total_gb": comp_info['storage_total_gb'],
            "storage_type": comp_info['storage_type'],
            "storage_available_gb": comp_info['storage_available_gb'],
            
            # Network Performance
            "upload_speed_mbps": comp_info['upload_speed_mbps'],
            "download_speed_mbps": comp_info['download_speed_mbps'],
            "latency_ms": comp_info['latency_ms'],
            
            # Uptime and Reliability
            "uptime_hours": comp_info['uptime_hours'],
            "last_reboot": comp_info['last_reboot'],
            
            # Network Configuration
            "public_ip": self.config['network']['public_ip'],
            "ssh_port": self.config['network']['ports']['ssh'],
            "rental_port_1": self.config['network']['ports']['rental_port_1'],
            "rental_port_2": self.config['network']['ports']['rental_port_2']
        }
        
        # Register with server
        result = await register_with_server(self.config, payload)
        
        if result['success']:
            self.gpu_uuid = result['gpu_uuid']
            
            # Store in database
            gpu_data = {
                'gpu_id': 'gpu-0',
                'gpu_uuid': self.gpu_uuid,
                'gpu_name': comp_info['gpu_name'],
                'total_vram_mb': comp_info['gpu_memory_mb'],
                'driver_version': comp_info['driver_version'],
                'cuda_version': comp_info['cuda_version'],
                'public_ip': self.config['network']['public_ip'],
                'ssh_port': self.config['network']['ports']['ssh'],
                'rental_port_1': self.config['network']['ports']['rental_port_1'],
                'rental_port_2': self.config['network']['ports']['rental_port_2'],
                'status': 'available',
                'is_healthy': True
            }
            
            await store_gpu_status(gpu_data)
            
            # Update config with GPU UUID
            self.config['gpu']['uuid'] = self.gpu_uuid
            config_path = "/etc/taolie-host-agent/config.yaml"
            if not os.path.exists(config_path):
                config_path = "config.yaml"
            
            with open(config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            
            logger.info(f"Registration successful: {self.gpu_uuid}")
        else:
            raise Exception(f"Registration failed: {result.get('error', 'Unknown error')}")
    
    async def cleanup_orphaned_deployments(self):
        """Check for and cleanup orphaned deployments from previous crashes."""
        try:
            active_deployments = await get_expired_deployments()
            for deployment in active_deployments:
                logger.info(f"Found orphaned deployment: {deployment['deployment_id']}")
                
                # Check if container still exists
                import subprocess
                result = subprocess.run(
                    ['docker', 'ps', '-a', '--filter', f'name={deployment["deployment_id"]}'],
                    capture_output=True, text=True, timeout=10
                )
                
                if deployment['deployment_id'] in result.stdout:
                    # Container exists, check if running
                    running_result = subprocess.run(
                        ['docker', 'inspect', deployment['deployment_id'], '--format', '{{.State.Running}}'],
                        capture_output=True, text=True, timeout=10
                    )
                    
                    if running_result.stdout.strip() == 'true':
                        logger.info(f"Resuming monitoring: {deployment['deployment_id']}")
                    else:
                        # Container stopped, clean up
                        subprocess.run(['docker', 'rm', deployment['deployment_id']], timeout=30)
                        await update_deployment_status(deployment['deployment_id'], 'failed')
                        logger.info(f"Cleaned up stopped container: {deployment['deployment_id']}")
                else:
                    # Container doesn't exist
                    await update_deployment_status(deployment['deployment_id'], 'failed')
                    logger.info(f"Marked as failed: {deployment['deployment_id']}")
                    
        except Exception as e:
            logger.error(f"Error in orphaned deployment cleanup: {e}")
    
    async def start_monitoring_threads(self):
        """Start all 7 monitoring threads."""
        threads = [
            ("GPU Monitoring", start_gpu_monitoring, self.config['monitoring']['metrics_push_interval']),
            ("GPU Health Check", start_health_monitoring, self.config['monitoring']['health_push_interval']),
            ("Heartbeat", start_heartbeat, self.config['monitoring']['heartbeat_interval']),
            ("Command Polling", start_command_polling, self.config['monitoring']['command_poll_interval']),
            ("Metrics Push", start_metrics_push, self.config['monitoring']['metrics_push_interval']),
            ("Health Push", start_health_push, self.config['monitoring']['health_push_interval']),
            ("Duration Monitor", start_duration_monitor, self.config['monitoring']['duration_check_interval'])
        ]
        
        for name, func, interval in threads:
            asyncio.create_task(func(self.config, self.agent_id, interval))
            logger.info(f"{name} thread started")
    
    async def generate_dashboard_html(self):
        """Generate HTML dashboard file."""
        gpu_status = await get_gpu_status()
        gpu_name = gpu_status.get('gpu_name', 'Unknown') if gpu_status else 'Unknown'
        vram = gpu_status.get('total_vram_mb', 0) if gpu_status else 0
        driver = gpu_status.get('driver_version', 'Unknown') if gpu_status else 'Unknown'
        cuda = gpu_status.get('cuda_version', 'Unknown') if gpu_status else 'Unknown'
        
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Taolie Host Agent</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            background: #1a1a1a;
            color: #e0e0e0;
            font-family: 'Consolas', 'Monaco', monospace;
            padding: 20px;
            line-height: 1.6;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: #2a2a2a;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 20px;
        }}
        h1 {{
            color: #00ff88;
            font-size: 20px;
            margin-bottom: 20px;
            border-bottom: 2px solid #444;
            padding-bottom: 10px;
        }}
        .section {{
            margin-bottom: 20px;
        }}
        .section-title {{
            color: #6eb5ff;
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }}
        .info-line {{
            display: flex;
            flex-direction: column;
            padding: 4px 0;
            font-size: 13px;
        }}
        .label {{
            color: #aaa;
            margin-bottom: 4px;
        }}
        .value {{
            color: #00ff88;
        }}
        @media (max-width: 768px) {{
            .info-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        .services {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 8px;
        }}
        .service {{
            color: #00ff88;
            font-size: 13px;
        }}
        .status {{
            display: inline-block;
            color: #00ff88;
            background: rgba(0, 255, 136, 0.1);
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>TAOLIE HOST AGENT <span class="status">● ONLINE</span></h1>
        
        <div class="section">
            <div class="info-grid">
                <div class="info-line">
                    <span class="label">Agent ID:</span>
                    <span class="value">{self.agent_id}</span>
                </div>
                <div class="info-line">
                    <span class="label">GPU UUID:</span>
                    <span class="value">{self.gpu_uuid or 'Not registered'}</span>
                </div>
                <div class="info-line">
                    <span class="label">Model:</span>
                    <span class="value">{gpu_name}</span>
                </div>
                <div class="info-line">
                    <span class="label">VRAM:</span>
                    <span class="value">{vram // 1024} GB ({vram} MB)</span>
                </div>
                <div class="info-line">
                    <span class="label">Driver Version:</span>
                    <span class="value">{driver}</span>
                </div>
                <div class="info-line">
                    <span class="label">CUDA Version:</span>
                    <span class="value">{cuda}</span>
                </div>
                <div class="info-line">
                    <span class="label">Public IP:</span>
                    <span class="value">{self.config['network']['public_ip']}</span>
                </div>
                <div class="info-line">
                    <span class="label">SSH Port:</span>
                    <span class="value">{self.config['network']['ports']['ssh']}</span>
                </div>
                <div class="info-line">
                    <span class="label">Rental Port 1:</span>
                    <span class="value">{self.config['network']['ports']['rental_port_1']}</span>
                </div>
                <div class="info-line">
                    <span class="label">Rental Port 2:</span>
                    <span class="value">{self.config['network']['ports']['rental_port_2']}</span>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Monitoring Services</div>
            <div class="services">
                <div class="service">✓ GPU Monitoring</div>
                <div class="service">✓ Health Checks</div>
                <div class="service">✓ Heartbeat</div>
                <div class="service">✓ Command Polling</div>
                <div class="service">✓ Metrics Push</div>
                <div class="service">✓ Duration Monitor</div>
            </div>
        </div>
    </div>
</body>
</html>"""
        
        # Write to file
        dashboard_path = '/var/www/taolie-dashboard.html'
        try:
            os.makedirs(os.path.dirname(dashboard_path), exist_ok=True)
            with open(dashboard_path, 'w') as f:
                f.write(html_content)
            logger.info(f"Dashboard generated: {dashboard_path}")
        except Exception as e:
            logger.warning(f"Could not write dashboard to {dashboard_path}: {e}")
            # Fallback to current directory
            dashboard_path = 'taolie-dashboard.html'
            with open(dashboard_path, 'w') as f:
                f.write(html_content)
            logger.info(f"Dashboard generated: {dashboard_path}")
    
    async def print_startup_banner(self):
        """Print simple startup information and generate HTML dashboard."""
        gpu_status = await get_gpu_status()
        gpu_name = gpu_status.get('gpu_name', 'Unknown') if gpu_status else 'Unknown'
        vram = gpu_status.get('total_vram_mb', 0) if gpu_status else 0
        driver = gpu_status.get('driver_version', 'Unknown') if gpu_status else 'Unknown'
        cuda = gpu_status.get('cuda_version', 'Unknown') if gpu_status else 'Unknown'
        
        # Generate HTML dashboard
        await self.generate_dashboard_html()
        
        # Print simple banner
        print("\n" + "="*80)
        print("TAOLIE HOST AGENT")
        print("="*80)
        
        print("\n[Agent Information]")
        print(f"  Agent ID:  {self.agent_id}")
        print(f"  GPU UUID:  {self.gpu_uuid or 'Not registered'}")
        print(f"  Status:    ONLINE")
        
        print("\n[GPU Configuration]")
        print(f"  Model:     {gpu_name}")
        print(f"  VRAM:      {vram // 1024} GB ({vram} MB)")
        print(f"  Driver:    {driver}")
        print(f"  CUDA:      {cuda}")
        
        print("\n[Network Configuration]")
        print(f"  Public IP:      {self.config['network']['public_ip']}")
        print(f"  SSH Port:       {self.config['network']['ports']['ssh']}")
        print(f"  Rental Port 1:  {self.config['network']['ports']['rental_port_1']}")
        print(f"  Rental Port 2:  {self.config['network']['ports']['rental_port_2']}")
        
        print("\n[Monitoring Services]")
        print("  ✓ GPU Monitoring")
        print("  ✓ Health Checks")
        print("  ✓ Heartbeat")
        print("  ✓ Command Polling")
        print("  ✓ Metrics Push")
        print("  ✓ Duration Monitor")
        
        print("\n" + "="*80)
        print("All systems operational - Ready to accept GPU rental requests!")
        print("="*80 + "\n")
    
    async def start(self):
        """Main startup sequence."""
        try:
            logger.info("Starting TAOLIE Host Agent...")
            
            # Step 1: Load configuration
            self.load_config()
            
            # Step 2: Validate configuration
            self.validate_config()
            
            # Step 3: Test network configuration
            await self.test_network_config()
            
            # Step 4: Connect to PostgreSQL
            await init_database()
            logger.info("Database initialized successfully")
            
            # Step 5: Generate or load agent ID
            self.generate_agent_id()
            
            # Step 6: Collect GPU information
            system_info = await self.collect_system_info()
            logger.info(f"GPU: {system_info['gpu']['name']}")
            logger.info(f"VRAM: {system_info['gpu']['memory_mb']} MB")
            
            # Step 7: Register with central server
            await self.register_gpu()
            
            # Step 8: Store configuration in PostgreSQL
            # (Already done in register_gpu)
            
            # Step 9: Check for orphaned deployments
            await self.cleanup_orphaned_deployments()
            
            # Step 10: Start monitoring threads
            await self.start_monitoring_threads()
            
            # Print startup banner
            await self.print_startup_banner()
            
            self.running = True
            logger.info("TAOLIE Host Agent started successfully")
            
            # Keep the main thread alive
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start TAOLIE Host Agent: {e}")
            raise
    
    async def stop(self):
        """Stop the agent gracefully."""
        logger.info("Stopping TAOLIE Host Agent...")
        self.running = False
        await cleanup_database()
        logger.info("TAOLIE Host Agent stopped")

async def main():
    """Main entry point."""
    agent = TAOLIEHostAgent()
    
    try:
        await agent.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())