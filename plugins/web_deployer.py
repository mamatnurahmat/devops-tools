#!/usr/bin/env python3
"""Web application deployment plugin using Docker Compose."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from config_utils import load_json_config, get_env_override
from plugins.shared_helpers import (
    load_auth_file,
    fetch_bitbucket_file,
    get_commit_hash_from_bitbucket,
    check_docker_image_exists,
    resolve_teams_webhook,
    send_teams_notification,
    send_loki_log
)
from plugins.ssh_helper import (
    run_remote_command,
    check_file_exists,
    read_remote_file,
    write_remote_file,
    parse_docker_compose_image,
    create_remote_directory
)


class WebDeployerConfig:
    """Configuration manager for web-deployer plugin."""
    
    def __init__(self):
        """Initialize configuration with defaults and overrides."""
        self.config_dir = Path.home() / ".doq"
        self.plugin_config_file = self.config_dir / "plugins" / "web-deployer.json"
        
        # Load plugin config
        self.config = self._load_config()
        
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from plugin config file."""
        default_config = {
            "ssh": {
                "user": "devops",
                "key_file": "~/.ssh/id_rsa",
                "timeout": 30
            },
            "docker": {
                "namespace": "loyaltolpi",
                "target_port": 3000
            },
            "bitbucket": {
                "org": "loyaltoid",
                "cicd_path": "cicd/cicd.json"
            }
        }
        
        # Load from file if exists
        if self.plugin_config_file.exists():
            try:
                file_config = load_json_config(self.plugin_config_file)
                # Merge with defaults
                return self._deep_merge(default_config, file_config)
            except Exception:
                pass
        
        return default_config
    
    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides to configuration."""
        ssh_user = get_env_override("WEB_DEPLOYER_SSH_USER")
        if ssh_user:
            self.config["ssh"]["user"] = ssh_user
        
        namespace = get_env_override("WEB_DEPLOYER_DOCKER_NAMESPACE")
        if namespace:
            self.config["docker"]["namespace"] = namespace
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-separated key path."""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value


class WebDeployer:
    """Web application deployer using Docker Compose."""
    
    def __init__(
        self,
        repo: str,
        refs: str,
        custom_image: Optional[str] = None,
        config: Optional[WebDeployerConfig] = None,
        webhook_url: Optional[str] = None
    ):
        """Initialize web deployer.
        
        Args:
            repo: Repository name
            refs: Branch or tag name
            custom_image: Custom image name (optional, overrides auto-generated image)
            config: WebDeployerConfig instance, or None to create new one
        """
        self.repo = repo
        self.refs = refs
        self.custom_image = custom_image
        self.config = config or WebDeployerConfig()
        self.webhook_url = resolve_teams_webhook(webhook_url)
        self.result = {
            'success': False,
            'action': 'unknown',
            'repository': repo,
            'refs': refs,
            'environment': None,
            'host': None,
            'image': None,
            'previous_image': None,
            'message': '',
            'custom_image_mode': custom_image is not None
        }
    
    def fetch_cicd_config(self, auth_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Fetch cicd.json from Bitbucket.
        
        Args:
            auth_data: Authentication data with GIT_USER and GIT_PASSWORD
            
        Returns:
            cicd.json content as dict, or None if failed
        """
        try:
            cicd_path = self.config.get('bitbucket.cicd_path', 'cicd/cicd.json')
            cicd_content = fetch_bitbucket_file(self.repo, self.refs, cicd_path, auth_data)
            cicd_data = json.loads(cicd_content)
            return cicd_data
        except Exception as e:
            error_msg = f"Error fetching cicd.json: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('deploy-web', 'error', error_msg)
            return None
    
    def determine_host(self, cicd_config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], str]:
        """Determine target host and domain based on refs.
        
        Args:
            cicd_config: cicd.json content
            
        Returns:
            Tuple of (host, domain, environment)
        """
        refs_lower = self.refs.lower()
        
        # Map refs to environment
        if refs_lower in ['development', 'develop']:
            env = 'development'
            host = cicd_config.get('DEVHOST')
            domain = cicd_config.get('DEVDOMAIN')
        elif refs_lower == 'staging':
            env = 'staging'
            host = cicd_config.get('STAHOST')
            domain = cicd_config.get('STADOMAIN')
        elif refs_lower == 'production' or self._is_tag(self.refs):
            env = 'production'
            host = cicd_config.get('PROHOST')
            domain = cicd_config.get('PRODOMAIN')
        else:
            # Default to development for other branches
            env = 'development'
            host = cicd_config.get('DEVHOST')
            domain = cicd_config.get('DEVDOMAIN')
        
        return (host, domain, env)
    
    def _is_tag(self, refs: str) -> bool:
        """Check if refs is a tag (starts with v followed by number)."""
        return refs.startswith('v') and len(refs) > 1 and refs[1].isdigit()
    
    def check_remote_image(self, host: str, user: str) -> Optional[str]:
        """Check current image on remote host.
        
        Args:
            host: Remote host IP
            user: SSH username
            
        Returns:
            Current image name, or None if not deployed
        """
        compose_path = f"~/{self.repo}/docker-compose.yaml"
        
        # Check if file exists
        if not check_file_exists(host, user, compose_path):
            return None
        
        # Read file content
        content = read_remote_file(host, user, compose_path)
        if not content:
            return None
        
        # Parse image from YAML
        image = parse_docker_compose_image(content)
        return image
    
    def generate_docker_compose(self, image_name: str, full_image: str, port: str) -> str:
        """Generate docker-compose.yaml content.
        
        Args:
            image_name: Image name (service/container name)
            full_image: Full image name with tag (e.g., loyaltolpi/app:tag or custom/image:tag)
            port: Published port
            
        Returns:
            docker-compose.yaml content as string
        """
        target_port = self.config.get('docker.target_port', 3000)
        
        compose_content = f"""name: {image_name}

services:
  {image_name}:
    container_name: {image_name}
    image: {full_image}
    network_mode: bridge
    ports:
      - mode: ingress
        target: {target_port}
        published: "{port}"
        protocol: tcp
    restart: always
"""
        return compose_content
    
    def deploy(self) -> int:
        """Main deployment logic.
        
        Returns:
            Exit code (0 for success, 1 for failure)
        """
        try:
            send_loki_log('deploy-web', 'info', f"Starting deployment for {self.repo}:{self.refs}")
            
            # Load auth
            auth_data = load_auth_file()
            
            # Step 1: Fetch cicd.json
            print("🔍 Fetching deployment configuration...")
            send_loki_log('deploy-web', 'info', f"Fetching deployment configuration for {self.repo}:{self.refs}")
            cicd_config = self.fetch_cicd_config(auth_data)
            if not cicd_config:
                error_msg = 'Failed to fetch cicd.json'
                send_loki_log('deploy-web', 'error', error_msg)
                self.result['message'] = error_msg
                return 1
            
            # Extract configuration
            image_name = cicd_config.get('IMAGE')
            port = cicd_config.get('PORT')
            
            if not image_name or not port:
                error_msg = 'Missing IMAGE or PORT in cicd.json'
                print(f"❌ Error: {error_msg}", file=sys.stderr)
                send_loki_log('deploy-web', 'error', error_msg)
                self.result['message'] = 'Missing required configuration in cicd.json'
                return 1
            
            # Step 2: Determine target host
            host, domain, environment = self.determine_host(cicd_config)
            
            if not host:
                error_msg = f"No host configured for environment '{environment}'"
                print(f"❌ Error: {error_msg}", file=sys.stderr)
                send_loki_log('deploy-web', 'error', error_msg)
                self.result['message'] = f'No host configured for {environment}'
                return 1
            
            self.result['environment'] = environment
            self.result['host'] = host
            
            print(f"🎯 Target: {environment} ({host})")
            send_loki_log('deploy-web', 'info', f"Target: {environment} ({host})")
            
            # Determine image to use
            if self.custom_image:
                # Custom image mode
                full_image = self.custom_image
                print(f"📦 Using custom image: {full_image}")
                
                # Skip Docker Hub check for custom images (might be from different registry)
                print(f"ℹ️  Custom image mode - skipping Docker Hub validation")
                send_loki_log('deploy-web', 'info', f"Using custom image: {full_image} (skipping Docker Hub validation)")
            else:
                # Auto-generated image from commit hash
                commit_info = get_commit_hash_from_bitbucket(self.repo, self.refs, auth_data)
                tag = commit_info['short_hash']
                
                namespace = self.config.get('docker.namespace', 'loyaltolpi')
                full_image = f"{namespace}/{image_name}:{tag}"
                print(f"📦 Image: {full_image}")
                
                # Step 3: Check if image exists in Docker Hub
                print(f"🔍 Checking if image exists in Docker Hub...")
                send_loki_log('deploy-web', 'info', f"Checking if image exists in Docker Hub: {full_image}")
                check_result = check_docker_image_exists(full_image, auth_data, verbose=False)
                
                if not check_result['exists']:
                    error_msg = f"Image {full_image} not found in Docker Hub"
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    if check_result.get('error'):
                        print(f"   Reason: {check_result['error']}", file=sys.stderr)
                    print(f"   Please build the image first using: doq devops-ci {self.repo} {self.refs}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = check_result.get('error', 'Image not found in Docker Hub')
                    return 1
                
                print(f"✅ Image found in Docker Hub")
                send_loki_log('deploy-web', 'info', f"Image found in Docker Hub: {full_image}")
            
            self.result['image'] = full_image
            
            # Step 4: Check existing deployment
            ssh_user = self.config.get('ssh.user', 'devops')
            print(f"🔍 Checking existing deployment on {ssh_user}@{host}...")
            send_loki_log('deploy-web', 'info', f"Checking existing deployment on {ssh_user}@{host}")
            
            current_image = self.check_remote_image(host, ssh_user)
            self.result['previous_image'] = current_image
            
            # Step 5: Deploy based on current state
            if current_image == full_image:
                # Case A: Same image - skip
                skip_msg = f"Already deployed with same image: {full_image}"
                print(f"✅ {skip_msg}")
                send_loki_log('deploy-web', 'info', skip_msg)
                self.result['success'] = True
                self.result['action'] = 'skipped'
                self.result['message'] = 'Already deployed with same image'
                return self._finalize(0)
            
            # Generate docker-compose.yaml
            compose_content = self.generate_docker_compose(image_name, full_image, port)
            compose_path = f"~/{self.repo}/docker-compose.yaml"
            
            if current_image is None:
                # Case B: New deployment
                print(f"🆕 New deployment to {host}")
                send_loki_log('deploy-web', 'info', f"New deployment to {host}")
                self.result['action'] = 'deployed'
                
                # Create directory
                print(f"📁 Creating directory ~/{self.repo}...")
                send_loki_log('deploy-web', 'info', f"Creating directory ~/{self.repo} on {host}")
                if not create_remote_directory(host, ssh_user, f"~/{self.repo}"):
                    error_msg = 'Failed to create directory'
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                # Upload docker-compose.yaml
                print(f"📤 Uploading docker-compose.yaml...")
                send_loki_log('deploy-web', 'info', f"Uploading docker-compose.yaml to {host}")
                if not write_remote_file(host, ssh_user, compose_path, compose_content):
                    error_msg = 'Failed to upload docker-compose.yaml'
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                # Pull and start
                print(f"🐳 Pulling image...")
                send_loki_log('deploy-web', 'info', f"Pulling image {full_image} on {host}")
                pull_cmd = f"cd ~/{self.repo} && docker pull {full_image}"
                success, stdout, stderr = run_remote_command(host, ssh_user, pull_cmd, timeout=300)
                
                if not success:
                    error_msg = f'Failed to pull image: {stderr}'
                    print(f"❌ Error pulling image: {stderr}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                print(f"🚀 Starting container...")
                send_loki_log('deploy-web', 'info', f"Starting container on {host}")
                up_cmd = f"cd ~/{self.repo} && docker compose up -d"
                success, stdout, stderr = run_remote_command(host, ssh_user, up_cmd, timeout=120)
                
                if not success:
                    error_msg = f'Failed to start container: {stderr}'
                    print(f"❌ Error starting container: {stderr}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                success_msg = f"Deployment successful! Image {full_image} deployed to {host}"
                print(f"✅ Deployment successful!")
                send_loki_log('deploy-web', 'info', success_msg)
                self.result['success'] = True
                self.result['message'] = 'Deployment successful'
                return self._finalize(0)
                
            else:
                # Case C: Update existing
                update_msg = f"Updating deployment (from {current_image} to {full_image})"
                print(f"🔄 {update_msg}")
                send_loki_log('deploy-web', 'info', update_msg)
                self.result['action'] = 'updated'
                
                # Upload updated docker-compose.yaml
                print(f"📤 Updating docker-compose.yaml...")
                send_loki_log('deploy-web', 'info', f"Updating docker-compose.yaml on {host}")
                if not write_remote_file(host, ssh_user, compose_path, compose_content):
                    error_msg = 'Failed to update docker-compose.yaml'
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                # Pull and restart
                print(f"🐳 Pulling new image...")
                send_loki_log('deploy-web', 'info', f"Pulling new image {full_image} on {host}")
                pull_cmd = f"cd ~/{self.repo} && docker compose pull"
                success, stdout, stderr = run_remote_command(host, ssh_user, pull_cmd, timeout=300)
                
                if not success:
                    error_msg = f'Failed to pull image: {stderr}'
                    print(f"❌ Error pulling image: {stderr}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                print(f"🔄 Restarting container...")
                send_loki_log('deploy-web', 'info', f"Restarting container on {host}")
                up_cmd = f"cd ~/{self.repo} && docker compose up -d"
                success, stdout, stderr = run_remote_command(host, ssh_user, up_cmd, timeout=120)
                
                if not success:
                    error_msg = f'Failed to restart container: {stderr}'
                    print(f"❌ Error restarting container: {stderr}", file=sys.stderr)
                    send_loki_log('deploy-web', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                success_msg = f"Update successful! Image {full_image} updated on {host}"
                print(f"✅ Update successful!")
                send_loki_log('deploy-web', 'info', success_msg)
                self.result['success'] = True
                self.result['message'] = 'Update successful'
                return self._finalize(0)
        
        except Exception as e:
            error_msg = f"Error during deployment: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('deploy-web', 'error', error_msg)
            self.result['message'] = str(e)
            return self._finalize(1)
    
    def get_result(self) -> Dict[str, Any]:
        """Get deployment result.
        
        Returns:
            Result dictionary
        """
        return self.result


    def _send_webhook(self, success: bool):
        """Send deployment summary to Microsoft Teams."""
        if not self.webhook_url:
            return
        
        environment = self.result.get('environment') or '-'
        host = self.result.get('host') or '-'
        image = self.result.get('image') or '-'
        previous_image = self.result.get('previous_image') or '-'
        action = self.result.get('action') or '-'
        message = self.result.get('message') or '-'
        
        status_text = "SUCCESS" if success else "FAILED"
        facts = [
            ("Repository", self.repo),
            ("Reference", self.refs),
            ("Environment", environment),
            ("Host", host),
            ("Action", action),
            ("Image", image),
            ("Previous Image", previous_image),
            ("Message", message),
        ]
        
        send_teams_notification(
            self.webhook_url,
            title=f"Web Deployment {status_text}",
            facts=facts,
            success=success,
            summary=f"Web Deployment {status_text}"
        )
    
    def _finalize(self, exit_code: int) -> int:
        """Finalize deployment by dispatching webhook notification."""
        success = exit_code == 0
        self.result['success'] = success
        if not self.result.get('message'):
            self.result['message'] = 'Deployment successful' if success else 'Deployment failed'
        self._send_webhook(success)
        return exit_code


def cmd_deploy_web(args):
    """Command handler for 'doq deploy-web'."""
    custom_image = getattr(args, 'image', None)
    webhook_url = getattr(args, 'webhook', None)
    deployer = WebDeployer(
        args.repo,
        args.refs,
        custom_image=custom_image,
        webhook_url=webhook_url
    )
    exit_code = deployer.deploy()
    
    # Output result as JSON
    if args.json:
        result = deployer.get_result()
        print("\n" + json.dumps(result, indent=2))
    
    sys.exit(exit_code)


def register_commands(subparsers):
    """Register web-deployer commands with argparse.
    
    This function is called by PluginManager to dynamically register
    the plugin's commands.
    
    Args:
        subparsers: The argparse subparsers object
    """
    # Deploy-web command
    deploy_web_parser = subparsers.add_parser('deploy-web',
                                              help='Deploy web application using Docker Compose',
                                              description='Deploy web application to remote server using Docker Compose based on cicd.json configuration')
    deploy_web_parser.add_argument('repo', help='Repository name (e.g., saas-fe-webadmin)')
    deploy_web_parser.add_argument('refs', help='Branch or tag name (e.g., development, staging, production, v1.0.0)')
    deploy_web_parser.add_argument('--image', type=str, default=None,
                                   help='Custom Docker image to deploy (e.g., loyaltolpi/myapp:v1.0.0 or registry.io/app:latest)')
    deploy_web_parser.add_argument('--webhook', type=str,
                                   help='Microsoft Teams webhook URL for deployment notifications (fallback to TEAMS_WEBHOOK env or ~/.doq/.env)')
    deploy_web_parser.add_argument('--json', action='store_true',
                                   help='Output result in JSON format')
    deploy_web_parser.set_defaults(func=cmd_deploy_web)

