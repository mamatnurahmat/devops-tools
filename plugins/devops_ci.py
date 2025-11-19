#!/usr/bin/env python3
"""DevOps CI/CD Build Tool - Python implementation."""
import json
import os
import subprocess
import sys
import time
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import requests

# Import shared helpers
from plugins.shared_helpers import (
    load_auth_file,
    check_docker_image_exists,
    fetch_bitbucket_file,
    get_commit_hash_from_bitbucket,
    resolve_teams_webhook,
    send_teams_notification,
    send_loki_log
)


VERSION = "2.0.1"
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")

# Dummy auth dictionary for creating empty auth.json files
DUMMY_AUTH_DICT = {
    "GIT_USER": "",
    "GIT_PASSWORD": "",
    "DOCKERHUB_USER": "",
    "DOCKERHUB_PASSWORD": "",
    "NTFY_URL": ""
}


def show_version():
    """Show version information."""
    print(f"DevOps CI/CD Builder v{VERSION}")
    print(f"Build date: {BUILD_DATE}")


def show_help():
    """Show extended help information."""
    help_text = """
DevOps CI/CD Docker Image Builder
==================================

A tool to build and manage Docker images from Bitbucket repositories.

USAGE:
    doq devops-ci <repo> <refs> [custom_image] [options]

ARGUMENTS:
    repo            Repository name (e.g., saas-be-core, saas-apigateway)
    refs            Branch or tag name (e.g., develop, main, v1.0.0)
    custom_image    (Optional) Custom image name/tag to override default

OPTIONS:
    --rebuild       Force rebuild even if image already exists
    --no-cache      Disable Docker layer caching during build
    --json          Show build progress + JSON result at end
    --short         Silent build, output only image name
    --local         Build from current working directory using local cicd/cicd.json
    --helper        Use helper mode (no API dependency)
    --image-name    (Helper mode) Custom image name to build
    --registry      (Helper mode) Registry URL for build args
    --port          (Helper mode) Application port for build args

EXAMPLES:
    # Build image for saas-be-core develop branch
    doq devops-ci saas-be-core develop

    # Force rebuild
    doq devops-ci saas-be-core develop --rebuild

    # Force rebuild with no cache
    doq devops-ci saas-be-core develop --rebuild --no-cache

    # Use helper mode
    doq devops-ci saas-be-core develop --helper

For more information, visit: https://github.com/mamatnurahmat/devops-tools
"""
    print(help_text)


class BuildConfig:
    """Configuration for DevOps CI/CD builds."""
    
    def __init__(self):
        """Initialize build configuration from plugin config file."""
        from config_utils import load_json_config, get_env_override
        
        self.config_dir = Path.home() / ".doq"
        self.plugin_config_file = self.config_dir / "plugins" / "devops-ci.json"
        
        # Migrate from old location if needed
        self._migrate_from_old_location()
        
        # Ensure auth file exists
        self._ensure_auth_file()
        
        # Load plugin config
        self.config = self._load_config()
        
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _migrate_from_old_location(self):
        """Migrate config from old ~/.devops to new ~/.doq location."""
        old_dir = Path.home() / ".devops"
        new_dir = self.config_dir
        
        # Migrate auth.json if exists in old location
        old_auth = old_dir / "auth.json"
        new_auth = new_dir / "auth.json"
        
        if old_auth.exists() and not new_auth.exists():
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_auth, new_auth)
            print(f"✅ Migrated auth.json from {old_dir} to {new_dir}")
    
    def _ensure_auth_file(self):
        """Ensure auth.json exists with dummy data if empty."""
        auth_file = self.config_dir / "auth.json"
        
        if not auth_file.exists():
            # Create with dummy values
            self.config_dir.mkdir(parents=True, exist_ok=True)
            with open(auth_file, 'w') as f:
                json.dump(DUMMY_AUTH_DICT, f, indent=2)
        elif auth_file.stat().st_size == 0 or auth_file.read_text().strip() == "":
            # File exists but is empty
            with open(auth_file, 'w') as f:
                json.dump(DUMMY_AUTH_DICT, f, indent=2)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from plugin config file."""
        from config_utils import load_json_config
        
        # Default configuration
        default_config = {
            "api": {
                "base_url": "https://api.devops.loyalto.id/v1",
                "timeout": 30
            },
            "docker": {
                "namespace": "loyaltolpi",
                "buildx_args": [
                    "--sbom=true",
                    "--provenance=true",
                    "--platform=linux/amd64"
                ]
            },
            "notification": {
                "enabled": True,
                "topic": "ci_status"
            },
            "git": {
                "clone_depth": 1
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
        from config_utils import get_env_override
        
        # API overrides
        api_url = get_env_override("DEVOPS_CI_API_URL")
        if api_url:
            self.config["api"]["base_url"] = api_url
        
        # Docker overrides
        docker_ns = get_env_override("DEVOPS_CI_DOCKER_NAMESPACE")
        if docker_ns:
            self.config["docker"]["namespace"] = docker_ns
        
        # Notification overrides
        notif_enabled = get_env_override("DEVOPS_CI_NOTIFICATION_ENABLED")
        if notif_enabled:
            self.config["notification"]["enabled"] = notif_enabled.lower() in ('true', '1', 'yes')
    
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


class DevOpsCIBuilder:
    """Main builder class for DevOps CI/CD."""
    
    def __init__(self, repo: str = "", refs: str = "", rebuild: bool = False,
                 json_output: bool = False, short_output: bool = False,
                 custom_image: str = "", helper_mode: bool = False,
                 helper_args: Optional[Dict[str, str]] = None,
                 builder_name: Optional[str] = None,
                 webhook_url: Optional[str] = None, no_cache: bool = False,
                 local_mode: bool = False, build_args: Optional[Dict[str, str]] = None):
        """Initialize builder with configuration."""
        self.repo = repo
        self.refs = refs
        self.rebuild = rebuild
        self.json_output = json_output
        self.short_output = short_output
        self.custom_image = custom_image
        self.helper_mode = helper_mode
        self.helper_args = helper_args or {}
        self.builder_name = builder_name
        self.teams_webhook_url = resolve_teams_webhook(webhook_url)
        self.no_cache = no_cache
        self.local_mode = local_mode
        self.build_args = build_args or {}
        
        self.config = BuildConfig()
        self.build_dir = None
        self.result = {
            'success': False,
            'image': '',
            'message': ''
        }
    
    def _output_build_result(self, metadata: Dict[str, Any]):
        """Output build result in appropriate format.
        
        Args:
            metadata: Dict with 'image_name' key
        """
        if self.short_output:
            print(metadata['image_name'])
            send_loki_log('devops-ci', 'info', f"Build completed: {metadata['image_name']}")
        elif not self.json_output:
            print(f"\n✅ Build completed successfully!")
            print(f"   Image: {metadata['image_name']}")
            send_loki_log('devops-ci', 'info', f"Build completed successfully! Image: {metadata['image_name']}")
        
        self.result['success'] = True
        self.result['image'] = metadata['image_name']
        self.result['message'] = 'Build successful'
        
        if self.json_output:
            print(json.dumps(self.result))
            send_loki_log('devops-ci', 'info', f"Build successful: {metadata['image_name']}")
    
    def _get_tag_version(self, commit_info: Dict[str, Any]) -> str:
        """Get tag version from commit info based on ref_type.
        
        Args:
            commit_info: Dict with 'ref_type' and 'short_hash'
            
        Returns:
            Tag version string (either refs for tags or short_hash for branches)
        """
        if commit_info['ref_type'] == 'tag':
            return self.refs
        else:
            return commit_info['short_hash']
    
    def build(self) -> int:
        """Execute the build process."""
        exit_code = 1
        try:
            if self.local_mode:
                if not self.short_output:
                    print("🏠 Running in LOCAL MODE")
                send_loki_log('devops-ci', 'info', f"Starting build in LOCAL MODE for {self.repo}:{self.refs}")
                exit_code = self._build_local_mode()
            elif self.helper_mode:
                if not self.short_output:
                    print("🔧 Running in HELPER MODE")
                send_loki_log('devops-ci', 'info', f"Starting build in HELPER MODE for {self.repo}:{self.refs}")
                exit_code = self._build_helper_mode()
            else:
                if not self.short_output:
                    print("🌐 Running in API MODE")
                send_loki_log('devops-ci', 'info', f"Starting build in API MODE for {self.repo}:{self.refs}")
                exit_code = self._build_api_mode()
        except Exception as e:
            self.result['message'] = str(e)
            error_msg = f"Build failed: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            if self.json_output:
                print(json.dumps(self.result))
            exit_code = 1
        finally:
            success = exit_code == 0 and self.result.get('success', False)
            if not success and not self.result.get('message'):
                self.result['message'] = 'Build failed'
            self.result['success'] = success
            self._send_teams_webhook(success)
        
        return exit_code
    
    def _build_api_mode(self) -> int:
        """Build using API mode (default)."""
        # Load auth
        try:
            auth_data = load_auth_file()
        except FileNotFoundError as e:
            if not self.short_output:
                print(f"❌ {e}", file=sys.stderr)
            return 1
        
        # Get build metadata
        metadata = self._fetch_build_metadata_local(auth_data)
        if not metadata:
            return 1
        
        # Check if image already exists (unless rebuild flag is set)
        if not self.rebuild:
            check_result = check_docker_image_exists(metadata['image_name'], auth_data, verbose=False)
            if check_result['exists']:
                skip_msg = f"Image already ready: {metadata['image_name']}. Skipping build."
                if not self.short_output:
                    print(f"✅ {skip_msg}")
                send_loki_log('devops-ci', 'info', skip_msg)
                if self.short_output:
                    print(metadata['image_name'])
                self.result['success'] = True
                self.result['image'] = metadata['image_name']
                self.result['message'] = 'Image already exists'
                
                # Send notification
                self._send_notification(auth_data, metadata['image_name'], "skipped")
                
                if self.json_output:
                    print(json.dumps(self.result))
                return 0
        
        # Get build config
        build_config = self._fetch_build_config_local(auth_data)
        if not build_config:
            return 1
        
        # Clone repository
        if not self._clone_repository(auth_data, metadata):
            return 1
        
        # Build Docker image
        if not self._build_docker_image(metadata, build_config):
            self._cleanup()
            return 1
        
        # Push image
        if not self._push_docker_image(metadata):
            self._cleanup()
            return 1
        
        # Send notification
        self._send_notification(auth_data, metadata['image_name'], "success")
        
        # Cleanup
        self._cleanup()
        
        # Output result
        self._output_build_result(metadata)
        
        return 0
    
    def _build_helper_mode(self) -> int:
        """Build using helper mode (no API dependency)."""
        # Load auth
        try:
            auth_data = load_auth_file()
        except FileNotFoundError as e:
            if not self.short_output:
                print(f"❌ {e}", file=sys.stderr)
            return 1
        
        # Get metadata from helper args or generate
        metadata = self._generate_helper_metadata(auth_data)
        if not metadata:
            return 1
        
        # Get build config from cicd.json
        build_config = self._fetch_build_config_local(auth_data)
        if not build_config:
            return 1
        
        # Clone repository
        if not self._clone_repository(auth_data, metadata):
            return 1
        
        # Build Docker image
        if not self._build_docker_image(metadata, build_config):
            self._cleanup()
            return 1
        
        # Push image
        if not self._push_docker_image(metadata):
            self._cleanup()
            return 1
        
        # Cleanup
        self._cleanup()
        
        # Output result
        self._output_build_result(metadata)
        
        return 0

    def _build_local_mode(self) -> int:
        """Build using local working directory as build context."""
        repo_path = Path.cwd()
        
        # Load auth for registry checks/push
        try:
            auth_data = load_auth_file()
        except FileNotFoundError as e:
            if not self.short_output:
                print(f"❌ {e}", file=sys.stderr)
            return 1
        
        # Load local cicd configuration
        try:
            build_config = self._load_local_build_config(repo_path)
        except Exception as e:
            error_msg = f"Failed to read local cicd/cicd.json: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            return 1
        
        # Resolve commit information from local git
        try:
            commit_info = self._get_local_commit_info(repo_path)
        except Exception as e:
            if not self.short_output:
                error_msg = f"Failed to resolve local git metadata: {e}"
                print(f"❌ {error_msg}", file=sys.stderr)
                send_loki_log('devops-ci', 'error', error_msg)
            return 1
        
        # Determine image name
        image_override = self.helper_args.get('image_name') or self.custom_image
        if image_override:
            image_name = self._parse_custom_image(image_override, commit_info)
        else:
            image_from_config = build_config.get('IMAGE', self.repo)
            namespace = self.config.get('docker.namespace', 'loyaltolpi')
            tag_version = self._get_tag_version(commit_info)
            image_name = f"{namespace}/{image_from_config}:{tag_version}"
        
        metadata = {
            'image_name': image_name,
            'commit_hash': commit_info['full_hash'],
            'short_hash': commit_info['short_hash'],
            'ref_type': commit_info['ref_type']
        }
        
        # Skip build if image already exists and rebuild not requested
        if not self.rebuild:
            check_result = check_docker_image_exists(metadata['image_name'], auth_data, verbose=False)
            if check_result['exists']:
                if not self.short_output:
                    print(f"✅ Image already ready: {metadata['image_name']}. Skipping build.")
                if self.short_output:
                    print(metadata['image_name'])
                self.result['success'] = True
                self.result['image'] = metadata['image_name']
                self.result['message'] = 'Image already exists'
                
                # Send notification
                self._send_notification(auth_data, metadata['image_name'], "skipped")
                
                if self.json_output:
                    print(json.dumps(self.result))
                return 0
        
        # Build Docker image from current working directory
        if not self._build_docker_image(metadata, build_config, build_context=str(repo_path)):
            return 1
        
        # Send notification
        self._send_notification(auth_data, metadata['image_name'], "success")
        
        # Output result
        self._output_build_result(metadata)
        
        return 0
    
    def _get_local_commit_info(self, repo_path: Path) -> Dict[str, Any]:
        """Resolve commit information for local repository."""
        def _run_git(*args: str) -> str:
            result = subprocess.run(
                ['git', *args],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                message = result.stderr.strip() or result.stdout.strip() or "Unknown git error"
                raise RuntimeError(message)
            return result.stdout.strip()
        
        if not self.refs:
            raise ValueError("Reference (branch/tag) is required in local mode")
        
        full_hash = _run_git('rev-parse', self.refs)
        short_hash = _run_git('rev-parse', '--short', full_hash)
        
        # Determine ref type
        ref_type = 'branch'
        tag_check = subprocess.run(
            ['git', 'rev-parse', '--verify', f'refs/tags/{self.refs}'],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if tag_check.returncode == 0:
            ref_type = 'tag'
        else:
            head_check = subprocess.run(
                ['git', 'rev-parse', '--verify', f'refs/heads/{self.refs}'],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            if head_check.returncode != 0 and self.refs == full_hash:
                ref_type = 'commit'
        
        return {
            'full_hash': full_hash,
            'short_hash': short_hash,
            'ref_type': ref_type
        }
    
    def _load_local_build_config(self, repo_path: Path) -> Dict[str, Any]:
        """Load cicd configuration from the local working tree."""
        cicd_path = repo_path / 'cicd' / 'cicd.json'
        if not cicd_path.exists():
            raise FileNotFoundError(f"{cicd_path} not found")
        
        try:
            with open(cicd_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {cicd_path}: {e}") from e
    
    def _fetch_build_metadata_local(self, auth_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Fetch build metadata using local Bitbucket API calls."""
        if not self.short_output:
            print(f"📦 Fetching build metadata for repo={self.repo}, refs={self.refs} ...")
        send_loki_log('devops-ci', 'info', f"Fetching build metadata for repo={self.repo}, refs={self.refs}")
        
        try:
            # Get commit hash from Bitbucket
            commit_info = get_commit_hash_from_bitbucket(self.repo, self.refs, auth_data)
            
            # Get cicd.json to find IMAGE name
            try:
                cicd_content = fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json", auth_data)
                cicd_data = json.loads(cicd_content)
                image_name = cicd_data.get('IMAGE', self.repo)
            except Exception:
                image_name = self.repo
            
            # Build full image name
            namespace = self.config.get('docker.namespace', 'loyaltolpi')
            tag_version = self._get_tag_version(commit_info)
            full_image = f"{namespace}/{image_name}:{tag_version}"
            
            return {
                'image_name': full_image,
                'commit_hash': commit_info['full_hash'],
                'short_hash': commit_info['short_hash'],
                'ref_type': commit_info['ref_type']
            }
        
        except Exception as e:
            error_msg = f"Failed to fetch metadata: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            return None
    
    def _fetch_build_config_local(self, auth_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Fetch build config (cicd.json) using local Bitbucket API calls."""
        try:
            cicd_content = fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json", auth_data)
            cicd_data = json.loads(cicd_content)
            return cicd_data
        except Exception as e:
            if not self.short_output:
                print(f"⚠️  Warning: Could not fetch cicd.json: {e}")
                print(f"   Using default build configuration")
            return {}
    
    def _parse_custom_image(self, custom_image: str, commit_info: Dict[str, Any]) -> str:
        """Parse custom image name and build full image name with tag.
        
        Args:
            custom_image: Custom image name (may or may not include tag)
            commit_info: Dict with commit info
            
        Returns:
            Full image name with tag
        """
        # Check if user provided explicit tag
        if ':' in custom_image:
            # User provided explicit tag - use as-is
            return custom_image
        
        # No tag provided - add commit hash
        image_base = custom_image
        
        # Check if already has namespace
        if '/' in image_base:
            full_image_base = image_base
        else:
            namespace = self.config.get('docker.namespace', 'loyaltolpi')
            full_image_base = f"{namespace}/{image_base}"
        
        # Add commit hash as tag
        tag_version = self._get_tag_version(commit_info)
        return f"{full_image_base}:{tag_version}"
    
    def _build_default_image(self, repo: str, commit_info: Dict[str, Any]) -> str:
        """Build default image name from repo and commit info.
        
        Args:
            repo: Repository name
            commit_info: Dict with commit info
            
        Returns:
            Full image name with tag
        """
        namespace = self.config.get('docker.namespace', 'loyaltolpi')
        tag_version = self._get_tag_version(commit_info)
        return f"{namespace}/{repo}:{tag_version}"
    
    def _generate_helper_metadata(self, auth_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Generate metadata for helper mode."""
        try:
            commit_info = get_commit_hash_from_bitbucket(self.repo, self.refs, auth_data)
            
            # Get custom image name from helper args if provided
            custom_image = self.helper_args.get('image_name', '')
            
            if custom_image:
                full_image = self._parse_custom_image(custom_image, commit_info)
            else:
                # No custom image - use default
                full_image = self._build_default_image(self.repo, commit_info)
            
            return {
                'image_name': full_image,
                'commit_hash': commit_info['full_hash'],
                'short_hash': commit_info['short_hash'],
                'ref_type': commit_info['ref_type']
            }
        
        except Exception as e:
            error_msg = f"Failed to generate metadata: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            return None
    
    def _clone_repository(self, auth_data: Dict[str, str], metadata: Dict[str, Any]) -> bool:
        """Clone Git repository."""
        if not self.short_output:
            print(f"\n📥 Cloning repository...")
        send_loki_log('devops-ci', 'info', f"Cloning repository {self.repo} (refs: {self.refs})")
        
        try:
            # Create temporary directory
            self.build_dir = tempfile.mkdtemp(prefix='doq-build-')
            
            git_user = auth_data.get('GIT_USER', '')
            git_password = auth_data.get('GIT_PASSWORD', '')
            
            if not git_user or not git_password:
                raise ValueError("GIT_USER and GIT_PASSWORD required in auth.json")
            
            # Build clone URL with credentials
            clone_url = f"https://{git_user}:{git_password}@bitbucket.org/loyaltoid/{self.repo}.git"
            
            # Clone repository
            clone_depth = self.config.get('git.clone_depth', 1)
            clone_cmd = [
                'git', 'clone',
                '--depth', str(clone_depth),
                '--branch', self.refs,
                clone_url,
                self.build_dir
            ]
            
            result = subprocess.run(clone_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise RuntimeError(f"Git clone failed: {result.stderr}")
            
            # Checkout specific commit
            checkout_cmd = ['git', 'checkout', metadata['commit_hash']]
            result = subprocess.run(checkout_cmd, cwd=self.build_dir, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise RuntimeError(f"Git checkout failed: {result.stderr}")
            
            if not self.short_output:
                print(f"✅ Repository cloned successfully")
            send_loki_log('devops-ci', 'info', f"Repository cloned successfully: {self.repo}")
            
            return True
        
        except Exception as e:
            error_msg = f"Clone failed: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            return False
    
    def _setup_builder(self, builder_name: str) -> bool:
        """Setup Docker buildx builder with docker-container driver.
        
        Args:
            builder_name: Name of the builder to create/setup
            
        Returns:
            bool: True if setup successful
        """
        try:
            # Check if builder exists
            inspect = subprocess.run(
                ['docker', 'buildx', 'inspect', builder_name],
                capture_output=True,
                text=True
            )
            
            if inspect.returncode == 0:
                # Builder exists, check if it's using docker-container driver
                if 'docker-container' in inspect.stdout:
                    if not self.short_output:
                        print(f"✅ Builder '{builder_name}' already exists with docker-container driver")
                    return True
                else:
                    # Builder exists but using different driver - still usable
                    if not self.short_output:
                        print(f"✅ Builder '{builder_name}' already exists")
                    return True
            
            # Builder doesn't exist, create it
            if not self.short_output:
                print(f"🔨 Creating Docker buildx builder '{builder_name}'...")
            
            create_cmd = [
                'docker', 'buildx', 'create',
                '--name', builder_name,
                '--driver', 'docker-container',
                '--use'
            ]
            
            result = subprocess.run(create_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create builder: {result.stderr}")
            
            if not self.short_output:
                print(f"✅ Builder '{builder_name}' created successfully")
            
            return True
        
        except Exception as e:
            if not self.short_output:
                print(f"❌ Failed to setup builder: {e}", file=sys.stderr)
            return False
    
    def _build_docker_image(self, metadata: Dict[str, Any], build_config: Dict[str, Any],
                            build_context: Optional[str] = None) -> bool:
        """Build Docker image using buildx."""
        if not self.short_output:
            print(f"\n🔨 Building Docker image...")
            print(f"   Image: {metadata['image_name']}")
        send_loki_log('devops-ci', 'info', f"Building Docker image: {metadata['image_name']}")
        
        context_dir = build_context or self.build_dir
        if not context_dir:
            raise RuntimeError("Build context is not defined")
        
        try:
            # Build command
            buildx_args = self.config.get('docker.buildx_args', [])
            
            build_cmd = [
                'docker', 'buildx', 'build',
            ]
            if self.builder_name:
                # Setup builder if needed
                if not self._setup_builder(self.builder_name):
                    raise RuntimeError(f"Failed to setup builder '{self.builder_name}'")
                if not self.short_output:
                    print(f"   Builder: {self.builder_name}")
                build_cmd.extend(['--builder', self.builder_name])
            else:
                # Use default builder or create container-builder
                default_builder = 'container-builder'
                if not self._setup_builder(default_builder):
                    raise RuntimeError(f"Failed to setup default builder '{default_builder}'")
                if not self.short_output:
                    print(f"   Builder: {default_builder}")
                build_cmd.extend(['--builder', default_builder])
            build_cmd.extend([
                '-t', metadata['image_name'],
                '--push'
            ])
            build_cmd += buildx_args
            build_cmd.extend([
                '--attest', 'type=provenance,mode=max'
            ])
            if self.no_cache:
                build_cmd.append('--no-cache')
            
            # Add build args from cicd.json
            if build_config:
                registry = build_config.get('REGISTRY', self.helper_args.get('registry', ''))
                port = build_config.get('PORT', self.helper_args.get('port', ''))
                
                if registry:
                    build_cmd.extend(['--build-arg', f'REGISTRY={registry}'])
                if port:
                    build_cmd.extend(['--build-arg', f'PORT={port}'])
            
            # Add build args from command line (can override config file args)
            for key, value in self.build_args.items():
                build_cmd.extend(['--build-arg', f'{key}={value}'])
            
            # Add build directory
            build_cmd.append('.')
            
            # Run build
            if self.short_output or self.json_output:
                result = subprocess.run(build_cmd, cwd=context_dir, capture_output=True, text=True)
            else:
                result = subprocess.run(build_cmd, cwd=context_dir)
            
            if result.returncode != 0:
                error_msg = result.stderr if hasattr(result, 'stderr') else "Build failed"
                raise RuntimeError(f"Docker build failed: {error_msg}")
            
            if not self.short_output:
                print(f"✅ Image built successfully")
            send_loki_log('devops-ci', 'info', f"Image built successfully: {metadata['image_name']}")
            
            return True
        
        except Exception as e:
            error_msg = f"Docker build failed: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            send_loki_log('devops-ci', 'error', error_msg)
            return False
    
    def _push_docker_image(self, metadata: Dict[str, Any]) -> bool:
        """Push is already done by buildx --push flag."""
        if not self.short_output:
            print(f"✅ Image pushed to registry")
        send_loki_log('devops-ci', 'info', f"Image pushed to registry: {metadata['image_name']}")
        return True
    
    def _send_notification(self, auth_data: Dict[str, str], image_name: str, status: str):
        """Send notification to ntfy.sh."""
        if not self.config.get('notification.enabled', True):
            return
        
        ntfy_url = auth_data.get('NTFY_URL', '')
        if not ntfy_url:
            return
        
        try:
            topic = self.config.get('notification.topic', 'ci_status')
            
            # Status emojis
            status_emoji = {
                'success': '✅',
                'skipped': '⏭️',
                'failed': '❌'
            }
            
            emoji = status_emoji.get(status, '📦')
            
            message = {
                'topic': topic,
                'title': f'{emoji} DevOps CI Build {status.title()}',
                'message': f'Repository: {self.repo}\nBranch: {self.refs}\nImage: {image_name}',
                'priority': 3 if status == 'success' else 4
            }
            
            resp = requests.post(
                ntfy_url,
                json=message,
                headers={'Content-Type': 'application/json; charset=utf-8'},
                timeout=10
            )
            
            if resp.status_code == 200:
                if not self.short_output:
                    print(f"📤 Notification sent to ntfy.sh")
        
        except Exception as e:
            if not self.short_output:
                print(f"⚠️  Warning: Failed to send notification to ntfy.sh: {e}")
    
    def _send_teams_webhook(self, success: bool):
        """Send build summary to Microsoft Teams."""
        if not self.teams_webhook_url:
            return
        
        image = self.result.get('image') or '-'
        message = self.result.get('message') or '-'
        status_text = "SUCCESS" if success else "FAILED"
        action = 'built'
        if message.lower().startswith('image already'):
            action = 'skipped'
        elif not success:
            action = 'failed'
        
        facts = [
            ("Repository", self.repo or '-'),
            ("Reference", self.refs or '-'),
            ("Action", action),
            ("Image", image),
            ("Message", message),
        ]
        
        send_teams_notification(
            self.teams_webhook_url,
            title=f"DevOps CI Build {status_text}",
            facts=facts,
            success=success,
            summary=f"DevOps CI Build {status_text}"
        )
    
    def _cleanup(self):
        """Clean up build directory."""
        if self.build_dir and os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
            if not self.short_output:
                print(f"🧹 Cleaned up build directory")


def _detect_helper_mode(args) -> tuple[bool, Dict[str, str]]:
    """Detect if helper mode should be enabled based on arguments.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Tuple of (helper_mode bool, helper_args dict)
    """
    helper_args: Dict[str, str] = {}
    auto_helper_mode = False
    local_mode = getattr(args, 'local', False)
    
    if hasattr(args, 'image_name') and args.image_name:
        helper_args['image_name'] = args.image_name
        if not local_mode:
            auto_helper_mode = True
    
    if hasattr(args, 'registry') and args.registry:
        helper_args['registry'] = args.registry
        if not local_mode:
            auto_helper_mode = True
    
    if hasattr(args, 'port') and args.port:
        helper_args['port'] = args.port
        if not local_mode:
            auto_helper_mode = True
    
    if local_mode:
        helper_mode = False
    else:
        # Use explicit --helper flag if provided, otherwise use auto-detected mode
        helper_mode = getattr(args, 'helper', False) or auto_helper_mode
    
    return helper_mode, helper_args


def cmd_devops_ci(args):
    """Command handler for 'doq devops-ci'."""
    # Handle special flags
    if hasattr(args, 'help_devops_ci') and args.help_devops_ci:
        show_help()
        sys.exit(0)
    
    if hasattr(args, 'version_devops_ci') and args.version_devops_ci:
        show_version()
        sys.exit(0)
    
    # Validate required arguments
    if not args.repo or not args.refs:
        print("❌ Error: repo and refs are required arguments", file=sys.stderr)
        print("   Usage: doq devops-ci <repo> <refs> [options]", file=sys.stderr)
        sys.exit(1)
    
    # Detect helper mode
    helper_mode, helper_args = _detect_helper_mode(args)
    
    # Parse build args from command line
    build_args = {}
    build_arg_list = getattr(args, 'build_arg', None) or []
    for build_arg_str in build_arg_list:
        if '=' not in build_arg_str:
            print(f"❌ Error: Invalid build-arg format: {build_arg_str}", file=sys.stderr)
            print("   Expected format: KEY=VALUE", file=sys.stderr)
            sys.exit(1)
        key, value = build_arg_str.split('=', 1)
        if not key.strip():
            print(f"❌ Error: Build arg key cannot be empty: {build_arg_str}", file=sys.stderr)
            sys.exit(1)
        build_args[key.strip()] = value
    
    # Create builder
    builder = DevOpsCIBuilder(
        repo=args.repo,
        refs=args.refs,
        rebuild=args.rebuild,
        json_output=args.json,
        short_output=args.short,
        custom_image=args.custom_image,
        helper_mode=helper_mode,
        helper_args=helper_args,
        builder_name=getattr(args, 'use_builder', None),
        webhook_url=getattr(args, 'webhook', None),
        no_cache=args.no_cache,
        local_mode=getattr(args, 'local', False),
        build_args=build_args
    )
    
    # Run build
    exit_code = builder.build()
    sys.exit(exit_code)


def register_commands(subparsers):
    """Register devops-ci commands with argparse.
    
    This function is called by PluginManager to dynamically register
    the plugin's commands.
    
    Args:
        subparsers: The argparse subparsers object
    """
    # DevOps CI/CD command
    devops_ci_parser = subparsers.add_parser('devops-ci', 
                                             help='Build Docker images from repositories',
                                             description='Build Docker images from Bitbucket repositories using buildx with SBOM and provenance support')
    devops_ci_parser.add_argument('repo', nargs='?', help='Repository name (e.g., saas-be-core, saas-apigateway)')
    devops_ci_parser.add_argument('refs', nargs='?', help='Branch or tag name (e.g., develop, main, v1.0.0)')
    devops_ci_parser.add_argument('custom_image', nargs='?', default='',
                                   help='(Optional) Custom image name/tag to override default')
    devops_ci_parser.add_argument('--rebuild', action='store_true',
                                   help='Force rebuild even if image already exists')
    devops_ci_parser.add_argument('--no-cache', action='store_true',
                                   help='Disable Docker layer caching during build')
    devops_ci_parser.add_argument('--json', action='store_true',
                                   help='Show build progress + JSON result at end')
    devops_ci_parser.add_argument('--short', action='store_true',
                                   help='Silent build, output only image name')
    devops_ci_parser.add_argument('--helper', action='store_true',
                                   help='Explicitly enable helper mode (auto-enabled if --image-name, --registry, or --port is used)')
    devops_ci_parser.add_argument('--image-name',
                                   help='Custom image name to build (auto-enables helper mode)')
    devops_ci_parser.add_argument('--registry',
                                   help='Registry URL for build args (auto-enables helper mode)')
    devops_ci_parser.add_argument('--port',
                                   help='Application port for build args (auto-enables helper mode)')
    devops_ci_parser.add_argument('--use-builder',
                                   help='Specify docker buildx builder name to use for the build')
    devops_ci_parser.add_argument('--webhook', type=str,
                                  help='Microsoft Teams webhook URL for build notifications (fallback to TEAMS_WEBHOOK env or ~/.doq/.env)')
    devops_ci_parser.add_argument('--local', action='store_true',
                                  help='Build from current working directory without cloning repository')
    devops_ci_parser.add_argument('--build-arg', action='append',
                                  help='Build argument in format KEY=VALUE (can be used multiple times)')
    devops_ci_parser.add_argument('--help-devops-ci', action='store_true',
                                   help='Show detailed DevOps CI help')
    devops_ci_parser.add_argument('--version-devops-ci', action='store_true',
                                   help='Show DevOps CI version')
    devops_ci_parser.set_defaults(func=cmd_devops_ci)

