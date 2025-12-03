#!/usr/bin/env python3
"""FastAPI Web Server for DevOps Tools."""
from __future__ import annotations
import sys
import io
import uuid
import json
import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from contextlib import redirect_stdout, redirect_stderr

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
from pathlib import Path

from rancher_api import login as rancher_login, RancherAPI
from config import load_config

# Import CLI functions
from plugins.docker_utils import cmd_images, cmd_get_cicd, cmd_get_file
from plugins.devops_ci import cmd_devops_ci
from plugins.k8s_deployer import cmd_deploy_k8s
from plugins.web_deployer import cmd_deploy_web
from doq import cmd_create_branch, cmd_pull_request, cmd_merge, cmd_set_image_yaml
from plugins.shared_helpers import resolve_teams_webhook, send_teams_notification

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Reduce noise from urllib3 and other libraries
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

# In-memory token store
token_store: dict[str, dict] = {}

# Token expiry time (1 hour)
TOKEN_EXPIRY_SECONDS = 3600

# Security scheme
security = HTTPBearer()


class LoginRequest(BaseModel):
    """Login request model - token only."""
    token: str


class LoginResponse(BaseModel):
    """Login response model."""
    token: str
    expires_in: int
    username: Optional[str] = None


class TokenValidationRequest(BaseModel):
    """Token validation request model."""
    token: str


class TokenValidationResponse(BaseModel):
    """Token validation response model."""
    valid: bool
    username: Optional[str] = None
    error: Optional[str] = None


class GitOpsCreateBranchRequest(BaseModel):
    repo: str
    src_branch: str
    dest_branch: str


class GitOpsSetImageYamlRequest(BaseModel):
    repo: str
    refs: str
    yaml_path: str
    image: str
    dry_run: bool = False


class GitOpsPullRequest(BaseModel):
    repo: str
    src_branch: str
    dest_branch: str
    delete_after_merge: bool = False


class GitOpsMergeRequest(BaseModel):
    pr_url: str
    delete_after_merge: bool = False


class PRRequest(BaseModel):
    """PR creation request model."""
    cluster: str
    ns: str
    deployment: str
    image: str


def cleanup_expired_tokens():
    """Remove expired tokens from store."""
    now = datetime.now()
    expired_tokens = [
        token for token, data in token_store.items()
        if data.get('expires_at', now) < now
    ]
    for token in expired_tokens:
        del token_store[token]


def get_static_token() -> Optional[str]:
    """Get static token from ~/.doq/.env."""
    env_file = Path.home() / ".doq" / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            return os.getenv("DOQ_API_TOKEN")
        except ImportError:
            pass
    return None


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify Bearer token (from login, Rancher token, or static env token)."""
    token = credentials.credentials

    # Step 0: Check static token from ~/.doq/.env
    static_token = get_static_token()
    if static_token and token == static_token:
        return "static_admin"

    # Step 0.5: Check if token matches RANCHER_TOKEN from ~/.doq/.env
    config = load_config()
    rancher_token_from_env = config.get('token', '')
    if rancher_token_from_env and token == rancher_token_from_env:
        return "rancher_token_user"

    # Step 1: Check token store (login tokens)
    cleanup_expired_tokens()
    if token in token_store:
        token_data = token_store[token]
        expires_at = token_data.get('expires_at')
        if not expires_at or expires_at >= datetime.now():
            return token_data.get('username', 'user')
        # Token expired, remove from store
        del token_store[token]

    # Step 2: Validate as Rancher token directly
    try:
        rancher_url = config.get('url')
        insecure = config.get('insecure', True)

        if not rancher_url:
            raise HTTPException(
                status_code=401,
                detail="Invalid token and RANCHER_URL not configured"
            )

        api = RancherAPI(url=rancher_url, token=token, insecure=insecure)
        validation_result = api.validate_token()

        if validation_result.get('valid') and not validation_result.get('expired'):
            return (
                validation_result.get('username')
                or validation_result.get('user_id')
                or 'rancher_user'
            )

        raise HTTPException(
            status_code=401,
            detail=validation_result.get('error', 'Invalid or expired token')
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Token validation failed: {exc}"
        )


def create_args_object(**kwargs):
    """Create a simple namespace object for CLI args."""
    class Args:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)
    
    return Args(**kwargs)


def parse_error_response(stderr: str, stdout: str = "") -> dict:
    """Parse error from stderr and determine error type and status code.
    
    Returns:
        dict with 'status_code', 'error_type', 'error', 'details'
    """
    error_lower = stderr.lower()
    
    # File not found errors
    if 'file not found' in error_lower or 'not found' in error_lower:
        if 'cicd.json' in error_lower or 'cicd' in error_lower:
            return {
                'status_code': 404,
                'error_type': 'file_not_found',
                'error': stderr.strip(),
                'details': {'file': 'cicd/cicd.json'}
            }
        return {
            'status_code': 404,
            'error_type': 'file_not_found',
            'error': stderr.strip(),
            'details': {}
        }
    
    # Authentication errors
    if 'auth' in error_lower or 'credential' in error_lower or 'unauthorized' in error_lower:
        return {
            'status_code': 401,
            'error_type': 'authentication_error',
            'error': stderr.strip(),
            'details': {}
        }

    # Conflict errors
    if 'already exists' in error_lower or 'conflict' in error_lower:
        return {
            'status_code': 409,
            'error_type': 'conflict',
            'error': stderr.strip(),
            'details': {}
        }
 
    # Validation errors
    if 'missing' in error_lower or 'required' in error_lower or 'invalid' in error_lower:
        return {
            'status_code': 400,
            'error_type': 'validation_error',
            'error': stderr.strip(),
            'details': {}
        }
    
    # Default to 500 for execution errors
    return {
        'status_code': 500,
        'error_type': 'execution_error',
        'error': stderr.strip() or 'Unknown error occurred',
        'details': {'stdout': stdout.strip() if stdout else None}
    }


def capture_cli_output(func, args_obj):
    """Capture stdout/stderr from CLI function and return result."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    try:
        # Redirect stdout and stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Some CLI functions call sys.exit(), so we catch SystemExit
            try:
                func(args_obj)
                exit_code = 0
            except SystemExit as e:
                # sys.exit() can be called with None (defaults to 0) or an int
                exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
            except Exception as e:
                # Capture any other exceptions
                stderr_capture.write(str(e))
                exit_code = 1
    except Exception as e:
        # Capture any exceptions during execution
        stderr_capture.write(str(e))
        exit_code = 1
    
    stdout_text = stdout_capture.getvalue()
    stderr_text = stderr_capture.getvalue()
    
    return {
        'exit_code': exit_code,
        'stdout': stdout_text,
        'stderr': stderr_text
    }


def build_cli_success_response(result: dict, extra: Optional[dict] = None) -> dict:
    """Build standardized success response for CLI executions."""
    response = {
        'success': True,
        'exit_code': result.get('exit_code', 0),
        'stdout': result.get('stdout', '').strip(),
        'stderr': result.get('stderr', '').strip()
    }
    if extra:
        response['details'] = extra
    return response


def build_cli_error_detail(result: dict, error_info: dict) -> dict:
    """Compose error detail payload for HTTPException."""
    details = error_info.get('details', {}).copy()
    stdout_text = result.get('stdout', '').strip()
    stderr_text = result.get('stderr', '').strip()
    if stdout_text:
        details['stdout'] = stdout_text
    if stderr_text:
        details['stderr'] = stderr_text
    return {
        'success': False,
        'error': error_info.get('error', 'Command failed'),
        'error_type': error_info.get('error_type', 'execution_error'),
        'details': details
    }


def extract_pr_url(stdout: str) -> Optional[str]:
    """Extract PR URL from command stdout."""
    # Look for "Pull Request URL: <url>" pattern
    pattern = r'Pull Request URL:\s*(https?://[^\s]+)'
    match = re.search(pattern, stdout)
    if match:
        return match.group(1)
    return None


# FastAPI app
app = FastAPI(
    title="DevOps Tools API",
    description="API server for DevOps CI/CD operations",
    version="1.0.0"
)


@app.post("/v1/validate-token", response_model=TokenValidationResponse)
async def validate_token(request: TokenValidationRequest):
    """Validate a Rancher token."""
    try:
        token = request.token
        if not token:
            return TokenValidationResponse(valid=False, error="Token is required")
        
        # Try to verify the token
        try:
            # Create a mock credentials object for verification
            from fastapi.security import HTTPAuthorizationCredentials
            mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            username = verify_token(mock_credentials)
            
            return TokenValidationResponse(valid=True, username=username)
        except HTTPException as e:
            return TokenValidationResponse(valid=False, error=e.detail)
        except Exception as e:
            return TokenValidationResponse(valid=False, error=str(e))
    except Exception as e:
        return TokenValidationResponse(valid=False, error=str(e))


@app.post("/v1/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login with Rancher token only.
    
    Validates the provided token and returns it for storage in localStorage.
    """
    try:
        if not request.token:
            raise HTTPException(
                status_code=400,
                detail="Token is required"
            )
        
        # Validate the token
        try:
            from fastapi.security import HTTPAuthorizationCredentials
            mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=request.token)
            username = verify_token(mock_credentials)
            
            # Return the token itself (not a generated session token)
            # This token will be stored in localStorage and used directly
            return LoginResponse(
                token=request.token,
                expires_in=TOKEN_EXPIRY_SECONDS,
                username=username
            )
        except HTTPException as e:
            raise HTTPException(
                status_code=401,
                detail=f"Token validation failed: {e.detail}"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Login error: {str(e)}"
        )


@app.get("/v1/image/{repo}/{refs}")
async def check_image(
    repo: str,
    refs: str,
    username: str = Depends(verify_token)
):
    """Check Docker image status."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            json=True,
            force_build=False
        )
        
        # Capture output
        result = capture_cli_output(cmd_images, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Parse JSON output from stdout
        try:
            output = json.loads(result['stdout'])
            return output
        except json.JSONDecodeError:
            # If not JSON, return raw output
            return {
                'success': result['exit_code'] == 0,
                'output': result['stdout'],
                'error': result['stderr'] if result['stderr'] else None
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error checking image: {str(e)}"
        )


@app.get("/v1/devops-ci/{repo}/{refs}")
async def build_image(
    repo: str,
    refs: str,
    username: str = Depends(verify_token)
):
    """Build Docker image using DevOps CI."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            rebuild=False,
            json=True,
            short=False,
            custom_image='',
            helper=False,
            image_name=None,
            registry=None,
            port=None,
            use_builder=None,
            help_devops_ci=False,
            version_devops_ci=False
        )
        
        # Capture output
        result = capture_cli_output(cmd_devops_ci, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Parse JSON output from stdout
        try:
            output = json.loads(result['stdout'])
            return output
        except json.JSONDecodeError:
            # If not JSON, return raw output
            return {
                'success': result['exit_code'] == 0,
                'output': result['stdout'],
                'error': result['stderr'] if result['stderr'] else None
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error building image: {str(e)}"
        )


@app.get("/v1/deploy-k8s/{repo}/{refs}")
async def deploy_k8s(
    repo: str,
    refs: str,
    username: str = Depends(verify_token)
):
    """Deploy application to Kubernetes."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            image=None,
            json=True
        )
        
        # Capture output
        result = capture_cli_output(cmd_deploy_k8s, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Parse JSON output from stdout
        try:
            stdout_text = result['stdout'].strip()
            
            # Try to find JSON object/array in the output
            # JSON might be at the end after print statements
            json_start = None
            json_end = None
            
            # Look for first { or [
            for i, char in enumerate(stdout_text):
                if char == '{' or char == '[':
                    json_start = i
                    break
            
            if json_start is not None:
                # Find matching closing brace/bracket
                open_char = stdout_text[json_start]
                close_char = '}' if open_char == '{' else ']'
                depth = 0
                
                for i in range(json_start, len(stdout_text)):
                    if stdout_text[i] == open_char:
                        depth += 1
                    elif stdout_text[i] == close_char:
                        depth -= 1
                        if depth == 0:
                            json_end = i + 1
                            break
                
                if json_end:
                    json_str = stdout_text[json_start:json_end]
                    json_output = json.loads(json_str)
                    return json_output
            
            # If no JSON found, try parsing whole stdout
            json_output = json.loads(stdout_text)
            return json_output
        except json.JSONDecodeError:
            # If not JSON, return raw output
            return {
                'success': result['exit_code'] == 0,
                'output': result['stdout'],
                'error': result['stderr'] if result['stderr'] else None
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deploying to Kubernetes: {str(e)}"
        )


@app.get("/v1/deploy-web/{repo}/{refs}")
async def deploy_web(
    repo: str,
    refs: str,
    username: str = Depends(verify_token)
):
    """Deploy web application using Docker Compose."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            image=None,
            json=True
        )
        
        # Capture output
        result = capture_cli_output(cmd_deploy_web, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Parse JSON output from stdout
        try:
            stdout_text = result['stdout'].strip()
            
            # Try to find JSON object/array in the output
            # JSON might be at the end after print statements
            json_start = None
            json_end = None
            
            # Look for first { or [
            for i, char in enumerate(stdout_text):
                if char == '{' or char == '[':
                    json_start = i
                    break
            
            if json_start is not None:
                # Find matching closing brace/bracket
                open_char = stdout_text[json_start]
                close_char = '}' if open_char == '{' else ']'
                depth = 0
                
                for i in range(json_start, len(stdout_text)):
                    if stdout_text[i] == open_char:
                        depth += 1
                    elif stdout_text[i] == close_char:
                        depth -= 1
                        if depth == 0:
                            json_end = i + 1
                            break
                
                if json_end:
                    json_str = stdout_text[json_start:json_end]
                    json_output = json.loads(json_str)
                    return json_output
            
            # If no JSON found, try parsing whole stdout
            json_output = json.loads(stdout_text)
            return json_output
        except json.JSONDecodeError:
            # If not JSON, return raw output
            return {
                'success': result['exit_code'] == 0,
                'output': result['stdout'],
                'error': result['stderr'] if result['stderr'] else None
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deploying web application: {str(e)}"
        )


@app.get("/v1/get-cicd/{repo}/{refs}")
async def get_cicd(
    repo: str,
    refs: str,
    username: str = Depends(verify_token)
):
    """Get cicd.json from Bitbucket repository."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            json=True
        )
        
        # Capture output
        result = capture_cli_output(cmd_get_cicd, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Parse JSON output from stdout
        try:
            output = json.loads(result['stdout'])
            return output
        except json.JSONDecodeError:
            # If not JSON, return raw output
            return {
                'success': False,
                'error': 'Failed to parse JSON response',
                'output': result['stdout'],
                'stderr': result['stderr'] if result['stderr'] else None
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching cicd.json: {str(e)}"
        )


@app.get("/v1/get-file/{repo}/{refs}")
async def get_file(
    repo: str,
    refs: str,
    file_path: str = Query(..., description="Path to file in repository"),
    username: str = Depends(verify_token)
):
    """Get file content from Bitbucket repository."""
    try:
        # Create args object
        args = create_args_object(
            repo=repo,
            refs=refs,
            file_path=file_path
        )
        
        # Capture output
        result = capture_cli_output(cmd_get_file, args)
        
        if result['exit_code'] != 0:
            # Parse error to get appropriate status code
            error_info = parse_error_response(result['stderr'], result['stdout'])
            raise HTTPException(
                status_code=error_info['status_code'],
                detail=build_cli_error_detail(result, error_info)
            )
        
        # Return file content
        return {
            'success': True,
            'repo': repo,
            'refs': refs,
            'file_path': file_path,
            'content': result['stdout']
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching file: {str(e)}"
        )


@app.post("/v1/gitops/create-branch")
async def gitops_create_branch(
    payload: GitOpsCreateBranchRequest,
    username: str = Depends(verify_token)
):
    """Create a new branch in Bitbucket repository."""
    args = create_args_object(
        repo=payload.repo,
        src_branch=payload.src_branch,
        dest_branch=payload.dest_branch
    )
    result = capture_cli_output(cmd_create_branch, args)
    if result['exit_code'] != 0:
        error_info = parse_error_response(result['stderr'], result['stdout'])
        raise HTTPException(
            status_code=error_info['status_code'],
            detail=build_cli_error_detail(result, error_info)
        )
    return build_cli_success_response(result)


@app.post("/v1/gitops/set-image-yaml")
async def gitops_set_image_yaml(
    payload: GitOpsSetImageYamlRequest,
    username: str = Depends(verify_token)
):
    """Update image reference inside YAML file in Bitbucket repository."""
    args = create_args_object(
        repo=payload.repo,
        refs=payload.refs,
        yaml_path=payload.yaml_path,
        image=payload.image,
        dry_run=payload.dry_run
    )
    result = capture_cli_output(cmd_set_image_yaml, args)
    if result['exit_code'] != 0:
        error_info = parse_error_response(result['stderr'], result['stdout'])
        raise HTTPException(
            status_code=error_info['status_code'],
            detail=build_cli_error_detail(result, error_info)
        )
    return build_cli_success_response(result)


@app.post("/v1/gitops/pull-request")
async def gitops_pull_request(
    payload: GitOpsPullRequest,
    username: str = Depends(verify_token)
):
    """Create a pull request in Bitbucket repository."""
    args = create_args_object(
        repo=payload.repo,
        src_branch=payload.src_branch,
        dest_branch=payload.dest_branch,
        delete=payload.delete_after_merge
    )
    result = capture_cli_output(cmd_pull_request, args)
    if result['exit_code'] != 0:
        error_info = parse_error_response(result['stderr'], result['stdout'])
        raise HTTPException(
            status_code=error_info['status_code'],
            detail=build_cli_error_detail(result, error_info)
        )
    return build_cli_success_response(result)


@app.get("/gitops", response_class=HTMLResponse)
async def gitops_dashboard():
    """GitOps Dashboard."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>GitOps Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 900px; 
            margin: 0 auto; 
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0;
            color: #333;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .user-info span {
            color: #666;
            font-size: 14px;
        }
        .logout-btn {
            padding: 8px 16px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .card { 
            background: white;
            border: 1px solid #ddd; 
            padding: 20px; 
            margin-bottom: 20px; 
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card h2 {
            margin-top: 0;
            margin-bottom: 15px;
            color: #333;
        }
        .form-group { margin-bottom: 15px; }
        label { 
            display: block; 
            margin-bottom: 5px; 
            font-weight: 500;
            color: #555;
        }
        input[type="text"], 
        input[type="password"] { 
            width: 100%; 
            padding: 10px; 
            box-sizing: border-box;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        input[type="text"]:focus,
        input[type="password"]:focus {
            outline: none;
            border-color: #007bff;
        }
        button { 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            border: none; 
            cursor: pointer;
            border-radius: 5px;
            font-size: 14px;
            font-weight: 500;
        }
        button:hover { background-color: #0056b3; }
        pre { 
            background: #f8f9fa; 
            padding: 15px; 
            overflow-x: auto;
            border-radius: 5px;
            border: 1px solid #e9ecef;
            font-size: 13px;
        }
        .hidden { display: none; }
        .token-section {
            background: #fff3cd;
            border: 1px solid #ffc107;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .token-section label {
            color: #856404;
        }
        .info-text {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
    <h1>GitOps Dashboard</h1>
        <div class="user-info">
            <span id="usernameDisplay">User</span>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
    </div>
    
    <div class="card token-section">
        <div class="form-group">
            <label>API Token (optional - will use saved token if available)</label>
            <input type="password" id="apiToken" placeholder="Enter Bearer Token or use saved token">
            <p class="info-text">If you're logged in, the saved token will be used automatically. You can override it here.</p>
        </div>
    </div>

    <div class="card">
        <h2>Create Branch</h2>
        <form id="createBranchForm">
            <div class="form-group"><label>Repo</label><input type="text" name="repo" required></div>
            <div class="form-group"><label>Source Branch</label><input type="text" name="src_branch" required></div>
            <div class="form-group"><label>Destination Branch</label><input type="text" name="dest_branch" required></div>
            <button type="submit">Create Branch</button>
        </form>
        <pre id="createBranchResult" class="hidden"></pre>
    </div>

    <div class="card">
        <h2>Set Image YAML</h2>
        <form id="setImageYamlForm">
            <div class="form-group"><label>Repo</label><input type="text" name="repo" required></div>
            <div class="form-group"><label>Refs</label><input type="text" name="refs" required></div>
            <div class="form-group"><label>YAML Path</label><input type="text" name="yaml_path" required></div>
            <div class="form-group"><label>Image</label><input type="text" name="image" required></div>
            <div class="form-group"><label><input type="checkbox" name="dry_run"> Dry Run</label></div>
            <button type="submit">Update YAML</button>
        </form>
        <pre id="setImageYamlResult" class="hidden"></pre>
    </div>

    <div class="card">
        <h2>Create Pull Request</h2>
        <form id="pullRequestForm">
            <div class="form-group"><label>Repo</label><input type="text" name="repo" required></div>
            <div class="form-group"><label>Source Branch</label><input type="text" name="src_branch" required></div>
            <div class="form-group"><label>Destination Branch</label><input type="text" name="dest_branch" required></div>
            <div class="form-group"><label><input type="checkbox" name="delete_after_merge"> Delete After Merge</label></div>
            <button type="submit">Create PR</button>
        </form>
        <pre id="pullRequestResult" class="hidden"></pre>
    </div>

    <div class="card">
        <h2>Merge Pull Request</h2>
        <form id="mergeForm">
            <div class="form-group"><label>PR URL</label><input type="text" name="pr_url" required></div>
            <div class="form-group"><label><input type="checkbox" name="delete_after_merge" checked> Delete After Merge</label></div>
            <button type="submit">Merge PR</button>
        </form>
        <pre id="mergeResult" class="hidden"></pre>
    </div>

    <script>
        // Initialize on page load - validate token
        window.addEventListener('DOMContentLoaded', async () => {
            const savedToken = localStorage.getItem('apiToken');
            const savedUsername = localStorage.getItem('username');
            
            // If no token, redirect to login immediately
            if (!savedToken) {
                window.location.href = '/login';
                return;
            }
            
            // Validate token
            try {
                const validateResponse = await fetch('/v1/validate-token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ token: savedToken })
                });
                
                const validateData = await validateResponse.json();
                
                if (!validateData.valid) {
                    // Token invalid, clear and redirect
                    localStorage.removeItem('apiToken');
                    localStorage.removeItem('username');
                    window.location.href = '/login';
                    return;
                }
                
                // Token is valid, proceed with initialization
                // Pre-fill token if available
                document.getElementById('apiToken').value = savedToken;
                
                if (savedUsername) {
                    document.getElementById('usernameDisplay').textContent = savedUsername;
                } else if (validateData.username) {
                    document.getElementById('usernameDisplay').textContent = validateData.username;
                    localStorage.setItem('username', validateData.username);
                }
            } catch (error) {
                // Error validating token, redirect to login
                console.error('Token validation error:', error);
                localStorage.removeItem('apiToken');
                localStorage.removeItem('username');
                window.location.href = '/login';
            }
        });
        
        function getToken() {
            const inputToken = document.getElementById('apiToken').value;
            const savedToken = localStorage.getItem('apiToken');
            
            // Use input token if provided, otherwise use saved token
            return inputToken || savedToken;
        }
        
        function logout() {
            if (confirm('Are you sure you want to logout?')) {
                localStorage.removeItem('apiToken');
                localStorage.removeItem('username');
                window.location.href = '/login';
            }
        }
        
        function sendRequest(endpoint, data, resultId) {
            const token = getToken();
            const resultEl = document.getElementById(resultId);
            
            if (!token) {
                alert('Please enter API Token or login first');
                return;
            }

            resultEl.textContent = 'Processing...';
            resultEl.classList.remove('hidden');

            fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + token
                },
                body: JSON.stringify(data)
            })
            .then(response => {
                if (response.status === 401) {
                    // Token invalid, clear and redirect
                    localStorage.removeItem('apiToken');
                    localStorage.removeItem('username');
                    alert('Session expired. Please login again.');
                    window.location.href = '/login';
                    return;
                }
                return response.json();
            })
            .then(data => {
                if (data) {
                resultEl.textContent = JSON.stringify(data, null, 2);
                }
            })
            .catch(error => {
                resultEl.textContent = 'Error: ' + error;
            });
        }

        document.getElementById('createBranchForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            sendRequest('/v1/gitops/create-branch', data, 'createBranchResult');
        });

        document.getElementById('setImageYamlForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            data.dry_run = e.target.querySelector('[name="dry_run"]').checked;
            sendRequest('/v1/gitops/set-image-yaml', data, 'setImageYamlResult');
        });

        document.getElementById('pullRequestForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            data.delete_after_merge = e.target.querySelector('[name="delete_after_merge"]').checked;
            sendRequest('/v1/gitops/pull-request', data, 'pullRequestResult');
        });

        document.getElementById('mergeForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            const data = Object.fromEntries(formData.entries());
            data.delete_after_merge = e.target.querySelector('[name="delete_after_merge"]').checked;
            sendRequest('/v1/gitops/merge', data, 'mergeResult');
        });
    </script>
</body>
</html>
"""


@app.post("/v1/gitops/merge")
async def gitops_merge(
    payload: GitOpsMergeRequest,
    username: str = Depends(verify_token)
):
    """Merge a pull request in Bitbucket repository."""
    args = create_args_object(
        pr_url=payload.pr_url,
        delete=payload.delete_after_merge
    )
    result = capture_cli_output(cmd_merge, args)
    if result['exit_code'] != 0:
        error_info = parse_error_response(result['stderr'], result['stdout'])
        raise HTTPException(
            status_code=error_info['status_code'],
            detail=build_cli_error_detail(result, error_info)
        )
    
    # Send Teams notification
    try:
        webhook_url = resolve_teams_webhook()
        if webhook_url:
            send_teams_notification(
                webhook_url=webhook_url,
                title="GitOps Merge Successful",
                facts=[
                    ("User", username),
                    ("PR URL", payload.pr_url),
                    ("Delete Branch", str(payload.delete_after_merge))
                ],
                success=True
            )
    except Exception as e:
        logger.warning(f"Failed to send Teams notification: {e}")

    return build_cli_success_response(result)


@app.get("/pr", response_class=HTMLResponse)
async def pr_form():
    """PR creation form page."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Create Pull Request - DevOps Tools</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            max-width: 900px; 
            margin: 0 auto; 
            padding: 20px;
            background: #f5f5f5;
        }
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 {
            margin: 0;
            color: #333;
        }
        .user-info {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .user-info span {
            color: #666;
            font-size: 14px;
        }
        .logout-btn {
            padding: 8px 16px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        .logout-btn:hover {
            background: #c82333;
        }
        .card { 
            background: white;
            border: 1px solid #ddd; 
            padding: 20px; 
            margin-bottom: 20px; 
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .card h2 {
            margin-top: 0;
            margin-bottom: 15px;
            color: #333;
        }
        .form-group { margin-bottom: 15px; }
        label { 
            display: block; 
            margin-bottom: 5px; 
            font-weight: 500;
            color: #555;
        }
        input[type="text"] { 
            width: 100%; 
            padding: 10px; 
            box-sizing: border-box;
            border: 2px solid #ddd;
            border-radius: 5px;
            font-size: 14px;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #007bff;
        }
        button { 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            border: none; 
            cursor: pointer;
            border-radius: 5px;
            font-size: 14px;
            font-weight: 500;
        }
        button:hover { background-color: #0056b3; }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .progress {
            margin-top: 20px;
        }
        .progress-step {
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 5px;
            border-left: 4px solid #ddd;
        }
        .progress-step.pending {
            background: #f8f9fa;
            border-left-color: #6c757d;
        }
        .progress-step.processing {
            background: #fff3cd;
            border-left-color: #ffc107;
        }
        .progress-step.success {
            background: #d4edda;
            border-left-color: #28a745;
        }
        .progress-step.error {
            background: #f8d7da;
            border-left-color: #dc3545;
        }
        .progress-step h3 {
            margin: 0 0 5px 0;
            font-size: 14px;
            font-weight: 600;
        }
        .progress-step p {
            margin: 0;
            font-size: 12px;
            color: #666;
        }
        .result {
            margin-top: 20px;
            padding: 15px;
            border-radius: 5px;
            display: none;
        }
        .result.success {
            background: #d4edda;
            border: 1px solid #28a745;
            color: #155724;
        }
        .result.error {
            background: #f8d7da;
            border: 1px solid #dc3545;
            color: #721c24;
        }
        .result.show {
            display: block;
        }
        .pr-url {
            margin-top: 10px;
            font-weight: 600;
        }
        .pr-url a {
            color: #007bff;
            text-decoration: none;
        }
        .pr-url a:hover {
            text-decoration: underline;
        }
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>Create Pull Request</h1>
        <div class="user-info">
            <span id="usernameDisplay">User</span>
            <button class="logout-btn" onclick="logout()">Logout</button>
        </div>
    </div>
    
    <div class="card">
        <h2>Deployment Information</h2>
        <form id="prForm" onsubmit="handleSubmit(event)">
            <div class="form-group">
                <label for="cluster">Cluster</label>
                <input type="text" id="cluster" name="cluster" placeholder="e.g., master, staging" required>
            </div>
            <div class="form-group">
                <label for="ns">Namespace</label>
                <input type="text" id="ns" name="ns" placeholder="e.g., staging-qoinplus" required>
            </div>
            <div class="form-group">
                <label for="deployment">Deployment</label>
                <input type="text" id="deployment" name="deployment" placeholder="e.g., plus-apigateway" required>
            </div>
            <div class="form-group">
                <label for="image">Image</label>
                <input type="text" id="image" name="image" placeholder="e.g., loyaltolpi/plus-apigateway:98bccc93-test1" required>
            </div>
            <button type="submit" id="submitBtn">Create Pull Request</button>
        </form>
        
        <div class="progress hidden" id="progress">
            <div class="progress-step pending" id="step1">
                <h3>Step 1: Create Branch</h3>
                <p>Waiting...</p>
            </div>
            <div class="progress-step pending" id="step2">
                <h3>Step 2: Set Image YAML</h3>
                <p>Waiting...</p>
            </div>
            <div class="progress-step pending" id="step3">
                <h3>Step 3: Create Pull Request</h3>
                <p>Waiting...</p>
            </div>
        </div>
        
        <div class="result" id="result">
            <div id="resultContent"></div>
        </div>
    </div>
    
    <script>
        // Initialize on page load - validate token
        window.addEventListener('DOMContentLoaded', async () => {
            const savedToken = localStorage.getItem('apiToken');
            const savedUsername = localStorage.getItem('username');
            
            // If no token, redirect to login immediately
            if (!savedToken) {
                window.location.href = '/login';
                return;
            }
            
            // Validate token
            try {
                const validateResponse = await fetch('/v1/validate-token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ token: savedToken })
                });
                
                const validateData = await validateResponse.json();
                
                if (!validateData.valid) {
                    // Token invalid, clear and redirect
                    localStorage.removeItem('apiToken');
                    localStorage.removeItem('username');
                    window.location.href = '/login';
                    return;
                }
                
                // Token is valid, proceed with initialization
                if (savedUsername) {
                    document.getElementById('usernameDisplay').textContent = savedUsername;
                } else if (validateData.username) {
                    document.getElementById('usernameDisplay').textContent = validateData.username;
                    localStorage.setItem('username', validateData.username);
                }
            } catch (error) {
                // Error validating token, redirect to login
                console.error('Token validation error:', error);
                localStorage.removeItem('apiToken');
                localStorage.removeItem('username');
                window.location.href = '/login';
            }
        });
        
        function logout() {
            if (confirm('Are you sure you want to logout?')) {
                localStorage.removeItem('apiToken');
                localStorage.removeItem('username');
                window.location.href = '/login';
            }
        }
        
        function updateStep(stepNum, status, message) {
            const step = document.getElementById(`step${stepNum}`);
            step.className = `progress-step ${status}`;
            step.querySelector('p').textContent = message;
        }
        
        async function handleSubmit(event) {
            event.preventDefault();
            
            const savedToken = localStorage.getItem('apiToken');
            if (!savedToken) {
                alert('Please login first');
                window.location.href = '/login';
                return;
            }
            
            const form = event.target;
            const submitBtn = document.getElementById('submitBtn');
            const progress = document.getElementById('progress');
            const result = document.getElementById('result');
            const resultContent = document.getElementById('resultContent');
            
            // Get form data
            const formData = new FormData(form);
            const data = {
                cluster: formData.get('cluster'),
                ns: formData.get('ns'),
                deployment: formData.get('deployment'),
                image: formData.get('image')
            };
            
            // Reset UI
            submitBtn.disabled = true;
            submitBtn.textContent = 'Processing...';
            progress.classList.remove('hidden');
            result.classList.remove('show');
            updateStep(1, 'pending', 'Waiting...');
            updateStep(2, 'pending', 'Waiting...');
            updateStep(3, 'pending', 'Waiting...');
            
            try {
                const response = await fetch('/pr', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + savedToken
                    },
                    body: JSON.stringify(data)
                });
                
                if (response.status === 401) {
                    localStorage.removeItem('apiToken');
                    localStorage.removeItem('username');
                    alert('Session expired. Please login again.');
                    window.location.href = '/login';
                    return;
                }
                
                const resultData = await response.json();
                
                // Update progress based on result
                if (resultData.steps) {
                    if (resultData.steps.create_branch) {
                        const step1 = resultData.steps.create_branch;
                        updateStep(1, step1.status === 'success' ? 'success' : 'error', 
                            step1.status === 'success' ? 'Branch created successfully' : step1.error || 'Failed');
                    }
                    if (resultData.steps.set_image_yaml) {
                        const step2 = resultData.steps.set_image_yaml;
                        updateStep(2, step2.status === 'success' ? 'success' : 'error',
                            step2.status === 'success' ? 'Image updated successfully' : step2.error || 'Failed');
                    }
                    if (resultData.steps.pull_request) {
                        const step3 = resultData.steps.pull_request;
                        updateStep(3, step3.status === 'success' ? 'success' : 'error',
                            step3.status === 'success' ? 'Pull request created successfully' : step3.error || 'Failed');
                    }
                }
                
                // Show result
                if (resultData.success) {
                    result.className = 'result success show';
                    let html = '<strong>✅ All steps completed successfully!</strong>';
                    if (resultData.pr_url) {
                        html += `<div class="pr-url">Pull Request URL: <a href="${resultData.pr_url}" target="_blank">${resultData.pr_url}</a></div>`;
                    }
                    resultContent.innerHTML = html;
                } else {
                    result.className = 'result error show';
                    let html = '<strong>❌ Error occurred during processing</strong>';
                    if (resultData.error) {
                        html += `<p>${resultData.error}</p>`;
                    }
                    resultContent.innerHTML = html;
                }
                
            } catch (error) {
                result.className = 'result error show';
                resultContent.innerHTML = `<strong>❌ Error:</strong> <p>${error.message}</p>`;
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Create Pull Request';
            }
        }
    </script>
</body>
</html>
"""


@app.post("/pr")
async def create_pr(
    payload: PRRequest,
    username: str = Depends(verify_token)
):
    """Create PR workflow: create-branch, set-image-yaml, pull-request."""
    logger.info("=" * 80)
    logger.info("POST /pr - Starting PR creation workflow")
    logger.info(f"User: {username}")
    logger.info(f"Request payload: cluster={payload.cluster}, ns={payload.ns}, "
                f"deployment={payload.deployment}, image={payload.image}")
    
    repo = "gitops-k8s"
    yaml_path = f"{payload.ns}/{payload.deployment}_deployment.yaml"
    
    logger.debug(f"Generated yaml_path: {yaml_path}")
    logger.debug(f"Repository: {repo}")
    
    response = {
        "success": False,
        "steps": {},
        "pr_url": None,
        "error": None
    }
    
    # Step 1: Create Branch
    logger.info("-" * 80)
    logger.info("STEP 1: Create Branch")
    logger.info(f"  Repository: {repo}")
    logger.info(f"  Source branch: {payload.cluster}")
    logger.info(f"  Destination branch: {yaml_path}")
    
    try:
        args = create_args_object(
            repo=repo,
            src_branch=payload.cluster,
            dest_branch=yaml_path
        )
        logger.debug(f"  Args object created: repo={args.repo}, src_branch={args.src_branch}, "
                    f"dest_branch={args.dest_branch}")
        
        logger.debug("  Executing cmd_create_branch...")
        result = capture_cli_output(cmd_create_branch, args)
        
        logger.debug(f"  Command exit code: {result['exit_code']}")
        logger.debug(f"  Command stdout length: {len(result.get('stdout', ''))} chars")
        logger.debug(f"  Command stderr length: {len(result.get('stderr', ''))} chars")
        
        if result['exit_code'] != 0:
            # Check if error is "branch already exists"
            stderr_text = result.get('stderr', '').lower()
            stdout_text = result.get('stdout', '').lower()
            error_text = (stderr_text + ' ' + stdout_text).lower()
            
            is_branch_exists = (
                'already exists' in error_text or
                'destination branch' in error_text and 'already' in error_text
            )
            
            if is_branch_exists:
                logger.warning(f"  ⚠️  Step 1 - Branch already exists (this is OK, continuing...)")
                logger.warning(f"  Stderr: {result.get('stderr', '')[:300]}")
                logger.info(f"  ✅ Step 1 CONTINUED (branch exists, will reuse existing branch)")
                logger.debug(f"  Output: {result.get('stdout', '')[:200]}...")
                
                response['steps']['create_branch'] = {
                    "status": "success",
                    "output": result.get('stdout', ''),
                    "message": "Branch already exists, reusing existing branch"
                }
            else:
                logger.error(f"  ❌ Step 1 FAILED - Exit code: {result['exit_code']}")
                logger.error(f"  Stderr: {result.get('stderr', '')[:500]}")
                logger.error(f"  Stdout: {result.get('stdout', '')[:500]}")
                
                error_info = parse_error_response(result['stderr'], result['stdout'])
                logger.error(f"  Parsed error: {error_info.get('error', 'Unknown error')}")
                
                response['steps']['create_branch'] = {
                    "status": "error",
                    "output": result.get('stdout', ''),
                    "error": error_info.get('error', 'Failed to create branch')
                }
                response['error'] = f"Step 1 (create-branch) failed: {error_info.get('error', 'Unknown error')}"
                logger.error(f"Workflow ABORTED at Step 1")
                return response
        else:
            logger.info(f"  ✅ Step 1 SUCCESS")
            logger.debug(f"  Output: {result.get('stdout', '')[:200]}...")
            response['steps']['create_branch'] = {
                "status": "success",
                "output": result.get('stdout', '')
            }
    except Exception as e:
        logger.exception(f"  ❌ Step 1 EXCEPTION: {str(e)}")
        response['steps']['create_branch'] = {
            "status": "error",
            "error": str(e)
        }
        response['error'] = f"Step 1 (create-branch) failed: {str(e)}"
        logger.error(f"Workflow ABORTED at Step 1 due to exception")
        return response
    
    # Step 2: Set Image YAML
    logger.info("-" * 80)
    logger.info("STEP 2: Set Image YAML")
    logger.info(f"  Repository: {repo}")
    logger.info(f"  Refs (branch): {yaml_path}")
    logger.info(f"  YAML Path: {yaml_path}")
    logger.info(f"  Image: {payload.image}")
    logger.info(f"  Dry run: False")
    
    try:
        args = create_args_object(
            repo=repo,
            refs=yaml_path,
            yaml_path=yaml_path,
            image=payload.image,
            dry_run=False
        )
        logger.debug(f"  Args object created: repo={args.repo}, refs={args.refs}, "
                    f"yaml_path={args.yaml_path}, image={args.image}, dry_run={args.dry_run}")
        
        logger.debug("  Executing cmd_set_image_yaml...")
        result = capture_cli_output(cmd_set_image_yaml, args)
        
        logger.debug(f"  Command exit code: {result['exit_code']}")
        logger.debug(f"  Command stdout length: {len(result.get('stdout', ''))} chars")
        logger.debug(f"  Command stderr length: {len(result.get('stderr', ''))} chars")
        
        # Log full output for debugging (truncated if too long)
        if result.get('stdout'):
            stdout_preview = result.get('stdout', '')[:1000] if len(result.get('stdout', '')) > 1000 else result.get('stdout', '')
            logger.debug(f"  Command stdout preview:\n{stdout_preview}")
        if result.get('stderr'):
            stderr_preview = result.get('stderr', '')[:1000] if len(result.get('stderr', '')) > 1000 else result.get('stderr', '')
            logger.debug(f"  Command stderr preview:\n{stderr_preview}")
        
        if result['exit_code'] != 0:
            logger.error(f"  ❌ Step 2 FAILED - Exit code: {result['exit_code']}")
            logger.error(f"  Stderr: {result.get('stderr', '')[:500]}")
            logger.error(f"  Stdout: {result.get('stdout', '')[:500]}")
            
            error_info = parse_error_response(result['stderr'], result['stdout'])
            logger.error(f"  Parsed error: {error_info.get('error', 'Unknown error')}")
            
            response['steps']['set_image_yaml'] = {
                "status": "error",
                "output": result.get('stdout', ''),
                "error": error_info.get('error', 'Failed to update image')
            }
            response['error'] = f"Step 2 (set-image-yaml) failed: {error_info.get('error', 'Unknown error')}"
            logger.error(f"Workflow ABORTED at Step 2")
            return response
        else:
            logger.info(f"  ✅ Step 2 SUCCESS")
            logger.debug(f"  Output: {result.get('stdout', '')[:200]}...")
            response['steps']['set_image_yaml'] = {
                "status": "success",
                "output": result.get('stdout', '')
            }
    except Exception as e:
        logger.exception(f"  ❌ Step 2 EXCEPTION: {str(e)}")
        response['steps']['set_image_yaml'] = {
            "status": "error",
            "error": str(e)
        }
        response['error'] = f"Step 2 (set-image-yaml) failed: {str(e)}"
        logger.error(f"Workflow ABORTED at Step 2 due to exception")
        return response
    
    # Step 3: Create Pull Request
    logger.info("-" * 80)
    logger.info("STEP 3: Create Pull Request")
    logger.info(f"  Repository: {repo}")
    logger.info(f"  Source branch: {yaml_path}")
    logger.info(f"  Destination branch: {payload.cluster}")
    logger.info(f"  Delete after merge: True")
    
    try:
        args = create_args_object(
            repo=repo,
            src_branch=yaml_path,
            dest_branch=payload.cluster,
            delete=True  # delete_after_merge
        )
        logger.debug(f"  Args object created: repo={args.repo}, src_branch={args.src_branch}, "
                    f"dest_branch={args.dest_branch}, delete={args.delete}")
        
        logger.debug("  Executing cmd_pull_request...")
        result = capture_cli_output(cmd_pull_request, args)
        
        logger.debug(f"  Command exit code: {result['exit_code']}")
        logger.debug(f"  Command stdout length: {len(result.get('stdout', ''))} chars")
        logger.debug(f"  Command stderr length: {len(result.get('stderr', ''))} chars")
        
        if result['exit_code'] != 0:
            logger.error(f"  ❌ Step 3 FAILED - Exit code: {result['exit_code']}")
            logger.error(f"  Stderr: {result.get('stderr', '')[:500]}")
            logger.error(f"  Stdout: {result.get('stdout', '')[:500]}")
            
            error_info = parse_error_response(result['stderr'], result['stdout'])
            logger.error(f"  Parsed error: {error_info.get('error', 'Unknown error')}")
            
            response['steps']['pull_request'] = {
                "status": "error",
                "output": result.get('stdout', ''),
                "error": error_info.get('error', 'Failed to create pull request')
            }
            response['error'] = f"Step 3 (pull-request) failed: {error_info.get('error', 'Unknown error')}"
            logger.error(f"Workflow ABORTED at Step 3")
            return response
        else:
            logger.info(f"  ✅ Step 3 SUCCESS")
            logger.debug(f"  Full stdout: {result.get('stdout', '')}")
            
            # Extract PR URL from stdout
            pr_url = extract_pr_url(result.get('stdout', ''))
            if pr_url:
                logger.info(f"  📎 PR URL extracted: {pr_url}")
            else:
                logger.warning(f"  ⚠️  Could not extract PR URL from stdout")
                logger.debug(f"  Attempting to extract from full output...")
            
            response['steps']['pull_request'] = {
                "status": "success",
                "output": result.get('stdout', ''),
                "pr_url": pr_url
            }
            response['pr_url'] = pr_url
            response['success'] = True
    except Exception as e:
        logger.exception(f"  ❌ Step 3 EXCEPTION: {str(e)}")
        response['steps']['pull_request'] = {
            "status": "error",
            "error": str(e)
        }
        response['error'] = f"Step 3 (pull-request) failed: {str(e)}"
        logger.error(f"Workflow ABORTED at Step 3 due to exception")
        return response
    
    # Final summary
    logger.info("=" * 80)
    if response['success']:
        logger.info("✅ PR CREATION WORKFLOW COMPLETED SUCCESSFULLY")
        logger.info(f"   PR URL: {response.get('pr_url', 'N/A')}")
    else:
        logger.error("❌ PR CREATION WORKFLOW FAILED")
        logger.error(f"   Error: {response.get('error', 'Unknown error')}")
    logger.info("=" * 80)
    
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Login page with token only."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>DevOps Tools - Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .login-container {
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            padding: 40px;
            max-width: 450px;
            width: 100%;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            text-align: center;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="password"] {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="password"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .login-btn {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .login-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .login-btn:active {
            transform: translateY(0);
        }
        .login-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .error-message {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: none;
            font-size: 14px;
        }
        .success-message {
            background: #efe;
            color: #3c3;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
            display: none;
            font-size: 14px;
        }
        .info-text {
            font-size: 12px;
            color: #999;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>DevOps Tools</h1>
        <p class="subtitle">Login with Rancher Token</p>
        
        <div class="error-message" id="errorMessage"></div>
        <div class="success-message" id="successMessage"></div>
        
        <form id="loginForm" onsubmit="handleLogin(event)">
            <div class="form-group">
                <label for="token">Rancher Token</label>
                <input type="password" id="token" name="token" placeholder="Enter your Rancher token" required>
                <p class="info-text">Token from ~/.doq/.env (RANCHER_TOKEN) or any valid Rancher token</p>
            </div>
            
            <button type="submit" class="login-btn" id="loginBtn">
                Login
            </button>
        </form>
    </div>
    
    <script>
        function showError(message) {
            const errorEl = document.getElementById('errorMessage');
            errorEl.textContent = message;
            errorEl.style.display = 'block';
            document.getElementById('successMessage').style.display = 'none';
        }
        
        function showSuccess(message) {
            const successEl = document.getElementById('successMessage');
            successEl.textContent = message;
            successEl.style.display = 'block';
            document.getElementById('errorMessage').style.display = 'none';
        }
        
        function hideMessages() {
            document.getElementById('errorMessage').style.display = 'none';
            document.getElementById('successMessage').style.display = 'none';
        }
        
        async function handleLogin(event) {
            event.preventDefault();
            hideMessages();
            
            const loginBtn = document.getElementById('loginBtn');
            loginBtn.disabled = true;
            loginBtn.textContent = 'Validating token...';
            
            const token = document.getElementById('token').value;
            
            if (!token) {
                showError('Please enter a token');
                loginBtn.disabled = false;
                loginBtn.textContent = 'Login';
                return;
            }
            
            try {
                // First validate the token
                const validateResponse = await fetch('/v1/validate-token', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ token })
                });
                
                const validateData = await validateResponse.json();
                
                if (!validateData.valid) {
                    showError('Invalid token: ' + (validateData.error || 'Token validation failed'));
                    loginBtn.disabled = false;
                    loginBtn.textContent = 'Login';
                    return;
                }
                
                // Token is valid, proceed with login
                loginBtn.textContent = 'Logging in...';
                
                const response = await fetch('/v1/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ token })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    showError(data.detail || 'Login failed');
                    loginBtn.disabled = false;
                    loginBtn.textContent = 'Login';
                    return;
                }
                
                // Store token in localStorage
                localStorage.setItem('apiToken', data.token);
                localStorage.setItem('username', data.username || 'user');
                
                showSuccess('Login successful! Redirecting to GitOps Dashboard...');
                
                // Redirect to GitOps dashboard after 1 second
                setTimeout(() => {
                    window.location.href = '/gitops';
                }, 1000);
                
            } catch (error) {
                showError('Login error: ' + error.message);
                loginBtn.disabled = false;
                loginBtn.textContent = 'Login';
            }
        }
        
        // Check if already logged in
        window.addEventListener('DOMContentLoaded', () => {
            const token = localStorage.getItem('apiToken');
            if (token) {
                // Optionally validate and redirect
                showSuccess('You are already logged in. Redirecting...');
                setTimeout(() => {
                    window.location.href = '/gitops';
                }, 1000);
            }
        });
    </script>
</body>
</html>
"""


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "DevOps Tools API",
        "version": "1.0.0",
        "docs": "/docs",
        "login": "/login",
        "gitops": "/gitops"
    }


def main():
    """Run the API server."""
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=9876,
        reload=False
    )


if __name__ == "__main__":
    main()

