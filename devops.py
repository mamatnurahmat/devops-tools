#!/usr/bin/env python3
"""DevOps Tools - Simple CLI tool for managing Rancher resources."""
import argparse
import getpass
import sys
from rancher_api import RancherAPI, login, check_token
from config import load_config, save_config, get_config_file_path, config_exists, ensure_config_dir


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
    try:
        api = RancherAPI()
        projects = api.list_projects(cluster_id=args.cluster)
        
        if args.json:
            import json
            print(json.dumps(projects, indent=2))
        else:
            rows = []
            for project in projects:
                rows.append([
                    project.get('id', ''),
                    project.get('name', ''),
                    project.get('clusterId', ''),
                    project.get('state', '')
                ])
            print_table(['ID', 'Name', 'Cluster ID', 'State'], rows)
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
    project_parser.add_argument('--json', action='store_true', help='Output as JSON')
    project_parser.set_defaults(func=cmd_list_projects)
    
    # List namespaces command
    namespace_parser = subparsers.add_parser('namespace', help='List namespaces')
    namespace_parser.add_argument('--project', help='Filter by project ID')
    namespace_parser.add_argument('--cluster', help='Filter by cluster ID')
    namespace_parser.add_argument('--json', action='store_true', help='Output as JSON')
    namespace_parser.set_defaults(func=cmd_list_namespaces)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()
