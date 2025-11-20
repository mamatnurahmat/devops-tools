#!/usr/bin/env python3
"""Kubernetes application deployment plugin."""
from __future__ import annotations
import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from config_utils import load_json_config, get_env_override
from plugins.shared_helpers import (
    load_auth_file,
    fetch_bitbucket_file,
    get_commit_hash_from_bitbucket,
    resolve_teams_webhook,
    send_teams_notification,
    send_loki_log
)


class K8sDeployerConfig:
    """Configuration manager for k8s-deployer plugin."""
    
    def __init__(self):
        """Initialize configuration with defaults and overrides."""
        self.config_dir = Path.home() / ".doq"
        self.plugin_config_file = self.config_dir / "plugins" / "k8s-deployer.json"
        
        # Load plugin config
        self.config = self._load_config()
        
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from plugin config file."""
        default_config = {
            "docker": {
                "namespace": "loyaltolpi"
            },
            "bitbucket": {
                "organization": "qoin-digital-indonesia",
                "cicd_path": "cicd/cicd.json"
            },
            "deployment": {
                "use_deployment_field": True
            }
        }
        
        if self.plugin_config_file.exists():
            try:
                file_config = load_json_config(str(self.plugin_config_file))
                # Deep merge with defaults
                from config_utils import deep_merge
                return deep_merge(default_config, file_config)
            except Exception:
                pass
        
        return default_config
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        # Docker namespace
        if env_val := get_env_override('DOQ_DOCKER_NAMESPACE'):
            self.config.setdefault('docker', {})['namespace'] = env_val
        
        # Bitbucket organization
        if env_val := get_env_override('DOQ_BITBUCKET_ORG'):
            self.config.setdefault('bitbucket', {})['organization'] = env_val
    
    def get(self, key: str, default=None):
        """Get configuration value using dot notation."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value if value is not None else default


class K8sDeployer:
    """Kubernetes application deployer."""
    
    def __init__(
        self,
        repo: str,
        refs: str,
        custom_image: Optional[str] = None,
        config: Optional[K8sDeployerConfig] = None,
        namespace_override: Optional[str] = None,
        deployment_override: Optional[str] = None,
        webhook_url: Optional[str] = None,
        gitops_mode: bool = False,
        verbose: bool = False
    ):
        """Initialize K8s deployer.
        
        Args:
            repo: Repository name
            refs: Branch or tag name
            custom_image: Custom image name (optional, overrides auto-generated image)
            config: K8sDeployerConfig instance, or None to create new one
        """
        self.repo = repo
        self.refs = refs
        self.custom_image = custom_image
        self.config = config or K8sDeployerConfig()
        self.namespace_override = namespace_override
        self.deployment_override = deployment_override
        self.webhook_url = resolve_teams_webhook(webhook_url)
        self.gitops_mode = gitops_mode
        self.verbose = verbose
        self.result = {
            'success': False,
            'action': 'unknown',
            'repository': repo,
            'refs': refs,
            'namespace': None,
            'deployment': None,
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
            send_loki_log('deploy-k8s', 'error', error_msg)
            return None
    
    def determine_namespace(self, cicd_config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Determine namespace and deployment name from cicd.json.
        
        Args:
            cicd_config: cicd.json content
            
        Returns:
            Tuple of (namespace, deployment_name)
        """
        # Get PROJECT field from cicd.json
        deployment = self.deployment_override or cicd_config.get('DEPLOYMENT')
        if not deployment:
            error_msg = "DEPLOYMENT field not found in cicd.json"
            print(f"❌ Error: {error_msg}", file=sys.stderr)
            send_loki_log('deploy-k8s', 'error', error_msg)
            return (None, None)
        
        if self.namespace_override:
            namespace = self.namespace_override
        else:
            project = cicd_config.get('PROJECT')
            if not project:
                error_msg = "PROJECT field not found in cicd.json"
                print(f"❌ Error: {error_msg}", file=sys.stderr)
                send_loki_log('deploy-k8s', 'error', error_msg)
                return (None, None)
            namespace = f"{self.refs}-{project}"
        
        return (namespace, deployment)
    
    def check_image_ready(self) -> Optional[Dict[str, Any]]:
        """Check if image is ready in Docker Hub using doq image command.
        
        Returns:
            Image info dict if ready, None if not ready
        """
        try:
            # Run doq image command
            result = self._run_subprocess(
                ['doq', 'image', self.repo, self.refs, '--json'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                print(f"❌ Error checking image status", file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return None
            
            # Parse JSON output
            image_info = json.loads(result.stdout)
            
            if not image_info.get('ready', False):
                print(f"❌ Image not ready in Docker Hub", file=sys.stderr)
                print(f"   Please build the image first using: doq devops-ci {self.repo} {self.refs}", file=sys.stderr)
                return None
            
            return image_info
            
        except subprocess.TimeoutExpired:
            print(f"❌ Timeout checking image status", file=sys.stderr)
            return None
        except json.JSONDecodeError:
            print(f"❌ Failed to parse image status response", file=sys.stderr)
            return None
        except Exception as e:
            print(f"❌ Error checking image status: {e}", file=sys.stderr)
            return None
    
    def get_current_image(self, namespace: str, deployment: str) -> Optional[str]:
        """Get current image from deployment using doq get-image command.
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            
        Returns:
            Current image name, or None if deployment not found
        """
        try:
            # Run doq get-image command
            result = self._run_subprocess(
                ['doq', 'get-image', namespace, deployment],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                # Deployment not found - this is OK for first-time deployment
                return None
            
            # Parse JSON output
            deployment_info = json.loads(result.stdout)
            containers = deployment_info.get('containers', [])
            
            if not containers:
                return None
            
            # Get first container's image
            current_image = containers[0].get('image')
            return current_image
            
        except subprocess.TimeoutExpired:
            print(f"❌ Timeout getting deployment info", file=sys.stderr)
            return None
        except json.JSONDecodeError:
            # If not JSON, deployment might not exist
            return None
        except Exception as e:
            print(f"⚠️  Warning: Could not get current deployment image: {e}", file=sys.stderr)
            return None
    
    def switch_context(self, namespace: str) -> bool:
        """Switch kubectl context using doq ns command.
        
        Args:
            namespace: Kubernetes namespace
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Run doq ns command
            result = self._run_subprocess(
                ['doq', 'ns', namespace],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"❌ Failed to switch context", file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            print(f"❌ Timeout switching context", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Error switching context: {e}", file=sys.stderr)
            return False
    
    def set_image(self, namespace: str, deployment: str, image: str) -> bool:
        """Deploy image using doq set-image command.
        
        Args:
            namespace: Kubernetes namespace
            deployment: Deployment name
            image: Image name with tag
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Run doq set-image command
            result = self._run_subprocess(
                ['doq', 'set-image', namespace, deployment, image],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                print(f"❌ Failed to set image", file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return False
            
            # Print command output
            if result.stdout and not self.verbose:
                print(result.stdout, end='')
            
            return True
            
        except subprocess.TimeoutExpired:
            print(f"❌ Timeout setting image", file=sys.stderr)
            return False
        except Exception as e:
            print(f"❌ Error setting image: {e}", file=sys.stderr)
            return False
    
    def deploy(self) -> int:
        """Main deployment logic.
        
        Returns:
            Exit code (0 for success, 1 for error)
        """
        try:
            send_loki_log('deploy-k8s', 'info', f"Starting deployment for {self.repo}:{self.refs}")
            
            # Step 1: Load authentication
            auth_data = load_auth_file()
            if not auth_data:
                error_msg = "Authentication not found. Please configure credentials in ~/.doq/auth.json"
                print(f"❌ Error: {error_msg}", file=sys.stderr)
                send_loki_log('deploy-k8s', 'error', error_msg)
                self.result['message'] = 'Authentication not found'
                return self._finalize(1)
            
            # Step 2: Fetch cicd.json
            print(f"🔍 Fetching deployment configuration...")
            send_loki_log('deploy-k8s', 'info', f"Fetching deployment configuration for {self.repo}:{self.refs}")
            cicd_config = self.fetch_cicd_config(auth_data)
            if not cicd_config:
                error_msg = 'Failed to fetch cicd.json'
                send_loki_log('deploy-k8s', 'error', error_msg)
                self.result['message'] = error_msg
                return self._finalize(1)
            
            # Step 3: Determine namespace and deployment
            namespace, deployment = self.determine_namespace(cicd_config)
            if not namespace or not deployment:
                error_msg = 'Failed to determine namespace or deployment'
                send_loki_log('deploy-k8s', 'error', error_msg)
                self.result['message'] = error_msg
                return self._finalize(1)
            
            self.result['namespace'] = namespace
            self.result['deployment'] = deployment
            
            print(f"🎯 Target: {namespace} / {deployment}")
            send_loki_log('deploy-k8s', 'info', f"Target: {namespace} / {deployment}")
            
            # Step 4: Determine image to use
            if self.custom_image:
                # Custom image mode
                full_image = self.custom_image
                print(f"📦 Using custom image: {full_image}")
                print(f"ℹ️  Custom image mode - skipping Docker Hub validation")
                send_loki_log('deploy-k8s', 'info', f"Using custom image: {full_image} (skipping Docker Hub validation)")
            else:
                # Auto mode - check image status
                print(f"🔍 Checking image status...")
                send_loki_log('deploy-k8s', 'info', f"Checking image status for {self.repo}:{self.refs}")
                image_info = self.check_image_ready()
                if not image_info:
                    error_msg = 'Image not ready in Docker Hub'
                    send_loki_log('deploy-k8s', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                
                # Get commit hash and construct image name
                commit_info = get_commit_hash_from_bitbucket(self.repo, self.refs, auth_data)
                tag = commit_info['short_hash']
                
                namespace_prefix = self.config.get('docker.namespace', 'loyaltolpi')
                image_name = cicd_config.get('IMAGE', self.repo)
                full_image = f"{namespace_prefix}/{image_name}:{tag}"
                
                print(f"✅ Image ready: {full_image}")
                send_loki_log('deploy-k8s', 'info', f"Image ready: {full_image}")
            
            self.result['image'] = full_image
            
            # Step 5 (optional): Update GitOps manifests
            if self.gitops_mode:
                print(f"🧩 Updating GitOps manifest in gitops-k8s repository...")
                send_loki_log('deploy-k8s', 'info', f"Updating GitOps manifest in gitops-k8s repository")
                if not self.update_gitops_manifest(namespace, deployment, full_image):
                    error_msg = 'Failed to update gitops-k8s manifest'
                    send_loki_log('deploy-k8s', 'error', error_msg)
                    self.result['message'] = error_msg
                    return self._finalize(1)
                print(f"✅ GitOps manifest updated")
                send_loki_log('deploy-k8s', 'info', 'GitOps manifest updated')
            
            # Step 6: Get current deployment image
            print(f"🔍 Checking current deployment...")
            send_loki_log('deploy-k8s', 'info', f"Checking current deployment in {namespace}/{deployment}")
            current_image = self.get_current_image(namespace, deployment)
            self.result['previous_image'] = current_image
            
            # Step 7: Compare images
            if current_image:
                if current_image == full_image:
                    # Same image - skip deployment
                    skip_msg = f"Already deployed with same image: {current_image}. Skipping deployment."
                    print(f"✅ Already deployed with same image")
                    print(f"   Current: {current_image}")
                    print(f"   Skipping deployment")
                    send_loki_log('deploy-k8s', 'info', skip_msg)
                    self.result['success'] = True
                    self.result['action'] = 'skipped'
                    self.result['message'] = 'Already deployed with same image'
                    return self._finalize(0)
                else:
                    # Different image - update
                    print(f"🔄 Different image detected")
                    print(f"   Current: {current_image}")
                    print(f"   New: {full_image}")
                    send_loki_log('deploy-k8s', 'info', f"Different image detected. Current: {current_image}, New: {full_image}")
                    self.result['action'] = 'updated'
            else:
                # First-time deployment
                print(f"📦 New deployment (not found)")
                send_loki_log('deploy-k8s', 'info', f"New deployment (not found) for {namespace}/{deployment}")
                self.result['action'] = 'deployed'
            
            # Step 8: Switch context
            print(f"🔄 Switching context to {namespace}...")
            send_loki_log('deploy-k8s', 'info', f"Switching context to {namespace}")
            if not self.switch_context(namespace):
                error_msg = 'Failed to switch context'
                send_loki_log('deploy-k8s', 'error', error_msg)
                self.result['message'] = error_msg
                return self._finalize(1)
            print(f"✅ Context switched")
            send_loki_log('deploy-k8s', 'info', f"Context switched to {namespace}")
            
            # Step 9: Deploy image
            action_verb = "Updating" if current_image else "Deploying"
            print(f"🚀 {action_verb} image...")
            send_loki_log('deploy-k8s', 'info', f"{action_verb} image {full_image} to {namespace}/{deployment}")
            if not self.set_image(namespace, deployment, full_image):
                error_msg = 'Failed to set image'
                send_loki_log('deploy-k8s', 'error', error_msg)
                self.result['message'] = error_msg
                return self._finalize(1)
            
            success_msg = f"Deployment successful! Image {full_image} deployed to {namespace}/{deployment}"
            print(f"✅ Deployment successful!")
            send_loki_log('deploy-k8s', 'info', success_msg)
            self.result['success'] = True
            self.result['message'] = 'Deployment successful'
            return self._finalize(0)
            
        except KeyboardInterrupt:
            error_msg = "Deployment cancelled by user"
            print(f"\n❌ {error_msg}", file=sys.stderr)
            send_loki_log('deploy-k8s', 'error', error_msg)
            self.result['message'] = 'Cancelled by user'
            return self._finalize(1)
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('deploy-k8s', 'error', error_msg)
            self.result['message'] = str(e)
            return self._finalize(1)
    
    def get_result(self) -> Dict[str, Any]:
        """Get deployment result.
        
        Returns:
            Result dictionary
        """
        return self.result


    def send_webhook(self, success: bool):
        """Send deployment result to Microsoft Teams webhook."""
        if not self.webhook_url:
            return
        
        status_text = "SUCCESS" if success else "FAILED"
        namespace = self.result.get('namespace') or '-'
        deployment = self.result.get('deployment') or '-'
        image = self.result.get('image') or '-'
        previous_image = self.result.get('previous_image') or '-'
        action = self.result.get('action') or '-'
        message = self.result.get('message') or '-'
        
        facts = [
            ("Repository", self.repo),
            ("Reference", self.refs),
            ("Action", action),
            ("Namespace", namespace),
            ("Deployment", deployment),
            ("Image", image),
            ("Previous Image", previous_image),
            ("Message", message),
        ]
        
        send_teams_notification(
            self.webhook_url,
            title=f"K8s Deployment {status_text}",
            facts=facts,
            success=success,
            summary=f"K8s Deployment {status_text}"
        )
    
    def _finalize(self, exit_code: int) -> int:
        """Finalize deployment by sending webhook notification if configured."""
        success = exit_code == 0
        self.result['success'] = success
        if self.webhook_url:
            self.send_webhook(success)
        return exit_code
    
    def _run_subprocess(self, command: list[str], **kwargs) -> subprocess.CompletedProcess:
        """Run subprocess command with optional verbose logging."""
        capture_output = kwargs.get('capture_output', False)
        text_mode = kwargs.get('text', True)
        
        if self.verbose:
            print(f"   ↳ Running: {' '.join(command)}")
        
        result = subprocess.run(command, **kwargs)
        
        if self.verbose and capture_output:
            if result.stdout:
                end = '' if text_mode else None
                print(result.stdout, end=end)
            if result.stderr:
                end = '' if text_mode else None
                print(result.stderr, file=sys.stderr, end=end)
        
        return result
    
    def update_gitops_manifest(self, namespace: str, deployment: str, image: str) -> bool:
        """Update gitops-k8s repository manifests using set-image-yaml."""
        branch = f"{self.refs}-qoin"
        manifest_path = f"{namespace}/{deployment}_deployment.yaml"
        
        print(f"   ➤ Branch: {branch}")
        print(f"   ➤ Path:   {manifest_path}")
        print(f"   ➤ Image:  {image}")
        
        try:
            result = self._run_subprocess(
                [
                    'doq',
                    'set-image-yaml',
                    'gitops-k8s',
                    branch,
                    manifest_path,
                    image
                ],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                print(f"❌ Failed to update gitops-k8s manifest", file=sys.stderr)
                if result.stdout and not self.verbose:
                    print(result.stdout, file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return False
            
            if result.stdout and not self.verbose:
                print(result.stdout, end='')
            
            return True
        except subprocess.TimeoutExpired:
            print(f"❌ Timeout updating gitops-k8s manifest", file=sys.stderr)
            return False
        except Exception as exc:
            print(f"❌ Error updating gitops-k8s manifest: {exc}", file=sys.stderr)
            return False


def cmd_deploy_k8s(args):
    """Command handler for 'doq deploy-k8s'."""
    custom_image = getattr(args, 'image', None)
    namespace_override = getattr(args, 'namespace', None)
    deployment_override = getattr(args, 'deployment', None)
    webhook_url = getattr(args, 'webhook', None)
    gitops_mode = getattr(args, 'gitops_k8s', False)
    verbose = getattr(args, 'verbose', False)
    deployer = K8sDeployer(
        args.repo,
        args.refs,
        custom_image=custom_image,
        namespace_override=namespace_override,
        deployment_override=deployment_override,
        webhook_url=webhook_url,
        gitops_mode=gitops_mode,
        verbose=verbose
    )
    exit_code = deployer.deploy()
    
    # Output result as JSON if requested
    if args.json:
        result = deployer.get_result()
        print("\n" + json.dumps(result, indent=2))
    
    sys.exit(exit_code)


def register_commands(subparsers):
    """Register k8s-deployer commands with argparse.
    
    This function is called by the plugin manager to register
    the plugin's commands.
    
    Args:
        subparsers: The argparse subparsers object
    """
    # Deploy-k8s command
    deploy_k8s_parser = subparsers.add_parser('deploy-k8s',
                                              help='Deploy application to Kubernetes',
                                              description='Deploy application to Kubernetes cluster using kubectl based on cicd.json configuration')
    deploy_k8s_parser.add_argument('repo', help='Repository name (e.g., saas-apigateway)')
    deploy_k8s_parser.add_argument('refs', help='Branch or tag name (e.g., develop, staging, production, v1.0.0)')
    deploy_k8s_parser.add_argument('--image', type=str, default=None,
                                   help='Custom Docker image to deploy (e.g., loyaltolpi/myapp:v1.0.0)')
    deploy_k8s_parser.add_argument('--namespace', type=str,
                                   help='Override Kubernetes namespace (skips auto construction)')
    deploy_k8s_parser.add_argument('--deployment', type=str,
                                   help='Override Kubernetes deployment name')
    deploy_k8s_parser.add_argument('--webhook', type=str,
                                   help='Microsoft Teams webhook URL for deployment notifications (fallback to TEAMS_WEBHOOK env or ~/.doq/.env)')
    deploy_k8s_parser.add_argument('--gitops-k8s', action='store_true',
                                   help='Also update gitops-k8s repository manifest before deployment')
    deploy_k8s_parser.add_argument('--verbose', action='store_true',
                                   help='Show underlying doq/kubectl commands being executed')
    deploy_k8s_parser.add_argument('--json', action='store_true',
                                   help='Output result in JSON format')
    deploy_k8s_parser.set_defaults(func=cmd_deploy_k8s)

