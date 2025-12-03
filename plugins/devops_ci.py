#!/usr/bin/env python3
"""
DevOps CI/CD Build Tool - Python implementation.
Optimized version with DRY and KISS principles.
"""
from __future__ import annotations
import json
import os
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import requests
from config_utils import get_env_override
from plugins.base import BasePlugin
from plugins.shared_helpers import resolve_teams_webhook

VERSION = "2.0.1"
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")

def show_version() -> None:
    """Show version information."""
    print(f"DevOps CI/CD Builder v{VERSION}")
    print(f"Build date: {BUILD_DATE}")

def show_help() -> None:
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

For more information, visit: https://github.com/mamatnurahmat/devops-tools
"""
    print(help_text)

class DevOpsCIBuilder(BasePlugin):
    """
    Main builder for DevOps CI/CD.
    """
    
    def __init__(self, repo: str = "", refs: str = "", rebuild: bool = False,
                 json_output: bool = False, short_output: bool = False,
                 custom_image: str = "", helper_mode: bool = False,
                 helper_args: Optional[Dict[str, str]] = None,
                 builder_name: Optional[str] = None,
                 webhook_url: Optional[str] = None, no_cache: bool = False,
                 local_mode: bool = False, build_args: Optional[Dict[str, str]] = None):
        
        super().__init__('devops-ci')
        
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
        
        self.build_dir = None
        
        self.result = {
            'success': False,
            'image': '',
            'message': ''
        }
        
        self._migrate_from_old_location()

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "api": {
                "base_url": "https://api.devops.loyalto.id/v1",
                "timeout": 30
            },
            "docker": {
                "namespace": "loyaltolpi",
                "buildx_args": [
                    "--sbom=true",
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

    def _apply_env_overrides(self):
        # Override API configuration
        if api_url := get_env_override("DEVOPS_CI_API_URL"):
            self.config["api"]["base_url"] = api_url
        
        # Override Docker namespace
        if docker_ns := get_env_override("DEVOPS_CI_DOCKER_NAMESPACE"):
            self.config["docker"]["namespace"] = docker_ns
        
        # Override notification enabled
        if notif_enabled := get_env_override("DEVOPS_CI_NOTIFICATION_ENABLED"):
            self.config["notification"]["enabled"] = notif_enabled.lower() in ('true', '1', 'yes')

    def _migrate_from_old_location(self) -> None:
        """Migrate config from old ~/.devops to new ~/.doq location."""
        old_dir = Path.home() / ".devops"
        new_dir = self.config_dir
        old_auth = old_dir / "auth.json"
        new_auth = new_dir / "auth.json"
        
        if old_auth.exists() and not new_auth.exists():
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_auth, new_auth)
            if not self.short_output:
                print(f"✅ Migrated auth.json from {old_dir} to {new_dir}")

    def build(self) -> int:
        """Run the build process."""
        exit_code = 1
        try:
            if self.local_mode:
                if not self.short_output:
                    print("🏠 Running in LOCAL MODE")
                self.log_info(f"Starting build in LOCAL MODE for {self.repo}:{self.refs}")
                exit_code = self._build_local_mode()
            elif self.helper_mode:
                if not self.short_output:
                    print("🔧 Running in HELPER MODE")
                self.log_info(f"Starting build in HELPER MODE for {self.repo}:{self.refs}")
                exit_code = self._build_helper_mode()
            else:
                if not self.short_output:
                    print("🌐 Running in API MODE")
                self.log_info(f"Starting build in API MODE for {self.repo}:{self.refs}")
                exit_code = self._build_api_mode()
        except Exception as e:
            self.result['message'] = str(e)
            error_msg = f"Build failed: {e}"
            if not self.short_output:
                print(f"❌ {error_msg}", file=sys.stderr)
            self.log_error(error_msg)
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
        if not self.load_auth():
            if not self.short_output:
                print("❌ Authentication failed", file=sys.stderr)
            return 1
        
        metadata = self._fetch_build_metadata_local()
        if not metadata:
            return 1
        
        if not self.rebuild:
            if self._skip_existing_image(metadata):
                return 0
        
        build_config = self._fetch_build_config_local()
        
        if not self._clone_repository(metadata):
            return 1
        
        if not self._build_docker_image(metadata, build_config):
            self._cleanup()
            return 1
        
        if not self._push_docker_image(metadata):
            self._cleanup()
            return 1
        
        self._send_notification(metadata['image_name'], "success")
        self._cleanup()
        self._output_build_result(metadata)
        
        return 0

    def _build_helper_mode(self) -> int:
        if not self.load_auth():
            if not self.short_output:
                print("❌ Authentication failed", file=sys.stderr)
            return 1
        
        metadata = self._generate_helper_metadata()
        if not metadata:
            return 1
        
        build_config = self._fetch_build_config_local()
        
        if not self._clone_repository(metadata):
            return 1
        
        if not self._build_docker_image(metadata, build_config):
            self._cleanup()
            return 1
        
        if not self._push_docker_image(metadata):
            self._cleanup()
            return 1
        
        self._cleanup()
        self._output_build_result(metadata)
        
        return 0

    def _build_local_mode(self) -> int:
        repo_path = Path.cwd()
        
        if not self.load_auth():
            if not self.short_output:
                print("❌ Authentication failed", file=sys.stderr)
            return 1
        
        try:
            build_config = self._load_local_build_config(repo_path)
        except Exception as e:
            self.log_error(f"Failed to read local cicd/cicd.json: {e}")
            return 1
        
        try:
            commit_info = self._get_local_commit_info(repo_path)
        except Exception as e:
            if not self.short_output:
                self.log_error(f"Failed to resolve local git metadata: {e}")
            return 1
        
        image_override = self.helper_args.get('image_name') or self.custom_image
        if image_override:
            image_name = self._parse_custom_image(image_override, commit_info)
        else:
            image_from_config = build_config.get('IMAGE', self.repo)
            namespace = self.get_config('docker.namespace', 'loyaltolpi')
            tag_version = self._get_tag_version(commit_info)
            image_name = f"{namespace}/{image_from_config}:{tag_version}"
        
        metadata = {
            'image_name': image_name,
            'commit_hash': commit_info['full_hash'],
            'short_hash': commit_info['short_hash'],
            'ref_type': commit_info['ref_type']
        }
        
        if not self.rebuild:
            if self._skip_existing_image(metadata):
                return 0
        
        if not self._build_docker_image(metadata, build_config, build_context=str(repo_path)):
            return 1
        
        self._send_notification(metadata['image_name'], "success")
        self._output_build_result(metadata)
        
        return 0

    def _skip_existing_image(self, metadata: Dict[str, Any]) -> bool:
        check_result = self.check_image_exists(metadata['image_name'])
        if check_result['exists']:
            skip_msg = f"Image already ready: {metadata['image_name']}. Skipping build."
            if not self.short_output:
                print(f"✅ {skip_msg}")
            self.log_info(skip_msg)
            if self.short_output:
                print(metadata['image_name'])
            self.result['success'] = True
            self.result['image'] = metadata['image_name']
            self.result['message'] = 'Image already exists'
            
            self._send_notification(metadata['image_name'], "skipped")
            
            if self.json_output:
                print(json.dumps(self.result))
            return True
        return False

    def _get_local_commit_info(self, repo_path: Path) -> Dict[str, Any]:
        def _run_git(*args: str) -> str:
            result = self.run_command(['git', *args], cwd=repo_path, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Unknown git error")
            return result.stdout.strip()
        
        if not self.refs:
            raise ValueError("Reference (branch/tag) is required in local mode")
        
        full_hash = _run_git('rev-parse', self.refs)
        short_hash = _run_git('rev-parse', '--short', full_hash)
        
        ref_type = 'branch'
        try:
            _run_git('rev-parse', '--verify', f'refs/tags/{self.refs}')
            ref_type = 'tag'
        except RuntimeError:
            pass
        
        return {
            'full_hash': full_hash,
            'short_hash': short_hash,
            'ref_type': ref_type
        }

    def _load_local_build_config(self, repo_path: Path) -> Dict[str, Any]:
        cicd_path = repo_path / 'cicd' / 'cicd.json'
        if not cicd_path.exists():
            raise FileNotFoundError(f"{cicd_path} not found")
        
        with open(cicd_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _fetch_build_metadata_local(self) -> Optional[Dict[str, Any]]:
        if not self.short_output:
            print(f"📦 Fetching build metadata for repo={self.repo}, refs={self.refs} ...")
        self.log_info(f"Fetching build metadata for repo={self.repo}, refs={self.refs}")
        
        try:
            commit_info = self.get_commit_hash(self.repo, self.refs)
            
            try:
                cicd_content = self.fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json")
                cicd_data = json.loads(cicd_content)
                image_name = cicd_data.get('IMAGE', self.repo)
            except Exception:
                image_name = self.repo
            
            namespace = self.get_config('docker.namespace', 'loyaltolpi')
            tag_version = self._get_tag_version(commit_info)
            full_image = f"{namespace}/{image_name}:{tag_version}"
            
            return {
                'image_name': full_image,
                'commit_hash': commit_info['full_hash'],
                'short_hash': commit_info['short_hash'],
                'ref_type': commit_info['ref_type']
            }
        
        except Exception as e:
            self.log_error(f"Failed to fetch metadata: {e}")
            return None

    def _fetch_build_config_local(self) -> Optional[Dict[str, Any]]:
        try:
            cicd_content = self.fetch_bitbucket_file(self.repo, self.refs, "cicd/cicd.json")
            return json.loads(cicd_content)
        except Exception as e:
            if not self.short_output:
                print(f"⚠️  Warning: Could not fetch cicd.json: {e}")
                print(f"   Using default build configuration")
            return {}

    def _get_tag_version(self, commit_info: Dict[str, Any]) -> str:
        if commit_info['ref_type'] == 'tag':
            return self.refs
        else:
            return commit_info['short_hash']

    def _parse_custom_image(self, custom_image: str, commit_info: Dict[str, Any]) -> str:
        if ':' in custom_image:
            return custom_image
        
        image_base = custom_image
        if '/' in image_base:
            full_image_base = image_base
        else:
            namespace = self.get_config('docker.namespace', 'loyaltolpi')
            full_image_base = f"{namespace}/{image_base}"
        
        tag_version = self._get_tag_version(commit_info)
        return f"{full_image_base}:{tag_version}"

    def _generate_helper_metadata(self) -> Optional[Dict[str, Any]]:
        try:
            commit_info = self.get_commit_hash(self.repo, self.refs)
            custom_image = self.helper_args.get('image_name', '')
            
            if custom_image:
                full_image = self._parse_custom_image(custom_image, commit_info)
            else:
                namespace = self.get_config('docker.namespace', 'loyaltolpi')
                tag_version = self._get_tag_version(commit_info)
                full_image = f"{namespace}/{self.repo}:{tag_version}"
            
            return {
                'image_name': full_image,
                'commit_hash': commit_info['full_hash'],
                'short_hash': commit_info['short_hash'],
                'ref_type': commit_info['ref_type']
            }
        except Exception as e:
            self.log_error(f"Failed to generate metadata: {e}")
            return None

    def _clone_repository(self, metadata: Dict[str, Any]) -> bool:
        if not self.short_output:
            print(f"\n📥 Cloning repository...")
        self.log_info(f"Cloning repository {self.repo} (refs: {self.refs})")
        
        try:
            self.build_dir = tempfile.mkdtemp(prefix='doq-build-')
            
            git_user = self.auth_data.get('GIT_USER', '')
            git_password = self.auth_data.get('GIT_PASSWORD', '')
            
            if not git_user or not git_password:
                raise ValueError("GIT_USER and GIT_PASSWORD required in auth.json")
            
            clone_url = f"https://{git_user}:{git_password}@bitbucket.org/loyaltoid/{self.repo}.git"
            clone_depth = self.get_config('git.clone_depth', 1)
            
            self.run_command([
                'git', 'clone',
                '--depth', str(clone_depth),
                '--branch', self.refs,
                clone_url,
                self.build_dir
            ])
            
            self.run_command(['git', 'checkout', metadata['commit_hash']], cwd=self.build_dir)
            
            if not self.short_output:
                print(f"✅ Repository cloned successfully")
            self.log_info(f"Repository cloned successfully: {self.repo}")
            return True
        
        except Exception as e:
            self.log_error(f"Clone failed: {e}")
            return False

    def _setup_builder(self, builder_name: str) -> bool:
        try:
            result = self.run_command(['docker', 'buildx', 'inspect', builder_name], capture_output=True, text=True)
            
            if result.returncode == 0:
                if 'docker-container' in result.stdout:
                    if not self.short_output:
                        print(f"✅ Builder '{builder_name}' already exists with docker-container driver")
                    return True
                else:
                    if not self.short_output:
                        print(f"✅ Builder '{builder_name}' already exists")
                    return True
            
            if not self.short_output:
                print(f"🔨 Creating Docker buildx builder '{builder_name}'...")
            
            self.run_command([
                'docker', 'buildx', 'create',
                '--name', builder_name,
                '--driver', 'docker-container',
                '--use'
            ])
            
            if not self.short_output:
                print(f"✅ Builder '{builder_name}' created successfully")
            return True
        
        except Exception as e:
            if not self.short_output:
                print(f"❌ Failed to setup builder: {e}", file=sys.stderr)
            return False

    def _build_docker_image(self, metadata: Dict[str, Any], build_config: Dict[str, Any],
                            build_context: Optional[str] = None) -> bool:
        if not self.short_output:
            print(f"\n🔨 Building Docker image...")
            print(f"   Image: {metadata['image_name']}")
        self.log_info(f"Building Docker image: {metadata['image_name']}")
        
        context_dir = build_context or self.build_dir
        if not context_dir:
            raise RuntimeError("Build context is not defined")
        
        try:
            default_builder = 'container-builder'
            builder_to_use = self.builder_name if self.builder_name else default_builder
            
            if not self._setup_builder(builder_to_use):
                raise RuntimeError(f"Failed to setup builder '{builder_to_use}'")
            
            if not self.short_output:
                print(f"   Builder: {builder_to_use}")
            
            buildx_args = self.get_config('docker.buildx_args', [])
            build_cmd = [
                'docker', 'buildx', 'build',
                '--builder', builder_to_use,
                '-t', metadata['image_name'],
                '--push'
            ]
            
            build_cmd += buildx_args
            build_cmd.extend(['--attest', 'type=provenance,mode=max'])
            
            if self.no_cache:
                build_cmd.append('--no-cache')
            
            if build_config:
                registry = build_config.get('REGISTRY', self.helper_args.get('registry', ''))
                port = build_config.get('PORT', self.helper_args.get('port', ''))
                
                if registry:
                    build_cmd.extend(['--build-arg', f'REGISTRY={registry}'])
                if port:
                    build_cmd.extend(['--build-arg', f'PORT={port}'])
            
            for key, value in self.build_args.items():
                build_cmd.extend(['--build-arg', f'{key}={value}'])
            
            build_cmd.append('.')
            
            capture = self.short_output or self.json_output
            self.run_command(build_cmd, cwd=context_dir, capture_output=capture, text=True, timeout=3600)
            
            if not self.short_output:
                print(f"✅ Image built successfully")
            self.log_info(f"Image built successfully: {metadata['image_name']}")
            return True
        
        except Exception as e:
            self.log_error(f"Docker build failed: {e}")
            return False

    def _push_docker_image(self, metadata: Dict[str, Any]) -> bool:
        if not self.short_output:
            print(f"✅ Image pushed to registry")
        self.log_info(f"Image pushed to registry: {metadata['image_name']}")
        return True

    def _output_build_result(self, metadata: Dict[str, Any]) -> None:
        if self.short_output:
            print(metadata['image_name'])
            self.log_info(f"Build completed: {metadata['image_name']}")
        elif not self.json_output:
            print(f"\n✅ Build completed successfully!")
            print(f"   Image: {metadata['image_name']}")
            self.log_info(f"Build completed successfully! Image: {metadata['image_name']}")
        
        self.result['success'] = True
        self.result['image'] = metadata['image_name']
        self.result['message'] = 'Build successful'
        
        if self.json_output:
            print(json.dumps(self.result))
            self.log_info(f"Build successful: {metadata['image_name']}")

    def _send_notification(self, image_name: str, status: str) -> None:
        if not self.get_config('notification.enabled', True):
            return
        
        ntfy_url = self.auth_data.get('NTFY_URL', '')
        if not ntfy_url:
            return
        
        try:
            topic = self.get_config('notification.topic', 'ci_status')
            status_emoji = {'success': '✅', 'skipped': '⏭️', 'failed': '❌'}
            emoji = status_emoji.get(status, '📦')
            
            message = {
                'topic': topic,
                'title': f'{emoji} DevOps CI Build {status.title()}',
                'message': f'Repository: {self.repo}\nBranch: {self.refs}\nImage: {image_name}',
                'priority': 3 if status == 'success' else 4
            }
            
            requests.post(ntfy_url, json=message, timeout=10)
            if not self.short_output:
                print(f"📤 Notification sent to ntfy.sh")
        except Exception as e:
            if not self.short_output:
                print(f"⚠️  Warning: Failed to send notification to ntfy.sh: {e}")

    def _send_teams_webhook(self, success: bool) -> None:
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
        
        self.send_notification(
            title=f"DevOps CI Build {status_text}",
            facts=facts,
            success=success,
            webhook_url=self.teams_webhook_url
        )

    def _cleanup(self) -> None:
        if self.build_dir and os.path.exists(self.build_dir):
            shutil.rmtree(self.build_dir)
            if not self.short_output:
                print(f"🧹 Cleaned up build directory")

def _detect_helper_mode(args) -> Tuple[bool, Dict[str, str]]:
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
        helper_mode = getattr(args, 'helper', False) or auto_helper_mode
    
    return helper_mode, helper_args

def cmd_devops_ci(args) -> None:
    if hasattr(args, 'help_devops_ci') and args.help_devops_ci:
        show_help()
        sys.exit(0)
    
    if hasattr(args, 'version_devops_ci') and args.version_devops_ci:
        show_version()
        sys.exit(0)
    
    if not args.repo or not args.refs:
        print("❌ Error: repo and refs are required arguments", file=sys.stderr)
        print("   Usage: doq devops-ci <repo> <refs> [options]", file=sys.stderr)
        sys.exit(1)
    
    helper_mode, helper_args = _detect_helper_mode(args)
    
    build_args = {}
    build_arg_list = getattr(args, 'build_arg', None) or []
    for build_arg_str in build_arg_list:
        if '=' not in build_arg_str:
            print(f"❌ Error: Invalid build-arg format: {build_arg_str}", file=sys.stderr)
            sys.exit(1)
        key, value = build_arg_str.split('=', 1)
        if not key.strip():
            print(f"❌ Error: Build arg key cannot be empty: {build_arg_str}", file=sys.stderr)
            sys.exit(1)
        build_args[key.strip()] = value
    
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
    
    exit_code = builder.build()
    sys.exit(exit_code)

def register_commands(subparsers) -> None:
    devops_ci_parser = subparsers.add_parser(
        'devops-ci',
        help='Build Docker images from repositories',
        description='Build Docker images from Bitbucket repositories using buildx with SBOM and provenance support'
    )
    
    devops_ci_parser.add_argument('repo', nargs='?', help='Repository name')
    devops_ci_parser.add_argument('refs', nargs='?', help='Branch or tag name')
    devops_ci_parser.add_argument('custom_image', nargs='?', default='', help='Custom image name/tag')
    
    devops_ci_parser.add_argument('--rebuild', action='store_true', help='Force rebuild')
    devops_ci_parser.add_argument('--no-cache', action='store_true', help='Disable Docker layer caching')
    devops_ci_parser.add_argument('--json', action='store_true', help='JSON output')
    devops_ci_parser.add_argument('--short', action='store_true', help='Short output')
    devops_ci_parser.add_argument('--helper', action='store_true', help='Helper mode')
    devops_ci_parser.add_argument('--local', action='store_true', help='Local mode')
    
    devops_ci_parser.add_argument('--image-name', help='Custom image name')
    devops_ci_parser.add_argument('--registry', help='Registry URL')
    devops_ci_parser.add_argument('--port', help='Application port')
    
    devops_ci_parser.add_argument('--use-builder', help='Docker buildx builder name')
    devops_ci_parser.add_argument('--webhook', type=str, help='Teams webhook URL')
    devops_ci_parser.add_argument('--build-arg', action='append', help='Build argument KEY=VALUE')
    
    devops_ci_parser.add_argument('--help-devops-ci', action='store_true', help='Show help')
    devops_ci_parser.add_argument('--version-devops-ci', action='store_true', help='Show version')
    
    devops_ci_parser.set_defaults(func=cmd_devops_ci)
