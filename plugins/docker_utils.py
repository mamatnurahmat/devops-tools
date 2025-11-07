#!/usr/bin/env python3
"""Docker utilities plugin for doq CLI."""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from config_utils import load_json_config, get_env_override
from plugins.shared_helpers import (
    load_auth_file,
    check_docker_image_exists,
    fetch_bitbucket_file,
    get_commit_hash_from_bitbucket
)


class DockerUtilsConfig:
    """Configuration manager for docker-utils plugin."""
    
    def __init__(self):
        """Initialize configuration with defaults and overrides."""
        self.config_dir = Path.home() / ".doq"
        self.plugin_config_file = self.config_dir / "plugins" / "docker-utils.json"
        
        # Load plugin config
        self.config = self._load_config()
        
        # Apply environment variable overrides
        self._apply_env_overrides()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from plugin config file."""
        default_config = {
            "registry": {
                "namespace": "loyaltolpi",
                "default_registry": "docker.io"
            },
            "bitbucket": {
                "org": "loyaltoid",
                "api_base": "https://api.bitbucket.org/2.0/repositories",
                "default_cicd_path": "cicd/cicd.json"
            },
            "force_build": {
                "enabled": True,
                "trigger_command": "devops-ci"
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
        # Registry overrides
        namespace = get_env_override("DOCKER_UTILS_REGISTRY_NAMESPACE")
        if namespace:
            self.config["registry"]["namespace"] = namespace
        
        registry = get_env_override("DOCKER_UTILS_REGISTRY")
        if registry:
            self.config["registry"]["default_registry"] = registry
        
        # Bitbucket overrides
        bb_org = get_env_override("DOCKER_UTILS_BITBUCKET_ORG")
        if bb_org:
            self.config["bitbucket"]["org"] = bb_org
        
        bb_api = get_env_override("DOCKER_UTILS_BITBUCKET_API_BASE")
        if bb_api:
            self.config["bitbucket"]["api_base"] = bb_api
    
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


class ImageChecker:
    """Check Docker image status in Docker Hub."""
    
    def __init__(self, config: Optional[DockerUtilsConfig] = None):
        """Initialize image checker.
        
        Args:
            config: DockerUtilsConfig instance, or None to create new one
        """
        self.config = config or DockerUtilsConfig()
    
    def check(self, repo: str, refs: str, force_build: bool = False, json_output: bool = False) -> Dict[str, Any]:
        """Check if Docker image exists for given repo and refs.
        
        Args:
            repo: Repository name
            refs: Branch or tag name
            force_build: If True, trigger build if image doesn't exist
            json_output: If True, output in JSON format
            
        Returns:
            Dict with 'ready' (bool), 'image' (str), 'exists' (bool), and error details if not ready
        """
        try:
            # Load auth
            auth_data = load_auth_file()
            
            # Get commit hash from Bitbucket
            commit_info = get_commit_hash_from_bitbucket(repo, refs, auth_data)
            short_hash = commit_info['short_hash']
            
            # Generate full image name
            namespace = self.config.get('registry.namespace', 'loyaltolpi')
            full_image = f"{namespace}/{repo}:{short_hash}"
            
            # Check if image exists in Docker Hub (now returns Dict)
            check_result = check_docker_image_exists(full_image, auth_data, verbose=False)
            
            result = {
                'ready': check_result['exists'],
                'image': full_image,
                'exists': check_result['exists'],
                'repository': repo,
                'reference': refs,
                'commit': short_hash
            }
            
            # Add error details if not ready
            if not check_result['exists']:
                result['error'] = check_result.get('error', 'Unknown error')
                result['error_type'] = check_result.get('error_type', 'unknown')
                
                # Add helpful suggestions based on error type
                if check_result['error_type'] == 'credentials_missing':
                    result['suggestion'] = 'Add DOCKERHUB_USER and DOCKERHUB_PASSWORD to ~/.doq/auth.json'
                elif check_result['error_type'] == 'auth_failed':
                    # More detailed suggestion for auth failures
                    if 'status: 500' in result['error']:
                        result['suggestion'] = 'Docker Hub API error. Verify: 1) Credentials are correct (username + password, not PAT), 2) Try: curl -X POST https://hub.docker.com/v2/users/login/ -H "Content-Type: application/json" -d \'{"username":"USER","password":"PASS"}\''
                    else:
                        result['suggestion'] = 'Check Docker Hub credentials in ~/.doq/auth.json (use actual password, not Personal Access Token)'
                elif check_result['error_type'] == 'not_found':
                    result['suggestion'] = f'Build image first: doq devops-ci {repo} {refs}'
                elif check_result['error_type'] in ['network_timeout', 'network_error']:
                    result['suggestion'] = 'Check network connectivity and firewall settings'
                elif check_result['error_type'] == 'invalid_format':
                    result['suggestion'] = 'Check image name format'
            
            return result
            
        except Exception as e:
            return {
                'ready': False,
                'image': None,
                'exists': False,
                'error': str(e),
                'error_type': 'unknown',
                'repository': repo,
                'reference': refs
            }


class CICDConfigFetcher:
    """Fetch cicd.json from Bitbucket."""
    
    def __init__(self, config: Optional[DockerUtilsConfig] = None):
        """Initialize CICD config fetcher.
        
        Args:
            config: DockerUtilsConfig instance, or None to create new one
        """
        self.config = config or DockerUtilsConfig()
    
    def fetch(self, repo: str, refs: str, json_output: bool = False) -> Dict[str, Any]:
        """Fetch cicd.json from Bitbucket repository.
        
        Args:
            repo: Repository name
            refs: Branch or tag name
            json_output: If True, return compact JSON format
            
        Returns:
            Dict with cicd.json content or error
        """
        try:
            # Load auth
            auth_data = load_auth_file()
            
            # Get cicd path from config
            cicd_path = self.config.get('bitbucket.default_cicd_path', 'cicd/cicd.json')
            
            # Fetch cicd.json
            cicd_content = fetch_bitbucket_file(repo, refs, cicd_path, auth_data)
            cicd_data = json.loads(cicd_content)
            
            return {
                'success': True,
                'data': cicd_data,
                'repository': repo,
                'reference': refs
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'repository': repo,
                'reference': refs
            }


def cmd_images(args):
    """Command handler for 'doq image'."""
    checker = ImageChecker()
    result = checker.check(args.repo, args.refs, args.force_build, args.json)
    
    # Handle force-build option
    if args.force_build and not result['ready']:
        print(f"\n🔨 Image not ready, starting build...")
        print(f"   Running: doq devops-ci {args.repo} {args.refs}\n")
        
        # Import and call devops-ci builder
        try:
            from plugins.devops_ci import DevOpsCIBuilder
            builder = DevOpsCIBuilder(
                repo=args.repo,
                refs=args.refs,
                rebuild=False,
                json_output=args.json,
                short_output=False,
                custom_image="",
                helper_mode=False,
                helper_args={}
            )
            
            exit_code = builder.build()
            sys.exit(exit_code)
        except Exception as e:
            print(f"❌ Build failed: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Output results - always JSON format
    output = {
        'repository': result.get('repository', args.repo),
        'reference': result.get('reference', args.refs),
        'image': result.get('image'),
        'ready': result['ready'],
        'status': 'ready' if result['ready'] else 'not-ready'
    }
    
    # Add error details if not ready
    if not result['ready']:
        if 'error' in result:
            output['error'] = result['error']
        if 'error_type' in result:
            output['error_type'] = result['error_type']
        if 'suggestion' in result:
            output['suggestion'] = result['suggestion']
    
    print(json.dumps(output, indent=2))
    sys.exit(0 if result['ready'] else 1)


def cmd_get_cicd(args):
    """Command handler for 'doq get-cicd'."""
    fetcher = CICDConfigFetcher()
    result = fetcher.fetch(args.repo, args.refs, args.json)
    
    if result['success']:
        # Always output pure JSON (silent mode)
        print(json.dumps(result['data'], indent=2))
        sys.exit(0)
    else:
        print(f"❌ Error: {result['error']}", file=sys.stderr)
        sys.exit(1)


def cmd_get_file(args):
    """Command handler for 'doq get-file'."""
    try:
        # Load auth
        auth_data = load_auth_file()
        
        # Fetch file from Bitbucket
        file_content = fetch_bitbucket_file(args.repo, args.refs, args.file_path, auth_data)
        
        # Output file content directly (silent mode)
        print(file_content)
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def register_commands(subparsers):
    """Register docker-utils commands with argparse.
    
    This function is called by PluginManager to dynamically register
    the plugin's commands.
    
    Args:
        subparsers: The argparse subparsers object
    """
    # Image command - check Docker image status
    image_parser = subparsers.add_parser('image',
                                          help='Check Docker image status in Docker Hub',
                                          description='Check if a Docker image exists in Docker Hub for the given repository and branch/tag')
    image_parser.add_argument('repo', help='Repository name (e.g., saas-be-core)')
    image_parser.add_argument('refs', help='Branch or tag name (e.g., develop)')
    image_parser.add_argument('--json', action='store_true',
                               help='Output in JSON format')
    image_parser.add_argument('--force-build', action='store_true',
                               help='Automatically build image if not ready')
    image_parser.set_defaults(func=cmd_images)
    
    # Get-cicd command - fetch cicd.json from Bitbucket
    get_cicd_parser = subparsers.add_parser('get-cicd',
                                            help='Get cicd.json from Bitbucket repository',
                                            description='Fetch and display the cicd.json configuration file from a Bitbucket repository')
    get_cicd_parser.add_argument('repo', help='Repository name (e.g., saas-be-core)')
    get_cicd_parser.add_argument('refs', help='Branch or tag name (e.g., develop)')
    get_cicd_parser.add_argument('--json', action='store_true',
                                 help='Output in compact JSON format (default is pretty-printed)')
    get_cicd_parser.set_defaults(func=cmd_get_cicd)
    
    # Get-file command - fetch any file from Bitbucket
    get_file_parser = subparsers.add_parser('get-file',
                                            help='Get any file from Bitbucket repository',
                                            description='Fetch and display any file content from a Bitbucket repository')
    get_file_parser.add_argument('repo', help='Repository name (e.g., saas-be-core)')
    get_file_parser.add_argument('refs', help='Branch or tag name (e.g., develop)')
    get_file_parser.add_argument('file_path', help='File path in repository (e.g., Dockerfile, README.md, src/main.py)')
    get_file_parser.set_defaults(func=cmd_get_file)


