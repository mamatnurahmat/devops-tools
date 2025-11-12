"""Configuration management for Rancher CLI."""
import os
from pathlib import Path
from dotenv import load_dotenv, set_key

CONFIG_DIR = Path.home() / ".doq"
CONFIG_FILE = CONFIG_DIR / ".env"


def ensure_config_dir():
    """Ensure config directory exists."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.touch()


def load_config():
    """Load configuration from $HOME/.doq/.env"""
    ensure_config_dir()
    load_dotenv(CONFIG_FILE)
    return {
        'url': os.getenv('RANCHER_URL', ''),
        'token': os.getenv('RANCHER_TOKEN', ''),
        'insecure': os.getenv('RANCHER_INSECURE', 'true').lower() == 'true',
        'username': os.getenv('RANCHER_USER', '')
    }


def save_config(url, token, insecure=True, username=None):
    """Save configuration to $HOME/.doq/.env"""
    ensure_config_dir()
    set_key(CONFIG_FILE, 'RANCHER_URL', url)
    set_key(CONFIG_FILE, 'RANCHER_TOKEN', token)
    set_key(CONFIG_FILE, 'RANCHER_INSECURE', str(insecure).lower())
    if username:
        set_key(CONFIG_FILE, 'RANCHER_USER', username)


def get_config_file_path():
    """Get the config file path."""
    return str(CONFIG_FILE)


def config_exists():
    """Check if config file exists."""
    return CONFIG_FILE.exists()
