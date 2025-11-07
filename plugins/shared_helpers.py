#!/usr/bin/env python3
"""Shared helper functions for doq plugins."""
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import requests


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


def validate_auth_file() -> Dict[str, Any]:
    """Validate auth.json has required fields.
    
    Returns:
        Dict with:
        - valid: bool - Whether all required fields are present
        - missing_fields: list - List of missing field names
        - message: str - Human-readable validation message
    """
    required_fields = {
        'docker': ['DOCKERHUB_USER', 'DOCKERHUB_PASSWORD'],
        'bitbucket': ['GIT_USER', 'GIT_PASSWORD']
    }
    
    try:
        auth_data = load_auth_file()
    except (FileNotFoundError, RuntimeError):
        return {
            'valid': False,
            'missing_fields': ['DOCKERHUB_USER', 'DOCKERHUB_PASSWORD', 'GIT_USER', 'GIT_PASSWORD'],
            'message': '~/.doq/auth.json not found or empty'
        }
    
    missing = []
    for category, fields in required_fields.items():
        for field in fields:
            if not auth_data.get(field):
                missing.append(field)
    
    return {
        'valid': len(missing) == 0,
        'missing_fields': missing,
        'message': f'Missing fields: {", ".join(missing)}' if missing else 'All required fields present'
    }


def check_docker_image_exists(image_name: str, auth_data: Dict[str, str], verbose: bool = False) -> Dict[str, Any]:
    """Check if Docker image exists in Docker Hub.
    
    Args:
        image_name: Full image name with tag (e.g. loyaltolpi/repo:tag)
        auth_data: Dict with DOCKERHUB_USER and DOCKERHUB_PASSWORD
        verbose: If True, print debug messages (deprecated, errors are now in return dict)
        
    Returns:
        Dict with:
        - exists: bool - Whether the image exists
        - error: str - Error message if exists=False
        - error_type: str - Type of error (credentials_missing/auth_failed/not_found/network_timeout/network_error/invalid_format/unknown)
    """
    result = {
        'exists': False,
        'error': None,
        'error_type': None
    }
    
    # Validate image format
    if ':' not in image_name:
        result['error'] = f"Invalid image format (missing tag): {image_name}"
        result['error_type'] = 'invalid_format'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result
    
    image_base, tag = image_name.rsplit(':', 1)
    if '/' not in image_base:
        result['error'] = f"Invalid image format (missing namespace): {image_name}"
        result['error_type'] = 'invalid_format'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result
    
    namespace, repo = image_base.split('/', 1)
    
    # Check credentials
    user = auth_data.get('DOCKERHUB_USER', '')
    password = auth_data.get('DOCKERHUB_PASSWORD', '')
    
    if not user or not password:
        result['error'] = 'Docker Hub credentials missing in ~/.doq/auth.json'
        result['error_type'] = 'credentials_missing'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
            print(f"   Required: DOCKERHUB_USER and DOCKERHUB_PASSWORD", file=sys.stderr)
        return result
    
    # Step 1: Get JWT token from Docker Hub
    try:
        login_resp = requests.post(
            'https://hub.docker.com/v2/users/login/',
            json={'username': user, 'password': password},
            timeout=10
        )
        if login_resp.status_code == 500:
            result['error'] = f'Docker Hub API error (status: 500) - API may be temporarily unavailable or credentials format incorrect'
            result['error_type'] = 'auth_failed'
            if verbose:
                print(f"⚠️  {result['error']}", file=sys.stderr)
                print(f"   Try: 1) Verify DOCKERHUB_USER and DOCKERHUB_PASSWORD are correct", file=sys.stderr)
                print(f"        2) Check if Docker Hub API is accessible", file=sys.stderr)
                print(f"        3) Ensure password is not a Personal Access Token (use actual password)", file=sys.stderr)
            return result
        elif login_resp.status_code != 200:
            result['error'] = f'Docker Hub login failed (status: {login_resp.status_code})'
            result['error_type'] = 'auth_failed'
            if verbose:
                print(f"⚠️  {result['error']}", file=sys.stderr)
            return result
        
        token = login_resp.json().get('token')
        if not token:
            result['error'] = 'Docker Hub login failed (no token received)'
            result['error_type'] = 'auth_failed'
            if verbose:
                print(f"⚠️  {result['error']}", file=sys.stderr)
            return result
            
    except requests.exceptions.Timeout:
        result['error'] = 'Docker Hub API timeout - check network connectivity'
        result['error_type'] = 'network_timeout'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result
    except requests.exceptions.ConnectionError as e:
        result['error'] = 'Cannot connect to Docker Hub - check network/firewall'
        result['error_type'] = 'network_error'
        if verbose:
            print(f"⚠️  {result['error']}: {e}", file=sys.stderr)
        return result
    except Exception as e:
        result['error'] = f'Docker Hub login error: {str(e)}'
        result['error_type'] = 'unknown'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result
    
    # Step 2: Check tag existence with Bearer token
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/{tag}/"
    headers = {"Authorization": f"JWT {token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 404:
            result['error'] = 'Image not found in Docker Hub'
            result['error_type'] = 'not_found'
            if verbose:
                print(f"⚠️  {result['error']}: {namespace}/{repo}:{tag}", file=sys.stderr)
            return result
        elif resp.status_code == 200:
            result['exists'] = True
            return result
        else:
            result['error'] = f'Docker Hub returned status {resp.status_code}'
            result['error_type'] = 'unknown'
            if verbose:
                print(f"⚠️  {result['error']} for {namespace}/{repo}:{tag}", file=sys.stderr)
            return result
            
    except requests.exceptions.Timeout:
        result['error'] = 'Docker Hub API timeout - check network connectivity'
        result['error_type'] = 'network_timeout'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result
    except requests.exceptions.ConnectionError as e:
        result['error'] = 'Cannot connect to Docker Hub - check network/firewall'
        result['error_type'] = 'network_error'
        if verbose:
            print(f"⚠️  {result['error']}: {e}", file=sys.stderr)
        return result
    except Exception as e:
        result['error'] = f'Error checking image: {str(e)}'
        result['error_type'] = 'unknown'
        if verbose:
            print(f"⚠️  {result['error']}", file=sys.stderr)
        return result


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
    full_hash = ref_data['target']['hash']
    short_hash = full_hash[:7]
    
    return {
        'ref_type': 'branch' if refs_type == 'branches' else 'tag',
        'full_hash': full_hash,
        'short_hash': short_hash
    }


