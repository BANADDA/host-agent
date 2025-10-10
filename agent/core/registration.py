# host-agent/agent/core/registration.py
import logging
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

async def register_with_server(config: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register GPU with central server."""
    try:
        url = f"{config['server']['url']}/api/host-agents/register"
        headers = {
            'Authorization': f"Bearer {config['agent']['api_key']}",
            'Content-Type': 'application/json'
        }
        
        logger.info("Registering with central server...")
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=config['server']['timeout']
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info("Registration successful")
            return {
                'success': True,
                'gpu_uuid': result.get('gpu_uuid'),
                'message': result.get('message', 'Registration successful')
            }
            
        elif response.status_code == 409:
            # Already registered
            result = response.json()
            logger.info("Already registered")
            return {
                'success': True,
                'gpu_uuid': result.get('gpu_uuid'),
                'message': 'Already registered'
            }
            
        elif response.status_code == 401:
            logger.error("Invalid API key")
            return {
                'success': False,
                'error': 'Invalid API key'
            }
            
        elif response.status_code == 422:
            logger.error("Invalid configuration data")
            error_msg = response.json().get('error', 'Invalid configuration data')
            return {
                'success': False,
                'error': error_msg
            }
            
        else:
            logger.error(f"Registration failed with status: {response.status_code}")
            return {
                'success': False,
                'error': f'Registration failed: {response.status_code}'
            }
            
    except requests.exceptions.Timeout:
        logger.error("Registration timeout")
        return {
            'success': False,
            'error': 'Registration timeout'
        }
        
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to central server")
        return {
            'success': False,
            'error': 'Cannot connect to central server'
        }
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {
            'success': False,
            'error': str(e)
        }
