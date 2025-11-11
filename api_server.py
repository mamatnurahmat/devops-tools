#!/usr/bin/env python3
"""FastAPI Web Server for DevOps Tools."""
import sys
import io
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional
from contextlib import redirect_stdout, redirect_stderr

from fastapi import FastAPI, HTTPException, Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from rancher_api import login as rancher_login, RancherAPI
from config import load_config

# Import CLI functions
from plugins.docker_utils import cmd_images, cmd_get_cicd, cmd_get_file
from plugins.devops_ci import cmd_devops_ci
from plugins.k8s_deployer import cmd_deploy_k8s
from plugins.web_deployer import cmd_deploy_web
from doq import cmd_create_branch, cmd_pull_request, cmd_merge, cmd_set_image_yaml


# In-memory token store
token_store: dict[str, dict] = {}

# Token expiry time (1 hour)
TOKEN_EXPIRY_SECONDS = 3600

# Security scheme
security = HTTPBearer()


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model."""
    token: str
    expires_in: int


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


def cleanup_expired_tokens():
    """Remove expired tokens from store."""
    now = datetime.now()
    expired_tokens = [
        token for token, data in token_store.items()
        if data.get('expires_at', now) < now
    ]
    for token in expired_tokens:
        del token_store[token]


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify Bearer token (from login or Rancher token directly)."""
    token = credentials.credentials

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
        config = load_config()
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


# FastAPI app
app = FastAPI(
    title="DevOps Tools API",
    description="API server for DevOps CI/CD operations",
    version="1.0.0"
)


@app.post("/v1/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login to Rancher API and get authentication token."""
    try:
        # Load Rancher config
        config = load_config()
        rancher_url = config.get('url')
        insecure = config.get('insecure', True)
        
        if not rancher_url:
            raise HTTPException(
                status_code=500,
                detail="RANCHER_URL not configured in ~/.doq/.env"
            )
        
        # Login to Rancher API
        rancher_token = rancher_login(
            url=rancher_url,
            username=request.username,
            password=request.password,
            insecure=insecure
        )
        
        # Generate API token
        api_token = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(seconds=TOKEN_EXPIRY_SECONDS)
        
        # Store token
        token_store[api_token] = {
            'username': request.username,
            'rancher_token': rancher_token,
            'created_at': datetime.now(),
            'expires_at': expires_at
        }
        
        return LoginResponse(
            token=api_token,
            expires_in=TOKEN_EXPIRY_SECONDS
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )
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
    return build_cli_success_response(result)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "DevOps Tools API",
        "version": "1.0.0",
        "docs": "/docs"
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

