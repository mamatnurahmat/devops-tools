"""Version tracking and update management for DevOps Q CLI."""
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


VERSION_FILE = Path.home() / ".doq" / "version.json"
REPO_URL = "https://github.com/mamatnurahmat/devops-tools"
REPO_BRANCH = "main"


def ensure_version_dir():
    """Ensure version directory exists."""
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)


def get_version():
    """Get current installed version information.
    
    Returns:
        dict: Version information with keys:
            - commit_hash: Git commit hash
            - installed_at: Installation timestamp (ISO format)
            - repo_url: Repository URL
            - branch: Git branch
    """
    if not VERSION_FILE.exists():
        return {
            'commit_hash': 'unknown',
            'installed_at': 'unknown',
            'repo_url': REPO_URL,
            'branch': REPO_BRANCH
        }
    
    try:
        with open(VERSION_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {
            'commit_hash': 'unknown',
            'installed_at': 'unknown',
            'repo_url': REPO_URL,
            'branch': REPO_BRANCH
        }


def save_version(commit_hash, branch=None):
    """Save version information to file.
    
    Args:
        commit_hash: Git commit hash to save
        branch: Branch name (optional, will preserve current if not provided)
    """
    ensure_version_dir()
    
    # Get current version to preserve branch if not specified
    if branch is None:
        current_version = get_version()
        branch = current_version.get('branch', REPO_BRANCH)
    
    version_info = {
        'commit_hash': commit_hash,
        'installed_at': datetime.now(timezone.utc).isoformat(),
        'repo_url': REPO_URL,
        'branch': branch
    }
    
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_info, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save version info: {e}")


def get_latest_commit_hash(branch=None):
    """Get latest commit hash from remote repository.
    
    Uses git ls-remote to get the latest commit hash without cloning.
    
    Args:
        branch: Branch name (optional, will use current version's branch if not provided)
    
    Returns:
        str: Latest commit hash or None if failed
    """
    # If branch not specified, get from current version
    if branch is None:
        current_version = get_version()
        branch = current_version.get('branch', REPO_BRANCH)
    
    try:
        result = subprocess.run(
            ['git', 'ls-remote', REPO_URL, f'refs/heads/{branch}'],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return None
        
        # Parse output: "commit_hash\trefs/heads/branch"
        output = result.stdout.strip()
        if not output:
            return None
        
        commit_hash = output.split('\t')[0]
        return commit_hash
    
    except Exception:
        return None


def check_for_updates():
    """Check if updates are available.
    
    Returns:
        dict: Update information with keys:
            - has_update: bool, True if update available
            - current_hash: Current commit hash
            - latest_hash: Latest commit hash
            - error: Error message if any
    """
    current_version = get_version()
    current_hash = current_version.get('commit_hash', 'unknown')
    
    # Get latest commit hash
    latest_hash = get_latest_commit_hash()
    
    if latest_hash is None:
        return {
            'has_update': False,
            'current_hash': current_hash,
            'latest_hash': None,
            'error': 'Could not fetch latest commit hash from repository'
        }
    
    # Compare hashes
    has_update = current_hash != latest_hash and current_hash != 'unknown'
    
    return {
        'has_update': has_update,
        'current_hash': current_hash,
        'latest_hash': latest_hash,
        'error': None
    }

