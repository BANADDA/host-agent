# host-agent/agent/core/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_server_url: str
    agent_port: int = 8000
    report_interval_seconds: int = 30

    class Config:
        env_file = ".env"

settings = Settings()
