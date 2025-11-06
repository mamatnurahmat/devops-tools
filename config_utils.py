#!/usr/bin/env python3
"""Configuration utilities for plugin and core config management."""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from copy import deepcopy


def get_env_override(key: str) -> Optional[str]:
    """Get environment variable override value.
    
    Args:
        key: Environment variable name
        
    Returns:
        Environment variable value or None if not set
    """
    return os.environ.get(key)


def load_json_config(file_path: Path, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Load JSON configuration with fallback to defaults.
    
    Args:
        file_path: Path to JSON config file
        defaults: Default configuration dict (optional)
        
    Returns:
        Dict with configuration (merged with defaults if provided)
    """
    result = deepcopy(defaults) if defaults else {}
    
    if not file_path.exists():
        return result
    
    try:
        with open(file_path, 'r') as f:
            file_config = json.load(f)
        
        # Merge file config into result
        result = deep_merge(result, file_config)
        
        return result
    except Exception as e:
        print(f"Warning: Could not load config from {file_path}: {e}")
        return result


def save_json_config(file_path: Path, data: Dict[str, Any]) -> bool:
    """Save JSON configuration to file.
    
    Args:
        file_path: Path to save JSON config
        data: Configuration dictionary to save
        
    Returns:
        bool: True if saved successfully
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error: Could not save config to {file_path}: {e}")
        return False


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.
    
    Args:
        base: Base dictionary
        overlay: Dictionary to merge on top (takes precedence)
        
    Returns:
        Merged dictionary
    """
    result = deepcopy(base)
    
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    
    return result


def merge_configs(
    defaults: Dict[str, Any],
    env_vars: Dict[str, Any],
    file_config: Dict[str, Any],
    cli_args: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Merge configurations with priority: CLI > env > file > defaults.
    
    Args:
        defaults: Default configuration values (lowest priority)
        env_vars: Environment variable overrides
        file_config: File-based configuration
        cli_args: CLI argument overrides (highest priority, optional)
        
    Returns:
        Merged configuration dictionary
    """
    # Start with defaults
    result = deepcopy(defaults)
    
    # Merge file config (overrides defaults)
    result = deep_merge(result, file_config)
    
    # Merge environment variables (overrides file config)
    result = deep_merge(result, env_vars)
    
    # Merge CLI args (highest priority)
    if cli_args:
        result = deep_merge(result, cli_args)
    
    return result


def get_plugin_config_path(plugin_name: str) -> Path:
    """Get the configuration file path for a plugin.
    
    Args:
        plugin_name: Name of the plugin
        
    Returns:
        Path to plugin config file
    """
    doq_dir = Path.home() / ".doq"
    return doq_dir / "plugins" / f"{plugin_name}.json"


def get_env_value(key: str, default: Any = None, value_type: type = str) -> Any:
    """Get environment variable with type conversion.
    
    Args:
        key: Environment variable name
        default: Default value if not found
        value_type: Type to convert to (str, int, bool, float)
        
    Returns:
        Environment variable value converted to specified type, or default
    """
    value = os.getenv(key)
    
    if value is None:
        return default
    
    # Type conversion
    try:
        if value_type == bool:
            return value.lower() in ('true', '1', 'yes', 'on')
        elif value_type == int:
            return int(value)
        elif value_type == float:
            return float(value)
        else:
            return str(value)
    except (ValueError, AttributeError):
        return default


def flatten_nested_dict(nested: Dict[str, Any], prefix: str = '', separator: str = '_') -> Dict[str, Any]:
    """Flatten nested dictionary to single level with prefixed keys.
    
    Useful for converting nested JSON config to environment variable style.
    
    Example:
        {'api': {'url': 'http://...', 'timeout': 30}}
        becomes
        {'api_url': 'http://...', 'api_timeout': 30}
    
    Args:
        nested: Nested dictionary to flatten
        prefix: Prefix for keys (used in recursion)
        separator: Separator between nested keys
        
    Returns:
        Flattened dictionary
    """
    result = {}
    
    for key, value in nested.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key
        
        if isinstance(value, dict):
            result.update(flatten_nested_dict(value, new_key, separator))
        else:
            result[new_key] = value
    
    return result


def unflatten_dict(flat: Dict[str, Any], separator: str = '_') -> Dict[str, Any]:
    """Convert flattened dictionary back to nested structure.
    
    Example:
        {'api_url': 'http://...', 'api_timeout': 30}
        becomes
        {'api': {'url': 'http://...', 'timeout': 30}}
    
    Args:
        flat: Flattened dictionary
        separator: Separator used in keys
        
    Returns:
        Nested dictionary
    """
    result = {}
    
    for key, value in flat.items():
        parts = key.split(separator)
        current = result
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    return result


def load_env_config(env_prefix: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Load configuration from environment variables with a prefix.
    
    Args:
        env_prefix: Environment variable prefix (e.g., 'DEVOPS_CI_')
        defaults: Default configuration structure (nested dict)
        
    Returns:
        Configuration dict with env vars applied
    """
    # Flatten defaults to get all possible keys
    flat_defaults = flatten_nested_dict(defaults)
    
    # Load env vars
    env_config = {}
    for flat_key in flat_defaults.keys():
        env_key = f"{env_prefix}{flat_key}".upper()
        env_value = os.getenv(env_key)
        
        if env_value is not None:
            env_config[flat_key] = env_value
    
    # Unflatten back to nested structure
    nested_env_config = unflatten_dict(env_config)
    
    return nested_env_config

