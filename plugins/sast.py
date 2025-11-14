#!/usr/bin/env python3
"""Static Application Security Testing (SAST) plugin using Semgrep CLI."""
import json
import os
import subprocess
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# Import shared helpers
from plugins.shared_helpers import (
    load_auth_file,
    load_netrc_credentials,
    fetch_bitbucket_file,
    resolve_teams_webhook,
    send_teams_notification
)


SEMGREP_INSTALL_URL = "https://semgrep.dev/docs/getting-started/"


def check_semgrep_installed() -> bool:
    """Check if Semgrep is installed and available in PATH.
    
    Returns:
        True if Semgrep is installed, False otherwise
    """
    return shutil.which('semgrep') is not None


def install_semgrep() -> bool:
    """Install Semgrep via pip with user approval.
    
    Returns:
        True if installation successful, False otherwise
    """
    print("📦 Installing Semgrep...")
    try:
        # Try using python3 -m pip first, fallback to pip
        pip_cmd = ['python3', '-m', 'pip', 'install', 'semgrep']
        result = subprocess.run(
            pip_cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode != 0:
            # Try with just 'pip'
            pip_cmd = ['pip', 'install', 'semgrep']
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
        
        if result.returncode != 0:
            print(f"❌ Error installing Semgrep: {result.stderr}", file=sys.stderr)
            return False
        
        # Verify installation
        if check_semgrep_installed():
            version_result = subprocess.run(
                ['semgrep', '--version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if version_result.returncode == 0:
                print(f"✅ Semgrep installed successfully: {version_result.stdout.strip()}")
                return True
        
        print("⚠️  Warning: Semgrep installed but not found in PATH", file=sys.stderr)
        print(f"   You may need to restart your terminal or add pip install location to PATH", file=sys.stderr)
        return False
        
    except subprocess.TimeoutExpired:
        print("❌ Error: Installation timeout", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error installing Semgrep: {e}", file=sys.stderr)
        return False


def clone_repository(repo: str, refs: str, machine: str = 'bitbucket.org', org_id: str = 'loyaltoid') -> Optional[Path]:
    """Clone repository and checkout specified refs.
    
    Args:
        repo: Repository name
        refs: Branch or tag name
        machine: Git host machine (default: bitbucket.org)
        org_id: Organization ID (default: loyaltoid)
        
    Returns:
        Path to cloned repository directory, or None if failed
    """
    try:
        # Load credentials from ~/.netrc
        try:
            creds = load_netrc_credentials(machine)
            username = creds['username']
            password = creds['password']
        except (FileNotFoundError, ValueError) as e:
            print(f"❌ Error: {e}", file=sys.stderr)
            print(f"   Create ~/.netrc with credentials for {machine}", file=sys.stderr)
            return None
        
        # Build Git URL with credentials
        auth_url = f"https://{username}:{password}@{machine}/{org_id}/{repo}.git"
        
        # Create temporary directory for clone
        temp_dir = tempfile.mkdtemp(prefix=f'doq-sast-{repo}-')
        repo_path = Path(temp_dir) / repo
        
        print(f"📦 Cloning repository: {repo} ({refs})...")
        
        # Clone single branch
        result = subprocess.run(
            ['git', 'clone', '--single-branch', '--branch', refs, auth_url, str(repo_path)],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            # Try cloning all branches and then checkout
            print(f"⚠️  Single branch clone failed, trying full clone...")
            result = subprocess.run(
                ['git', 'clone', auth_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                print(f"❌ Error cloning repository: {result.stderr}", file=sys.stderr)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
            
            # Checkout the specified refs
            checkout_result = subprocess.run(
                ['git', 'checkout', refs],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if checkout_result.returncode != 0:
                print(f"❌ Error checking out {refs}: {checkout_result.stderr}", file=sys.stderr)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return None
        
        print(f"✅ Repository cloned successfully")
        return repo_path
        
    except subprocess.TimeoutExpired:
        print("❌ Error: Clone operation timeout", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Error cloning repository: {e}", file=sys.stderr)
        return None


def run_semgrep_scan(repo_path: Path) -> Optional[Dict[str, Any]]:
    """Run Semgrep scan on repository.
    
    Args:
        repo_path: Path to repository directory
        
    Returns:
        Dict with scan results (JSON format), or None if failed
    """
    try:
        print(f"🔍 Running Semgrep scan...")
        
        # Run Semgrep with JSON output
        result = subprocess.run(
            ['semgrep', '--json', '--config', 'auto', str(repo_path)],
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )
        
        # Semgrep returns exit code 1 if findings are found (this is normal)
        # Exit code 0 means no findings
        if result.returncode not in [0, 1]:
            print(f"❌ Error running Semgrep: {result.stderr}", file=sys.stderr)
            return None
        
        # Parse JSON output
        try:
            scan_data = json.loads(result.stdout)
            return scan_data
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing Semgrep output: {e}", file=sys.stderr)
            print(f"   Raw output: {result.stdout[:500]}", file=sys.stderr)
            return None
            
    except subprocess.TimeoutExpired:
        print("❌ Error: Semgrep scan timeout", file=sys.stderr)
        return None
    except Exception as e:
        print(f"❌ Error running Semgrep: {e}", file=sys.stderr)
        return None


def display_report(report_data: Dict[str, Any]) -> None:
    """Display Semgrep scan report in terminal.
    
    Args:
        report_data: Semgrep JSON output data
    """
    if not report_data:
        print("⚠️  No scan data to display")
        return
    
    # Extract findings
    results = report_data.get('results', [])
    errors = report_data.get('errors', [])
    
    # Count findings by severity
    severity_counts = {
        'ERROR': 0,
        'WARNING': 0,
        'INFO': 0
    }
    
    for result in results:
        severity = result.get('extra', {}).get('severity', 'INFO')
        if severity in severity_counts:
            severity_counts[severity] += 1
        else:
            severity_counts['INFO'] += 1
    
    total_findings = len(results)
    total_errors = len(errors)
    
    # Display summary
    print("\n" + "=" * 70)
    print("📊 SAST Scan Report Summary")
    print("=" * 70)
    print(f"Total Findings: {total_findings}")
    print(f"  - ERROR:   {severity_counts['ERROR']}")
    print(f"  - WARNING: {severity_counts['WARNING']}")
    print(f"  - INFO:    {severity_counts['INFO']}")
    if total_errors > 0:
        print(f"Scan Errors: {total_errors}")
    print("=" * 70)
    
    if total_findings == 0:
        print("✅ No security issues found!")
        return
    
    # Display findings grouped by file
    print("\n📋 Findings by File:\n")
    
    # Group by file path
    findings_by_file = {}
    for result in results:
        file_path = result.get('path', 'unknown')
        if file_path not in findings_by_file:
            findings_by_file[file_path] = []
        findings_by_file[file_path].append(result)
    
    # Display findings
    for file_path, findings in findings_by_file.items():
        print(f"📄 {file_path}")
        for finding in findings:
            severity = finding.get('extra', {}).get('severity', 'INFO')
            rule_id = finding.get('check_id', 'unknown')
            message = finding.get('message', 'No message')
            start_line = finding.get('start', {}).get('line', 0)
            end_line = finding.get('end', {}).get('line', 0)
            
            # Severity emoji
            severity_emoji = {
                'ERROR': '🔴',
                'WARNING': '🟡',
                'INFO': '🔵'
            }.get(severity, '⚪')
            
            print(f"  {severity_emoji} [{severity}] Line {start_line}-{end_line}: {rule_id}")
            print(f"     {message}")
        print()
    
    # Display scan errors if any
    if total_errors > 0:
        print("\n⚠️  Scan Errors:\n")
        for error in errors:
            error_type = error.get('type', 'unknown')
            message = error.get('message', 'No message')
            path = error.get('path', 'unknown')
            print(f"  ❌ {error_type} in {path}: {message}")
        print()


def export_report(report_data: Dict[str, Any], format: str, output_file: Optional[str] = None, 
                  repo: str = '', refs: str = '') -> bool:
    """Export Semgrep scan report to file.
    
    Args:
        report_data: Semgrep JSON output data
        format: Export format ('json', 'html', 'sarif')
        output_file: Output file path (optional, will generate if not provided)
        repo: Repository name for default filename
        refs: Reference name for default filename
        
    Returns:
        True if export successful, False otherwise
    """
    if not report_data:
        print("⚠️  No scan data to export", file=sys.stderr)
        return False
    
    # Generate default filename if not provided
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if repo and refs:
            default_name = f"sast-report-{repo}-{refs}-{timestamp}"
        else:
            default_name = f"sast-report-{timestamp}"
        
        if format == 'json':
            output_file = f"{default_name}.json"
        elif format == 'html':
            output_file = f"{default_name}.html"
        elif format == 'sarif':
            output_file = f"{default_name}.sarif"
        else:
            output_file = f"{default_name}.json"
    
    try:
        if format == 'json':
            # Export as JSON
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"✅ Report exported to: {output_file}")
            return True
            
        elif format == 'html':
            # Generate HTML report
            html_content = generate_html_report(report_data)
            with open(output_file, 'w') as f:
                f.write(html_content)
            print(f"✅ Report exported to: {output_file}")
            return True
            
        elif format == 'sarif':
            # Convert to SARIF format
            sarif_data = convert_to_sarif(report_data)
            with open(output_file, 'w') as f:
                json.dump(sarif_data, f, indent=2)
            print(f"✅ Report exported to: {output_file}")
            return True
            
        else:
            print(f"❌ Unsupported export format: {format}", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error exporting report: {e}", file=sys.stderr)
        return False


def generate_html_report(report_data: Dict[str, Any]) -> str:
    """Generate HTML report from Semgrep JSON data.
    
    Args:
        report_data: Semgrep JSON output data
        
    Returns:
        HTML content as string
    """
    results = report_data.get('results', [])
    errors = report_data.get('errors', [])
    
    # Count findings by severity
    severity_counts = {
        'ERROR': 0,
        'WARNING': 0,
        'INFO': 0
    }
    
    for result in results:
        severity = result.get('extra', {}).get('severity', 'INFO')
        if severity in severity_counts:
            severity_counts[severity] += 1
        else:
            severity_counts['INFO'] += 1
    
    total_findings = len(results)
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SAST Scan Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .summary {{
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }}
        .summary-card {{
            flex: 1;
            min-width: 200px;
            padding: 15px;
            border-radius: 5px;
            background-color: #f9f9f9;
        }}
        .summary-card.error {{ background-color: #ffebee; }}
        .summary-card.warning {{ background-color: #fff3e0; }}
        .summary-card.info {{ background-color: #e3f2fd; }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: #666;
        }}
        .summary-card .count {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }}
        .finding {{
            margin: 20px 0;
            padding: 15px;
            border-left: 4px solid #ddd;
            background-color: #fafafa;
        }}
        .finding.error {{ border-left-color: #f44336; }}
        .finding.warning {{ border-left-color: #ff9800; }}
        .finding.info {{ border-left-color: #2196F3; }}
        .finding-header {{
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }}
        .finding-message {{
            color: #666;
            margin: 5px 0;
        }}
        .finding-location {{
            color: #999;
            font-size: 0.9em;
        }}
        .file-header {{
            background-color: #333;
            color: white;
            padding: 10px;
            margin-top: 30px;
            border-radius: 5px 5px 0 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 SAST Scan Report</h1>
        <p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <div class="summary">
            <div class="summary-card">
                <h3>Total Findings</h3>
                <div class="count">{total_findings}</div>
            </div>
            <div class="summary-card error">
                <h3>ERROR</h3>
                <div class="count">{severity_counts['ERROR']}</div>
            </div>
            <div class="summary-card warning">
                <h3>WARNING</h3>
                <div class="count">{severity_counts['WARNING']}</div>
            </div>
            <div class="summary-card info">
                <h3>INFO</h3>
                <div class="count">{severity_counts['INFO']}</div>
            </div>
        </div>
"""
    
    # Group findings by file
    findings_by_file = {}
    for result in results:
        file_path = result.get('path', 'unknown')
        if file_path not in findings_by_file:
            findings_by_file[file_path] = []
        findings_by_file[file_path].append(result)
    
    # Add findings to HTML
    for file_path, findings in findings_by_file.items():
        html += f"""
        <div class="file-header">📄 {file_path}</div>
"""
        for finding in findings:
            severity = finding.get('extra', {}).get('severity', 'INFO').lower()
            rule_id = finding.get('check_id', 'unknown')
            message = finding.get('message', 'No message')
            start_line = finding.get('start', {}).get('line', 0)
            end_line = finding.get('end', {}).get('line', 0)
            
            html += f"""
        <div class="finding {severity}">
            <div class="finding-header">[{severity.upper()}] {rule_id}</div>
            <div class="finding-message">{message}</div>
            <div class="finding-location">Lines {start_line}-{end_line}</div>
        </div>
"""
    
    html += """
    </div>
</body>
</html>
"""
    
    return html


def convert_to_sarif(report_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert Semgrep JSON output to SARIF format.
    
    Args:
        report_data: Semgrep JSON output data
        
    Returns:
        SARIF format data
    """
    results = report_data.get('results', [])
    
    # SARIF structure
    sarif = {
        "version": "2.1.0",
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Semgrep",
                        "informationUri": "https://semgrep.dev",
                        "rules": []
                    }
                },
                "results": []
            }
        ]
    }
    
    # Convert findings to SARIF results
    rules_map = {}
    for result in results:
        rule_id = result.get('check_id', 'unknown')
        severity = result.get('extra', {}).get('severity', 'INFO')
        message = result.get('message', 'No message')
        file_path = result.get('path', '')
        start_line = result.get('start', {}).get('line', 0)
        start_col = result.get('start', {}).get('col', 0)
        end_line = result.get('end', {}).get('line', 0)
        end_col = result.get('end', {}).get('col', 0)
        
        # Map severity to SARIF level
        level_map = {
            'ERROR': 'error',
            'WARNING': 'warning',
            'INFO': 'note'
        }
        level = level_map.get(severity, 'note')
        
        # Add rule if not exists
        if rule_id not in rules_map:
            rules_map[rule_id] = {
                "id": rule_id,
                "shortDescription": {
                    "text": rule_id
                }
            }
        
        # Create SARIF result
        sarif_result = {
            "ruleId": rule_id,
            "level": level,
            "message": {
                "text": message
            },
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": file_path
                        },
                        "region": {
                            "startLine": start_line,
                            "startColumn": start_col,
                            "endLine": end_line,
                            "endColumn": end_col
                        }
                    }
                }
            ]
        }
        
        sarif["runs"][0]["results"].append(sarif_result)
    
    # Add rules
    sarif["runs"][0]["tool"]["driver"]["rules"] = list(rules_map.values())
    
    return sarif


def send_teams_report(report_data: Dict[str, Any], repo: str, refs: str) -> None:
    """Send SAST scan report to Microsoft Teams via webhook.
    
    Args:
        report_data: Semgrep JSON output data
        repo: Repository name
        refs: Branch or tag name
    """
    # Resolve webhook URL from env or config
    webhook_url = resolve_teams_webhook()
    if not webhook_url:
        return  # No webhook configured, skip silently
    
    if not report_data:
        return
    
    # Extract findings
    results = report_data.get('results', [])
    errors = report_data.get('errors', [])
    
    # Count findings by severity
    severity_counts = {
        'ERROR': 0,
        'WARNING': 0,
        'INFO': 0
    }
    
    for result in results:
        severity = result.get('extra', {}).get('severity', 'INFO')
        if severity in severity_counts:
            severity_counts[severity] += 1
        else:
            severity_counts['INFO'] += 1
    
    total_findings = len(results)
    total_errors = len(errors)
    
    # Determine success status (success if no ERROR findings)
    has_errors = severity_counts['ERROR'] > 0
    success = not has_errors
    
    # Prepare facts for Teams notification
    facts = [
        ("Repository", repo),
        ("Reference", refs),
        ("Total Findings", str(total_findings)),
        ("🔴 ERROR", str(severity_counts['ERROR'])),
        ("🟡 WARNING", str(severity_counts['WARNING'])),
        ("🔵 INFO", str(severity_counts['INFO'])),
    ]
    
    if total_errors > 0:
        facts.append(("Scan Errors", str(total_errors)))
    
    # Generate summary message
    if total_findings == 0:
        summary = f"✅ No security issues found in {repo} ({refs})"
        status_text = "CLEAN"
    elif has_errors:
        summary = f"🔴 Found {severity_counts['ERROR']} critical issue(s) in {repo} ({refs})"
        status_text = "ISSUES FOUND"
    else:
        summary = f"⚠️  Found {total_findings} security finding(s) in {repo} ({refs})"
        status_text = "WARNINGS FOUND"
    
    # Send notification
    send_teams_notification(
        webhook_url,
        title=f"SAST Scan {status_text}",
        facts=facts,
        success=success,
        summary=summary
    )


def cmd_sast_scan(args):
    """Command handler for 'doq sast <repo> <refs> scan'."""
    repo = args.repo
    refs = args.refs
    scan_action = getattr(args, 'scan', 'scan')
    
    # Validate scan action
    if scan_action != 'scan':
        print(f"❌ Error: Invalid action '{scan_action}'. Only 'scan' is supported.", file=sys.stderr)
        print("   Usage: doq sast <repo> <refs> scan [--export <format>] [--output <file>]", file=sys.stderr)
        sys.exit(1)
    
    if not repo or not refs:
        print("❌ Error: repo and refs are required arguments", file=sys.stderr)
        print("   Usage: doq sast <repo> <refs> scan [--export <format>] [--output <file>]", file=sys.stderr)
        sys.exit(1)
    
    # Check if Semgrep is installed
    if not check_semgrep_installed():
        print("⚠️  Semgrep tidak terinstall.")
        response = input("Install sekarang? (yes/no): ").strip().lower()
        
        if response in ['yes', 'y']:
            if not install_semgrep():
                print(f"\n❌ Gagal menginstall Semgrep.", file=sys.stderr)
                print(f"   Silakan install manual dari: {SEMGREP_INSTALL_URL}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"\n📖 Rekomendasi install Semgrep:")
            print(f"   {SEMGREP_INSTALL_URL}")
            print(f"\n   Atau jalankan: pip install semgrep")
            sys.exit(0)
    
    # Clone repository
    repo_path = clone_repository(repo, refs)
    if not repo_path:
        sys.exit(1)
    
    # Cleanup function
    def cleanup():
        if repo_path and repo_path.exists():
            shutil.rmtree(repo_path.parent, ignore_errors=True)
    
    try:
        # Run Semgrep scan
        report_data = run_semgrep_scan(repo_path)
        if report_data is None:
            cleanup()
            sys.exit(1)
        
        # Display report
        display_report(report_data)
        
        # Send report to Teams if webhook is configured
        send_teams_report(report_data, repo, refs)
        
        # Export report if requested
        if args.export:
            export_success = export_report(
                report_data,
                args.export,
                args.output,
                repo,
                refs
            )
            if not export_success:
                cleanup()
                sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n❌ Scan cancelled by user", file=sys.stderr)
        cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        cleanup()
        sys.exit(1)
    finally:
        cleanup()


def register_commands(subparsers):
    """Register sast commands with argparse.
    
    This function is called by PluginManager to dynamically register
    the plugin's commands.
    
    Args:
        subparsers: The argparse subparsers object
    """
    # SAST command - structure: doq sast <repo> <refs> [scan]
    sast_parser = subparsers.add_parser('sast', 
                                        help='Static Application Security Testing',
                                        description='Run SAST scan on repositories using Semgrep. Usage: doq sast <repo> <refs> [scan]')
    sast_parser.add_argument('repo', help='Repository name (e.g., saas-be-core)')
    sast_parser.add_argument('refs', help='Branch or tag name (e.g., develop, main)')
    sast_parser.add_argument('scan', nargs='?', default='scan', const='scan',
                            help='Scan action (optional, default: scan)')
    sast_parser.add_argument('--export', 
                            choices=['json', 'html', 'sarif'],
                            help='Export report format (json, html, or sarif)')
    sast_parser.add_argument('--output', 
                            help='Output file path (default: auto-generated filename)')
    sast_parser.set_defaults(func=cmd_sast_scan)

