#!/usr/bin/env python3
"""Base plugin class for doq plugins."""
from __future__ import annotations
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from config_utils import load_json_config, get_env_override
from plugins.shared_helpers import (
    load_auth_file,
    fetch_bitbucket_file,
    get_commit_hash_from_bitbucket,
    resolve_teams_webhook,
    send_teams_notification,
    send_loki_log,
    check_docker_image_exists
)

class BasePlugin:
    """Base class for all plugins to inherit from."""
    
    def __init__(self, name: str):
        """Initialize base plugin.
        
        Args:
            name: Plugin name (e.g., 'devops-ci', 'k8s-deployer')
        """
        self.name = name
        self.config_dir = Path.home() / ".doq"
        self.plugin_config_file = self.config_dir / "plugins" / f"{name}.json"
        self.config = self._load_config()
        self._apply_env_overrides()
        self.auth_data = None

    def _apply_env_overrides(self):
        """Apply environment variable overrides. Should be overridden by subclasses."""
        pass

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from plugin config file."""
        default_config = self.get_default_config()
        
        if self.plugin_config_file.exists():
            try:
                file_config = load_json_config(self.plugin_config_file)
                return self._deep_merge(default_config, file_config)
            except Exception as e:
                print(f"Warning: Failed to load config for {self.name}: {e}", file=sys.stderr)
        
        return default_config

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration. Should be overridden by subclasses."""
        return {}

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Merge two dictionaries recursively."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value if value is not None else default

    def load_auth(self) -> bool:
        """Load authentication data."""
        try:
            self.auth_data = load_auth_file()
            return True
        except Exception as e:
            self.log_error(f"Failed to load authentication: {e}")
            return False

    def run_command(self, command: List[str], cwd: Optional[Path] = None, 
                   capture_output: bool = True, text: bool = True, 
                   timeout: int = 60, verbose: bool = False) -> subprocess.CompletedProcess:
        """Run a subprocess command safely."""
        if verbose:
            print(f"   ↳ Running: {' '.join(command)}")
            
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=capture_output,
                text=text,
                timeout=timeout
            )
            
            if verbose and capture_output:
                if result.stdout:
                    print(result.stdout, end='' if text else None)
                if result.stderr:
                    print(result.stderr, file=sys.stderr, end='' if text else None)
                    
            return result
        except subprocess.TimeoutExpired:
            self.log_error(f"Command timed out: {' '.join(command)}")
            raise
        except Exception as e:
            self.log_error(f"Command failed: {e}")
            raise

    def log_info(self, message: str):
        """Log info message to Loki and stdout."""
        send_loki_log(self.name, 'info', message)

    def log_error(self, message: str):
        """Log error message to Loki and stderr."""
        print(f"❌ {message}", file=sys.stderr)
        send_loki_log(self.name, 'error', message)

    def send_notification(self, title: str, facts: List[Tuple[str, str]], success: bool, webhook_url: Optional[str] = None):
        """Send Teams notification."""
        url = resolve_teams_webhook(webhook_url)
        if url:
            send_teams_notification(url, title, facts, success)

    def fetch_bitbucket_file(self, repo: str, refs: str, path: str) -> str:
        """Fetch file from Bitbucket using loaded auth."""
        if not self.auth_data:
            raise RuntimeError("Authentication not loaded")
        return fetch_bitbucket_file(repo, refs, path, self.auth_data)

    def get_commit_hash(self, repo: str, refs: str) -> Dict[str, Any]:
        """Get commit hash from Bitbucket using loaded auth."""
        if not self.auth_data:
            raise RuntimeError("Authentication not loaded")
        return get_commit_hash_from_bitbucket(repo, refs, self.auth_data)

    def check_image_exists(self, image_name: str) -> Dict[str, Any]:
        """Check if docker image exists."""
        if not self.auth_data:
            raise RuntimeError("Authentication not loaded")
        return check_docker_image_exists(image_name, self.auth_data)
