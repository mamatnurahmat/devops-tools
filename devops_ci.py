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


VERSION = "2.0.1"
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")

# Bitbucket API constants
BITBUCKET_ORG = "loyaltoid"
BITBUCKET_API_BASE = "https://api.bitbucket.org/2.0/repositories"


def load_auth_file(auth_file_path: Optional[Path] = None) -> Dict[str, str]:
    """Centralized auth loading with migration support.
    
    Args:
        auth_file_path: Optional path to auth.json file
        
    Returns:
        Dict with authentication credentials
        
    Raises:
        FileNotFoundError: If auth file not found
    """
    if auth_file_path is None:
        auth_file_path = Path.home() / ".doq" / "auth.json"
    
    if not auth_file_path.exists():
        raise FileNotFoundError(f"Authentication file {auth_file_path} not found. Run 'doq login' to configure.")
    
    try:
        with open(auth_file_path, 'r') as f:
            auth_data = json.load(f)
        return auth_data
    except Exception as e:
        raise RuntimeError(f"Failed to load authentication: {str(e)}")


def check_docker_image_exists(image_name: str, auth_data: Dict[str, str], verbose: bool = False) -> bool:
    """Check if Docker image exists in Docker Hub.
    
    Args:
        image_name: Full image name with tag (e.g. loyaltolpi/repo:tag)
        auth_data: Dict with DOCKERHUB_USER and DOCKERHUB_PASSWORD
        verbose: If True, print debug messages
        
    Returns:
        True if image exists, False otherwise
    """
    if ':' not in image_name:
        if verbose:
            print(f"⚠️  Invalid image format (missing tag): {image_name}", file=sys.stderr)
        return False
    
    image_base, tag = image_name.rsplit(':', 1)
    if '/' not in image_base:
        if verbose:
            print(f"⚠️  Invalid image format (missing namespace): {image_name}", file=sys.stderr)
        return False
    
    namespace, repo = image_base.split('/', 1)
    
    user = auth_data.get('DOCKERHUB_USER', '')
    password = auth_data.get('DOCKERHUB_PASSWORD', '')
    
    if not user or not password:
        if verbose:
            print(f"⚠️  Docker Hub credentials not found in auth.json", file=sys.stderr)
            print(f"   Required: DOCKERHUB_USER and DOCKERHUB_PASSWORD", file=sys.stderr)
            print(f"   Unable to verify image existence in Docker Hub", file=sys.stderr)
        return False
    
    # Step 1: Get JWT token from Docker Hub
    try:
        login_resp = requests.post(
            'https://hub.docker.com/v2/users/login/',
            json={'username': user, 'password': password},
            timeout=10
        )
        if login_resp.status_code != 200:
            if verbose:
                print(f"⚠️  Docker Hub login failed (status: {login_resp.status_code})", file=sys.stderr)
            return False
        token = login_resp.json().get('token')
        if not token:
            if verbose:
                print(f"⚠️  Docker Hub login failed (no token received)", file=sys.stderr)
            return False
    except Exception as e:
        if verbose:
            print(f"⚠️  Docker Hub login error: {e}", file=sys.stderr)
        return False
    
    # Step 2: Check tag existence with Bearer token
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/{tag}/"
    headers = {"Authorization": f"JWT {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        # Only show verbose output if check fails
        if verbose and resp.status_code != 200:
            print(f"⚠️  Docker Hub returned status {resp.status_code} for {namespace}/{repo}:{tag}", file=sys.stderr)
        return resp.status_code == 200
    except Exception as e:
        if verbose:
            print(f"⚠️  Error checking image: {e}", file=sys.stderr)
        return False


def fetch_bitbucket_file(repo: str, refs: str, path: str, auth_data: Dict[str, str]) -> str:
    """Fetch any file from Bitbucket.
    
    Args:
        repo: Repository name
        refs: Branch or tag name
        path: File path in repository
        auth_data: Dict with GIT_USER and GIT_PASSWORD
        
    Returns:
        File content as string
        
    Raises:
        requests.RequestException: If fetch fails
    """
    git_user = auth_data.get('GIT_USER', '')
    git_password = auth_data.get('GIT_PASSWORD', '')
    
    if not git_user or not git_password:
        raise ValueError("GIT_USER and GIT_PASSWORD required in auth.json")
    
    file_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/src/{refs}/{path}"
    resp = requests.get(file_url, auth=(git_user, git_password), timeout=30)
    
    if resp.status_code == 404:
        raise requests.RequestException(f"File not found: {path}")
    
    resp.raise_for_status()
    return resp.text


def get_commit_hash_from_bitbucket(repo: str, refs: str, auth_data: Dict[str, str]) -> Dict[str, Any]:
    """Get commit hash and ref details from Bitbucket.
    
    Args:
        repo: Repository name
        refs: Branch or tag name
        auth_data: Dict with GIT_USER and GIT_PASSWORD
        
    Returns:
        Dict with ref_type ('branch' or 'tag'), full_hash, short_hash (7 chars)
        
    Raises:
        requests.RequestException: If fetch fails
    """
    git_user = auth_data.get('GIT_USER', '')
    git_password = auth_data.get('GIT_PASSWORD', '')
    
    if not git_user or not git_password:
        raise ValueError("GIT_USER and GIT_PASSWORD required in auth.json")
    
    # Determine ref type
    if refs in ['develop', 'development', 'staging', 'bash', 'master']:
        refs_type = 'branches'
    else:
        refs_type = 'tags'
    
    # Fetch ref details
    ref_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/{refs_type}/{refs}"
    ref_resp = requests.get(ref_url, auth=(git_user, git_password), timeout=30)
    ref_resp.raise_for_status()
    
    ref_data = ref_resp.json()
    
    if ref_data.get('type') == 'error':
        raise requests.RequestException(f"Reference {refs} not found in repository {repo}")
    
    # Extract commit hash
    if ref_data.get('type') == 'tag':
        # For tags, use the tag name as version
        return {
            'ref_type': 'tag',
            'full_hash': refs,
            'short_hash': refs,
            'tag_name': refs
        }
    else:
        # For branches, get commit hash
        full_hash = ref_data['target']['hash']
        short_hash = full_hash[:7]
        return {
            'ref_type': 'branch',
            'full_hash': full_hash,
            'short_hash': short_hash
        }


class BuildResult:
    """Build result with status, timing, and metadata."""
    
    def __init__(self, repo: str, refs: str, rebuild: bool):
        self.status = "pending"
        self.repo = repo
        self.refs = refs
        self.image = ""
        self.rebuild = rebuild
        self.start_time = int(time.time())
        self.end_time = 0
        self.error = ""
        self.ready = False
        self.custom_image = ""
        self.config = {
            "memory": "",
            "cpus": "",
            "cpu_period": "",
            "cpu_quota": "",
            "builder": ""
        }
        self.api_url = ""
    
    def finish(self):
        """Mark build as finished."""
        self.end_time = int(time.time())
    
    def duration_seconds(self) -> int:
        """Get build duration in seconds."""
        end = self.end_time if self.end_time > 0 else int(time.time())
        return end - self.start_time
    
    def duration_formatted(self) -> str:
        """Get formatted build duration."""
        duration = self.duration_seconds()
        if duration >= 3600:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
            return f"{hours}h {minutes}m {seconds}s"
        elif duration >= 60:
            minutes = duration // 60
            seconds = duration % 60
            return f"{minutes}m {seconds}s"
        else:
            return f"{duration}s"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        return {
            "status": self.status,
            "repository": self.repo,
            "branch": self.refs,
            "image": self.image,
            "rebuild": self.rebuild,
            "build_time": {
                "start_unix": self.start_time,
                "end_unix": self.end_time,
                "start_iso": datetime.fromtimestamp(self.start_time, tz=timezone.utc).isoformat(),
                "end_iso": datetime.fromtimestamp(self.end_time, tz=timezone.utc).isoformat() if self.end_time > 0 else "",
                "duration": {
                    "seconds": self.duration_seconds(),
                    "formatted": self.duration_formatted()
                }
            },
            "config": self.config,
            "metadata": {
                "ready": self.ready,
                "custom_image": self.custom_image,
                "api_url": self.api_url
            },
            "error": self.error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


class BuildConfig:
    """Build configuration manager."""
    
    def __init__(self, helper_mode: bool = False, helper_args: Optional[Dict[str, Any]] = None):
        self.memory = os.getenv("DEFAULT_MEMORY", "2g")
        self.cpus = os.getenv("DEFAULT_CPUS", "1")
        self.cpu_period = os.getenv("DEFAULT_CPU_PERIOD", "100000")
        self.cpu_quota = os.getenv("DEFAULT_CPU_QUOTA", "100000")
        self.api_url = os.getenv("DEFAULT_URL_API", "http://193.1.1.3:5000")
        self.builder_name = "container-builder"
        self.ntfy_url = os.getenv("NTFY_URL", "https://ntfy.sh/doi-notif")
        
        # Build args from environment or config
        self.registry01_url = os.getenv("REGISTRY01_URL", "")
        self.image = os.getenv("IMAGE", "")
        self.port = os.getenv("PORT", "")
        self.port2 = os.getenv("PORT2", "")
        self.gitusertoken = os.getenv("GITUSERTOKEN", "")
        self.bitbucket_user = os.getenv("BITBUCKET_USER", "")
        self.github_user = os.getenv("GITHUB_USER", "")
        self.bitbucket_token = os.getenv("BITBUCKET_TOKEN", "")
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        
        # Auth file and config directories - NEW LOCATION: ~/.doq/
        self.auth_file = Path.home() / ".doq" / "auth.json"
        self.devops_dir = Path.home() / ".doq"
        self.env_file = self.devops_dir / ".env"
        self.helper_config_file = self.devops_dir / "helper-config.json"
        
        # Migration and initialization
        self._migrate_from_old_location()
        self._ensure_auth_file()
        
        # Mode configuration
        self.mode = self._load_mode_from_env()
        self.helper_mode = helper_mode or (self.mode == "helper")
        self.helper_args = helper_args or {}
        
        # Helper mode settings
        if self.helper_mode:
            self._load_helper_config()
    
    def _migrate_from_old_location(self):
        """Migrate config files from ~/.devops/ to ~/.doq/ if needed."""
        old_dir = Path.home() / ".devops"
        new_dir = self.devops_dir
        
        # If old directory doesn't exist, nothing to migrate
        if not old_dir.exists():
            return
        
        # If new directory already has files, don't migrate
        if new_dir.exists() and (new_dir / "auth.json").exists():
            return
        
        # Create new directory
        new_dir.mkdir(parents=True, exist_ok=True)
        
        # Migrate files
        files_to_migrate = ["auth.json", ".env", "helper-config.json"]
        migrated_any = False
        
        for filename in files_to_migrate:
            old_file = old_dir / filename
            new_file = new_dir / filename
            
            if old_file.exists() and not new_file.exists():
                try:
                    import shutil
                    shutil.copy2(old_file, new_file)
                    migrated_any = True
                except Exception:
                    pass
        
        if migrated_any:
            print(f"✅ Migrated configuration from ~/.devops/ to ~/.doq/")
    
    def _ensure_auth_file(self):
        """Ensure auth.json exists with template if missing."""
        # Create directory if it doesn't exist
        self.devops_dir.mkdir(parents=True, exist_ok=True)
        
        # If auth.json doesn't exist or is empty, create template
        if not self.auth_file.exists():
            template = {
                "GIT_USER": "",
                "GIT_PASSWORD": "",
                "DOCKERHUB_USER": "",
                "DOCKERHUB_PASSWORD": ""
            }
            try:
                with open(self.auth_file, 'w') as f:
                    json.dump(template, f, indent=2)
                print(f"📝 Created {self.auth_file} template. Run 'doq login' to configure.")
            except Exception:
                pass
        elif self.auth_file.stat().st_size == 0:
            # File exists but is empty
            template = {
                "GIT_USER": "",
                "GIT_PASSWORD": "",
                "DOCKERHUB_USER": "",
                "DOCKERHUB_PASSWORD": ""
            }
            try:
                with open(self.auth_file, 'w') as f:
                    json.dump(template, f, indent=2)
                print(f"📝 Initialized empty {self.auth_file}. Run 'doq login' to configure.")
            except Exception:
                pass
    
    def _load_mode_from_env(self) -> str:
        """Load mode from environment or config file.
        
        Returns:
            str: "api" or "helper"
        """
        # Check environment variable first
        env_mode = os.getenv("DEVOPS_CI_MODE", "").lower()
        if env_mode in ("api", "helper"):
            return env_mode
        
        # Check .env file
        if self.devops_dir.exists() and self.env_file.exists():
            try:
                with open(self.env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEVOPS_CI_MODE="):
                            mode = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                            if mode in ("api", "helper"):
                                return mode
            except Exception:
                pass
        
        # Check helper-config.json
        if self.helper_config_file.exists():
            try:
                with open(self.helper_config_file, 'r') as f:
                    config = json.load(f)
                    mode = config.get("mode", "").lower()
                    if mode in ("api", "helper"):
                        return mode
            except Exception:
                pass
        
        # Default: API mode
        return "api"
    
    def _load_helper_config(self):
        """Load helper mode configuration from files or environment."""
        # Default helper settings
        self.helper_image_template = "loyaltolpi/{repo}:{refs}-{short_hash}"
        self.helper_registry01 = ""
        self.helper_port = "3000"
        self.helper_port2 = ""
        
        # Load from environment variables
        self.helper_image_template = os.getenv("HELPER_IMAGE_TEMPLATE", self.helper_image_template)
        self.helper_registry01 = os.getenv("HELPER_REGISTRY01", self.helper_registry01)
        self.helper_port = os.getenv("HELPER_DEFAULT_PORT", self.helper_port)
        self.helper_port2 = os.getenv("HELPER_DEFAULT_PORT2", self.helper_port2)
        
        # Load from .env file
        if self.env_file.exists():
            try:
                with open(self.env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("HELPER_IMAGE_TEMPLATE="):
                            self.helper_image_template = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("HELPER_REGISTRY01="):
                            self.helper_registry01 = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("HELPER_DEFAULT_PORT="):
                            self.helper_port = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("HELPER_DEFAULT_PORT2="):
                            self.helper_port2 = line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
        
        # Load from helper-config.json
        if self.helper_config_file.exists():
            try:
                with open(self.helper_config_file, 'r') as f:
                    config = json.load(f)
                    self.helper_image_template = config.get("image_template", self.helper_image_template)
                    self.helper_registry01 = config.get("registry01", self.helper_registry01)
                    self.helper_port = config.get("default_port", self.helper_port)
                    self.helper_port2 = config.get("default_port2", self.helper_port2)
            except Exception:
                pass
        
        # Override with CLI args if provided
        if self.helper_args:
            if "image_name" in self.helper_args and self.helper_args["image_name"]:
                # If custom image name provided, don't use template
                pass  # Will be handled in builder
            if "registry" in self.helper_args and self.helper_args["registry"]:
                self.helper_registry01 = self.helper_args["registry"]
            if "port" in self.helper_args and self.helper_args["port"]:
                self.helper_port = str(self.helper_args["port"])


class DevOpsCIBuilder:
    """Main DevOps CI/CD builder."""
    
    def __init__(self, repo: str, refs: str, rebuild: bool = False, 
                 json_output: bool = False, short_output: bool = False,
                 custom_image: str = "", helper_mode: bool = False,
                 helper_args: Optional[Dict[str, Any]] = None):
        self.repo = repo
        self.refs = refs
        self.rebuild = rebuild
        self.json_output = json_output
        self.short_output = short_output
        self.custom_image = custom_image
        self.helper_mode = helper_mode
        self.helper_args = helper_args or {}
        
        self.config = BuildConfig(helper_mode=helper_mode, helper_args=helper_args)
        self.result = BuildResult(repo, refs, rebuild)
        self.result.custom_image = custom_image
        self.result.api_url = self.config.api_url if not self.config.helper_mode else "helper-mode"
        self.result.config = {
            "memory": self.config.memory,
            "cpus": self.config.cpus,
            "cpu_period": self.config.cpu_period,
            "cpu_quota": self.config.cpu_quota,
            "builder": self.config.builder_name
        }
        
        self.clone_dir = None
    
    def log(self, message: str):
        """Log message (respects output mode)."""
        if not self.short_output:
            if self.json_output and not sys.stdout.isatty():
                # JSON mode with piped output - send to stderr
                print(message, file=sys.stderr)
            else:
                print(message)
    
    def fix_buildx_permissions(self):
        """Fix Docker buildx directory permissions."""
        buildx_dir = Path.home() / ".docker" / "buildx"
        
        if not buildx_dir.exists():
            return
        
        self.log("🔧 Checking Docker buildx permissions...")
        
        # Check if we have write access
        if not os.access(buildx_dir, os.W_OK):
            self.log("⚠️  Fixing Docker buildx directory permissions...")
            try:
                subprocess.run(
                    ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(buildx_dir)],
                    capture_output=True,
                    timeout=30
                )
            except Exception:
                try:
                    subprocess.run(
                        ["chmod", "-R", "u+rw", str(buildx_dir)],
                        capture_output=True,
                        timeout=30
                    )
                except Exception:
                    pass
        
        # Fix activity directory
        activity_dir = buildx_dir / "activity"
        if activity_dir.exists():
            if not os.access(activity_dir, os.W_OK):
                self.log("⚠️  Fixing Docker buildx activity directory permissions...")
                try:
                    subprocess.run(
                        ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(activity_dir)],
                        capture_output=True,
                        timeout=30
                    )
                except Exception:
                    pass
            
            # Fix individual files
            for activity_file in activity_dir.iterdir():
                if activity_file.is_file() and not os.access(activity_file, os.W_OK):
                    try:
                        subprocess.run(
                            ["sudo", "chown", f"{os.getuid()}:{os.getgid()}", str(activity_file)],
                            capture_output=True,
                            timeout=30
                        )
                    except Exception:
                        pass
        
        # Fix refs directory
        refs_dir = buildx_dir / "refs"
        if refs_dir.exists():
            for refs_subdir in refs_dir.iterdir():
                if refs_subdir.is_dir() and not os.access(refs_subdir, os.R_OK | os.W_OK | os.X_OK):
                    self.log(f"⚠️  Fixing permissions on refs/{refs_subdir.name}...")
                    try:
                        subprocess.run(
                            ["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(refs_subdir)],
                            capture_output=True,
                            timeout=30
                        )
                    except Exception:
                        pass
    
    def setup_buildx_builder(self) -> bool:
        """Setup and verify buildx builder with resource limits."""
        builder_name = self.config.builder_name
        
        # Fix permissions first
        self.fix_buildx_permissions()
        
        # Create BuildKit configuration
        self.log("📝 Creating BuildKit configuration with metrics...")
        buildx_dir = Path.home() / ".docker" / "buildx"
        buildx_dir.mkdir(parents=True, exist_ok=True)
        
        buildkitd_config = buildx_dir / "buildkitd.toml"
        buildkitd_config.write_text('[server]\n  metrics_addr = "0.0.0.0:9333"\n')
        
        # Check if builder exists
        self.log(f"🔍 Verifying builder '{builder_name}'...")
        result = subprocess.run(
            ["docker", "buildx", "ls"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and builder_name in result.stdout:
            self.log(f"✅ Builder '{builder_name}' exists")
            
            # Try to use the builder
            use_result = subprocess.run(
                ["docker", "buildx", "use", builder_name],
                capture_output=True,
                timeout=30
            )
            
            if use_result.returncode == 0:
                self.log(f"✅ Successfully switched to builder '{builder_name}'")
                
                # Apply resource limits
                self.log("🔧 Checking resource limits on builder container...")
                container_result = subprocess.run(
                    ["docker", "ps", "-a", "--filter", f"name=buildx_buildkit_{builder_name}", "--format", "{{.Names}}"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if container_result.returncode == 0 and container_result.stdout.strip():
                    container_name = container_result.stdout.strip().split('\n')[0]
                    
                    # Check container status
                    status_result = subprocess.run(
                        ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if status_result.returncode == 0 and status_result.stdout.strip() != "running":
                        self.log("⚡ Starting builder container...")
                        subprocess.run(["docker", "start", container_name], capture_output=True, timeout=30)
                        time.sleep(2)
                    
                    # Apply resource limits
                    update_result = subprocess.run(
                        ["docker", "update", "--cpus=4", "--memory=4g", "--memory-swap=4g", container_name],
                        capture_output=True,
                        timeout=30
                    )
                    
                    if update_result.returncode == 0:
                        self.log("✅ Resource limits applied/updated: 4 CPUs, 4GB RAM")
                
                return True
            else:
                self.log(f"⚠️  Could not switch to builder '{builder_name}', recreating...")
                subprocess.run(["docker", "buildx", "rm", builder_name], capture_output=True)
        
        # Create builder
        self.log(f"🔨 Creating builder '{builder_name}' with resource limits (4 CPUs, 4GB RAM)...")
        
        # Clean up leftover files
        instances_file = buildx_dir / "instances" / builder_name
        activity_file = buildx_dir / "activity" / builder_name
        if instances_file.exists() or activity_file.exists():
            self.log("🧹 Cleaning up leftover builder files...")
            instances_file.unlink(missing_ok=True)
            activity_file.unlink(missing_ok=True)
        
        create_result = subprocess.run(
            [
                "docker", "buildx", "create",
                "--name", builder_name,
                "--driver", "docker-container",
                "--buildkitd-config", str(buildkitd_config),
                "--use"
            ],
            capture_output=True,
            timeout=60
        )
        
        if create_result.returncode == 0:
            self.log(f"✅ Builder '{builder_name}' created successfully")
            self.log("📊 Metrics enabled on 0.0.0.0:9333")
            
            # Bootstrap builder
            self.log("⚡ Bootstrapping builder to start container...")
            subprocess.run(
                ["docker", "buildx", "inspect", "--bootstrap", builder_name],
                capture_output=True,
                timeout=60
            )
            time.sleep(3)
            
            # Apply resource limits
            self.log("🔧 Applying resource limits to builder container...")
            container_result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name=buildx_buildkit_{builder_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if container_result.returncode == 0 and container_result.stdout.strip():
                container_name = container_result.stdout.strip().split('\n')[0]
                
                update_result = subprocess.run(
                    ["docker", "update", "--cpus=4", "--memory=4g", "--memory-swap=4g", container_name],
                    capture_output=True,
                    timeout=30
                )
                
                if update_result.returncode == 0:
                    self.log("✅ Resource limits applied: 4 CPUs, 4GB RAM")
                else:
                    self.log("⚠️  Warning: Could not apply resource limits to builder container")
                
                # Get container IP for metrics
                ip_result = subprocess.run(
                    ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if ip_result.returncode == 0 and ip_result.stdout.strip():
                    container_ip = ip_result.stdout.strip()
                    self.log(f"📊 Metrics endpoint: http://{container_ip}:9333/metrics")
            else:
                self.log("⚠️  Warning: Could not find builder container to apply limits")
                self.log("   Limits will be applied on first use")
            
            return True
        else:
            self.log(f"⚠️  Warning: Could not create builder '{builder_name}'")
            self.log("   Attempting to use default builder...")
            return False
    
    def fetch_build_metadata(self) -> Dict[str, Any]:
        """Fetch build metadata from API or locally."""
        # Use local mode if no API URL or explicitly requested
        use_local = not self.config.api_url or self.config.api_url == "helper-mode"
        
        if use_local:
            return self.fetch_build_metadata_local()
        
        self.log(f"📦 Fetching build metadata for repo={self.repo}, refs={self.refs} ...")
        
        try:
            response = requests.get(
                f"{self.config.api_url}/v1/image/fe",
                params={"repo": self.repo, "refs": self.refs},
                headers={"accept": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "ready" not in data:
                raise ValueError("Invalid response format - missing 'ready' field")
            
            return data
        
        except requests.RequestException as e:
            self.result.status = "failed"
            self.result.error = f"Failed to fetch build metadata from API: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
        except ValueError as e:
            self.result.status = "failed"
            self.result.error = str(e)
            self.log(f"❌ Error: {self.result.error}")
            raise
    
    def fetch_build_metadata_local(self) -> Dict[str, Any]:
        """Fetch build metadata locally (no API dependency).
        
        Returns:
            Dict with 'ready', 'image' or 'build-image' keys
        """
        self.log(f"📦 Checking image locally for repo={self.repo}, refs={self.refs} ...")
        
        try:
            # Load auth
            auth_data = load_auth_file(self.config.auth_file)
            
            # Get cicd.json to find IMAGE name
            try:
                cicd_content = fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json", auth_data)
                cicd_data = json.loads(cicd_content)
                image_name = cicd_data.get('IMAGE', self.repo)
            except Exception:
                # If cicd.json not found, use repo name
                image_name = self.repo
            
            # Get commit hash
            commit_info = get_commit_hash_from_bitbucket(self.repo, self.refs, auth_data)
            
            # Build full image name
            if commit_info['ref_type'] == 'tag':
                tag_version = self.refs
            else:
                tag_version = commit_info['short_hash']
            
            full_image = f"loyaltolpi/{image_name}:{tag_version}"
            
            # Check if image exists in Docker Hub
            exists = check_docker_image_exists(full_image, auth_data)
            
            if exists:
                self.log(f"✅ Image exists: {full_image}")
                return {'ready': True, 'image': full_image}
            else:
                self.log(f"⚠️  Image not found: {full_image}")
                return {'ready': False, 'build-image': full_image}
        
        except Exception as e:
            self.result.status = "failed"
            self.result.error = f"Failed to check image locally: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
    
    def fetch_build_config(self) -> Dict[str, Any]:
        """Fetch build configuration from API or locally."""
        # Use local mode if no API URL or explicitly requested
        use_local = not self.config.api_url or self.config.api_url == "helper-mode"
        
        if use_local:
            return self.fetch_build_config_local()
        
        self.log("📥 Fetching build configuration...")
        
        try:
            response = requests.get(
                f"{self.config.api_url}/v1/file",
                params={"repo": self.repo, "refs": self.refs, "path": "cicd/cicd.json"},
                headers={"accept": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            return data
        
        except requests.RequestException as e:
            self.result.status = "failed"
            self.result.error = f"Failed to fetch build configuration from API: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
        except ValueError as e:
            self.result.status = "failed"
            self.result.error = f"Invalid configuration response from API: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
    
    def fetch_build_config_local(self) -> Dict[str, Any]:
        """Fetch build configuration locally (no API dependency).
        
        Returns:
            Dict with cicd.json content
        """
        self.log("📥 Fetching build configuration from Bitbucket...")
        
        try:
            # Load auth
            auth_data = load_auth_file(self.config.auth_file)
            
            # Fetch cicd.json
            cicd_content = fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json", auth_data)
            data = json.loads(cicd_content)
            
            self.log("✅ Configuration loaded successfully")
            return data
        
        except Exception as e:
            self.result.status = "failed"
            self.result.error = f"Failed to fetch build configuration locally: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
    
    def load_auth(self) -> Dict[str, str]:
        """Load authentication from ~/.doq/auth.json."""
        if not self.config.auth_file.exists():
            self.result.status = "failed"
            self.result.error = f"Authentication file {self.config.auth_file} not found"
            self.log(f"❌ Error: {self.result.error}")
            self.log("   Please ensure the authentication file exists and is accessible")
            raise FileNotFoundError(self.result.error)
        
        try:
            with open(self.config.auth_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.result.status = "failed"
            self.result.error = f"Failed to load authentication: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            raise
    
    def _generate_image_name(self) -> str:
        """Generate image name from template or custom name.
        
        Returns:
            str: Generated image name
        """
        # If custom image provided via CLI or helper_args, use it
        if self.helper_args.get("image_name"):
            return self.helper_args["image_name"]
        
        # If custom_image set, use it
        if self.custom_image:
            return self.custom_image
        
        # Generate from template
        template = self.config.helper_image_template
        short_hash = "unknown"
        
        # Try to get short hash from git (will be available after clone)
        # For now, use timestamp as fallback
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Replace template variables
        image_name = template.replace("{repo}", self.repo)
        image_name = image_name.replace("{refs}", self.refs)
        image_name = image_name.replace("{short_hash}", short_hash)
        image_name = image_name.replace("{timestamp}", timestamp)
        
        return image_name
    
    def fetch_build_metadata_helper(self) -> Dict[str, Any]:
        """Generate metadata without API (helper mode).
        
        Returns:
            dict: Metadata dict compatible with API mode
        """
        self.log("🔧 Helper mode: Generating metadata locally...")
        
        # In helper mode:
        # - Always return ready=False to force build
        # - Generate image name from template or custom name
        image_name = self._generate_image_name()
        
        self.log(f"📝 Generated image name: {image_name}")
        
        return {
            "ready": False,  # Always build in helper mode
            "build-image": image_name,
            "image": ""
        }
    
    def fetch_build_config_helper(self) -> Dict[str, Any]:
        """Load config from helper settings (no API required).
        
        Returns:
            dict: Build config dict compatible with API mode
        """
        self.log("🔧 Helper mode: Loading configuration from local settings...")
        
        # Build config from helper settings
        config = {
            "REGISTRY01_URL": self.config.helper_registry01 or self.config.registry01_url,
            "IMAGE": self.repo,  # Use repo name as IMAGE
            "PORT": self.config.helper_port,
            "PORT2": self.config.helper_port2,
        }
        
        self.log(f"📝 Helper config loaded:")
        self.log(f"   Registry: {config['REGISTRY01_URL'] or '(not set)'}")
        self.log(f"   Port: {config['PORT']}")
        if config['PORT2']:
            self.log(f"   Port2: {config['PORT2']}")
        
        return config
    
    def pre_clone_repository(self, git_url: str) -> str:
        """Pre-clone repository with --no-recurse-submodules to avoid submodule errors."""
        self.log("📥 Pre-cloning repository (avoiding submodule issues)...")
        
        # Create temp directory
        self.clone_dir = tempfile.mkdtemp(prefix=f"buildx-{self.repo}-{self.refs}-")
        
        try:
            # Clone with --no-recurse-submodules
            result = subprocess.run(
                [
                    "git", "clone",
                    "--no-recurse-submodules",
                    "-b", self.refs,
                    git_url,
                    self.clone_dir
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                self.result.status = "failed"
                self.result.error = "Failed to pre-clone repository"
                self.log(f"❌ Error: {self.result.error}")
                if result.stderr:
                    self.log(f"   {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, result.args)
            
            self.log("✅ Repository pre-cloned successfully")
            return self.clone_dir
        
        except Exception as e:
            if self.clone_dir and os.path.exists(self.clone_dir):
                shutil.rmtree(self.clone_dir, ignore_errors=True)
            raise
    
    def execute_docker_build(self, build_config: Dict[str, Any], auth: Dict[str, str]) -> bool:
        """Execute docker buildx build command."""
        self.log("🔨 Executing Docker buildx command...")
        self.result.status = "building"
        
        # Update config from API response
        for key, value in build_config.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Update auth from file
        for key, value in auth.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Build git URL
        git_url = f"https://{self.config.bitbucket_user}:{self.config.bitbucket_token}@bitbucket.org/loyaltoid/{self.repo}.git"
        
        # Pre-clone repository
        try:
            clone_dir = self.pre_clone_repository(git_url)
        except Exception:
            return False
        
        # Build docker command
        docker_cmd = [
            "docker", "buildx", "build",
            "--builder", self.config.builder_name,
            "--sbom=true",
            "--no-cache",
            "--attest", "type=provenance,mode=max",
            "--memory", self.config.memory,
            "--cpu-period", self.config.cpu_period,
            "--cpu-quota", self.config.cpu_quota,
            "--progress=plain",
            "--build-arg", f"REGISTRY01={self.config.registry01_url}",
            "--build-arg", f"BRANCH={self.refs}",
            "--build-arg", f"PROJECT={self.config.image}",
            "--build-arg", f"PORT={self.config.port}",
            "--build-arg", f"PORT2={self.config.port2}",
            "--build-arg", f"GITUSERTOKEN={self.config.gitusertoken}",
            "--build-arg", f"BITBUCKET_USER={self.config.bitbucket_user}",
            "--build-arg", f"GITHUB_USER={self.config.github_user}",
            "--build-arg", f"BITBUCKET_TOKEN={self.config.bitbucket_token}",
            "--build-arg", f"GITHUB_TOKEN={self.config.github_token}",
            "--build-arg", "GIT_TERMINAL_PROMPT=0",
            "--build-arg", "GIT_AUTHOR_NAME=CI",
            "--build-arg", "GIT_AUTHOR_EMAIL=ci@loyalto.id",
            "--build-arg", "GIT_SUBMODULE_STRATEGY=none",
            "-t", self.result.image,
            "--push",
            clone_dir
        ]
        
        try:
            # Execute docker build
            if self.short_output:
                # Silent mode
                result = subprocess.run(
                    docker_cmd,
                    capture_output=True,
                    timeout=3600
                )
            else:
                # Normal/JSON mode with output
                result = subprocess.run(
                    docker_cmd,
                    timeout=3600
                )
            
            if result.returncode == 0:
                self.result.status = "success"
                if not self.short_output:
                    self.log(f"✅ Build complete: {self.result.image}")
                return True
            else:
                self.result.status = "failed"
                self.result.error = "Docker buildx command failed"
                self.log("❌ Build failed")
                return False
        
        except subprocess.TimeoutExpired:
            self.result.status = "failed"
            self.result.error = "Docker build timed out (1 hour limit)"
            self.log(f"❌ Error: {self.result.error}")
            return False
        except Exception as e:
            self.result.status = "failed"
            self.result.error = f"Docker build error: {str(e)}"
            self.log(f"❌ Error: {self.result.error}")
            return False
        finally:
            # Cleanup clone directory
            if self.clone_dir and os.path.exists(self.clone_dir):
                shutil.rmtree(self.clone_dir, ignore_errors=True)
    
    def send_notification(self):
        """Send build notification to ntfy.sh."""
        # Determine notification properties (ASCII-safe for HTTP headers)
        if self.result.status == "success":
            title = f"Build Success: {self.repo}"
            priority = "high"
            tags = "white_check_mark,package"
        elif self.result.status == "failed":
            title = f"Build Failed: {self.repo}"
            priority = "urgent"
            tags = "x,package,warning"
        elif self.result.status == "skipped":
            title = f"Build Skipped: {self.repo}"
            priority = "low"
            tags = "fast_forward,package"
        else:
            title = f"Build {self.result.status.title()}: {self.repo}"
            priority = "default"
            tags = "package"
        
        try:
            # Prepare the payload with title in body for proper unicode support
            payload = self.result.to_dict()
            payload['notification_title'] = title
            
            response = requests.post(
                self.config.ntfy_url,
                headers={
                    "Title": title,  # ASCII-safe title in header
                    "Priority": priority,
                    "Tags": tags,
                    "Content-Type": "application/json; charset=utf-8"
                },
                json=payload,
                timeout=30
            )
            
            if response.status_code in (200, 201):
                self.log("📤 Notification sent to ntfy.sh")
            else:
                self.log(f"⚠️  Warning: Failed to send notification to ntfy.sh (status: {response.status_code})")
        
        except Exception as e:
            self.log(f"⚠️  Warning: Failed to send notification to ntfy.sh: {str(e)}")
    
    def build(self) -> int:
        """Main build process."""
        try:
            # Determine mode and show info
            if self.config.helper_mode:
                self.log("🔧 Running in HELPER MODE (no API dependency)")
            else:
                self.log("🌐 Running in API MODE")
            
            # Fetch metadata (API or helper mode)
            if self.config.helper_mode:
                metadata = self.fetch_build_metadata_helper()
            else:
                metadata = self.fetch_build_metadata()
            
            self.result.ready = metadata.get("ready", False)
            
            # Determine build image
            if self.custom_image:
                self.result.image = self.custom_image
                self.log(f"📝 Using custom image: {self.result.image}")
            elif self.rebuild:
                if self.result.ready:
                    self.result.image = metadata.get("image", "")
                    self.log(f"♻️  Rebuilding existing image: {self.result.image}")
                else:
                    self.result.image = metadata.get("build-image", "")
                    self.log(f"🆕 Building new image: {self.result.image}")
            else:
                if self.result.ready:
                    self.result.image = metadata.get("image", "")
                    self.result.status = "skipped"
                    self.log(f"✅ Image already ready: {self.result.image}. Skipping build.")
                    return 0
                else:
                    self.result.image = metadata.get("build-image", "")
                    self.log(f"🆕 Building new image: {self.result.image}")
            
            # Show build configuration
            self.log("🚧 Starting build process...")
            self.log("📋 Build configuration:")
            self.log(f"   Mode: {'Helper' if self.config.helper_mode else 'API'}")
            self.log(f"   Repository: {self.repo}")
            self.log(f"   Branch/Tag: {self.refs}")
            self.log(f"   Image: {self.result.image}")
            self.log(f"   Rebuild: {self.rebuild}")
            self.log(f"   Memory: {self.config.memory}")
            self.log(f"   CPUs: {self.config.cpus}")
            
            # Fetch build config (API or helper mode)
            if self.config.helper_mode:
                build_config = self.fetch_build_config_helper()
            else:
                build_config = self.fetch_build_config()
            
            # Load auth
            auth = self.load_auth()
            
            # Setup builder
            self.setup_buildx_builder()
            
            # Execute build
            success = self.execute_docker_build(build_config, auth)
            
            return 0 if success else 1
        
        except KeyboardInterrupt:
            self.result.status = "failed"
            self.result.error = "Build cancelled by user"
            self.log("\n❌ Build cancelled by user")
            return 1
        except Exception as e:
            if not self.result.error:
                self.result.error = str(e)
            return 1
        finally:
            self.result.finish()
            self.send_notification()
            
            # Output final result
            if self.json_output:
                if sys.stdout.isatty():
                    print("\n========== BUILD RESULT (JSON) ==========")
                    print(json.dumps(self.result.to_dict(), indent=2))
                    print("==========================================")
                else:
                    print(json.dumps(self.result.to_dict(), indent=2))
            elif self.short_output:
                print(self.result.image)


def show_version():
    """Show version information."""
    print(f"🔧 DevOps CI/CD Build Tool v{VERSION}")
    print(f"Build Date: {BUILD_DATE}")


def show_help():
    """Show help information."""
    print("""🔧 DevOps CI/CD Build Tool
==========================

DESCRIPTION:
  Build Docker images from Bitbucket repositories using buildx with advanced features
  like SBOM generation, provenance attestation, and resource management.

USAGE:
  doq devops-ci <REPO> <REFS> [--rebuild] [--json|--short] [CUSTOM_IMAGE]

ARGUMENTS:
  REPO           Repository name (e.g., saas-be-core, saas-apigateway)
  REFS           Branch or tag name (e.g., develop, main, v1.0.0)
  --rebuild      (Optional) Force rebuild even if image already exists
  --json         (Optional) Show build progress + JSON result at end
  --short        (Optional) Silent build, output only image name
  CUSTOM_IMAGE   (Optional) Override image name/tag for build output

OUTPUT MODES:
  Default Mode   : Full progress with emoji and human-readable messages
  --json Mode    : Full progress + structured JSON result at the end
                   (Best for automation with real-time monitoring)
  --short Mode   : Silent build, only outputs the final image name
                   (Best for simple scripts and variable assignment)

ENVIRONMENT VARIABLES:
  Resource Limits:
    DEFAULT_MEMORY       Memory limit (default: 2g)
    DEFAULT_CPUS         CPU count (default: 1)
    DEFAULT_CPU_PERIOD   CPU period (default: 100000)
    DEFAULT_CPU_QUOTA    CPU quota (default: 100000)

  API Configuration:
    DEFAULT_URL_API      API endpoint URL (default: http://193.1.1.3:5000)

  Authentication:
    GITUSERTOKEN         Git user token
    BITBUCKET_USER       Bitbucket username
    GITHUB_USER          GitHub username
    BITBUCKET_TOKEN      Bitbucket access token
    GITHUB_TOKEN         GitHub access token

  Notification:
    NTFY_URL             Ntfy.sh notification URL (default: https://ntfy.sh/doi-notif)

EXAMPLES:
  # Basic build
  doq devops-ci saas-be-core develop

  # Force rebuild existing image
  doq devops-ci saas-be-core develop --rebuild

  # Build with custom image name
  doq devops-ci saas-be-core develop --rebuild loyaltolpi/saas-be-core:dev-123

  # Build with JSON output
  doq devops-ci saas-be-core develop --json

  # Build with short output (silent)
  IMAGE=$(doq devops-ci saas-be-core develop --short)

  # Build with custom resource limits
  DEFAULT_MEMORY=4g DEFAULT_CPUS=2 doq devops-ci saas-be-core develop

FEATURES:
  ✅ Multi-platform build support
  ✅ SBOM (Software Bill of Materials) generation
  ✅ Provenance attestation for security
  ✅ Resource limit management
  ✅ Automatic image caching
  ✅ Bitbucket integration
  ✅ Progress tracking
  ✅ Real-time notifications via ntfy.sh

EXIT CODES:
  0 - Build successful or skipped
  1 - Invalid arguments or build failed

NOTES:
  - Requires ~/.devops/auth.json for authentication
  - Uses container-builder for multi-platform builds
  - Images are automatically pushed to registry
  - Build cache is disabled for reproducible builds
  - Build notifications are automatically sent to ntfy.sh
""")

