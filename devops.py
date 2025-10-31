#!/usr/bin/env python3
"""DevOps Tools - Simple CLI tool for managing Rancher resources."""
import argparse
import getpass
import sys
from rancher_api import RancherAPI, login, check_token
from config import load_config, save_config, get_config_file_path, config_exists, ensure_config_dir
from version import get_version, save_version, check_for_updates, get_latest_commit_hash


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


def cmd_list_clusters(args):
    """List clusters."""
    try:
        api = RancherAPI()
        clusters = api.list_clusters()
        
        if args.json:
            import json
            print(json.dumps(clusters, indent=2))
        else:
            rows = []
            for cluster in clusters:
                rows.append([
                    cluster.get('id', ''),
                    cluster.get('name', ''),
                    cluster.get('state', ''),
                    cluster.get('kubernetesVersion', '')
                ])
            print_table(['ID', 'Name', 'State', 'Kubernetes Version'], rows)
    except Exception as e:
        print(f"Error listing clusters: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_projects(args):
    """List projects."""
    import json
    from pathlib import Path
    
    try:
        api = RancherAPI()
        projects = api.list_projects(cluster_id=args.cluster)
        
        # Filter by System project name if --system flag is set
        if args.system:
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
            # --save requires --system flag
            if not args.system:
                print("Error: --save requires --system flag", file=sys.stderr)
                print("Usage: devops project --system --save", file=sys.stderr)
                sys.exit(1)
            
            # Ensure .devops directory exists
            devops_dir = Path.home() / '.devops'
            devops_dir.mkdir(parents=True, exist_ok=True)
            
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
            output_file = devops_dir / 'project.json'
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
                
                rows.append([
                    project.get('id', ''),
                    project.get('name', ''),
                    cluster_name,
                    cluster_id,
                    project.get('state', '')
                ])
            print_table(['ID', 'Name', 'Cluster Name', 'Cluster ID', 'State'], rows)
    except Exception as e:
        print(f"Error listing projects: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_namespaces(args):
    """List namespaces."""
    try:
        api = RancherAPI()
        namespaces = api.list_namespaces(project_id=args.project, cluster_id=args.cluster)
        
        if args.json:
            import json
            print(json.dumps(namespaces, indent=2))
        else:
            rows = []
            for namespace in namespaces:
                rows.append([
                    namespace.get('id', ''),
                    namespace.get('name', ''),
                    namespace.get('projectId', ''),
                    namespace.get('clusterId', ''),
                    namespace.get('state', '')
                ])
            print_table(['ID', 'Name', 'Project ID', 'Cluster ID', 'State'], rows)
    except Exception as e:
        print(f"Error listing namespaces: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_login(args):
    """Login to Rancher API."""
    # Default values
    default_url = "https://193.1.1.4"
    default_insecure = True
    
    # Check if config exists and token is valid
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
                    print("\nUse 'devops login --force' to force re-login.")
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
        save_config(url, token, insecure)
        
        print(f"Login successful!")
        print(f"Configuration saved to {get_config_file_path()}")
    except Exception as e:
        print(f"Error logging in: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_token_check(args):
    """Check token validity and expiration."""
    try:
        # Get config
        config = load_config()
        url = args.url or config.get('url')
        token = args.token or config.get('token')
        insecure = args.insecure if args.insecure is not None else config.get('insecure', True)
        
        if not url or not token:
            print("Error: URL and token must be configured or provided", file=sys.stderr)
            print("Use 'rancher_cli.py login' to configure or provide --url and --token", file=sys.stderr)
            sys.exit(1)
        
        if args.json:
            import json
            result = check_token(url, token, insecure)
            print(json.dumps(result, indent=2))
        else:
            print(f"Checking token for: {url}")
            print(f"Insecure mode: {insecure}")
            print()
            
            result = check_token(url, token, insecure)
            
            if result['valid']:
                print("? Token is VALID")
                
                if result['expires_at']:
                    from datetime import datetime
                    try:
                        exp_time = datetime.fromisoformat(result['expires_at'].replace('Z', '+00:00'))
                        now = datetime.now(exp_time.tzinfo)
                        
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
            print("Usage: devops kube-config <project-id>", file=sys.stderr)
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
    import subprocess
    import re
    import shutil
    
    ns_input = args.namespace
    
    # Parse format: {project}-{env}
    # Example: develop-saas -> env: develop, project: saas
    parts = ns_input.split('-', 1)
    if len(parts) != 2:
        print(f"Error: Invalid namespace format. Expected format: {{project}}-{{env}}", file=sys.stderr)
        print(f"Example: develop-saas (where 'develop' is env and 'saas' is project)", file=sys.stderr)
        sys.exit(1)
    
    env, project = parts
    print(f"?? Looking for context matching env: {env}, project: {project}")
    
    # Check if kubectl is available
    if not shutil.which('kubectl'):
        print("Error: kubectl is not installed or not in PATH", file=sys.stderr)
        print("Please install kubectl first: https://kubernetes.io/docs/tasks/tools/", file=sys.stderr)
        sys.exit(1)
    
    # Get list of contexts
    try:
        result = subprocess.run(
            ['kubectl', 'config', 'get-contexts', '-o', 'name'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"Error getting contexts: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        contexts = [ctx.strip() for ctx in result.stdout.strip().split('\n') if ctx.strip()]
        
        if not contexts:
            print("Error: No contexts found in kubectl config", file=sys.stderr)
            sys.exit(1)
        
        # Search for context matching env using regex
        # Pattern: look for env in context name (case-insensitive)
        # Examples: rke2-develop-qoin matches "develop"
        pattern = re.compile(rf'\b{re.escape(env)}\b', re.IGNORECASE)
        matched_contexts = [ctx for ctx in contexts if pattern.search(ctx)]
        
        if not matched_contexts:
            print(f"?? No context found matching env '{env}'")
            print(f"\nAvailable contexts:")
            for ctx in contexts:
                print(f"  - {ctx}")
            print(f"\nSuggestion: Check if env '{env}' exists in any context name")
            sys.exit(1)
        
        # If multiple matches, prefer exact match or first match
        # Priority: exact match > contains match
        exact_match = None
        for ctx in matched_contexts:
            if env.lower() in ctx.lower():
                exact_match = ctx
                break
        
        selected_context = exact_match if exact_match else matched_contexts[0]
        
        if len(matched_contexts) > 1:
            print(f"?? Multiple contexts found matching env '{env}':")
            for ctx in matched_contexts:
                marker = " (selected)" if ctx == selected_context else ""
                print(f"  - {ctx}{marker}")
        
        # Switch to selected context
        print(f"\n?? Switching to context: {selected_context}")
        result = subprocess.run(
            ['kubectl', 'config', 'use-context', selected_context],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"Error switching context: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        
        print(f"? Switched to context: {selected_context}")
        
        # Verify current context
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
        
    except subprocess.TimeoutExpired:
        print("Error: kubectl command timed out", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
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
            print(f"   devops update {update_info['latest_hash']}")
            print("\nAtau update otomatis ke latest:")
            print("   devops update --latest")
        else:
            print("\n? Sudah menggunakan versi terbaru!")
            print(f"   Commit: {update_info['current_hash']}")
        
    except Exception as e:
        print(f"Error checking for updates: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_update(args):
    """Update DevOps Tools from GitHub repository."""
    import subprocess
    import shutil
    import tempfile
    from pathlib import Path
    
    repo_url = "https://github.com/mamatnurahmat/devops-tools"
    branch = "main"
    
    # Determine commit hash
    if args.latest:
        commit_hash = get_latest_commit_hash()
        if not commit_hash:
            print("Error: Tidak dapat mengambil latest commit hash dari repository", file=sys.stderr)
            sys.exit(1)
    elif args.commit_hash:
        commit_hash = args.commit_hash
    else:
        # If no commit hash provided, check current version and update to latest
        print("?? Checking current version...")
        current_version = get_version()
        current_hash = current_version.get('commit_hash', 'unknown')
        
        # Get latest commit hash
        latest_hash = get_latest_commit_hash()
        if not latest_hash:
            print("Error: Tidak dapat mengambil latest commit hash dari repository", file=sys.stderr)
            sys.exit(1)
        
        # Compare with current version
        if current_hash != 'unknown' and current_hash == latest_hash:
            print("? Sudah menggunakan versi terbaru!")
            print(f"   Current version: {current_hash[:8]}...")
            print(f"   Latest version:  {latest_hash[:8]}...")
            print(f"   Installed at:    {current_version.get('installed_at', 'unknown')}")
            print("\nTidak ada update yang diperlukan.")
            return
        
        # Update to latest
        if current_hash != 'unknown':
            print(f"\n?? Update tersedia!")
            print(f"   Current version: {current_hash[:8]}...")
            print(f"   Latest version:  {latest_hash[:8]}...")
            print(f"   Will update to latest version...\n")
        else:
            print(f"\n?? Will update to latest version: {latest_hash[:8]}...\n")
        
        commit_hash = latest_hash
    
    # Check if git is available
    if not shutil.which('git'):
        print("Error: git is not installed or not in PATH", file=sys.stderr)
        print("Please install git first: https://git-scm.com/downloads", file=sys.stderr)
        sys.exit(1)
    
    # Create temporary directory for cloning
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix='devops-update-')
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
        
        # Save version after successful update
        save_version(commit_hash)
        
        print("\n" + "=" * 50)
        print("? Update completed successfully!")
        print(f"   Updated to commit: {commit_hash}")
        
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
        
        print("?? DevOps Tools Version Information")
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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='DevOps Tools - Simple CLI tool for managing Rancher resources',
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
    login_parser.add_argument('--insecure', action='store_true', default=None,
                              help='Enable insecure mode (skip SSL verification, default: True)')
    login_parser.add_argument('--secure', action='store_false', dest='insecure',
                              help='Disable insecure mode (enable SSL verification)')
    login_parser.set_defaults(func=cmd_login)
    
    # Token check command
    token_parser = subparsers.add_parser('token-check', help='Check token validity and expiration')
    token_parser.add_argument('--url', help='Rancher API URL (uses config if not provided)')
    token_parser.add_argument('--token', help='Token to check (uses config if not provided)')
    token_parser.add_argument('--insecure', action='store_true', default=None,
                              help='Enable insecure mode (skip SSL verification)')
    token_parser.add_argument('--secure', action='store_false', dest='insecure',
                              help='Disable insecure mode (enable SSL verification)')
    token_parser.add_argument('--json', action='store_true', help='Output as JSON')
    token_parser.set_defaults(func=cmd_token_check)
    
    # Check update command
    check_update_parser = subparsers.add_parser('check-update', help='Check if there are updates available')
    check_update_parser.add_argument('--json', action='store_true', help='Output as JSON')
    check_update_parser.set_defaults(func=cmd_check_update)
    
    # Update command
    update_parser = subparsers.add_parser('update', 
                                          help='Update DevOps Tools from GitHub repository',
                                          description='Update DevOps Tools to latest version or specific commit. '
                                                    'If no commit hash is provided, will update to latest commit from main branch.')
    update_parser.add_argument('commit_hash', nargs='?', 
                              help='Git commit hash to update to (optional, defaults to latest if not provided)')
    update_parser.add_argument('--latest', action='store_true', 
                              help='Update to latest commit from repository (same as running without arguments)')
    update_parser.set_defaults(func=cmd_update)
    
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
    
    # List clusters command
    cluster_parser = subparsers.add_parser('cluster', help='List clusters')
    cluster_parser.add_argument('--json', action='store_true', help='Output as JSON')
    cluster_parser.set_defaults(func=cmd_list_clusters)
    
    # List projects command
    project_parser = subparsers.add_parser('project', help='List projects')
    project_parser.add_argument('--cluster', help='Filter by cluster ID')
    project_parser.add_argument('--system', action='store_true', 
                                 help='Show only System projects')
    project_parser.add_argument('--save', action='store_true',
                                 help='Save System projects to $HOME/.devops/project.json (requires --system)')
    project_parser.add_argument('--json', action='store_true', help='Output as JSON')
    project_parser.set_defaults(func=cmd_list_projects)
    
    # List namespaces command
    namespace_parser = subparsers.add_parser('namespace', help='List namespaces')
    namespace_parser.add_argument('--project', help='Filter by project ID')
    namespace_parser.add_argument('--cluster', help='Filter by cluster ID')
    namespace_parser.add_argument('--json', action='store_true', help='Output as JSON')
    namespace_parser.set_defaults(func=cmd_list_namespaces)
    
    # Namespace switch command
    ns_parser = subparsers.add_parser('ns', 
                                      help='Switch kubectl context based on namespace format {project}-{env}',
                                      description='Switch kubectl context by matching environment name. '
                                                'Format: {project}-{env} (e.g., develop-saas)')
    ns_parser.add_argument('namespace', help='Namespace in format {project}-{env} (e.g., develop-saas)')
    ns_parser.set_defaults(func=cmd_ns)
    
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
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
