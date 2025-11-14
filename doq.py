#!/usr/bin/env python3
"""DevOps Q - Simple CLI tool for managing Rancher resources."""
import argparse
import getpass
import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote
from rancher_api import RancherAPI, login, check_token
from config import load_config, save_config, get_config_file_path, config_exists, ensure_config_dir
from version import get_version, save_version, check_for_updates, get_latest_commit_hash
from plugin_manager import PluginManager
from plugins.shared_helpers import (
    load_netrc_credentials,
    load_auth_file,
    _load_auth_from_docker,
    _load_auth_from_netrc,
    _load_auth_from_env,
    BITBUCKET_API_BASE,
    BITBUCKET_ORG,
    resolve_teams_webhook,
    send_teams_notification,
    validate_auth_file
)

def _is_remote_auth_enabled() -> bool:
    """Return True if RANCHER_AUTH flag is set in env or ~/.doq/.env."""
    value = os.getenv("RANCHER_AUTH")
    if value is None:
        env_file = Path.home() / ".doq" / ".env"
        if env_file.exists():
            try:
                from dotenv import load_dotenv  # type: ignore
            except ImportError:
                pass
            else:
                try:
                    load_dotenv(env_file, override=False)
                    value = os.getenv("RANCHER_AUTH")
                except Exception:
                    pass
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bootstrap_auth_credentials(url: str, token: str, insecure: bool, username: str, force: bool = False) -> None:
    """Ensure ~/.doq/auth.json exists by fetching from auth-api when empty, with user confirmation (unless force=True)."""
    auth_path = Path.home() / ".doq" / "auth.json"

    # When force=True, always attempt to fetch from auth-api (for --update-auth or --force)
    if not force:
        requires_bootstrap = False
        bootstrap_reason = ""

        try:
            validation = validate_auth_file()
            if not validation.get("valid", False):
                requires_bootstrap = True
                bootstrap_reason = validation.get("message", "missing required credentials")
        except Exception as exc:
            requires_bootstrap = True
            bootstrap_reason = str(exc)

        if not requires_bootstrap:
            return

        if auth_path.exists() and auth_path.stat().st_size == 0:
            bootstrap_reason = "auth.json exists but is empty"
        elif not auth_path.exists():
            bootstrap_reason = bootstrap_reason or "auth.json not found"

        print(f"ℹ️  {bootstrap_reason}.", file=sys.stderr)
    else:
        print(f"🔄 Force updating auth.json from auth-api...", file=sys.stderr)

    remote_auth_mode = _is_remote_auth_enabled()
    if remote_auth_mode:
        print("🔒 RANCHER_AUTH enabled: using remote auth-api credentials (local fallbacks disabled).", file=sys.stderr)

    # Try to fetch from auth-api
    auth_data = None
    fetched_from_api = False

    print(f"🔍 Attempting to fetch credentials from auth-api...", file=sys.stderr)

    base_url = url.rstrip("/")
    encoded_username = quote(username)
    auth_api_url = (
        f"{base_url}/api/v1/namespaces/default/services/http:auth-api:8080/proxy/v1/auth/{encoded_username}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            auth_api_url,
            headers=headers,
            timeout=20,
            verify=not insecure,
        )
        response.raise_for_status()

        try:
            payload = response.json()
        except ValueError as exc:
            print(f"⚠️  Warning: auth-api returned invalid JSON: {exc}", file=sys.stderr)
        else:
            if isinstance(payload, dict):
                raw_value = payload.get("value")
                if raw_value:
                    try:
                        auth_data = json.loads(raw_value)
                        if isinstance(auth_data, dict):
                            fetched_from_api = True
                            print(f"✅ Successfully fetched credentials from auth-api", file=sys.stderr)
                        else:
                            print("⚠️  Warning: auth-api credentials payload is not a JSON object", file=sys.stderr)
                    except json.JSONDecodeError as exc:
                        print(f"⚠️  Warning: Failed to parse auth-api credentials payload: {exc}", file=sys.stderr)
                else:
                    print("⚠️  Warning: auth-api response missing 'value' field", file=sys.stderr)
            else:
                print("⚠️  Warning: auth-api response is not a JSON object", file=sys.stderr)
    except requests.RequestException as exc:
        print(f"⚠️  Warning: Failed to fetch credentials from auth-api: {exc}", file=sys.stderr)

    # If API failed, try fallback sources
    if not fetched_from_api:
        if remote_auth_mode:
            print("❌ Unable to retrieve credentials from auth-api while RANCHER_AUTH remote mode is enabled.", file=sys.stderr)
            print("   Please ensure the remote credential service is available, or unset RANCHER_AUTH to use local sources.", file=sys.stderr)
            return

        print(f"🔄 Falling back to local credential sources...", file=sys.stderr)

        # Try ~/.docker/config.json
        docker_auth = _load_auth_from_docker()
        if docker_auth:
            print(f"✅ Found Docker Hub credentials in ~/.docker/config.json", file=sys.stderr)
            auth_data = auth_data or {}
            auth_data.update(docker_auth)

        # Try ~/.netrc
        netrc_auth = _load_auth_from_netrc()
        if netrc_auth:
            print(f"✅ Found Bitbucket credentials in ~/.netrc", file=sys.stderr)
            auth_data = auth_data or {}
            auth_data.update(netrc_auth)

        # Try environment variables
        env_auth = _load_auth_from_env()
        if env_auth:
            print(f"✅ Found credentials in environment variables", file=sys.stderr)
            auth_data = auth_data or {}
            auth_data.update(env_auth)

    if not auth_data:
        print(f"❌ No credentials found in auth-api, ~/.docker/config.json, ~/.netrc, or environment variables.", file=sys.stderr)
        print(f"   Please ensure Docker Hub and Bitbucket credentials are available.", file=sys.stderr)
        return

    # Show what we found
    found_sources = []
    if 'DOCKERHUB_USER' in auth_data or 'DOCKERHUB_PASSWORD' in auth_data:
        found_sources.append("Docker Hub")
    if 'GIT_USER' in auth_data or 'GIT_PASSWORD' in auth_data:
        found_sources.append("Bitbucket")

    if found_sources:
        print(f"📋 Found credentials for: {', '.join(found_sources)}", file=sys.stderr)

    # Ask user for confirmation before saving (unless force=True)
    if not force:
        try:
            while True:
                response = input("Save credentials to ~/.doq/auth.json? (y/N): ").strip().lower()
                if response in ('y', 'yes'):
                    break
                elif response in ('n', 'no', ''):
                    print(f"ℹ️  Credentials not saved. You can manually create ~/.doq/auth.json or use environment variables.", file=sys.stderr)
                    return
                else:
                    print("Please answer 'y' or 'n'", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            print(f"\nℹ️  Credentials not saved due to interrupted input.", file=sys.stderr)
            return

    # Save the credentials
    try:
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        with open(auth_path, "w") as file_handle:
            json.dump(auth_data, file_handle, indent=2)
        auth_path.chmod(0o600)
        print(f"✅ Credentials saved to {auth_path}", file=sys.stderr)
    except Exception as exc:
        print(f"❌ Failed to save credentials: {exc}", file=sys.stderr)


def _validate_dockerhub_credentials(username: str, password: str) -> Dict[str, Any]:
    """Verify Docker Hub credentials by attempting a login."""
    result: Dict[str, Any] = {"valid": False, "message": ""}

    if not username or not password:
        result["message"] = "Docker Hub credentials missing (DOCKERHUB_USER / DOCKERHUB_PASSWORD)."
        return result

    try:
        response = requests.post(
            "https://hub.docker.com/v2/users/login/",
            json={"username": username, "password": password},
            headers={"User-Agent": "doq-cli/1.0"},
            timeout=15,
        )
    except requests.RequestException as exc:
        result["message"] = f"Docker Hub login request failed: {exc}"
        return result

    if response.status_code == 200:
        result["valid"] = True
        result["message"] = "Docker Hub credentials are valid."
    elif response.status_code in (401, 403):
        result["message"] = "Docker Hub credentials rejected (401/403)."
    else:
        result["message"] = f"Docker Hub login failed (HTTP {response.status_code})."

    return result


def _validate_bitbucket_credentials(username: str, password: str) -> Dict[str, Any]:
    """Verify Bitbucket credentials by querying the repositories endpoint."""
    result: Dict[str, Any] = {"valid": False, "message": ""}

    if not username or not password:
        result["message"] = "Bitbucket credentials missing (GIT_USER / GIT_PASSWORD)."
        return result

    try:
        # Use repository listing endpoint which works with repository admin permissions
        response = requests.get(
            "https://api.bitbucket.org/2.0/repositories/loyaltoid",
            auth=(username, password),
            timeout=15,
        )
    except requests.RequestException as exc:
        result["message"] = f"Bitbucket authentication request failed: {exc}"
        return result

    if response.status_code == 200:
        result["valid"] = True
        result["message"] = "Bitbucket credentials are valid."
    elif response.status_code in (401, 403):
        result["message"] = "Bitbucket credentials rejected (401/403)."
    else:
        result["message"] = f"Bitbucket authentication failed (HTTP {response.status_code})."

    return result


from plugins.set_image_yaml import update_image_in_repo, ImageUpdateError
import requests
# Plugins are now loaded dynamically via PluginManager
# No need to import plugin modules directly


def print_table(headers, rows):
    """Print data in table format."""
    if not rows:
        print("No data found.")
        return
    
    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Print header
    header_row = " | ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_row)
    print("-" * len(header_row))
    
    # Print rows
    for row in rows:
        row_str = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        print(row_str)


def cmd_list_projects(args):
    """List projects."""
    import json
    from pathlib import Path
    
    try:
        api = RancherAPI()
        projects = api.list_projects(cluster_id=args.cluster)
        
        # Default behavior: show only System projects
        # --all flag shows all projects
        if not args.all:
            # Default: filter to System projects only
            projects = [p for p in projects if p.get('name', '').lower() == 'system']
        
        # Get all clusters to map cluster ID to name
        clusters = {}
        try:
            all_clusters = api.list_clusters()
            for cluster in all_clusters:
                clusters[cluster.get('id', '')] = cluster.get('name', 'Unknown')
        except Exception:
            # If can't get clusters, continue without cluster names
            pass
        
        # Save to file if --save flag is set
        if args.save:
            # --save only works with System projects (default)
            # Cannot use --save with --all
            if args.all:
                print("Error: --save only works with System projects", file=sys.stderr)
                print("Usage: doq project --save", file=sys.stderr)
                sys.exit(1)
            
            # Ensure .doq directory exists
            doq_dir = Path.home() / '.doq'
            doq_dir.mkdir(parents=True, exist_ok=True)
            
            # Create simple format: list of dicts with id and cluster_name
            simple_data = []
            for project in projects:
                cluster_id = project.get('clusterId', '')
                cluster_name = clusters.get(cluster_id, cluster_id if cluster_id else 'N/A')
                
                simple_data.append({
                    'id': project.get('id', ''),
                    'cluster_name': cluster_name
                })
            
            # Save to file
            output_file = doq_dir / 'project.json'
            with open(output_file, 'w') as f:
                json.dump(simple_data, f, indent=2)
            
            print(f"? Saved {len(simple_data)} project(s) to {output_file}")
        
        if args.json:
            print(json.dumps(projects, indent=2))
        else:
            rows = []
            for project in projects:
                cluster_id = project.get('clusterId', '')
                cluster_name = clusters.get(cluster_id, cluster_id if cluster_id else 'N/A')
                
                if args.all:
                    # Detailed output for --all: show ID, Name, Cluster Name, Cluster ID, State
                    rows.append([
                        project.get('id', ''),
                        project.get('name', ''),
                        cluster_name,
                        cluster_id,
                        project.get('state', '')
                    ])
                else:
                    # Output for default: show ID and Cluster Name only
                    rows.append([
                        project.get('id', ''),
                        cluster_name
                    ])
            
            if args.all:
                # Detailed output for --all
                print_table(['ID', 'Name', 'Cluster Name', 'Cluster ID', 'State'], rows)
            else:
                # Simple output for default
                print_table(['ID', 'Cluster Name'], rows)
    except Exception as e:
        print(f"Error listing projects: {e}", file=sys.stderr)
        sys.exit(1)


def save_auth_to_api(url: str, token: str, insecure: bool, username: str) -> None:
    """Save current auth.json credentials to auth-api for the specified username."""
    auth_path = Path.home() / ".doq" / "auth.json"

    # Check if auth.json exists
    if not auth_path.exists():
        print("❌ Error: ~/.doq/auth.json does not exist. Run 'doq login' first.", file=sys.stderr)
        return

    # Load current auth data
    try:
        with open(auth_path, 'r') as f:
            auth_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error reading auth.json: {e}", file=sys.stderr)
        return

    if not auth_data:
        print("❌ Error: auth.json is empty. No credentials to save.", file=sys.stderr)
        return

    # Convert auth data to JSON string for storage
    try:
        auth_json = json.dumps(auth_data, separators=(',', ':'))
    except Exception as e:
        print(f"❌ Error serializing auth data: {e}", file=sys.stderr)
        return

    # URL encode username
    encoded_username = requests.utils.quote(username)

    # Construct auth-api URL
    base_url = url.rstrip('/')
    auth_api_url = (
        f"{base_url}/api/v1/namespaces/default/services/http:auth-api:8080/proxy/v1/auth/{encoded_username}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payload = {
        "value": auth_json
    }

    try:
        print(f"🔄 Saving credentials to auth-api for user '{username}'...", file=sys.stderr)
        response = requests.put(
            auth_api_url,
            headers=headers,
            json=payload,
            timeout=20,
            verify=not insecure,
        )
        response.raise_for_status()

        try:
            result = response.json()
            if result.get('status') == 'stored':
                print(f"✅ Successfully saved credentials to auth-api for user '{username}'", file=sys.stderr)
            else:
                print(f"⚠️  Warning: Unexpected response from auth-api: {result}", file=sys.stderr)
        except ValueError:
            print(f"✅ Credentials saved to auth-api for user '{username}' (response not JSON)", file=sys.stderr)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"❌ Error: auth-api service not found. Make sure auth-api is deployed.", file=sys.stderr)
        else:
            print(f"❌ Error saving to auth-api: {e.response.status_code} {e.response.reason}", file=sys.stderr)
            try:
                error_data = e.response.json()
                if 'error' in error_data:
                    print(f"   Details: {error_data['error']}", file=sys.stderr)
            except:
                pass
    except Exception as e:
        print(f"❌ Error saving credentials to auth-api: {e}", file=sys.stderr)


def cmd_login(args):
    """Login to Rancher API."""
    # Default values
    default_url = "https://193.1.1.4"
    default_insecure = True
    
    # Handle --update-auth: use existing config and just update auth.json
    if args.update_auth and config_exists():
        config = load_config()
        url = config.get('url')
        token = config.get('token')
        insecure = config.get('insecure', True)
        username = args.username or config.get('username')

        if not username:
            # Try to get username from current token
            try:
                print("🔍 Detecting username from current Rancher token...", file=sys.stderr)
                token_info = check_token(url, token, insecure)
                if token_info.get('username'):
                    username = token_info['username']
                    print(f"✅ Detected username: {username}", file=sys.stderr)
                else:
                    print("⚠️  Could not detect username from token, falling back to manual input.", file=sys.stderr)
                    username = input("Username: ")
            except Exception as e:
                print(f"⚠️  Error detecting username from token: {e}", file=sys.stderr)
                print("   Falling back to manual input.", file=sys.stderr)
                username = input("Username: ")

        if url and token and username:
            print(f"🔄 Updating auth.json using existing Rancher configuration...")
            print(f"  URL: {url}")
            print(f"  Username: {username}")
            print(f"  Insecure mode: {insecure}")
            print()

            # Save the username to config if it wasn't already stored
            if not config.get('username'):
                save_config(url, token, insecure, username)

            _bootstrap_auth_credentials(url, token, insecure, username, force=True)
            return
        else:
            print("❌ Error: Valid Rancher configuration not found.", file=sys.stderr)
            print("   Run 'doq login' first to configure Rancher API access.", file=sys.stderr)
            sys.exit(1)

    # Handle --save-auth: save current auth.json to auth-api
    if args.save_auth and config_exists():
        config = load_config()
        url = config.get('url')
        token = config.get('token')
        insecure = config.get('insecure', True)
        username = args.username or config.get('username')

        if not username:
            # Try to get username from current token
            try:
                print("🔍 Detecting username from current Rancher token...", file=sys.stderr)
                token_info = check_token(url, token, insecure)
                if token_info.get('username'):
                    username = token_info['username']
                    print(f"✅ Detected username: {username}", file=sys.stderr)
                else:
                    print("⚠️  Could not detect username from token, falling back to manual input.", file=sys.stderr)
                    username = input("Username: ")
            except Exception as e:
                print(f"⚠️  Error detecting username from token: {e}", file=sys.stderr)
                print("   Falling back to manual input.", file=sys.stderr)
                username = input("Username: ")

        if url and token and username:
            print(f"🔄 Saving auth.json to auth-api...")
            print(f"  URL: {url}")
            print(f"  Username: {username}")
            print(f"  Insecure mode: {insecure}")
            print()

            # Save the username to config if it wasn't already stored
            if not config.get('username'):
                save_config(url, token, insecure, username)

            save_auth_to_api(url, token, insecure, username)
            return
        else:
            print("❌ Error: Valid Rancher configuration not found.", file=sys.stderr)
            print("   Run 'doq login' first to configure Rancher API access.", file=sys.stderr)
            sys.exit(1)

    # Check if config exists and token is valid (skip if --force)
    if config_exists() and not args.force:
        config = load_config()
        existing_url = config.get('url')
        existing_token = config.get('token')
        existing_insecure = config.get('insecure', True)

        if existing_url and existing_token:
            # Check if token is valid and not expired
            try:
                result = check_token(existing_url, existing_token, existing_insecure)

                if result['valid'] and not result['expired']:
                    print("? Existing configuration found and token is valid!")
                    print(f"  URL: {existing_url}")
                    print(f"  Insecure mode: {existing_insecure}")
                    if result['expires_at']:
                        from datetime import datetime
                        try:
                            exp_str = result['expires_at']
                            if 'Z' in exp_str:
                                exp_str = exp_str.replace('Z', '+00:00')
                            exp_time = datetime.fromisoformat(exp_str)
                            if exp_time.tzinfo:
                                now = datetime.now(exp_time.tzinfo)
                            else:
                                now = datetime.now()
                            delta = exp_time - now
                            days = delta.days
                            hours = delta.seconds // 3600
                            minutes = (delta.seconds % 3600) // 60
                            if days > 0:
                                print(f"  Token expires in: {days} days, {hours} hours, {minutes} minutes")
                            elif hours > 0:
                                print(f"  Token expires in: {hours} hours, {minutes} minutes")
                            else:
                                print(f"  Token expires in: {minutes} minutes")
                        except Exception:
                            if result['expires_at']:
                                print(f"  Token expires at: {result['expires_at']}")

                    print(f"\n? No need to login. Using existing configuration.")
                    print(f"  Config file: {get_config_file_path()}")
                    print("\nUse 'doq login --force' to force re-login.")
                    print("Use 'doq login --update-auth' to update auth.json.")
                    return
                elif result['expired']:
                    print("??  Existing token found but it's EXPIRED.")
                    print("   Proceeding with login...")
                    print()
                elif not result['valid']:
                    print("??  Existing token found but it's INVALID.")
                    print("   Proceeding with login...")
                    print()
            except Exception as e:
                print(f"??  Error checking existing token: {e}")
                print("   Proceeding with login...")
                print()
    
    # Get URL (use default if not provided and config doesn't exist)
    if args.url:
        url = args.url
    elif config_exists():
        config = load_config()
        url = config.get('url') or default_url
    else:
        url = default_url
    
    # Get insecure mode (default True)
    insecure = args.insecure if args.insecure is not None else default_insecure
    
    # Get username
    if args.username:
        username = args.username
    else:
        username = input("Username: ")
    
    # Get password
    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Password: ")
    
    try:
        print(f"Logging in to {url}...")
        print(f"Insecure mode: {insecure}")
        
        # Login to get token
        token = login(url, username, password, insecure)
        
        # Ensure config directory exists
        ensure_config_dir()
        
        # Save configuration
        save_config(url, token, insecure, username)
        
        print(f"Login successful!")
        print(f"Configuration saved to {get_config_file_path()}")

        # Force update auth.json if --update-auth is specified, otherwise use normal bootstrap logic
        force_bootstrap = args.force or args.update_auth
        _bootstrap_auth_credentials(url, token, insecure, username, force_bootstrap)
    except Exception as e:
        print(f"Error logging in: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_check(args):
    """Check token validity and expiration with auth validation."""
    try:
        # First check if config exists
        if not config_exists():
            print("Error: Rancher configuration not found.", file=sys.stderr)
            print("Run 'doq login' to configure Rancher API access.", file=sys.stderr)
            sys.exit(1)

        # Check auth file validity
        validation = validate_auth_file()
        if not validation.get("valid", False):
            if _is_remote_auth_enabled():
                print("ℹ️  Auth file missing or incomplete (RANCHER_AUTH=true).", file=sys.stderr)
                print("   Some checks may be skipped. Run 'doq login' to bootstrap credentials.", file=sys.stderr)
                auth_data = None
            else:
                print("Error: ~/.doq/auth.json is missing or incomplete.", file=sys.stderr)
                message = validation.get("message")
                if message:
                    print(f"  Details: {message}", file=sys.stderr)
                missing = validation.get("missing_fields") or []
                if missing:
                    print(f"  Missing fields: {', '.join(missing)}", file=sys.stderr)
                print("Run 'doq login' to bootstrap credentials automatically.", file=sys.stderr)
                sys.exit(1)
        else:
            auth_data = load_auth_file()
        # Validate credentials if auth_data is available
        if auth_data:
            dockerhub_status = _validate_dockerhub_credentials(
                auth_data.get("DOCKERHUB_USER", ""),
                auth_data.get("DOCKERHUB_PASSWORD", ""),
            )
            bitbucket_status = _validate_bitbucket_credentials(
                auth_data.get("GIT_USER", ""),
                auth_data.get("GIT_PASSWORD", ""),
            )
        else:
            # Skip credential validation if auth_data is None (RANCHER_AUTH=true but no auth file)
            dockerhub_status = {"valid": False, "message": "Skipped (no auth data)"}
            bitbucket_status = {"valid": False, "message": "Skipped (no auth data)"}

        if args.json:
            import json
            output: Dict[str, Any] = {
                "auth": {
                    "dockerhub": dockerhub_status,
                    "bitbucket": bitbucket_status,
                }
            }
        else:
            print("Validating Docker Hub credentials...")
            if dockerhub_status["valid"]:
                print("  ✅ Docker Hub credentials are valid.")
            elif dockerhub_status["message"] == "Skipped (no auth data)":
                print(f"  ℹ️  {dockerhub_status['message']}")
            else:
                print(f"  ❌ {dockerhub_status['message']}", file=sys.stderr)
                sys.exit(1)

            print("Validating Bitbucket credentials...")
            if bitbucket_status["valid"]:
                print("  ✅ Bitbucket credentials are valid.")
            elif bitbucket_status["message"] == "Skipped (no auth data)":
                print(f"  ℹ️  {bitbucket_status['message']}")
            else:
                print(f"  ❌ {bitbucket_status['message']}", file=sys.stderr)
                sys.exit(1)

        # Get config
        config = load_config()
        if config is None:
            print("Error: Rancher configuration not found.", file=sys.stderr)
            print("Use 'doq login' to configure Rancher API access.", file=sys.stderr)
            sys.exit(1)
        url = args.url or config.get('url')
        token = args.token or config.get('token')
        insecure = args.insecure if args.insecure is not None else config.get('insecure', True)
        
        if not url or not token:
            print("Error: URL and token must be configured or provided", file=sys.stderr)
            print("Use 'doq login' to configure or provide --url and --token", file=sys.stderr)
            sys.exit(1)
        
        if args.json:
            token_result = check_token(url, token, insecure)
            output["token"] = token_result
            print(json.dumps(output, indent=2))
        else:
            print(f"Checking token for: {url}")
            print(f"Insecure mode: {insecure}")
            print()
            
            result = check_token(url, token, insecure)
            
            if result['valid']:
                print("? Token is VALID")
                
                # Display user information if available
                if result.get('username') or result.get('name') or result.get('user_id'):
                    print()
                    print("User Information:")
                    if result.get('username'):
                        print(f"  Username: {result['username']}")
                    if result.get('name'):
                        print(f"  Name: {result['name']}")
                    if result.get('user_id'):
                        print(f"  User ID: {result['user_id']}")
                
                if result['expires_at']:
                    from datetime import datetime
                    try:
                        exp_time = datetime.fromisoformat(result['expires_at'].replace('Z', '+00:00'))
                        now = datetime.now(exp_time.tzinfo)
                        
                        print()
                        if result['expired']:
                            print(f"? Token is EXPIRED")
                            print(f"  Expired at: {result['expires_at']}")
                            delta = now - exp_time
                            print(f"  Expired {delta.days} days ago")
                        else:
                            print(f"? Token is NOT expired")
                            print(f"  Expires at: {result['expires_at']}")
                            delta = exp_time - now
                            days = delta.days
                            hours = delta.seconds // 3600
                            minutes = (delta.seconds % 3600) // 60
                            if days > 0:
                                print(f"  Expires in: {days} days, {hours} hours, {minutes} minutes")
                            elif hours > 0:
                                print(f"  Expires in: {hours} hours, {minutes} minutes")
                            else:
                                print(f"  Expires in: {minutes} minutes")
                    except Exception as e:
                        print(f"  Expires at: {result['expires_at']}")
                        if result['expired']:
                            print(f"  Status: EXPIRED")
                        else:
                            print(f"  Status: Valid")
                else:
                    print("  Expiry information: Not available")
            else:
                print("? Token is INVALID")
                if result['error']:
                    print(f"  Error: {result['error']}")
                if result['expired']:
                    print("  Status: EXPIRED")
    except Exception as e:
        print(f"Error checking token: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_kube_config(args):
    """Get kubeconfig from project and save to ~/.kube/config."""
    import os
    import yaml
    from pathlib import Path
    
    try:
        api = RancherAPI()
        
        if not args.project_id:
            print("Error: project_id is required", file=sys.stderr)
            print("Usage: doq kube-config <project-id>", file=sys.stderr)
            sys.exit(1)
        
        project_id = args.project_id
        
        print(f"Getting kubeconfig for project: {project_id}")
        
        # Get kubeconfig from project
        # flatten defaults to True via set_defaults
        kubeconfig_content = api.get_kubeconfig_from_project(project_id, flatten=args.flatten)
        
        # Parse kubeconfig
        if isinstance(kubeconfig_content, str):
            kubeconfig_data = yaml.safe_load(kubeconfig_content)
        else:
            kubeconfig_data = kubeconfig_content
        
        # Ensure ~/.kube directory exists
        kube_dir = Path.home() / '.kube'
        kube_dir.mkdir(parents=True, exist_ok=True)
        kube_config_path = kube_dir / 'config'
        
        # Read existing config if exists
        existing_config = None
        if kube_config_path.exists() and not args.replace:
            try:
                with open(kube_config_path, 'r') as f:
                    existing_config = yaml.safe_load(f)
            except Exception as e:
                print(f"Warning: Could not read existing kubeconfig: {e}", file=sys.stderr)
                existing_config = None
        
        # Merge or replace config
        if existing_config and not args.replace:
            # Merge: add new context to existing config
            if 'clusters' not in existing_config:
                existing_config['clusters'] = []
            if 'users' not in existing_config:
                existing_config['users'] = []
            if 'contexts' not in existing_config:
                existing_config['contexts'] = []
            if 'current-context' not in existing_config:
                existing_config['current-context'] = ''
            
            # Add clusters from new config
            if 'clusters' in kubeconfig_data:
                for cluster in kubeconfig_data['clusters']:
                    # Check if cluster already exists
                    cluster_exists = any(
                        c.get('name') == cluster.get('name') 
                        for c in existing_config['clusters']
                    )
                    if not cluster_exists:
                        existing_config['clusters'].append(cluster)
            
            # Add users from new config
            if 'users' in kubeconfig_data:
                for user in kubeconfig_data['users']:
                    user_exists = any(
                        u.get('name') == user.get('name') 
                        for u in existing_config['users']
                    )
                    if not user_exists:
                        existing_config['users'].append(user)
            
            # Add contexts from new config
            if 'contexts' in kubeconfig_data:
                for context in kubeconfig_data['contexts']:
                    context_exists = any(
                        c.get('name') == context.get('name') 
                        for c in existing_config['contexts']
                    )
                    if not context_exists:
                        existing_config['contexts'].append(context)
                    else:
                        # Update existing context
                        for i, c in enumerate(existing_config['contexts']):
                            if c.get('name') == context.get('name'):
                                existing_config['contexts'][i] = context
                                break
            
            # Set current context if specified or if not set
            if args.set_context and 'contexts' in kubeconfig_data and kubeconfig_data['contexts']:
                existing_config['current-context'] = kubeconfig_data['contexts'][0].get('name')
            elif not existing_config['current-context'] and 'contexts' in kubeconfig_data and kubeconfig_data['contexts']:
                existing_config['current-context'] = kubeconfig_data['contexts'][0].get('name')
            
            final_config = existing_config
        else:
            # Replace: use new config as-is
            final_config = kubeconfig_data
        
        # Write config to file
        with open(kube_config_path, 'w') as f:
            yaml.dump(final_config, f, default_flow_style=False, sort_keys=False)
        
        # Set proper permissions
        os.chmod(kube_config_path, 0o600)
        
        print(f"? Kubeconfig saved to {kube_config_path}")
        
        if 'contexts' in final_config and final_config['contexts']:
            current_context = final_config.get('current-context', '')
            if current_context:
                print(f"? Current context: {current_context}")
            
            print(f"\nAvailable contexts:")
            for ctx in final_config['contexts']:
                ctx_name = ctx.get('name', '')
                marker = " (current)" if ctx_name == current_context else ""
                print(f"  - {ctx_name}{marker}")
        
    except Exception as e:
        print(f"Error getting kubeconfig: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_ns(args):
    """Switch kubectl context based on namespace format {project}-{env}."""
    ns_input = args.namespace
    
    print(f"?? Looking for context matching namespace: {ns_input}")
    selected_context = _switch_context_by_namespace(ns_input)
    
    if selected_context:
        print(f"? Switched to context: {selected_context}")
        
        # Verify current context
        import subprocess
        try:
            verify_result = subprocess.run(
                ['kubectl', 'config', 'current-context'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if verify_result.returncode == 0:
                current = verify_result.stdout.strip()
                if current == selected_context:
                    print(f"? Current context verified: {current}")
                else:
                    print(f"?? Warning: Expected context {selected_context}, but current is {current}")
        except Exception:
            pass
    else:
        sys.exit(1)


def _switch_context_by_namespace(ns_input, silent=False):
    """Helper function to switch kubectl context based on namespace format {project}-{env}.
    Returns the matched context name or None if failed.
    If silent=True, suppresses all output messages.
    """
    import subprocess
    import re
    import shutil
    
    # Parse format: {project}-{env}
    # Example: develop-saas -> env: develop, project: saas
    parts = ns_input.split('-', 1)
    if len(parts) != 2:
        if not silent:
            print(f"Error: Invalid namespace format. Expected format: {{project}}-{{env}}", file=sys.stderr)
            print(f"Example: develop-saas (where 'develop' is env and 'saas' is project)", file=sys.stderr)
        return None
    
    env, project = parts
    
    # Check if kubectl is available
    if not shutil.which('kubectl'):
        if not silent:
            print("Error: kubectl is not installed or not in PATH", file=sys.stderr)
            print("Please install kubectl first: https://kubernetes.io/docs/tasks/tools/", file=sys.stderr)
        return None
    
    # Get list of contexts
    try:
        result = subprocess.run(
            ['kubectl', 'config', 'get-contexts', '-o', 'name'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            if not silent:
                print(f"Error getting contexts: {result.stderr}", file=sys.stderr)
            return None
        
        contexts = [ctx.strip() for ctx in result.stdout.strip().split('\n') if ctx.strip()]
        
        if not contexts:
            if not silent:
                print("Error: No contexts found in kubectl config", file=sys.stderr)
            return None
        
        # Search for context matching env using regex
        # Pattern: look for env in context name (case-insensitive)
        # Examples: rke2-develop-qoin matches "develop"
        pattern = re.compile(rf'\b{re.escape(env)}\b', re.IGNORECASE)
        matched_contexts = [ctx for ctx in contexts if pattern.search(ctx)]
        
        if not matched_contexts:
            if not silent:
                print(f"?? No context found matching env '{env}'")
                print(f"\nAvailable contexts:")
                for ctx in contexts:
                    print(f"  - {ctx}")
                print(f"\nSuggestion: Check if env '{env}' exists in any context name")
            return None
        
        # If multiple matches, prefer exact match or first match
        exact_match = None
        for ctx in matched_contexts:
            if env.lower() in ctx.lower():
                exact_match = ctx
                break
        
        selected_context = exact_match if exact_match else matched_contexts[0]
        
        # Switch to selected context
        result = subprocess.run(
            ['kubectl', 'config', 'use-context', selected_context],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            if not silent:
                print(f"Error switching context: {result.stderr}", file=sys.stderr)
            return None
        
        return selected_context
        
    except subprocess.TimeoutExpired:
        if not silent:
            print("Error: kubectl command timed out", file=sys.stderr)
        return None
    except Exception as e:
        if not silent:
            print(f"Error: {e}", file=sys.stderr)
        return None


def _execute_kubectl_get_resource(namespace: str, resource_type: str, resource_name: str = None, 
                                  error_not_found_msg: str = None, post_process_fn=None) -> None:
    """Execute kubectl get command for a resource and output JSON.
    
    Args:
        namespace: Kubernetes namespace
        resource_type: Resource type (e.g., 'configmap', 'secret', 'service', 'deployment')
        resource_name: Resource name (None for listing all)
        error_not_found_msg: Custom error message when resource not found
        post_process_fn: Optional function to process JSON data before output (takes dict, returns dict)
    """
    import subprocess
    import shutil
    import json
    
    # Ensure context is correct (silently)
    selected_context = _switch_context_by_namespace(namespace, silent=True)
    
    if not selected_context:
        print(json.dumps({"error": "Failed to switch to correct context"}, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Check if kubectl is available
    if not shutil.which('kubectl'):
        print(json.dumps({"error": "kubectl is not installed or not in PATH"}, indent=2), file=sys.stderr)
        sys.exit(1)
    
    # Build kubectl command
    cmd = ['kubectl', f'-n={namespace}', 'get', resource_type]
    if resource_name:
        cmd.append(resource_name)
    cmd.extend(['-o', 'json'])
    
    # Execute kubectl command
    try:
        get_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if get_result.returncode != 0:
            if error_not_found_msg:
                error_msg = error_not_found_msg
            else:
                resource_display = f"{resource_type} '{resource_name}'" if resource_name else resource_type
                error_msg = f"{resource_display} not found in namespace '{namespace}'"
            
            error_output = {
                "error": error_msg,
                "stderr": get_result.stderr.strip() if get_result.stderr else None
            }
            print(json.dumps(error_output, indent=2))
            sys.exit(1)
        
        # Parse JSON
        resource_data = json.loads(get_result.stdout)
        
        # Apply post-processing if provided
        if post_process_fn:
            resource_data = post_process_fn(resource_data)
        
        # Output JSON
        print(json.dumps(resource_data, indent=2))
        
    except json.JSONDecodeError:
        error_output = {"error": f"Failed to parse {resource_type} JSON"}
        print(json.dumps(error_output, indent=2), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_output = {"error": str(e)}
        print(json.dumps(error_output, indent=2), file=sys.stderr)
        sys.exit(1)


def cmd_get_cm(args):
    """Get configmap resource information in JSON format."""
    _execute_kubectl_get_resource(
        namespace=args.namespace,
        resource_type='configmap',
        resource_name=args.configmap,
        error_not_found_msg=f"ConfigMap '{args.configmap}' not found in namespace '{args.namespace}'"
    )


def cmd_get_secret(args):
    """Get secret resource information in JSON format with base64 decoded values."""
    import base64
    
    def decode_secret_data(secret_data):
        """Post-process function to decode base64 values in secret data."""
        if 'data' in secret_data and secret_data['data']:
            decoded_data = {}
            for key, value in secret_data['data'].items():
                try:
                    decoded_value = base64.b64decode(value).decode('utf-8')
                    decoded_data[key] = decoded_value
                except Exception:
                    # If decoding fails, keep original value
                    decoded_data[key] = value
            
            # Replace data with decoded values
            secret_data['data'] = decoded_data
            # Add note that data is decoded
            if 'annotations' not in secret_data['metadata']:
                secret_data['metadata']['annotations'] = {}
            secret_data['metadata']['annotations']['_doq.decoded'] = 'true'
        return secret_data
    
    _execute_kubectl_get_resource(
        namespace=args.namespace,
        resource_type='secret',
        resource_name=args.secret,
        error_not_found_msg=f"Secret '{args.secret}' not found in namespace '{args.namespace}'",
        post_process_fn=decode_secret_data
    )


def cmd_get_svc(args):
    """Get service resource information in JSON format."""
    _execute_kubectl_get_resource(
        namespace=args.namespace,
        resource_type='service',
        resource_name=args.service,
        error_not_found_msg=f"Service '{args.service}' not found in namespace '{args.namespace}'"
    )


def cmd_get_deploy(args):
    """Get deployment resource information in JSON format."""
    import json
    
    ns = args.namespace
    deployment = args.deployment
    
    # Special handling for --name flag
    if args.name:
        if deployment:
            # If specific deployment is provided, just return the name
            print(json.dumps([deployment], indent=2))
            return
        
        # List all deployment names
        def extract_names(deployments_data):
            """Post-process function to extract only deployment names."""
            deployment_names = []
            if 'items' in deployments_data:
                for item in deployments_data['items']:
                    if 'metadata' in item and 'name' in item['metadata']:
                        deployment_names.append(item['metadata']['name'])
            return deployment_names
        
        _execute_kubectl_get_resource(
            namespace=ns,
            resource_type='deployments',
            resource_name=None,
            error_not_found_msg=f"Failed to get deployments from namespace '{ns}'",
            post_process_fn=extract_names
        )
        return
    
    # Regular get deployment(s)
    if not deployment:
        # List all deployments
        _execute_kubectl_get_resource(
            namespace=ns,
            resource_type='deployments',
            resource_name=None,
            error_not_found_msg=f"Failed to get deployments from namespace '{ns}'"
        )
    else:
        # Get specific deployment
        _execute_kubectl_get_resource(
            namespace=ns,
            resource_type='deployment',
            resource_name=deployment,
            error_not_found_msg=f"Deployment '{deployment}' not found in namespace '{ns}'"
        )


def _get_deployment_containers(namespace: str, deployment: str, silent: bool = False):
    """Get container information from a deployment.
    
    Args:
        namespace: Kubernetes namespace
        deployment: Deployment name
        silent: If True, suppress verbose output
        
    Returns:
        Tuple of (deployment_data dict, containers list, selected_context str)
        
    Raises:
        SystemExit: If deployment not found or containers not available
    """
    import subprocess
    import shutil
    import json
    
    # Ensure context is correct
    selected_context = _switch_context_by_namespace(namespace, silent=silent)
    
    if not selected_context:
        if not silent:
            print("Error: Failed to switch to correct context", file=sys.stderr)
        sys.exit(1)
    
    # Check if kubectl is available
    if not shutil.which('kubectl'):
        if not silent:
            print("Error: kubectl is not installed or not in PATH", file=sys.stderr)
            print("Please install kubectl first: https://kubernetes.io/docs/tasks/tools/", file=sys.stderr)
        sys.exit(1)
    
    # Get deployment information
    try:
        get_result = subprocess.run(
            ['kubectl', f'-n={namespace}', 'get', 'deployment', deployment, '-o', 'json'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if get_result.returncode != 0:
            if get_result.stderr and not silent:
                print(f"Error getting deployment: {get_result.stderr}", file=sys.stderr)
            if not silent:
                print(f"Error: Deployment '{deployment}' not found in namespace '{namespace}'", file=sys.stderr)
            sys.exit(1)
        
        # Parse deployment JSON to get containers
        deployment_data = json.loads(get_result.stdout)
        containers = deployment_data.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
        
        if not containers:
            if not silent:
                print("Error: No containers found in deployment", file=sys.stderr)
            sys.exit(1)
        
        return deployment_data, containers, selected_context
        
    except json.JSONDecodeError:
        if not silent:
            print("Error: Failed to parse deployment JSON", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        if not silent:
            print(f"Error getting deployment info: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_get_image(args):
    """Get current image information for deployment in namespace."""
    import json
    
    ns = args.namespace
    deployment = args.deployment
    
    # Get deployment containers
    deployment_data, containers, selected_context = _get_deployment_containers(ns, deployment, silent=True)
    
    # Extract image information with tag version
    images_info = []
    for container in containers:
        image_full = container.get('image', 'unknown')
        
        # Parse image to extract tag version
        # Format: registry/namespace/repo:tag or namespace/repo:tag or repo:tag
        if ':' in image_full:
            image_base, tag = image_full.rsplit(':', 1)
        else:
            image_base = image_full
            tag = 'latest'
        
        images_info.append({
            'container': container.get('name', 'unknown'),
            'image': image_full,
            'tag': tag
        })
    
    # Always output as JSON (silent mode)
    output = {
        'namespace': ns,
        'deployment': deployment,
        'context': selected_context,
        'containers': images_info
    }
    print(json.dumps(output, indent=2))


def cmd_set_image(args):
    """Set image for deployment in namespace."""
    import subprocess
    import shutil
    
    ns = args.namespace
    deployment = args.deployment
    image = args.image
    
    print(f"?? Setting image for deployment '{deployment}' in namespace '{ns}'")
    print(f"   Image: {image}")
    
    # First, ensure context is correct
    print(f"\n?? Ensuring correct context for namespace '{ns}'...")
    selected_context = _switch_context_by_namespace(ns)
    
    if not selected_context:
        print("Error: Failed to switch to correct context", file=sys.stderr)
        sys.exit(1)
    
    print(f"? Context verified: {selected_context}")
    
    # Check if kubectl is available
    if not shutil.which('kubectl'):
        print("Error: kubectl is not installed or not in PATH", file=sys.stderr)
        print("Please install kubectl first: https://kubernetes.io/docs/tasks/tools/", file=sys.stderr)
        sys.exit(1)
    
    # Get container name(s) from deployment
    print(f"\n?? Getting container information from deployment '{deployment}'...")
    deployment_data, containers, _ = _get_deployment_containers(ns, deployment, silent=False)
    
    container_names = [c.get('name') for c in containers if c.get('name')]
    
    if not container_names:
        print("Error: Could not determine container names from deployment", file=sys.stderr)
        sys.exit(1)
    
    # Use first container if multiple containers exist
    container_name = container_names[0]
    
    if len(container_names) > 1:
        print(f"?? Multiple containers found: {', '.join(container_names)}")
        print(f"   Using first container: {container_name}")
    else:
        print(f"? Container name: {container_name}")
    
    # Execute kubectl set image command
    # kubectl -n=${ns} set image deployment/${deploy} ${container_name}=${image}
    print(f"\n?? Executing: kubectl -n={ns} set image deployment/{deployment} {container_name}={image}")
    
    try:
        # Run kubectl command and capture output for better error handling
        result = subprocess.run(
            ['kubectl', f'-n={ns}', 'set', 'image', f'deployment/{deployment}', f'{container_name}={image}'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Print stdout if available
        if result.stdout:
            print(result.stdout)
        
        if result.returncode != 0:
            if result.stderr:
                print(f"Error: {result.stderr}", file=sys.stderr)
            print(f"Error setting image (exit code: {result.returncode})", file=sys.stderr)
            sys.exit(1)
        
        print(f"\n? Image updated successfully!")
        print(f"   Namespace: {ns}")
        print(f"   Deployment: {deployment}")
        print(f"   Container: {container_name}")
        print(f"   Image: {image}")
        
    except subprocess.TimeoutExpired:
        print("Error: kubectl command timed out", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_set_image_yaml(args):
    """Update image reference inside YAML file in Bitbucket repo."""
    repo = args.repo
    refs = args.refs
    yaml_path = args.yaml_path
    image = args.image
    dry_run = args.dry_run

    if not repo or not refs or not yaml_path or not image:
        print("Error: repo, refs, yaml_path, dan image wajib diisi", file=sys.stderr)
        sys.exit(1)

    print("?? Updating image in YAML file")
    print(f"   Repository : {repo}")
    print(f"   Branch     : {refs}")
    print(f"   YAML Path  : {yaml_path}")
    print(f"   New Image  : {image}")

    try:
        result = update_image_in_repo(repo, refs, yaml_path, image, dry_run=dry_run)

        if result.get('success'):
            if result.get('skipped'):
                # Image sudah sesuai, skip update
                print(f"✅ {result.get('message')}")
                return
            elif dry_run:
                print("✅ Perubahan sukses (dry-run). Tidak ada push dilakukan.")
            else:
                print("✅ Image berhasil diperbarui dan dipush.")
                commit_info = result.get('commit')
                if commit_info:
                    print(commit_info)
        else:
            print(f"⚠️  {result.get('message')}")
            sys.exit(1)

    except ImageUpdateError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error tidak terduga: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_check_update(args):
    """Check if there are updates available."""
    try:
        update_info = check_for_updates()
        current_version = get_version()
        
        if args.json:
            import json
            output = {
                'has_update': update_info['has_update'],
                'current_hash': update_info['current_hash'],
                'latest_hash': update_info['latest_hash'],
                'installed_at': current_version.get('installed_at', 'unknown'),
                'error': update_info.get('error')
            }
            print(json.dumps(output, indent=2))
            return
        
        print("?? Checking for updates...")
        print("=" * 50)
        print(f"Current version: {update_info['current_hash']}")
        print(f"Installed at: {current_version.get('installed_at', 'unknown')}")
        
        if update_info.get('error'):
            print(f"\n?? Error: {update_info['error']}")
            return
        
        if update_info['latest_hash']:
            print(f"Latest version: {update_info['latest_hash']}")
        
        if update_info['has_update']:
            print("\n? Update tersedia!")
            print(f"   Current: {update_info['current_hash'][:8]}...")
            print(f"   Latest:  {update_info['latest_hash'][:8]}...")
            print("\nGunakan command berikut untuk update:")
            print(f"   doq update {update_info['latest_hash']}")
            print("\nAtau update otomatis ke latest:")
            print("   doq update --latest")
        else:
            print("\n? Sudah menggunakan versi terbaru!")
            print(f"   Commit: {update_info['current_hash']}")
        
    except Exception as e:
        print(f"Error checking for updates: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_update(args):
    """Update DevOps Q from GitHub repository."""
    import subprocess
    import shutil
    import tempfile
    from pathlib import Path
    
    # Get current version info
    current_version = get_version()
    repo_url = current_version.get('repo_url', "https://github.com/mamatnurahmat/devops-tools")
    
    # Determine branch: CLI arg > version.json > default "main"
    if args.branch:
        branch = args.branch
        print(f"🔀 Using branch from CLI argument: {branch}")
    else:
        branch = current_version.get('branch', "main")
        print(f"🔀 Using branch from version.json: {branch}")
    
    # Determine commit hash
    if args.latest:
        commit_hash = get_latest_commit_hash(branch)
        if not commit_hash:
            print(f"Error: Tidak dapat mengambil latest commit hash dari branch '{branch}'", file=sys.stderr)
            sys.exit(1)
    elif args.commit_hash:
        commit_hash = args.commit_hash
    else:
        # If no commit hash provided, check current version and update to latest
        print("🔍 Checking current version...")
        current_hash = current_version.get('commit_hash', 'unknown')
        
        # Get latest commit hash from the specified branch
        latest_hash = get_latest_commit_hash(branch)
        if not latest_hash:
            print(f"Error: Tidak dapat mengambil latest commit hash dari branch '{branch}'", file=sys.stderr)
            sys.exit(1)
        
        # Get current branch for comparison
        current_branch = current_version.get('branch', 'main')
        
        # If switching branch, always update
        if args.branch and args.branch != current_branch:
            print(f"\n🔀 Switching branch: {current_branch} → {branch}")
            print(f"   Latest commit on '{branch}': {latest_hash[:8]}...")
            print(f"   Will update to new branch...\n")
            commit_hash = latest_hash
        # If same branch, compare commit hashes
        elif current_hash != 'unknown' and current_hash == latest_hash:
            print("✅ Sudah menggunakan versi terbaru!")
            print(f"   Branch: {branch}")
            print(f"   Current version: {current_hash[:8]}...")
            print(f"   Latest version:  {latest_hash[:8]}...")
            print(f"   Installed at:    {current_version.get('installed_at', 'unknown')}")
            print("\nTidak ada update yang diperlukan.")
            return
        # Update to latest
        else:
            if current_hash != 'unknown':
                print(f"\n📢 Update tersedia!")
                print(f"   Branch: {branch}")
                print(f"   Current version: {current_hash[:8]}...")
                print(f"   Latest version:  {latest_hash[:8]}...")
                print(f"   Will update to latest version...\n")
            else:
                print(f"\n📢 Will update to latest version: {latest_hash[:8]}...")
                print(f"   Branch: {branch}\n")
            commit_hash = latest_hash
    
    # Check if git is available
    if not shutil.which('git'):
        print("Error: git is not installed or not in PATH", file=sys.stderr)
        print("Please install git first: https://git-scm.com/downloads", file=sys.stderr)
        sys.exit(1)
    
    # Create temporary directory for cloning
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix='doq-update-')
        print(f"\n?? Cloning repository from {repo_url}...")
        print(f"   Branch: {branch}")
        print(f"   Commit: {commit_hash}")
        
        # Clone repository
        clone_cmd = ['git', 'clone', '--branch', branch, '--single-branch', repo_url, temp_dir]
        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error cloning repository: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        print("? Repository cloned successfully")
        
        # Checkout to specific commit
        print(f"?? Checking out commit {commit_hash}...")
        checkout_cmd = ['git', '-C', temp_dir, 'checkout', commit_hash]
        result = subprocess.run(checkout_cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Error checking out commit: {result.stderr}", file=sys.stderr)
            print(f"Commit {commit_hash} may not exist in branch {branch}", file=sys.stderr)
            sys.exit(1)
        
        print("? Commit checked out successfully")
        
        # Check if install.sh exists
        install_script = Path(temp_dir) / 'install.sh'
        if not install_script.exists():
            print(f"Error: install.sh not found in repository", file=sys.stderr)
            sys.exit(1)
        
        # Run installer
        print("\n?? Running installer...")
        print("=" * 50)
        
        # Make install.sh executable
        install_script.chmod(0o755)
        
        # Run installer script
        install_cmd = ['bash', str(install_script)]
        result = subprocess.run(install_cmd, cwd=temp_dir)
        
        if result.returncode != 0:
            print(f"\nError running installer (exit code: {result.returncode})", file=sys.stderr)
            sys.exit(1)
        
        # Save version after successful update (preserve branch)
        save_version(commit_hash, branch)
        
        print("\n" + "=" * 50)
        print("? Update completed successfully!")
        print(f"   Branch: {branch}")
        print(f"   Commit: {commit_hash}")
        
    except KeyboardInterrupt:
        print("\n\nUpdate cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during update: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up temporary directory
        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"\n?? Cleaned up temporary files")
            except Exception:
                pass


def cmd_version(args):
    """Show installed version information."""
    try:
        version_info = get_version()
        
        if args.json:
            import json
            print(json.dumps(version_info, indent=2))
            return
        
        print("?? DevOps Q Version Information")
        print("=" * 50)
        print(f"Commit Hash: {version_info.get('commit_hash', 'unknown')}")
        print(f"Installed At: {version_info.get('installed_at', 'unknown')}")
        print(f"Repository: {version_info.get('repo_url', 'unknown')}")
        print(f"Branch: {version_info.get('branch', 'unknown')}")
        
    except Exception as e:
        print(f"Error getting version: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config(args):
    """Configure Rancher API settings."""
    if args.url or args.token:
        url = args.url or ''
        token = args.token or ''
        insecure = args.insecure if args.insecure is not None else True
        
        # Load existing config to preserve values not being updated
        config = load_config()
        url = url or config['url']
        token = token or config['token']
        
        if not url or not token:
            print("Error: URL and token are required", file=sys.stderr)
            sys.exit(1)
        
        save_config(url, token, insecure)
        print(f"Configuration saved to {get_config_file_path()}")
    else:
        # Show current config
        config = load_config()
        print(f"Config file: {get_config_file_path()}")
        print(f"URL: {config['url'] or '(not set)'}")
        print(f"Token: {'*' * len(config['token']) if config['token'] else '(not set)'}")
        print(f"Insecure: {config['insecure']}")


def _detect_ref_type(repo, ref, git_user, git_password):
    """Detect if ref is a tag or branch and return commit hash."""
    # Try branch first
    try:
        branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches/{ref}"
        resp = requests.get(branch_url, auth=(git_user, git_password), timeout=30)
        if resp.status_code == 200:
            branch_data = resp.json()
            commit_hash = branch_data['target']['hash']
            return {'type': 'branch', 'commit_hash': commit_hash}
    except Exception:
        pass
    
    # Try tag
    try:
        tag_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/tags/{ref}"
        resp = requests.get(tag_url, auth=(git_user, git_password), timeout=30)
        if resp.status_code == 200:
            tag_data = resp.json()
            commit_hash = tag_data['target']['hash']
            return {'type': 'tag', 'commit_hash': commit_hash}
    except Exception:
        pass
    
    return None


def _get_branches_for_commit(repo, commit_hash, git_user, git_password):
    """Get branches that contain the specified commit."""
    try:
        branches_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/commit/{commit_hash}/branches"
        resp = requests.get(branches_url, auth=(git_user, git_password), timeout=30)
        if resp.status_code == 200:
            branches_data = resp.json()
            branches = branches_data.get('values', [])
            # Extract branch names
            branch_names = [b.get('name', '') for b in branches if b.get('name')]
            return branch_names
    except Exception:
        pass
    
    return []


def _format_commit_date(commit_date):
    """Format commit date from ISO format to readable format."""
    if not commit_date:
        return 'Unknown date'
    
    try:
        from datetime import datetime
        # Parse ISO format date
        if 'T' in commit_date:
            if commit_date.endswith('Z'):
                commit_date = commit_date.replace('Z', '+00:00')
            dt = datetime.fromisoformat(commit_date)
            return dt.strftime('%a %b %d %H:%M:%S %Y %z')
        else:
            return commit_date
    except Exception:
        return commit_date


def _extract_author_info(author_info):
    """Extract author name and email from author info."""
    author_name = None
    author_email = None
    
    # Try to get from author.user object first
    if 'user' in author_info and author_info['user']:
        author_name = author_info['user'].get('display_name') or author_info['user'].get('username')
        author_email = author_info['user'].get('email')
    
    # Fallback to author.raw if available (format: "Name <email>")
    if not author_name and 'raw' in author_info:
        raw_author = author_info['raw']
        if '<' in raw_author and '>' in raw_author:
            # Parse "Name <email>" format
            parts = raw_author.split('<', 1)
            author_name = parts[0].strip()
            author_email = parts[1].rstrip('>').strip()
        else:
            author_name = raw_author.strip()
    
    return author_name, author_email


def _format_commit_json(commit_data, commit_id=None, branch=None):
    """Format commit data as JSON."""
    commit_hash = commit_data.get('hash', commit_id or 'unknown')
    author_info = commit_data.get('author', {})
    author_name, author_email = _extract_author_info(author_info)
    commit_date = commit_data.get('date', '')
    formatted_date = _format_commit_date(commit_date)
    commit_message = commit_data.get('message', '').strip()
    
    result = {
        'commit': commit_hash,
        'author': {
            'name': author_name or 'Unknown',
            'email': author_email or None
        },
        'date': formatted_date,
        'message': commit_message or '(no commit message)'
    }
    
    if branch:
        result['branch'] = branch
    
    return result


def _display_single_commit(commit_data, commit_id=None, json_output=False, branch=None):
    """Display single commit information."""
    if json_output:
        output = _format_commit_json(commit_data, commit_id, branch)
        print(json.dumps(output, indent=2))
        return
    
    commit_hash = commit_data.get('hash', commit_id or 'unknown')
    author_info = commit_data.get('author', {})
    author_name, author_email = _extract_author_info(author_info)
    commit_date = commit_data.get('date', '')
    formatted_date = _format_commit_date(commit_date)
    commit_message = commit_data.get('message', '').strip()
    
    print(f"commit {commit_hash}")
    if branch:
        print(f"Branch: {branch}")
    if author_name:
        if author_email:
            print(f"Author: {author_name} <{author_email}>")
        else:
            print(f"Author: {author_name}")
    else:
        print("Author: Unknown")
    
    print(f"Date:   {formatted_date}")
    print()
    if commit_message:
        # Split message into lines and display
        for line in commit_message.split('\n'):
            print(f"    {line}")
    else:
        print("    (no commit message)")


def cmd_commit(args):
    """Display commit information from Bitbucket repository."""
    repo = args.repo
    ref = args.ref
    commit_id = args.commit_id
    
    if not repo or not ref:
        print("Error: Repository name and refs (branch/tag) are required", file=sys.stderr)
        print("Usage: doq commit <repo> <ref> [commit_id]", file=sys.stderr)
        sys.exit(1)

    try:
        # Load authentication
        try:
            auth_data = load_auth_file()
            if auth_data is None:
                print("❌ Error: Authentication required but not available.", file=sys.stderr)
                if _is_remote_auth_enabled():
                    print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
                else:
                    print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            if _is_remote_auth_enabled():
                print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
            else:
                print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading authentication: {e}", file=sys.stderr)
            sys.exit(1)

        git_user = auth_data.get('GIT_USER', '')
        git_password = auth_data.get('GIT_PASSWORD', '')

        if not git_user or not git_password:
            print("❌ Error: GIT_USER and GIT_PASSWORD required in ~/.doq/auth.json", file=sys.stderr)
            sys.exit(1)
        
        if commit_id:
            # Display single commit
            commit_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/commit/{commit_id}"
            
            try:
                resp = requests.get(commit_url, auth=(git_user, git_password), timeout=30)
                
                if resp.status_code == 404:
                    print(f"❌ Error: Commit '{commit_id}' not found in repository '{repo}'", file=sys.stderr)
                    print(f"   Check if commit ID is correct and exists in the repository", file=sys.stderr)
                    sys.exit(1)
                
                resp.raise_for_status()
                commit_data = resp.json()
                
                # If ref is a tag, get branch information
                branch = None
                if ref:
                    ref_info = _detect_ref_type(repo, ref, git_user, git_password)
                    if ref_info and ref_info['type'] == 'tag':
                        # Get branches that contain this commit
                        branches = _get_branches_for_commit(repo, commit_data.get('hash', commit_id), git_user, git_password)
                        if branches:
                            branch = branches[0]  # Use first branch found
                
                _display_single_commit(commit_data, commit_id, json_output=args.json, branch=branch)
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error fetching commit information: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            # Display last 5 commits
            # First detect if ref is tag or branch
            ref_info = _detect_ref_type(repo, ref, git_user, git_password)
            
            if not ref_info:
                print(f"❌ Error: Branch/tag '{ref}' not found in repository '{repo}'", file=sys.stderr)
                print(f"   Check if branch/tag name is correct", file=sys.stderr)
                sys.exit(1)
            
            # If tag, get commit hash and use it to get commits
            if ref_info['type'] == 'tag':
                # Get commit details for the tag
                commit_hash = ref_info['commit_hash']
                commit_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/commit/{commit_hash}"
                
                try:
                    resp = requests.get(commit_url, auth=(git_user, git_password), timeout=30)
                    resp.raise_for_status()
                    commit_data = resp.json()
                    
                    # Get branches that contain this commit
                    branches = _get_branches_for_commit(repo, commit_hash, git_user, git_password)
                    branch = branches[0] if branches else None
                    
                    if args.json:
                        output = _format_commit_json(commit_data, commit_hash, branch)
                        print(json.dumps(output, indent=2))
                    else:
                        _display_single_commit(commit_data, commit_hash, json_output=False, branch=branch)
                    
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error fetching commit information: {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                # It's a branch, show last 5 commits
                commits_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/commits/{ref}"
                
                try:
                    resp = requests.get(
                        commits_url,
                        auth=(git_user, git_password),
                        params={'pagelen': 5},
                        timeout=30
                    )
                    
                    if resp.status_code == 404:
                        print(f"❌ Error: Branch '{ref}' not found in repository '{repo}'", file=sys.stderr)
                        print(f"   Check if branch name is correct", file=sys.stderr)
                        sys.exit(1)
                    
                    resp.raise_for_status()
                    commits_data = resp.json()
                    commits = commits_data.get('values', [])
                    
                    if not commits:
                        if args.json:
                            print(json.dumps({'commits': []}, indent=2))
                        else:
                            print(f"No commits found for '{ref}' in repository '{repo}'")
                        return
                    
                    if args.json:
                        # Format as JSON array
                        commits_json = []
                        for commit_data in commits:
                            commits_json.append(_format_commit_json(commit_data))
                        print(json.dumps({'commits': commits_json}, indent=2))
                    else:
                        print(f"Last 5 commits on '{ref}':")
                        print("=" * 70)
                        
                        for i, commit_data in enumerate(commits, 1):
                            commit_hash = commit_data.get('hash', 'unknown')
                            short_hash = commit_hash[:7] if len(commit_hash) >= 7 else commit_hash
                            author_info = commit_data.get('author', {})
                            author_name, author_email = _extract_author_info(author_info)
                            commit_date = commit_data.get('date', '')
                            formatted_date = _format_commit_date(commit_date)
                            commit_message = commit_data.get('message', '').strip()
                            # Get first line of commit message
                            first_line = commit_message.split('\n')[0] if commit_message else '(no commit message)'
                            
                            print(f"\n[{i}] {short_hash} - {first_line}")
                            if author_name:
                                author_display = f"{author_name} <{author_email}>" if author_email else author_name
                                print(f"     Author: {author_display}")
                            else:
                                print(f"     Author: Unknown")
                            print(f"     Date:   {formatted_date}")
                        
                        print("\n" + "=" * 70)
                        print(f"Use 'doq commit {repo} {ref} <commit_id>' to view full details of a commit")
                    
                except requests.exceptions.RequestException as e:
                    print(f"❌ Error fetching commits: {e}", file=sys.stderr)
                    sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n❌ Command cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_create_branch(args):
    """Create a new branch in Bitbucket repository from source branch."""
    repo = args.repo
    src_branch = args.src_branch
    dest_branch = args.dest_branch
    
    if not repo or not src_branch or not dest_branch:
        print("Error: Repository name, source branch, and destination branch are required", file=sys.stderr)
        print("Usage: doq create-branch <repo> <src_branch> <dest_branch>", file=sys.stderr)
        sys.exit(1)

    try:
        # Load authentication
        try:
            auth_data = load_auth_file()
            if auth_data is None:
                print("❌ Error: Authentication required but not available.", file=sys.stderr)
                if _is_remote_auth_enabled():
                    print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
                else:
                    print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            if _is_remote_auth_enabled():
                print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
            else:
                print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading authentication: {e}", file=sys.stderr)
            sys.exit(1)

        git_user = auth_data.get('GIT_USER', '')
        git_password = auth_data.get('GIT_PASSWORD', '')

        if not git_user or not git_password:
            print("❌ Error: GIT_USER and GIT_PASSWORD required in ~/.doq/auth.json", file=sys.stderr)
            sys.exit(1)
        
        print(f"🔍 Creating branch '{dest_branch}' from '{src_branch}' in repository '{repo}'...")
        
        # Step 1: Validate source branch exists and get commit hash
        src_branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches/{src_branch}"
        
        try:
            resp = requests.get(src_branch_url, auth=(git_user, git_password), timeout=30)
            
            if resp.status_code == 404:
                print(f"❌ Error: Source branch '{src_branch}' not found in repository '{repo}'", file=sys.stderr)
                print(f"   Check if branch name is correct", file=sys.stderr)
                sys.exit(1)
            
            resp.raise_for_status()
            src_branch_data = resp.json()
            src_commit_hash = src_branch_data['target']['hash']
            short_hash = src_commit_hash[:7] if len(src_commit_hash) >= 7 else src_commit_hash
            
            print(f"✅ Source branch '{src_branch}' found (commit: {short_hash})")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching source branch: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Step 2: Check if destination branch already exists
        dest_branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches/{dest_branch}"
        
        try:
            resp = requests.get(dest_branch_url, auth=(git_user, git_password), timeout=30)
            
            if resp.status_code == 200:
                print(f"❌ Error: Destination branch '{dest_branch}' already exists in repository '{repo}'", file=sys.stderr)
                print(f"   Use a different branch name or delete the existing branch first", file=sys.stderr)
                sys.exit(1)
            elif resp.status_code != 404:
                # If it's not 404, there might be another error
                resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            # If error is not 404, it's a real error
            if "404" not in str(e):
                print(f"❌ Error checking destination branch: {e}", file=sys.stderr)
                sys.exit(1)
        
        # Step 3: Create new branch
        create_branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches"
        branch_data = {
            "name": dest_branch,
            "target": {
                "hash": src_commit_hash
            }
        }
        
        try:
            resp = requests.post(
                create_branch_url,
                auth=(git_user, git_password),
                json=branch_data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if resp.status_code == 201:
                created_branch = resp.json()
                created_hash = created_branch.get('target', {}).get('hash', src_commit_hash)
                created_short_hash = created_hash[:7] if len(created_hash) >= 7 else created_hash
                
                print(f"✅ Branch '{dest_branch}' created successfully!")
                print(f"   Repository: {repo}")
                print(f"   Source branch: {src_branch}")
                print(f"   Commit: {created_short_hash}")
            elif resp.status_code == 409:
                # Conflict - branch might already exist
                error_data = resp.json()
                error_msg = error_data.get('error', {}).get('message', 'Branch already exists')
                print(f"❌ Error: {error_msg}", file=sys.stderr)
                print(f"   Branch '{dest_branch}' might already exist", file=sys.stderr)
                sys.exit(1)
            else:
                resp.raise_for_status()
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error creating branch: {e}", file=sys.stderr)
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', {}).get('message', str(e))
                    print(f"   Details: {error_msg}", file=sys.stderr)
                except Exception:
                    pass
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n❌ Command cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pull_request(args):
    """Create a pull request in Bitbucket repository from source branch to destination branch."""
    repo = args.repo
    src_branch = args.src_branch
    dest_branch = args.dest_branch
    delete_after_merge = args.delete if hasattr(args, 'delete') else False
    webhook_url = resolve_teams_webhook(getattr(args, 'webhook', None))
    
    result: Dict[str, Any] = {
        'repository': repo,
        'source': src_branch,
        'destination': dest_branch,
        'delete_after_merge': delete_after_merge,
        'pr_url': '',
        'message': '',
        'success': False
    }
    
    exit_code = 1
    
    try:
        while True:
            if not repo or not src_branch or not dest_branch:
                print("Error: Repository name, source branch, and destination branch are required", file=sys.stderr)
                print("Usage: doq pull-request <repo> <src_branch> <dest_branch> [--delete]", file=sys.stderr)
                result['message'] = 'Missing required arguments'
                break

            try:
                auth_data = load_auth_file()
                if auth_data is None:
                    print("❌ Error: Authentication required but not available.", file=sys.stderr)
                    if _is_remote_auth_enabled():
                        print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
                    else:
                        print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
                    result['message'] = 'Authentication required but not available'
                    break
            except FileNotFoundError as e:
                print(f"❌ Error: {e}", file=sys.stderr)
                if _is_remote_auth_enabled():
                    print("   Run 'doq login' to fetch credentials from auth-api.", file=sys.stderr)
                else:
                    print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
                result['message'] = str(e)
                break
            except Exception as e:
                print(f"❌ Error loading authentication: {e}", file=sys.stderr)
                result['message'] = str(e)
                break

            git_user = auth_data.get('GIT_USER', '')
            git_password = auth_data.get('GIT_PASSWORD', '')
            
            if not git_user or not git_password:
                print("❌ Error: GIT_USER and GIT_PASSWORD required in ~/.doq/auth.json", file=sys.stderr)
                result['message'] = 'Missing Git credentials'
                break
            
            print(f"🔍 Creating pull request from '{src_branch}' to '{dest_branch}' in repository '{repo}'...")
            if delete_after_merge:
                print(f"   ⚠️  Source branch '{src_branch}' will be deleted after merge")
            
            # Step 1: Validate source branch exists
            src_branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches/{src_branch}"
            
            try:
                resp = requests.get(src_branch_url, auth=(git_user, git_password), timeout=30)
                
                if resp.status_code == 404:
                    print(f"❌ Error: Source branch '{src_branch}' not found in repository '{repo}'", file=sys.stderr)
                    print(f"   Check if branch name is correct", file=sys.stderr)
                    result['message'] = f"Source branch '{src_branch}' not found"
                    break
                
                resp.raise_for_status()
                print(f"✅ Source branch '{src_branch}' validated")
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error validating source branch: {e}", file=sys.stderr)
                result['message'] = f"Error validating source branch: {e}"
                break
            
            # Step 2: Validate destination branch exists
            dest_branch_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/refs/branches/{dest_branch}"
            
            try:
                resp = requests.get(dest_branch_url, auth=(git_user, git_password), timeout=30)
                
                if resp.status_code == 404:
                    print(f"❌ Error: Destination branch '{dest_branch}' not found in repository '{repo}'", file=sys.stderr)
                    print(f"   Check if branch name is correct", file=sys.stderr)
                    result['message'] = f"Destination branch '{dest_branch}' not found"
                    break
                
                resp.raise_for_status()
                print(f"✅ Destination branch '{dest_branch}' validated")
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error validating destination branch: {e}", file=sys.stderr)
                result['message'] = f"Error validating destination branch: {e}"
                break
            
            # Step 3: Create pull request
            pr_url = f"{BITBUCKET_API_BASE}/{BITBUCKET_ORG}/{repo}/pullrequests"
            pr_data = {
                "title": f"Merge {src_branch} into {dest_branch}",
                "source": {
                    "branch": {
                        "name": src_branch
                    }
                },
                "destination": {
                    "branch": {
                        "name": dest_branch
                    }
                },
                "close_source_branch": delete_after_merge
            }
            
            try:
                resp = requests.post(
                    pr_url,
                    auth=(git_user, git_password),
                    json=pr_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if resp.status_code == 201:
                    pr_response = resp.json()
                    pr_html_url = None
                    if 'links' in pr_response and 'html' in pr_response['links']:
                        pr_html_url = pr_response['links']['html'].get('href')
                    
                    if not pr_html_url and 'links' in pr_response:
                        for link_type, link_data in pr_response['links'].items():
                            if isinstance(link_data, dict) and 'href' in link_data:
                                if link_type == 'html' or 'html' in str(link_data.get('href', '')):
                                    pr_html_url = link_data['href']
                                    break
                    
                    if not pr_html_url:
                        pr_id = pr_response.get('id', 'unknown')
                        pr_html_url = f"https://bitbucket.org/{BITBUCKET_ORG}/{repo}/pull-requests/{pr_id}"
                    
                    result['pr_url'] = pr_html_url or ''
                    result['message'] = 'Pull request created successfully'
                    result['success'] = True
                    exit_code = 0
                    
                    print(f"✅ Pull request created successfully!")
                    print(f"   Repository: {repo}")
                    print(f"   Source branch: {src_branch}")
                    print(f"   Destination branch: {dest_branch}")
                    if delete_after_merge:
                        print(f"   ⚠️  Source branch will be deleted after merge")
                    print(f"   Pull Request URL: {pr_html_url}")
                    
                    break
                
                elif resp.status_code == 400:
                    error_data = resp.json()
                    error_msg = error_data.get('error', {}).get('message', 'Failed to create pull request')
                    error_detail = error_data.get('error', {}).get('detail', {})
                    
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    if error_detail:
                        if 'source' in error_detail:
                            print(f"   Source branch issue: {error_detail['source']}", file=sys.stderr)
                        if 'destination' in error_detail:
                            print(f"   Destination branch issue: {error_detail['destination']}", file=sys.stderr)
                    result['message'] = error_msg
                    break
                elif resp.status_code == 409:
                    error_data = resp.json()
                    error_msg = error_data.get('error', {}).get('message', 'Pull request already exists')
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    print(f"   A pull request from '{src_branch}' to '{dest_branch}' might already exist", file=sys.stderr)
                    result['message'] = error_msg
                    break
                else:
                    resp.raise_for_status()
                    result['message'] = f"Unexpected response from Bitbucket (HTTP {resp.status_code})"
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error creating pull request: {e}", file=sys.stderr)
                details = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        details = error_data.get('error', {}).get('message', str(e))
                        print(f"   Details: {details}", file=sys.stderr)
                    except Exception:
                        pass
                result['message'] = details or f"Error creating pull request: {e}"
                break
            
            break
    
    except KeyboardInterrupt:
        print("\n❌ Command cancelled by user", file=sys.stderr)
        result['message'] = 'Command cancelled by user'
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        result['message'] = str(e)
    finally:
        success = result.get('success', False) and exit_code == 0
        result['success'] = success
        if not result.get('message'):
            result['message'] = 'Pull request created successfully' if success else 'Pull request failed'
        
        if webhook_url:
            facts = [
                ("Repository", result.get('repository') or '-'),
                ("Source Branch", result.get('source') or '-'),
                ("Destination Branch", result.get('destination') or '-'),
                ("Delete After Merge", "Yes" if delete_after_merge else "No"),
                ("PR URL", result.get('pr_url') or '-'),
                ("Message", result.get('message') or '-'),
            ]
            send_teams_notification(
                webhook_url,
                title=f"Pull Request {'SUCCESS' if success else 'FAILED'}",
                facts=facts,
                success=success,
                summary=f"Pull Request {'SUCCESS' if success else 'FAILED'}"
            )
    
    sys.exit(0 if result.get('success') else 1)


def cmd_merge(args):
    """Merge a pull request from Bitbucket PR URL."""
    import re
    
    pr_url = args.pr_url
    delete_after_merge = args.delete if hasattr(args, 'delete') else False
    webhook_url = resolve_teams_webhook(getattr(args, 'webhook', None))
    
    result: Dict[str, Any] = {
        'pr_url': pr_url,
        'repository': '',
        'pr_id': '',
        'source': '',
        'destination': '',
        'message': '',
        'success': False,
        'delete_after_merge': delete_after_merge
    }
    
    exit_code = 1
    
    try:
        while True:
            if not pr_url:
                print("Error: Pull request URL is required", file=sys.stderr)
                print("Usage: doq merge <pr_url> [--delete]", file=sys.stderr)
                result['message'] = 'Missing pull request URL'
                break
            
            try:
                auth_data = load_auth_file()
            except FileNotFoundError as e:
                print(f"❌ Error: {e}", file=sys.stderr)
                print("   Configure authentication via ~/.doq/auth.json or environment variables", file=sys.stderr)
                result['message'] = str(e)
                break
            except Exception as e:
                print(f"❌ Error loading authentication: {e}", file=sys.stderr)
                result['message'] = str(e)
                break
            
            git_user = auth_data.get('GIT_USER', '')
            git_password = auth_data.get('GIT_PASSWORD', '')
            
            if not git_user or not git_password:
                print("❌ Error: GIT_USER and GIT_PASSWORD required in ~/.doq/auth.json", file=sys.stderr)
                result['message'] = 'Missing Git credentials'
                break
            
            url_pattern = r'https?://bitbucket\.org/([^/]+)/([^/]+)/pull-requests/(\d+)'
            match = re.search(url_pattern, pr_url)
            
            if not match:
                print(f"❌ Error: Invalid pull request URL format", file=sys.stderr)
                print(f"   Expected format: https://bitbucket.org/{BITBUCKET_ORG}/<repo>/pull-requests/<id>", file=sys.stderr)
                print(f"   Got: {pr_url}", file=sys.stderr)
                result['message'] = 'Invalid pull request URL format'
                break
            
            org, repo, pr_id = match.groups()
            result['repository'] = repo
            result['pr_id'] = pr_id
            
            print(f"🔍 Merging pull request #{pr_id} in repository '{repo}'...")
            if delete_after_merge:
                print(f"   ⚠️  Source branch will be deleted after merge")
            
            pr_details_url = f"{BITBUCKET_API_BASE}/{org}/{repo}/pullrequests/{pr_id}"
            
            try:
                resp = requests.get(pr_details_url, auth=(git_user, git_password), timeout=30)
                
                if resp.status_code == 404:
                    print(f"❌ Error: Pull request #{pr_id} not found in repository '{repo}'", file=sys.stderr)
                    print(f"   Check if PR URL is correct", file=sys.stderr)
                    result['message'] = f"Pull request #{pr_id} not found"
                    break
                
                resp.raise_for_status()
                pr_data = resp.json()
                
                pr_state = pr_data.get('state', '').upper()
                source_branch = pr_data.get('source', {}).get('branch', {}).get('name', 'unknown')
                dest_branch = pr_data.get('destination', {}).get('branch', {}).get('name', 'unknown')
                result['source'] = source_branch
                result['destination'] = dest_branch
                
                if pr_state == 'MERGED':
                    print(f"✅ Pull request #{pr_id} is already merged")
                    merge_commit = pr_data.get('merge_commit', {})
                    if merge_commit:
                        merge_hash = merge_commit.get('hash', 'unknown')
                        short_hash = merge_hash[:7] if len(merge_hash) >= 7 else merge_hash
                        print(f"   Merge commit: {short_hash}")
                    result['message'] = 'Pull request already merged'
                    result['success'] = True
                    exit_code = 0
                    break
                
                if pr_state in ['DECLINED', 'SUPERSEDED']:
                    print(f"❌ Error: Pull request #{pr_id} is {pr_state.lower()}", file=sys.stderr)
                    print(f"   Cannot merge a {pr_state.lower()} pull request", file=sys.stderr)
                    result['message'] = f"Pull request is {pr_state.lower()}"
                    break
                
                print(f"✅ Pull request validated")
                print(f"   Source branch: {source_branch}")
                print(f"   Destination branch: {dest_branch}")
                
            except requests.exceptions.RequestException as e:
                print(f"❌ Error fetching pull request details: {e}", file=sys.stderr)
                result['message'] = f"Error fetching pull request details: {e}"
                break
            
            merge_url = f"{BITBUCKET_API_BASE}/{org}/{repo}/pullrequests/{pr_id}/merge"
            merge_data = {
                "message": "Merged via doq merge",
                "close_source_branch": delete_after_merge
            }
            
            try:
                resp = requests.post(
                    merge_url,
                    auth=(git_user, git_password),
                    json=merge_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=30
                )
                
                if resp.status_code == 200:
                    merge_response = resp.json()
                    merge_commit = merge_response.get('merge_commit', {})
                    merge_hash = merge_commit.get('hash', 'unknown') if merge_commit else 'unknown'
                    short_hash = merge_hash[:7] if len(merge_hash) >= 7 else merge_hash
                    
                    print(f"✅ Pull request #{pr_id} merged successfully!")
                    print(f"   Repository: {repo}")
                    print(f"   Source branch: {source_branch}")
                    print(f"   Destination branch: {dest_branch}")
                    if merge_hash != 'unknown':
                        print(f"   Merge commit: {short_hash}")
                    if delete_after_merge:
                        print(f"   ⚠️  Source branch '{source_branch}' will be deleted")
                    
                    result['message'] = 'Pull request merged successfully'
                    result['success'] = True
                    exit_code = 0
                    break
                
                elif resp.status_code == 400:
                    error_data = resp.json()
                    error_msg = error_data.get('error', {}).get('message', 'Failed to merge pull request')
                    error_detail = error_data.get('error', {}).get('detail', {})
                    
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    if error_detail:
                        if 'merge_strategy' in error_detail:
                            print(f"   Merge strategy issue: {error_detail['merge_strategy']}", file=sys.stderr)
                        if 'conflicts' in str(error_detail):
                            print(f"   Merge conflicts detected. Please resolve conflicts manually.", file=sys.stderr)
                    result['message'] = error_msg
                    break
                elif resp.status_code == 409:
                    error_data = resp.json()
                    error_msg = error_data.get('error', {}).get('message', 'Cannot merge pull request')
                    print(f"❌ Error: {error_msg}", file=sys.stderr)
                    print(f"   Pull request may have merge conflicts or may already be merged", file=sys.stderr)
                    result['message'] = error_msg
                    break
                else:
                    resp.raise_for_status()
                    result['message'] = f"Unexpected response from Bitbucket (HTTP {resp.status_code})"
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ Error merging pull request: {e}", file=sys.stderr)
                details = None
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        details = error_data.get('error', {}).get('message', str(e))
                        print(f"   Details: {details}", file=sys.stderr)
                    except Exception:
                        pass
                result['message'] = details or f"Error merging pull request: {e}"
                break
            
            break
    
    except KeyboardInterrupt:
        print("\n❌ Command cancelled by user", file=sys.stderr)
        result['message'] = 'Command cancelled by user'
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        result['message'] = str(e)
    finally:
        success = result.get('success', False) and exit_code == 0
        result['success'] = success
        if not result.get('message'):
            result['message'] = 'Pull request merged successfully' if success else 'Pull request merge failed'
        
        if webhook_url:
            facts = [
                ("Repository", result.get('repository') or '-'),
                ("Pull Request ID", result.get('pr_id') or '-'),
                ("Source Branch", result.get('source') or '-'),
                ("Destination Branch", result.get('destination') or '-'),
                ("Delete After Merge", "Yes" if delete_after_merge else "No"),
                ("PR URL", result.get('pr_url') or '-'),
                ("Message", result.get('message') or '-'),
            ]
            send_teams_notification(
                webhook_url,
                title=f"Merge {'SUCCESS' if success else 'FAILED'}",
                facts=facts,
                success=success,
                summary=f"Merge {'SUCCESS' if success else 'FAILED'}"
            )
    
    sys.exit(0 if result.get('success') else 1)


def cmd_serve(args):
    """Start API web server."""
    try:
        import uvicorn
        from api_server import app
        
        host = args.host
        port = args.port
        
        print(f"🚀 Starting API server on {host}:{port}")
        print(f"📚 Swagger docs available at http://{host}:{port}/docs")
        print(f"   Press CTRL+C to stop")
        
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Error: Missing required dependencies", file=sys.stderr)
        print(f"   Please install: pip install fastapi uvicorn", file=sys.stderr)
        print(f"   Or: pip install -e .", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n✅ Server stopped")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Error starting server: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_clone(args):
    """Clone Git repository using credentials from ~/.netrc."""
    try:
        # Default values
        machine = args.machine or 'bitbucket.org'
        org_id = args.org_id or 'loyaltoid'
        repo = args.repo
        refs = args.refs
        
        if not repo or not refs:
            print("Error: Repository name and refs (branch/tag) are required", file=sys.stderr)
            print("Usage: doq clone <repo> <refs> [--machine MACHINE] [--org-id ORG_ID] [--all]", file=sys.stderr)
            sys.exit(1)
        
        # Load credentials from ~/.netrc
        try:
            creds = load_netrc_credentials(machine)
            username = creds['username']
            password = creds['password']
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            print(f"   Create ~/.netrc with credentials for {machine}", file=sys.stderr)
            sys.exit(1)
        
        # Build Git URL
        git_url = f"https://{machine}/{org_id}/{repo}.git"
        
        # Build URL with credentials embedded
        # Format: https://username:password@host/path
        auth_url = f"https://{username}:{password}@{machine}/{org_id}/{repo}.git"
        
        print(f"🔍 Cloning repository: {repo}")
        print(f"   Machine: {machine}")
        print(f"   Organization: {org_id}")
        print(f"   Reference: {refs}")
        print(f"   URL: https://{machine}/{org_id}/{repo}.git")
        
        # Check if git is available
        try:
            subprocess.run(['git', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("❌ Error: git command not found. Please install git.", file=sys.stderr)
            sys.exit(1)
        
        # Clone repository
        if args.all:
            # Clone all branches
            print(f"📦 Cloning all branches...")
            result = subprocess.run(
                ['git', 'clone', auth_url, repo],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error cloning repository: {result.stderr}", file=sys.stderr)
                sys.exit(1)
            
            # Checkout the specified refs
            print(f"🔀 Checking out {refs}...")
            checkout_result = subprocess.run(
                ['git', 'checkout', refs],
                cwd=repo,
                capture_output=True,
                text=True
            )
            
            if checkout_result.returncode != 0:
                print(f"⚠️  Warning: Could not checkout {refs}: {checkout_result.stderr}", file=sys.stderr)
                print(f"   Repository cloned successfully, but checkout failed.", file=sys.stderr)
                print(f"   Available branches/tags:", file=sys.stderr)
                subprocess.run(['git', 'branch', '-a'], cwd=repo)
                subprocess.run(['git', 'tag'], cwd=repo)
        else:
            # Clone single branch
            print(f"📦 Cloning single branch: {refs}...")
            result = subprocess.run(
                ['git', 'clone', '--single-branch', '--branch', refs, auth_url, repo],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                print(f"❌ Error cloning repository: {result.stderr}", file=sys.stderr)
                sys.exit(1)
        
        print(f"✅ Successfully cloned {repo} ({refs})")
        print(f"   Location: {Path(repo).absolute()}")
        
    except KeyboardInterrupt:
        print("\n❌ Clone cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_plugin_list(args):
    """List all plugins and their status."""
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    plugins = plugin_manager.list_plugins()
    
    if not plugins:
        print("No plugins found.")
        return
    
    if args.json:
        output = [p.to_dict() for p in plugins]
        print(json.dumps(output, indent=2))
    else:
        print("\n📦 Installed Plugins:")
        print("=" * 70)
        for plugin in plugins:
            status = "✅ enabled" if plugin.enabled else "❌ disabled"
            print(f"\n  {plugin.name} (v{plugin.version}) - {status}")
            print(f"  Description: {plugin.description}")
            print(f"  Module: {plugin.module}")
            print(f"  Config: {plugin.config_file}")
            print(f"  Commands: {', '.join(plugin.commands)}")
        print("\n" + "=" * 70)


def cmd_plugin_enable(args):
    """Enable a plugin."""
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    if plugin_manager.enable_plugin(args.name):
        print(f"✅ Plugin '{args.name}' enabled")
    else:
        print(f"❌ Plugin '{args.name}' not found")
        sys.exit(1)


def cmd_plugin_disable(args):
    """Disable a plugin."""
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    if plugin_manager.disable_plugin(args.name):
        print(f"✅ Plugin '{args.name}' disabled")
    else:
        print(f"❌ Plugin '{args.name}' not found")
        sys.exit(1)


def cmd_plugin_config(args):
    """Show or edit plugin configuration."""
    import os
    import subprocess
    from pathlib import Path
    
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    config = plugin_manager.get_plugin_config(args.name)
    
    if config is None:
        print(f"❌ Plugin '{args.name}' not found or no config available")
        sys.exit(1)
    
    if args.edit:
        if args.name not in plugin_manager.plugins:
            print(f"❌ Plugin '{args.name}' not found")
            sys.exit(1)
        
        plugin = plugin_manager.plugins[args.name]
        config_path = Path.home() / ".doq" / plugin.config_file
        
        editor = os.environ.get('EDITOR', 'vi')
        try:
            subprocess.run([editor, str(config_path)])
            print(f"✅ Configuration updated for '{args.name}'")
        except Exception as e:
            print(f"❌ Error editing config: {e}")
            sys.exit(1)
    else:
        print(json.dumps(config, indent=2))


def main():
    """Main CLI entry point."""
    # Initialize plugin manager
    plugin_manager = PluginManager()
    plugin_manager.load_plugins()
    
    parser = argparse.ArgumentParser(
        description='DevOps Q - Simple CLI tool for managing Rancher resources',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Login command
    login_parser = subparsers.add_parser('login', help='Login to Rancher API')
    login_parser.add_argument('--url', help=f'Rancher API URL (default: https://193.1.1.4)')
    login_parser.add_argument('--username', '-u', help='Username (prompt if not provided)')
    login_parser.add_argument('--password', '-p', help='Password (prompt if not provided)')
    login_parser.add_argument('--force', action='store_true',
                              help='Force re-login even if valid token exists')
    login_parser.add_argument('--update-auth', action='store_true',
                              help='Force update ~/.doq/auth.json from auth-api (skip confirmation)')
    login_parser.add_argument('--save-auth', action='store_true',
                              help='Save current auth.json credentials to auth-api for the current user')
    login_parser.add_argument('--insecure', action='store_true', default=None,
                              help='Enable insecure mode (skip SSL verification, default: True)')
    login_parser.add_argument('--secure', action='store_false', dest='insecure',
                              help='Disable insecure mode (enable SSL verification)')
    login_parser.set_defaults(func=cmd_login)
    
    # Token check command
    check_parser = subparsers.add_parser(
        'check',
        help='Validate auth.json and Rancher token status'
    )
    check_parser.add_argument('--url', help='Rancher API URL (uses config if not provided)')
    check_parser.add_argument('--token', help='Token to check (uses config if not provided)')
    check_parser.add_argument('--insecure', action='store_true', default=None,
                              help='Enable insecure mode (skip SSL verification)')
    check_parser.add_argument('--secure', action='store_false', dest='insecure',
                              help='Disable insecure mode (enable SSL verification)')
    check_parser.add_argument('--json', action='store_true', help='Output as JSON')
    check_parser.set_defaults(func=cmd_check)
    
    # Check update command
    check_update_parser = subparsers.add_parser('check-update', help='Check if there are updates available')
    check_update_parser.add_argument('--json', action='store_true', help='Output as JSON')
    check_update_parser.set_defaults(func=cmd_check_update)
    
    # Update command
    update_parser = subparsers.add_parser('update', 
                                          help='Update DevOps Q from GitHub repository',
                                          description='Update DevOps Q to latest version or specific commit. '
                                                    'By default uses branch from version.json, or specify with --branch.')
    update_parser.add_argument('commit_hash', nargs='?', 
                              help='Git commit hash to update to (optional, defaults to latest if not provided)')
    update_parser.add_argument('--latest', action='store_true', 
                              help='Update to latest commit from repository (same as running without arguments)')

    update_parser.add_argument('--branch', type=str, default=None,
                              help='Branch to update from (default: use branch from version.json)')
    update_parser.set_defaults(func=cmd_update)
    
    # Plugin management commands
    plugin_parser = subparsers.add_parser('plugin', 
                                          help='Manage plugins',
                                          description='View and manage doq plugins')
    plugin_subparsers = plugin_parser.add_subparsers(dest='plugin_command', help='Plugin commands', required=False)
    
    # Default to list if no subcommand provided
    plugin_parser.set_defaults(func=cmd_plugin_list)
    
    # Plugin list command
    plugin_list_parser = plugin_subparsers.add_parser('list', help='List all plugins')
    plugin_list_parser.add_argument('--json', action='store_true', help='Output as JSON')
    plugin_list_parser.set_defaults(func=cmd_plugin_list)
    
    # Plugin enable command
    plugin_enable_parser = plugin_subparsers.add_parser('enable', help='Enable a plugin')
    plugin_enable_parser.add_argument('name', help='Plugin name')
    plugin_enable_parser.set_defaults(func=cmd_plugin_enable)
    
    # Plugin disable command
    plugin_disable_parser = plugin_subparsers.add_parser('disable', help='Disable a plugin')
    plugin_disable_parser.add_argument('name', help='Plugin name')
    plugin_disable_parser.set_defaults(func=cmd_plugin_disable)
    
    # Plugin config command
    plugin_config_parser = plugin_subparsers.add_parser('config', help='Show or edit plugin configuration')
    plugin_config_parser.add_argument('name', help='Plugin name')
    plugin_config_parser.add_argument('--edit', action='store_true', help='Edit configuration in $EDITOR')
    plugin_config_parser.set_defaults(func=cmd_plugin_config)
    
    # Version command
    version_parser = subparsers.add_parser('version', help='Show installed version information')
    version_parser.add_argument('--json', action='store_true', help='Output as JSON')
    version_parser.set_defaults(func=cmd_version)
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Configure Rancher API settings')
    config_parser.add_argument('--url', help='Rancher API URL')
    config_parser.add_argument('--token', help='Rancher API token')
    config_parser.add_argument('--insecure', action='store_true', default=None,
                               help='Enable insecure mode (skip SSL verification)')
    config_parser.add_argument('--secure', action='store_false', dest='insecure',
                               help='Disable insecure mode (enable SSL verification)')
    config_parser.set_defaults(func=cmd_config)
    
    # List projects command
    project_parser = subparsers.add_parser('project', help='List projects (default: System projects only)')
    project_parser.add_argument('--all', action='store_true', 
                                 help='Show all projects')
    project_parser.add_argument('--cluster', help='Filter by cluster ID')
    project_parser.add_argument('--save', action='store_true',
                                 help='Save System projects to $HOME/.doq/project.json')
    project_parser.add_argument('--json', action='store_true', help='Output as JSON')
    project_parser.set_defaults(func=cmd_list_projects)
    
    # Namespace switch command
    ns_parser = subparsers.add_parser('ns', 
                                      help='Switch kubectl context based on namespace format {project}-{env}',
                                      description='Switch kubectl context by matching environment name. '
                                                'Format: {project}-{env} (e.g., develop-saas)')
    ns_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    ns_parser.set_defaults(func=cmd_ns)
    
    # Set image command
    set_image_parser = subparsers.add_parser('set-image',
                                             help='Set image for deployment in namespace',
                                             description='Set image for deployment. Automatically switches to correct context based on namespace.')
    set_image_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    set_image_parser.add_argument('deployment', help='Deployment name')
    set_image_parser.add_argument('image', help='Image URL/tag (e.g., nginx:1.20 or registry.example.com/app:v1.0)')
    set_image_parser.set_defaults(func=cmd_set_image)

    set_image_yaml_parser = subparsers.add_parser('set-image-yaml',
                                                  help='Update image field inside YAML file in Bitbucket repo',
                                                  description='Clone repository, update YAML image field, commit, dan push ke branch yang sama.')
    set_image_yaml_parser.add_argument('repo', help='Repository name (contoh: saas-apigateway)')
    set_image_yaml_parser.add_argument('refs', help='Branch target (contoh: develop)')
    set_image_yaml_parser.add_argument('yaml_path', help='Lokasi file YAML relatif terhadap root repo')
    set_image_yaml_parser.add_argument('image', help='Image baru (contoh: loyaltolpi/api:fc0bd25)')
    set_image_yaml_parser.add_argument('--dry-run', action='store_true', help='Hanya simulasi perubahan tanpa commit/push')
    set_image_yaml_parser.set_defaults(func=cmd_set_image_yaml)

    # Get image command
    get_image_parser = subparsers.add_parser('get-image',
                                             help='Get current image information for deployment in namespace',
                                             description='Get current image information for deployment. Automatically switches to correct context based on namespace.')
    get_image_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    get_image_parser.add_argument('deployment', help='Deployment name')
    get_image_parser.add_argument('--json', action='store_true', help='Output as JSON')
    get_image_parser.set_defaults(func=cmd_get_image)
    
    # Get deployment command
    get_deploy_parser = subparsers.add_parser('get-deploy',
                                              help='Get deployment resource information in JSON format',
                                              description='Get deployment resource information in JSON format. Automatically switches to correct context based on namespace. Output is silent (JSON only). If deployment name is not provided, lists all deployments in the namespace.')
    get_deploy_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    get_deploy_parser.add_argument('deployment', nargs='?', help='Deployment name (optional, if not provided lists all deployments)')
    get_deploy_parser.add_argument('--name', action='store_true', help='Output only deployment names as JSON array')
    get_deploy_parser.set_defaults(func=cmd_get_deploy)
    
    # Get service command
    get_svc_parser = subparsers.add_parser('get-svc',
                                           help='Get service resource information in JSON format',
                                           description='Get service resource information in JSON format. Automatically switches to correct context based on namespace. Output is silent (JSON only).')
    get_svc_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    get_svc_parser.add_argument('service', help='Service name')
    get_svc_parser.set_defaults(func=cmd_get_svc)
    
    # Get configmap command
    get_cm_parser = subparsers.add_parser('get-cm',
                                          help='Get configmap resource information in JSON format',
                                          description='Get configmap resource information in JSON format. Automatically switches to correct context based on namespace. Output is silent (JSON only).')
    get_cm_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    get_cm_parser.add_argument('configmap', help='ConfigMap name')
    get_cm_parser.set_defaults(func=cmd_get_cm)
    
    # Get secret command
    get_secret_parser = subparsers.add_parser('get-secret',
                                             help='Get secret resource information in JSON format with base64 decoded values',
                                             description='Get secret resource information in JSON format with base64 decoded values. Automatically switches to correct context based on namespace. Output is silent (JSON only).')
    get_secret_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    get_secret_parser.add_argument('secret', help='Secret name')
    get_secret_parser.set_defaults(func=cmd_get_secret)
    
    # Kubeconfig command
    kubeconfig_parser = subparsers.add_parser('kube-config', help='Get kubeconfig from project and save to ~/.kube/config')
    kubeconfig_parser.add_argument('project_id', help='Project ID')
    kubeconfig_parser.add_argument('--flatten', action='store_true', default=True,
                                    help='Flatten kubeconfig (default: True)')
    kubeconfig_parser.add_argument('--no-flatten', action='store_false', dest='flatten',
                                    help='Do not flatten kubeconfig')
    kubeconfig_parser.add_argument('--replace', action='store_true',
                                    help='Replace existing kubeconfig instead of merging')
    kubeconfig_parser.add_argument('--set-context', action='store_true',
                                    help='Set as current context after saving')
    kubeconfig_parser.set_defaults(func=cmd_kube_config, flatten=True)
    
    # Clone command
    clone_parser = subparsers.add_parser('clone', 
                                         help='Clone Git repository using credentials from ~/.netrc',
                                         description='Clone Git repositories using HTTPS with credentials from ~/.netrc. '
                                                   'Default machine is bitbucket.org and default org-id is loyaltoid.')
    clone_parser.add_argument('repo', help='Repository name (e.g., saas-apigateway)')
    clone_parser.add_argument('refs', help='Branch or tag name (e.g., develop, main, v1.0.0)')
    clone_parser.add_argument('--machine', default='bitbucket.org',
                              help='Git host machine (default: bitbucket.org)')
    clone_parser.add_argument('--org-id', default='loyaltoid',
                              help='Organization ID (default: loyaltoid)')
    clone_parser.add_argument('--all', action='store_true',
                              help='Clone all branches instead of single branch (default: single branch only)')
    clone_parser.set_defaults(func=cmd_clone)
    
    # Commit command
    commit_parser = subparsers.add_parser('commit',
                                         help='Display commit information from Bitbucket repository',
                                         description='Display commit information (timestamp, author name & email, commit message) from Bitbucket. '
                                                   'If commit_id is provided, shows details of that commit. '
                                                   'If omitted, shows last 5 commits from the specified branch/tag.')
    commit_parser.add_argument('repo', help='Repository name (e.g., saas-apigateway)')
    commit_parser.add_argument('ref', help='Branch or tag name (e.g., develop, main, v1.0.0)')
    commit_parser.add_argument('commit_id', nargs='?', help='Short commit ID (e.g., abc1234). If omitted, shows last 5 commits.')
    commit_parser.add_argument('--json', action='store_true', help='Output as JSON')
    commit_parser.set_defaults(func=cmd_commit)
    
    # Create branch command
    create_branch_parser = subparsers.add_parser('create-branch',
                                                 help='Create a new branch in Bitbucket repository from source branch',
                                                 description='Create a new branch in Bitbucket repository from an existing source branch. '
                                                           'The new branch will point to the same commit as the source branch.')
    create_branch_parser.add_argument('repo', help='Repository name (e.g., saas-apigateway)')
    create_branch_parser.add_argument('src_branch', help='Source branch name (e.g., develop, main)')
    create_branch_parser.add_argument('dest_branch', help='Destination branch name (new branch to create)')
    create_branch_parser.set_defaults(func=cmd_create_branch)
    
    # Pull request command
    pull_request_parser = subparsers.add_parser('pull-request',
                                                help='Create a pull request in Bitbucket repository',
                                                description='Create a pull request from source branch to destination branch. '
                                                          'Use --delete flag to delete source branch after merge.')
    pull_request_parser.add_argument('repo', help='Repository name (e.g., saas-apigateway)')
    pull_request_parser.add_argument('src_branch', help='Source branch name (e.g., feature-branch)')
    pull_request_parser.add_argument('dest_branch', help='Destination branch name (e.g., develop, main)')
    pull_request_parser.add_argument('--delete', action='store_true', default=False,
                                     help='Delete source branch after merge (default: False)')
    pull_request_parser.add_argument('--webhook', type=str,
                                     help='Microsoft Teams webhook URL for notifications (fallback to TEAMS_WEBHOOK env or ~/.doq/.env)')
    pull_request_parser.set_defaults(func=cmd_pull_request)
    
    # Merge command
    merge_parser = subparsers.add_parser('merge',
                                        help='Merge a pull request from Bitbucket PR URL',
                                        description='Merge a pull request automatically from its URL. '
                                                  'Use --delete flag to delete source branch after merge.')
    merge_parser.add_argument('pr_url', help='Pull request URL (e.g., https://bitbucket.org/loyaltoid/repo/pull-requests/123)')
    merge_parser.add_argument('--delete', action='store_true', default=False,
                              help='Delete source branch after merge (default: False)')
    merge_parser.add_argument('--webhook', type=str,
                              help='Microsoft Teams webhook URL for notifications (fallback to TEAMS_WEBHOOK env or ~/.doq/.env)')
    merge_parser.set_defaults(func=cmd_merge)
    
    # Serve command - Start API server
    serve_parser = subparsers.add_parser('serve',
                                         help='Start API web server',
                                         description='Start FastAPI web server on 0.0.0.0:9876 with Swagger documentation')
    serve_parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    serve_parser.add_argument('--port', type=int, default=9876, help='Port to bind to (default: 9876)')
    serve_parser.set_defaults(func=cmd_serve)
    
    # Register plugin commands dynamically
    plugin_manager.register_plugin_commands(subparsers)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()

