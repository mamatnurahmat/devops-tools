# DevOps Tools API Server

## Overview
The DevOps Tools API Server wraps existing `doq` CLI capabilities into a FastAPI web service. It exposes authentication, CI/CD, deployment, and GitOps workflows through REST endpoints and serves interactive Swagger documentation at `/docs`.

## Features
- Rancher login flow with session tokens (in-memory store)
- Direct Rancher token validation (use Rancher token as Bearer token)
- CI pipeline actions: image build, deployment to Kubernetes and web targets
- GitOps utilities: create branch, update YAML image, create and merge pull requests
- Bitbucket helpers to fetch CICD configuration and arbitrary repository files

## Requirements
- Python 3.8+
- Dependencies listed in `pyproject.toml` (FastAPI, Uvicorn, etc.). Install with `pip install -e .` or your preferred manager.
- `~/.doq/.env` configured with Rancher connection info (`RANCHER_URL`, `RANCHER_INSECURE`, optional `RANCHER_TOKEN`).
- `~/.doq/auth.json` containing Bitbucket credentials (`GIT_USER`, `GIT_PASSWORD`) for GitOps operations.

## Running the Server
```bash
# Start via doq CLI
poetry run doq serve  # adjust command per your environment

# Or directly with uvicorn
uvicorn api_server:app --host 0.0.0.0 --port 9876
```

Visit `http://<host>:9876/docs` for Swagger UI or `http://<host>:9876/redoc` for ReDoc.

## Authentication
### Login Endpoint
`POST /v1/login`
```json
{
  "username": "rancher_user",
  "password": "rancher_password"
}
```
Response:
```json
{
  "token": "<uuid>",
  "expires_in": 3600
}
```
Use the returned token as `Authorization: Bearer <token>`. Tokens are stored in-memory and expire after one hour.

### Rancher Token Shortcut
Instead of logging in, you can supply an existing Rancher API token in the Bearer header. The server validates it against the configured Rancher endpoint on every request.

```
Authorization: Bearer token-xxxx:abcdef...
```

## Endpoint Summary
| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/login` | Authenticate against Rancher and obtain session token |
| GET | `/v1/image/{repo}/{refs}` | Check Docker image readiness |
| GET | `/v1/devops-ci/{repo}/{refs}` | Build Docker image via CI pipeline |
| GET | `/v1/deploy-k8s/{repo}/{refs}` | Deploy application to Kubernetes |
| GET | `/v1/deploy-web/{repo}/{refs}` | Deploy web application via SSH/docker compose |
| GET | `/v1/get-cicd/{repo}/{refs}` | Retrieve `cicd.json` from Bitbucket |
| GET | `/v1/get-file/{repo}/{refs}?file_path=...` | Download arbitrary file from repo |
| POST | `/v1/gitops/create-branch` | Create new branch in Bitbucket |
| POST | `/v1/gitops/set-image-yaml` | Update image tag inside YAML file |
| POST | `/v1/gitops/pull-request` | Open pull request between branches |
| POST | `/v1/gitops/merge` | Merge pull request by URL |

### GitOps Payloads
#### Create Branch
```json
{
  "repo": "saas-apigateway",
  "src_branch": "develop",
  "dest_branch": "feature/x"
}
```

#### Set Image YAML
```json
{
  "repo": "saas-apigateway",
  "refs": "develop",
  "yaml_path": "k8s/deployment.yaml",
  "image": "loyaltolpi/saas-apigateway:abcdef1",
  "dry_run": false
}
```

#### Pull Request
```json
{
  "repo": "saas-apigateway",
  "src_branch": "feature/x",
  "dest_branch": "develop",
  "delete_after_merge": false
}
```

#### Merge Pull Request
```json
{
  "pr_url": "https://bitbucket.org/org/repo/pull-requests/123",
  "delete_after_merge": true
}
```

## Error Handling
Errors from CLI executions are parsed into structured JSON. Example:
```json
{
  "success": false,
  "error": "❌ Error: Destination branch 'feature/x' already exists...",
  "error_type": "conflict",
  "details": {
    "stderr": "❌ Error: ...",
    "stdout": ""
  }
}
```

Status codes map to common scenarios:
- `400` validation issues / missing parameters
- `401` invalid Bearer token or authentication failures
- `404` missing files or resources (`cicd.json` absent, branch not found)
- `409` conflicts (branch already exists, etc.)
- `500` unexpected execution errors

## Operational Notes
- Tokens stored in-memory—restart clears sessions.
- CLI commands rely on external tools (git, docker, kubectl). Ensure they are available in the runtime environment.
- Logging currently mirrors CLI standard output; consider wrapping with structured logging for production deployments.

## Extending the API
- Add new CLI functionality in `doq.py` or plugins.
- Expose via FastAPI by importing the command function, defining a Pydantic model, and creating an endpoint that calls `capture_cli_output` with appropriate arguments.
- Reuse `parse_error_response`, `build_cli_success_response`, and `build_cli_error_detail` for consistent responses.

