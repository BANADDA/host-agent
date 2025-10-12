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
from .core.hardware import collect_gpu_metrics, get_gpu_info, get_host_info
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
        
        # Collect system info
        system_info = await self.collect_system_info()
        
        # Prepare registration payload
        payload = {
            "host_agent_id": self.agent_id,
            "gpu_specs": system_info['gpu'],
            "host_specs": system_info['host'],
            "network_config": {
                "public_ip": self.config['network']['public_ip'],
                "ssh_port": self.config['network']['ports']['ssh'],
                "rental_port_1": self.config['network']['ports']['rental_port_1'],
                "rental_port_2": self.config['network']['ports']['rental_port_2']
            }
        }
        
        # Register with server
        result = await register_with_server(self.config, payload)
        
        if result['success']:
            self.gpu_uuid = result['gpu_uuid']
            
            # Store in database
            gpu_data = {
                'gpu_id': 'gpu-0',
                'gpu_uuid': self.gpu_uuid,
                'gpu_name': system_info['gpu']['name'],
                'total_vram_mb': system_info['gpu']['memory_mb'],
                'driver_version': system_info['gpu']['driver_version'],
                'cuda_version': system_info['gpu']['cuda_version'],
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
    
    async def print_startup_banner(self):
        """Print the beautiful startup banner."""
        gpu_status = await get_gpu_status()
        gpu_name = gpu_status.get('gpu_name', 'Unknown') if gpu_status else 'Unknown'
        vram = gpu_status.get('total_vram_mb', 0) if gpu_status else 0
        driver = gpu_status.get('driver_version', 'Unknown') if gpu_status else 'Unknown'
        cuda = gpu_status.get('cuda_version', 'Unknown') if gpu_status else 'Unknown'
        
        # ANSI color codes
        PURPLE = '\033[95m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
        
        print("")
        print(f"{PURPLE}{'═' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║{BOLD}  ████████╗ █████╗  ██████╗ ██╗     ██╗███████╗                              {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{BOLD}  ╚══██╔══╝██╔══██╗██╔═══██╗██║     ██║██╔════╝                              {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{BOLD}     ██║   ███████║██║   ██║██║     ██║█████╗                                {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{BOLD}     ██║   ██╔══██║██║   ██║██║     ██║██╔══╝                                {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{BOLD}     ██║   ██║  ██║╚██████╔╝███████╗██║███████╗                              {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{BOLD}     ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝╚══════╝                              {RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}██╗  ██╗ ██████╗ ███████╗████████╗     █████╗  ██████╗ ███████╗███████╗████████╗{RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║  {BOLD}██║  ██║██╔═══██╗██╔════╝╚══██╔══╝    ██╔══██╗██╔════╝ ██╔════╝██╔════╝╚══██╔══╝{RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║  {BOLD}███████║██║   ██║███████╗   ██║       ███████║██║  ███╗█████╗  ███████╗   ██║   {RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║  {BOLD}██╔══██║██║   ██║╚════██║   ██║       ██╔══██║██║   ██║██╔══╝  ╚════██║   ██║   {RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║  {BOLD}██║  ██║╚██████╔╝███████║   ██║       ██║  ██║╚██████╔╝███████╗███████║   ██║   {RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║  {BOLD}╚═╝  ╚═╝ ╚═════╝ ╚══════╝   ╚═╝       ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝   ╚═╝   {RESET}  {PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║{GREEN}{BOLD}                    🚀 Successfully Started & Ready{' ' * 28}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'═' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}{CYAN}💎 Agent Information{RESET}{' ' * 56}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Agent ID:{RESET}      {GREEN}{self.agent_id[:40]:<40}{RESET}      {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}GPU UUID:{RESET}      {GREEN}{(self.gpu_uuid or 'Not registered')[:40]:<40}{RESET}      {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Status:{RESET}        {GREEN}● ONLINE{' ' * 48}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'─' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}{CYAN}🎮 GPU Configuration{RESET}{' ' * 56}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Model:{RESET}         {GREEN}{gpu_name[:45]:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}VRAM:{RESET}          {GREEN}{vram // 1024} GB ({vram} MB){' ' * 40}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Driver:{RESET}        {GREEN}{driver:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}CUDA:{RESET}          {GREEN}{cuda:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Health:{RESET}        {GREEN}✓ Healthy & Available{' ' * 43}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'─' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}{CYAN}🌐 Network Configuration{RESET}{' ' * 52}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Public IP:{RESET}     {GREEN}{self.config['network']['public_ip']:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}SSH Port:{RESET}      {GREEN}{self.config['network']['ports']['ssh']:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Rental Port 1:{RESET} {GREEN}{self.config['network']['ports']['rental_port_1']:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Rental Port 2:{RESET} {GREEN}{self.config['network']['ports']['rental_port_2']:<45}{RESET}     {PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'─' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}{CYAN}📊 Monitoring Services{RESET}{' ' * 54}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║    {GREEN}✓{RESET} GPU Monitoring        {GREEN}✓{RESET} Health Checks          {GREEN}✓{RESET} Heartbeat          {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {GREEN}✓{RESET} Command Polling       {GREEN}✓{RESET} Metrics Push           {GREEN}✓{RESET} Duration Monitor   {PURPLE}║{RESET}")
        print(f"{PURPLE}║    {GREEN}✓{RESET} Central Server Connected                                              {PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'─' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {BOLD}{CYAN}📝 Quick Actions{RESET}{' ' * 60}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}View Logs:{RESET}         {CYAN}tail -f /var/log/taolie-host-agent/agent.log{' ' * 13}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Check Status:{RESET}      {CYAN}docker logs -f taolie-host-agent{' ' * 25}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║    {YELLOW}Dashboard:{RESET}         {CYAN}https://platform.taolie.com/dashboard{' ' * 20}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'═' * 80}{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}║  {GREEN}{BOLD}🎉 All systems operational - Ready to accept GPU rental requests!{' ' * 13}{RESET}{PURPLE}║{RESET}")
        print(f"{PURPLE}║{' ' * 78}║{RESET}")
        print(f"{PURPLE}{'═' * 80}{RESET}")
        print("")
    
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