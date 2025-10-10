# host-agent/agent/core/database.py
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import asyncpg
import yaml

logger = logging.getLogger(__name__)

# Database connection
db_pool = None

def load_config():
    """Load configuration from YAML file."""
    config_path = "/etc/taolie-host-agent/config.yaml"
    if not os.path.exists(config_path):
        config_path = "config.yaml"  # Fallback for development
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

async def init_database():
    """Initialize PostgreSQL database connection."""
    global db_pool
    try:
        config = load_config()
        db_config = config['database']
        
        db_pool = await asyncpg.create_pool(
            host=db_config['host'],
            port=db_config['port'],
            user=db_config['user'],
            password=db_config['password'],
            database=db_config['name'],
            min_size=1,
            max_size=10
        )
        
        # Create tables with new schema
        async with db_pool.acquire() as conn:
            # GPU Status Table with network configuration
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS gpu_status (
                    id SERIAL PRIMARY KEY,
                    gpu_id VARCHAR(100) NOT NULL UNIQUE,
                    gpu_uuid VARCHAR(255) UNIQUE,
                    
                    -- GPU Hardware Info
                    gpu_name VARCHAR(255),
                    driver_version VARCHAR(50),
                    cuda_version VARCHAR(50),
                    total_vram_mb INTEGER,
                    
                    -- Network Configuration
                    public_ip VARCHAR(255) NOT NULL,
                    ssh_port INTEGER NOT NULL,
                    rental_port_1 INTEGER NOT NULL,
                    rental_port_2 INTEGER NOT NULL,
                    
                    -- Current Status
                    status VARCHAR(50) NOT NULL,
                    is_healthy BOOLEAN DEFAULT true,
                    
                    -- Current Metrics
                    gpu_utilization DECIMAL(5,2),
                    vram_used_mb INTEGER,
                    temperature_celsius DECIMAL(5,2),
                    power_draw_watts DECIMAL(6,2),
                    fan_speed_percent DECIMAL(5,2),
                    
                    -- Health indicators
                    last_health_check TIMESTAMP,
                    consecutive_failures INTEGER DEFAULT 0,
                    
                    -- Availability
                    current_deployment_id VARCHAR(255),
                    
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Deployments Table with port assignments
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS deployments (
                    id SERIAL PRIMARY KEY,
                    deployment_id VARCHAR(255) UNIQUE NOT NULL,
                    gpu_id VARCHAR(100) NOT NULL,
                    template_type VARCHAR(50) NOT NULL,
                    container_id VARCHAR(255),
                    status VARCHAR(50) NOT NULL,
                    
                    -- Timing
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_minutes INTEGER NOT NULL,
                    
                    -- User info
                    user_id VARCHAR(255),
                    
                    -- Network Access Info (what ports the container is exposed on)
                    ssh_port INTEGER,           -- For SSH access (management)
                    rental_port_1 INTEGER,      -- Primary rental port
                    rental_port_2 INTEGER,      -- Secondary rental port
                    
                    -- Container Access Credentials
                    ssh_username VARCHAR(100),
                    ssh_password VARCHAR(255),
                    
                    -- Metadata
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW(),
                    
                    FOREIGN KEY (gpu_id) REFERENCES gpu_status(gpu_id)
                )
            ''')
            
            # GPU Metrics Table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS gpu_metrics (
                    id SERIAL PRIMARY KEY,
                    gpu_id VARCHAR(100) NOT NULL,
                    deployment_id VARCHAR(255),
                    
                    -- GPU Metrics
                    gpu_utilization DECIMAL(5,2),
                    vram_used_mb INTEGER,
                    vram_total_mb INTEGER,
                    temperature_celsius DECIMAL(5,2),
                    power_draw_watts DECIMAL(6,2),
                    fan_speed_percent DECIMAL(5,2),
                    
                    -- Container metrics (only if deployment_id is set)
                    container_status VARCHAR(50),
                    uptime_seconds INTEGER,
                    
                    timestamp TIMESTAMP DEFAULT NOW(),
                    
                    FOREIGN KEY (gpu_id) REFERENCES gpu_status(gpu_id),
                    FOREIGN KEY (deployment_id) REFERENCES deployments(deployment_id)
                )
            ''')
            
            # GPU Health History Table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS gpu_health_history (
                    id SERIAL PRIMARY KEY,
                    gpu_id VARCHAR(100) NOT NULL,
                    
                    health_status VARCHAR(50) NOT NULL,
                    
                    -- Health checks
                    driver_responsive BOOLEAN,
                    temperature_normal BOOLEAN,
                    power_normal BOOLEAN,
                    no_ecc_errors BOOLEAN,
                    fan_operational BOOLEAN,
                    
                    -- Error details
                    error_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Health Checks Table (for deployments)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS health_checks (
                    id SERIAL PRIMARY KEY,
                    deployment_id VARCHAR(255) REFERENCES deployments(deployment_id),
                    
                    health_status VARCHAR(50) NOT NULL,
                    container_running BOOLEAN,
                    gpu_accessible BOOLEAN,
                    temperature_safe BOOLEAN,
                    
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Command Queue Table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS command_queue (
                    id SERIAL PRIMARY KEY,
                    command_id VARCHAR(255) UNIQUE NOT NULL,
                    host_agent_id VARCHAR(255) NOT NULL,
                    type VARCHAR(50) NOT NULL,
                    data JSONB NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW(),
                    processed_at TIMESTAMP
                )
            ''')
            
            # Create indexes
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_gpu_status_gpu_uuid ON gpu_status(gpu_uuid);
                CREATE INDEX IF NOT EXISTS idx_gpu_status_status ON gpu_status(status);
                CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status);
                CREATE INDEX IF NOT EXISTS idx_deployments_gpu_id ON deployments(gpu_id);
                CREATE INDEX IF NOT EXISTS idx_gpu_metrics_deployment ON gpu_metrics(deployment_id);
                CREATE INDEX IF NOT EXISTS idx_gpu_metrics_timestamp ON gpu_metrics(timestamp);
                CREATE INDEX IF NOT EXISTS idx_command_queue_status ON command_queue(status);
                CREATE INDEX IF NOT EXISTS idx_command_queue_agent ON command_queue(host_agent_id);
            ''')
            
        logger.info("Database initialized successfully with new schema")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

# New database functions for the updated schema

async def store_gpu_status(gpu_data: Dict[str, Any]):
    """Store or update GPU status in the database."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot store GPU status")
        raise Exception("Database not initialized")
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO gpu_status (
                    gpu_id, gpu_uuid, gpu_name, total_vram_mb,
                    driver_version, cuda_version,
                    public_ip, ssh_port, rental_port_1, rental_port_2,
                    status, is_healthy
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (gpu_uuid) DO UPDATE SET
                    gpu_name = EXCLUDED.gpu_name,
                    total_vram_mb = EXCLUDED.total_vram_mb,
                    driver_version = EXCLUDED.driver_version,
                    cuda_version = EXCLUDED.cuda_version,
                    public_ip = EXCLUDED.public_ip,
                    ssh_port = EXCLUDED.ssh_port,
                    rental_port_1 = EXCLUDED.rental_port_1,
                    rental_port_2 = EXCLUDED.rental_port_2,
                    status = EXCLUDED.status,
                    is_healthy = EXCLUDED.is_healthy,
                    updated_at = NOW()
            ''', 
                gpu_data['gpu_id'],
                gpu_data['gpu_uuid'],
                gpu_data['gpu_name'],
                gpu_data['total_vram_mb'],
                gpu_data['driver_version'],
                gpu_data['cuda_version'],
                gpu_data['public_ip'],
                gpu_data['ssh_port'],
                gpu_data['rental_port_1'],
                gpu_data['rental_port_2'],
                gpu_data['status'],
                gpu_data['is_healthy']
            )
            
        logger.info(f"GPU status stored/updated for {gpu_data['gpu_uuid']}")
        
    except Exception as e:
        logger.error(f"Failed to store GPU status: {e}")
        raise

async def create_deployment(deployment_data: Dict[str, Any]):
    """Create a new deployment record."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot create deployment")
        raise Exception("Database not initialized")
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO deployments (
                    deployment_id, gpu_id, template_type, status,
                    start_time, duration_minutes, user_id,
                    ssh_port, rental_port_1, rental_port_2
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''', 
                deployment_data['deployment_id'],
                deployment_data['gpu_id'],
                deployment_data['template_type'],
                deployment_data['status'],
                deployment_data['start_time'],
                deployment_data['duration_minutes'],
                deployment_data['user_id'],
                deployment_data['ssh_port'],
                deployment_data['rental_port_1'],
                deployment_data['rental_port_2']
            )
            
        logger.info(f"Deployment {deployment_data['deployment_id']} created")
        
    except Exception as e:
        logger.error(f"Failed to create deployment: {e}")
        raise

async def update_deployment_status(deployment_id: str, status: str, **kwargs):
    """Update deployment status and optional fields."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot update deployment")
        return
    
    try:
        async with db_pool.acquire() as conn:
            # Build dynamic update query
            set_clauses = ["status = $2", "updated_at = NOW()"]
            values = [deployment_id, status]
            param_count = 2
            
            for key, value in kwargs.items():
                if value is not None:
                    param_count += 1
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
            
            query = f"UPDATE deployments SET {', '.join(set_clauses)} WHERE deployment_id = $1"
            await conn.execute(query, *values)
            
        logger.info(f"Deployment {deployment_id} status updated to {status}")
        
    except Exception as e:
        logger.error(f"Failed to update deployment status: {e}")

async def get_expired_deployments():
    """Get all expired deployments that need to be terminated."""
    if db_pool is None:
        logger.warning("Database not initialized, skipping expired deployments check")
        return []
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT d.deployment_id, d.container_id, d.gpu_id,
                       d.start_time, d.duration_minutes, d.user_id,
                       g.gpu_uuid, g.public_ip
                FROM deployments d
                JOIN gpu_status g ON d.gpu_id = g.gpu_id
                WHERE d.status = 'running'
                AND NOW() >= (d.start_time + (d.duration_minutes || ' minutes')::INTERVAL)
            ''')
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        logger.error(f"Failed to get expired deployments: {e}")
        return []

async def get_active_deployments():
    """Get all active deployments."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot get active deployments")
        return []
    
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT deployment_id, container_id, gpu_id, start_time, duration_minutes
                FROM deployments 
                WHERE status = 'running'
                ORDER BY start_time
            ''')
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        logger.error(f"Failed to get active deployments: {e}")
        return []

async def store_gpu_metrics(gpu_id: str, metrics: Dict[str, Any], deployment_id: str = None):
    """Store GPU metrics in the database."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot store metrics")
        return
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO gpu_metrics (
                    gpu_id, deployment_id, gpu_utilization,
                    vram_used_mb, vram_total_mb, temperature_celsius,
                    power_draw_watts, fan_speed_percent,
                    container_status, uptime_seconds
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''', 
                gpu_id,
                deployment_id,
                metrics.get('gpu_utilization'),
                metrics.get('vram_used_mb'),
                metrics.get('vram_total_mb'),
                metrics.get('temperature_celsius'),
                metrics.get('power_draw_watts'),
                metrics.get('fan_speed_percent'),
                metrics.get('container_status'),
                metrics.get('uptime_seconds')
            )
            
    except Exception as e:
        logger.error(f"Failed to store GPU metrics: {e}")

async def store_health_check(gpu_id: str, health_data: Dict[str, Any]):
    """Store GPU health check results."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot store health check")
        return
    
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO gpu_health_history (
                    gpu_id, health_status, driver_responsive,
                    temperature_normal, power_normal, no_ecc_errors,
                    fan_operational, error_count, error_message
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ''', 
                gpu_id,
                health_data['health_status'],
                health_data.get('driver_responsive'),
                health_data.get('temperature_normal'),
                health_data.get('power_normal'),
                health_data.get('no_ecc_errors'),
                health_data.get('fan_operational'),
                health_data.get('error_count', 0),
                health_data.get('error_message')
            )
            
    except Exception as e:
        logger.error(f"Failed to store health check: {e}")

async def get_gpu_status(gpu_id: str = "gpu-0"):
    """Get current GPU status."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot get GPU status")
        return None
    
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM gpu_status WHERE gpu_id = $1
            ''', gpu_id)
            
            return dict(row) if row else None
            
    except Exception as e:
        logger.error(f"Failed to get GPU status: {e}")
        return None

async def update_gpu_status(gpu_id: str, **kwargs):
    """Update GPU status fields."""
    if db_pool is None:
        logger.warning("Database not initialized, cannot update GPU status")
        return
    
    try:
        async with db_pool.acquire() as conn:
            # Build dynamic update query
            set_clauses = ["updated_at = NOW()"]
            values = [gpu_id]
            param_count = 1
            
            for key, value in kwargs.items():
                if value is not None:
                    param_count += 1
                    set_clauses.append(f"{key} = ${param_count}")
                    values.append(value)
            
            query = f"UPDATE gpu_status SET {', '.join(set_clauses)} WHERE gpu_id = $1"
            await conn.execute(query, *values)
            
    except Exception as e:
        logger.error(f"Failed to update GPU status: {e}")

async def cleanup_database():
    """Clean up database connection."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
