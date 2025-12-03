#!/usr/bin/env python3
"""Kubernetes application deployment plugin."""
from __future__ import annotations
import json
import sys
import subprocess
from typing import Dict, Any, Optional, Tuple

from config_utils import get_env_override
from plugins.base import BasePlugin
from plugins.shared_helpers import (
    get_commit_hash_from_bitbucket,
    resolve_teams_webhook
)


class K8sDeployer(BasePlugin):
    """Kubernetes application deployer."""
    
    def __init__(
        self,
        repo: str,
        refs: str,
        custom_image: Optional[str] = None,
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
            namespace_override: Override Kubernetes namespace
            deployment_override: Override Kubernetes deployment name
            webhook_url: Microsoft Teams webhook URL
            gitops_mode: Also update gitops-k8s repository manifest
            verbose: Show underlying commands
        """
        super().__init__('k8s-deployer')
        self.repo = repo
        self.refs = refs
        self.custom_image = custom_image
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

    def get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
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

    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        # Docker namespace
        if env_val := get_env_override('DOQ_DOCKER_NAMESPACE'):
            self.config.setdefault('docker', {})['namespace'] = env_val
        
        # Bitbucket organization
        if env_val := get_env_override('DOQ_BITBUCKET_ORG'):
            self.config.setdefault('bitbucket', {})['organization'] = env_val
    
    def fetch_cicd_config(self) -> Optional[Dict[str, Any]]:
        """Fetch cicd.json from Bitbucket."""
        try:
            cicd_path = self.get_config('bitbucket.cicd_path', 'cicd/cicd.json')
            cicd_content = self.fetch_bitbucket_file(self.repo, self.refs, cicd_path)
            return json.loads(cicd_content)
        except Exception as e:
            self.log_error(f"Error fetching cicd.json: {e}")
            return None
    
    def determine_namespace(self, cicd_config: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """Determine namespace and deployment name from cicd.json."""
        deployment = self.deployment_override or cicd_config.get('DEPLOYMENT')
        if not deployment:
            self.log_error("DEPLOYMENT field not found in cicd.json")
            return (None, None)
        
        if self.namespace_override:
            namespace = self.namespace_override
        else:
            project = cicd_config.get('PROJECT')
            if not project:
                self.log_error("PROJECT field not found in cicd.json")
                return (None, None)
            namespace = f"{self.refs}-{project}"
        
        return (namespace, deployment)
    
    def check_image_ready(self) -> Optional[Dict[str, Any]]:
        """Check if image is ready in Docker Hub using doq image command."""
        try:
            result = self.run_command(
                ['doq', 'image', self.repo, self.refs, '--json'],
                capture_output=True,
                text=True,
                timeout=60,
                verbose=self.verbose
            )
            
            if result.returncode != 0:
                print(f"❌ Error checking image status", file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return None
            
            image_info = json.loads(result.stdout)
            
            if not image_info.get('ready', False):
                print(f"❌ Image not ready in Docker Hub", file=sys.stderr)
                print(f"   Please build the image first using: doq devops-ci {self.repo} {self.refs}", file=sys.stderr)
                return None
            
            return image_info
            
        except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
            print(f"❌ Error checking image status: {e}", file=sys.stderr)
            return None
    
    def get_current_image(self, namespace: str, deployment: str) -> Optional[str]:
        """Get current image from deployment using doq get-image command."""
        try:
            result = self.run_command(
                ['doq', 'get-image', namespace, deployment],
                capture_output=True,
                text=True,
                timeout=60,
                verbose=self.verbose
            )
            
            if result.returncode != 0:
                return None
            
            deployment_info = json.loads(result.stdout)
            containers = deployment_info.get('containers', [])
            
            if not containers:
                return None
            
            return containers[0].get('image')
            
        except Exception as e:
            print(f"⚠️  Warning: Could not get current deployment image: {e}", file=sys.stderr)
            return None
    
    def switch_context(self, namespace: str) -> bool:
        """Switch kubectl context using doq ns command."""
        try:
            result = self.run_command(
                ['doq', 'ns', namespace],
                capture_output=True,
                text=True,
                timeout=30,
                verbose=self.verbose
            )
            return result.returncode == 0
        except Exception as e:
            self.log_error(f"Error switching context: {e}")
            return False
    
    def set_image(self, namespace: str, deployment: str, image: str) -> bool:
        """Deploy image using doq set-image command."""
        try:
            result = self.run_command(
                ['doq', 'set-image', namespace, deployment, image],
                capture_output=True,
                text=True,
                timeout=120,
                verbose=self.verbose
            )
            
            if result.returncode != 0:
                self.log_error("Failed to set image")
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return False
            
            if result.stdout and not self.verbose:
                print(result.stdout, end='')
            
            return True
        except Exception as e:
            self.log_error(f"Error setting image: {e}")
            return False
    
    def deploy(self) -> int:
        """Main deployment logic."""
        try:
            self.log_info(f"Starting deployment for {self.repo}:{self.refs}")
            
            # Step 1: Load authentication
            if not self.load_auth():
                self.result['message'] = 'Authentication not found'
                return self._finalize(1)
            
            # Step 2: Fetch cicd.json
            print(f"🔍 Fetching deployment configuration...")
            self.log_info(f"Fetching deployment configuration for {self.repo}:{self.refs}")
            cicd_config = self.fetch_cicd_config()
            if not cicd_config:
                self.result['message'] = 'Failed to fetch cicd.json'
                return self._finalize(1)
            
            # Step 3: Determine namespace and deployment
            namespace, deployment = self.determine_namespace(cicd_config)
            if not namespace or not deployment:
                self.result['message'] = 'Failed to determine namespace or deployment'
                return self._finalize(1)
            
            self.result['namespace'] = namespace
            self.result['deployment'] = deployment
            
            print(f"🎯 Target: {namespace} / {deployment}")
            self.log_info(f"Target: {namespace} / {deployment}")
            
            # Step 4: Determine image to use
            if self.custom_image:
                full_image = self.custom_image
                print(f"📦 Using custom image: {full_image}")
                print(f"ℹ️  Custom image mode - skipping Docker Hub validation")
                self.log_info(f"Using custom image: {full_image}")
            else:
                print(f"🔍 Checking image status...")
                self.log_info(f"Checking image status for {self.repo}:{self.refs}")
                image_info = self.check_image_ready()
                if not image_info:
                    self.result['message'] = 'Image not ready in Docker Hub'
                    return self._finalize(1)
                
                commit_info = self.get_commit_hash(self.repo, self.refs)
                tag = commit_info['short_hash']
                
                namespace_prefix = self.get_config('docker.namespace', 'loyaltolpi')
                image_name = cicd_config.get('IMAGE', self.repo)
                full_image = f"{namespace_prefix}/{image_name}:{tag}"
                
                print(f"✅ Image ready: {full_image}")
                self.log_info(f"Image ready: {full_image}")
            
            self.result['image'] = full_image
            
            # Step 5: Update GitOps manifests
            if self.gitops_mode:
                print(f"🧩 Updating GitOps manifest in gitops-k8s repository...")
                self.log_info(f"Updating GitOps manifest in gitops-k8s repository")
                if not self.update_gitops_manifest(namespace, deployment, full_image):
                    self.result['message'] = 'Failed to update gitops-k8s manifest'
                    return self._finalize(1)
                print(f"✅ GitOps manifest updated")
            
            # Step 6: Get current deployment image
            print(f"🔍 Checking current deployment...")
            self.log_info(f"Checking current deployment in {namespace}/{deployment}")
            current_image = self.get_current_image(namespace, deployment)
            self.result['previous_image'] = current_image
            
            # Step 7: Compare images
            if current_image:
                if current_image == full_image:
                    skip_msg = f"Already deployed with same image: {current_image}. Skipping deployment."
                    print(f"✅ Already deployed with same image")
                    print(f"   Current: {current_image}")
                    print(f"   Skipping deployment")
                    self.log_info(skip_msg)
                    self.result['success'] = True
                    self.result['action'] = 'skipped'
                    self.result['message'] = 'Already deployed with same image'
                    return self._finalize(0)
                else:
                    print(f"🔄 Different image detected")
                    print(f"   Current: {current_image}")
                    print(f"   New: {full_image}")
                    self.log_info(f"Different image detected. Current: {current_image}, New: {full_image}")
                    self.result['action'] = 'updated'
            else:
                print(f"📦 New deployment (not found)")
                self.log_info(f"New deployment (not found) for {namespace}/{deployment}")
                self.result['action'] = 'deployed'
            
            # Step 8: Switch context
            print(f"🔄 Switching context to {namespace}...")
            self.log_info(f"Switching context to {namespace}")
            if not self.switch_context(namespace):
                self.result['message'] = 'Failed to switch context'
                return self._finalize(1)
            print(f"✅ Context switched")
            
            # Step 9: Deploy image
            action_verb = "Updating" if current_image else "Deploying"
            print(f"🚀 {action_verb} image...")
            self.log_info(f"{action_verb} image {full_image} to {namespace}/{deployment}")
            if not self.set_image(namespace, deployment, full_image):
                self.result['message'] = 'Failed to set image'
                return self._finalize(1)
            
            success_msg = f"Deployment successful! Image {full_image} deployed to {namespace}/{deployment}"
            print(f"✅ Deployment successful!")
            self.log_info(success_msg)
            self.result['success'] = True
            self.result['message'] = 'Deployment successful'
            return self._finalize(0)
            
        except KeyboardInterrupt:
            self.log_error("Deployment cancelled by user")
            self.result['message'] = 'Cancelled by user'
            return self._finalize(1)
        except Exception as e:
            self.log_error(f"Unexpected error: {e}")
            self.result['message'] = str(e)
            return self._finalize(1)

    def send_webhook(self, success: bool):
        """Send deployment result to Microsoft Teams webhook."""
        if not self.webhook_url:
            return
        
        status_text = "SUCCESS" if success else "FAILED"
        facts = [
            ("Repository", self.repo),
            ("Reference", self.refs),
            ("Action", self.result.get('action', '-')),
            ("Namespace", self.result.get('namespace', '-')),
            ("Deployment", self.result.get('deployment', '-')),
            ("Image", self.result.get('image', '-')),
            ("Previous Image", self.result.get('previous_image', '-')),
            ("Message", self.result.get('message', '-')),
        ]
        
        self.send_notification(
            title=f"K8s Deployment {status_text}",
            facts=facts,
            success=success,
            webhook_url=self.webhook_url
        )
    
    def _finalize(self, exit_code: int) -> int:
        """Finalize deployment by sending webhook notification if configured."""
        success = exit_code == 0
        self.result['success'] = success
        if self.webhook_url:
            self.send_webhook(success)
        return exit_code
    
    def update_gitops_manifest(self, namespace: str, deployment: str, image: str) -> bool:
        """Update gitops-k8s repository manifests using set-image-yaml."""
        branch = f"{self.refs}-qoin"
        manifest_path = f"{namespace}/{deployment}_deployment.yaml"
        
        print(f"   ➤ Branch: {branch}")
        print(f"   ➤ Path:   {manifest_path}")
        print(f"   ➤ Image:  {image}")
        
        try:
            result = self.run_command(
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
                timeout=120,
                verbose=self.verbose
            )
            
            if result.returncode != 0:
                self.log_error("Failed to update gitops-k8s manifest")
                if result.stdout and not self.verbose:
                    print(result.stdout, file=sys.stderr)
                if result.stderr and not self.verbose:
                    print(result.stderr, file=sys.stderr)
                return False
            
            if result.stdout and not self.verbose:
                print(result.stdout, end='')
            
            return True
        except Exception as exc:
            self.log_error(f"Error updating gitops-k8s manifest: {exc}")
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
    
    if args.json:
        print("\n" + json.dumps(deployer.result, indent=2))
    
    sys.exit(exit_code)


def register_commands(subparsers):
    """Register k8s-deployer commands with argparse."""
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
                                   help='Microsoft Teams webhook URL for deployment notifications')
    deploy_k8s_parser.add_argument('--gitops-k8s', action='store_true',
                                   help='Also update gitops-k8s repository manifest before deployment')
    deploy_k8s_parser.add_argument('--verbose', action='store_true',
                                   help='Show underlying doq/kubectl commands being executed')
    deploy_k8s_parser.add_argument('--json', action='store_true',
                                   help='Output result in JSON format')
    deploy_k8s_parser.set_defaults(func=cmd_deploy_k8s)
