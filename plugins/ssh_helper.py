#!/usr/bin/env python3
"""SSH operations helper for remote server management."""
import subprocess
import sys
from typing import Optional, Tuple


def run_remote_command(host: str, user: str, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
    """Execute command on remote host via SSH.
    
    Args:
        host: Remote host IP or hostname
        user: SSH username
        command: Command to execute
        timeout: Command timeout in seconds
        
    Returns:
        Tuple of (success, stdout, stderr)
    """
    ssh_cmd = [
        'ssh',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'LogLevel=ERROR',
        f'{user}@{host}',
        command
    ]
    
    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return (result.returncode == 0, result.stdout, result.stderr)
        
    except subprocess.TimeoutExpired:
        return (False, "", f"Command timed out after {timeout} seconds")
    except Exception as e:
        return (False, "", str(e))


def check_file_exists(host: str, user: str, filepath: str) -> bool:
    """Check if file exists on remote host.
    
    Args:
        host: Remote host IP or hostname
        user: SSH username
        filepath: Path to file on remote host
        
    Returns:
        True if file exists, False otherwise
    """
    command = f"test -f {filepath} && echo 'exists' || echo 'not_exists'"
    success, stdout, _ = run_remote_command(host, user, command)
    
    if not success:
        return False
    
    return stdout.strip() == 'exists'


def read_remote_file(host: str, user: str, filepath: str) -> Optional[str]:
    """Read file content from remote host.
    
    Args:
        host: Remote host IP or hostname
        user: SSH username
        filepath: Path to file on remote host
        
    Returns:
        File content as string, or None if failed
    """
    command = f"cat {filepath}"
    success, stdout, stderr = run_remote_command(host, user, command)
    
    if not success:
        return None
    
    return stdout


def write_remote_file(host: str, user: str, filepath: str, content: str) -> bool:
    """Write content to file on remote host.
    
    Args:
        host: Remote host IP or hostname
        user: SSH username
        filepath: Path to file on remote host
        content: Content to write
        
    Returns:
        True if successful, False otherwise
    """
    # Escape single quotes in content
    escaped_content = content.replace("'", "'\\''")
    
    # Create directory if not exists and write file
    dirname = filepath.rsplit('/', 1)[0] if '/' in filepath else '.'
    command = f"mkdir -p {dirname} && cat > {filepath} << 'EOF'\n{content}\nEOF"
    
    success, _, _ = run_remote_command(host, user, command, timeout=60)
    return success


def parse_docker_compose_image(yaml_content: str) -> Optional[str]:
    """Extract image name from docker-compose.yaml content.
    
    Args:
        yaml_content: Content of docker-compose.yaml
        
    Returns:
        Image name (e.g., 'loyaltolpi/saas-fe-webadmin:dd3ecc9') or None
    """
    try:
        import yaml
        
        data = yaml.safe_load(yaml_content)
        
        # Try to find image in services
        if 'services' in data:
            for service_name, service_config in data['services'].items():
                if 'image' in service_config:
                    return service_config['image']
        
        return None
        
    except Exception as e:
        print(f"Error parsing docker-compose.yaml: {e}", file=sys.stderr)
        return None


def create_remote_directory(host: str, user: str, dirpath: str) -> bool:
    """Create directory on remote host.
    
    Args:
        host: Remote host IP or hostname
        user: SSH username
        dirpath: Directory path to create
        
    Returns:
        True if successful, False otherwise
    """
    command = f"mkdir -p {dirpath}"
    success, _, _ = run_remote_command(host, user, command)
    return success

