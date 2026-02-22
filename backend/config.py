"""
Configuration module demonstrating:
  - .env file loading (load_dotenv)
  - Environment variable loading (load_env)
  - Dict-based config (load_dict)
  - Config validation with dataclasses
"""
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from lcore import Lcore


@dataclass
class AppConfigSchema:
    """Dataclass schema for config validation."""
    debug: bool = False
    secret_key: str = 'change-me'
    host: str = '0.0.0.0'
    port: int = 8080
    db_path: str = './taskflow.db'
    cors_origins: str = '*'
    smtp_host: str = 'smtp.gmail.com'
    smtp_port: int = 587
    smtp_user: str = ''
    smtp_password: str = ''
    smtp_from: str = 'noreply@taskflow.app'
    smtp_use_tls: bool = True
    rate_limit_default: int = 100
    rate_limit_window: int = 60
    max_upload_size: int = 10_485_760
    upload_dir: str = './uploads'


def configure_app(app: Lcore) -> None:
    """Load configuration from multiple sources and validate."""

    # 1. Load defaults via dict
    app.config.load_dict({
        'debug': False,
        'secret_key': 'change-me-in-production',
        'host': '0.0.0.0',
        'port': 8080,
        'db_path': './taskflow.db',
        'cors_origins': '*',
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': 587,
        'smtp_user': '',
        'smtp_password': '',
        'smtp_from': 'noreply@taskflow.app',
        'smtp_use_tls': True,
        'rate_limit_default': 100,
        'rate_limit_window': 60,
        'max_upload_size': 10_485_760,
        'upload_dir': './uploads',
    })

    # 2. Load from .env file (overrides defaults)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        app.config.load_dotenv(env_path)

    # 3. Load from environment variables with APP_ prefix (overrides .env)
    app.config.load_env('APP_', strip_prefix=True)

    # 4. Validate config against schema
    try:
        app.config.validate_config(AppConfigSchema)
        print("[CONFIG] Configuration validated successfully")
    except ValueError as e:
        print(f"[CONFIG WARNING] {e}")

    # Ensure upload directory exists
    upload_dir = app.config.get('upload_dir', './uploads')
    os.makedirs(upload_dir, exist_ok=True)
