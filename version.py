"""Version tracking for DevOps Tools CLI."""
import json
import subprocess
from pathlib import Path
from typing import Optional, Dict


VERSION_FILE = Path.home() / '.devops' / 'version.json'
REPO_URL = "https://github.com/mamatnurahmat/devops-tools"
BRANCH = "main"


def ensure_version_file():
    """Ensure version file exists."""
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not VERSION_FILE.exists():
        # Create file with default values without calling save_version to avoid recursion
        import datetime
        version_data = {
            'commit_hash': 'unknown',
            'installed_at': datetime.datetime.now().isoformat(),
            'repo_url': REPO_URL,
            'branch': BRANCH
        }
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_data, f, indent=2)


def get_version() -> Dict[str, str]:
    """Get current installed version from version file."""
    ensure_version_file()
    try:
        with open(VERSION_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {'commit_hash': 'unknown', 'installed_at': 'unknown'}


def save_version(commit_hash: str, installed_at: Optional[str] = None):
    """Save version information to version file."""
    ensure_version_file()
    import datetime
    
    if installed_at is None:
        installed_at = datetime.datetime.now().isoformat()
    
    version_data = {
        'commit_hash': commit_hash,
        'installed_at': installed_at,
        'repo_url': REPO_URL,
        'branch': BRANCH
    }
    
    with open(VERSION_FILE, 'w') as f:
        json.dump(version_data, f, indent=2)


def get_latest_commit_hash() -> Optional[str]:
    """Get latest commit hash from remote repository."""
    try:
        # Use git ls-remote to get latest commit without cloning
        cmd = ['git', 'ls-remote', REPO_URL, f'refs/heads/{BRANCH}']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode != 0:
            return None
        
        # Extract commit hash from output
        # Format: <commit_hash>    refs/heads/<branch>
        output = result.stdout.strip()
        if output:
            commit_hash = output.split()[0]
            return commit_hash
        
        return None
    except Exception:
        return None


def check_for_updates() -> Dict[str, any]:
    """Check if there are updates available."""
    current_version = get_version()
    current_hash = current_version.get('commit_hash', 'unknown')
    
    if current_hash == 'unknown':
        return {
            'has_update': False,
            'current_hash': current_hash,
            'latest_hash': None,
            'error': 'Cannot determine current version'
        }
    
    latest_hash = get_latest_commit_hash()
    
    if latest_hash is None:
        return {
            'has_update': False,
            'current_hash': current_hash,
            'latest_hash': None,
            'error': 'Cannot fetch latest version from repository'
        }
    
    has_update = latest_hash != current_hash
    
    return {
        'has_update': has_update,
        'current_hash': current_hash,
        'latest_hash': latest_hash,
        'error': None
    }

