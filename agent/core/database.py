# host-agent/agent/core/database.py
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import asyncpg

logger = logging.getLogger(__name__)

# Database connection
db_pool = None

async def init_database():
    """Initialize PostgreSQL database connection."""
    global db_pool
    try:
        import os
        
        db_pool = await asyncpg.create_pool(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            user=os.getenv('POSTGRES_USER', 'hostagent'),
            password=os.getenv('POSTGRES_PASSWORD', 'hostagent123'),
            database=os.getenv('POSTGRES_DB', 'hostagent'),
            min_size=1,
            max_size=10
        )
        
        # Create tables
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS rentals (
                    id SERIAL PRIMARY KEY,
                    rental_id VARCHAR(255) UNIQUE NOT NULL,
                    host_id VARCHAR(255) NOT NULL,
                    container_id VARCHAR(255) NOT NULL,
                    gpu_type VARCHAR(255) NOT NULL,
                    os_image VARCHAR(255) NOT NULL,
                    duration_hours INTEGER NOT NULL,
                    auth_type VARCHAR(50) NOT NULL,
                    password VARCHAR(255),
                    ssh_key TEXT,
                    instance_name VARCHAR(255) NOT NULL,
                    environment_variables JSONB,
                    port_mappings JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    status VARCHAR(50) DEFAULT 'active',
                    ssh_port INTEGER,
                    web_port INTEGER
                )
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_rentals_expires_at ON rentals(expires_at);
                CREATE INDEX IF NOT EXISTS idx_rentals_status ON rentals(status);
            ''')
            
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def store_rental_in_db(rental_id: str, rental_request, container_info: Dict[str, Any]):
    """Store rental information in the database."""
    try:
        async with db_pool.acquire() as conn:
            expires_at = datetime.now() + timedelta(hours=rental_request.duration_hours)
            
            await conn.execute('''
                INSERT INTO rentals (
                    rental_id, host_id, container_id, gpu_type, os_image,
                    duration_hours, auth_type, password, ssh_key, instance_name,
                    environment_variables, port_mappings, expires_at,
                    ssh_port, web_port
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            ''', 
                rental_id,
                rental_request.host_id,
                container_info.get('Id'),
                rental_request.gpu_type,
                rental_request.os_image,
                rental_request.duration_hours,
                rental_request.auth_type,
                rental_request.password,
                rental_request.ssh_key,
                rental_request.instance_name,
                json.dumps(rental_request.environment_variables),
                json.dumps(rental_request.port_mappings),
                expires_at,
                container_info.get('ssh_port', 22),
                container_info.get('web_port', 8080)
            )
            
        logger.info(f"Rental {rental_id} stored in database")
        
    except Exception as e:
        logger.error(f"Failed to store rental in database: {e}")
        raise

async def get_expired_rentals():
    """Get all expired rentals that need to be terminated."""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT rental_id, container_id, instance_name
                FROM rentals 
                WHERE expires_at <= NOW() AND status = 'active'
            ''')
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        logger.error(f"Failed to get expired rentals: {e}")
        return []

async def mark_rental_terminated(rental_id: str):
    """Mark a rental as terminated in the database."""
    try:
        async with db_pool.acquire() as conn:
            await conn.execute('''
                UPDATE rentals 
                SET status = 'terminated' 
                WHERE rental_id = $1
            ''', rental_id)
            
        logger.info(f"Rental {rental_id} marked as terminated")
        
    except Exception as e:
        logger.error(f"Failed to mark rental as terminated: {e}")

async def get_active_rentals():
    """Get all active rentals."""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT rental_id, container_id, instance_name, expires_at
                FROM rentals 
                WHERE status = 'active'
                ORDER BY expires_at
            ''')
            
            return [dict(row) for row in rows]
            
    except Exception as e:
        logger.error(f"Failed to get active rentals: {e}")
        return []

async def cleanup_database():
    """Clean up database connection."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
