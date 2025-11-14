# DevOps Q - AI Coding Agent Guide

## Project Overview

**DevOps Q** (`doq`) is a comprehensive CLI tool for managing Rancher resources, Docker image building, and multi-environment application deployment. It's built around a plugin architecture and integrates with Bitbucket, Docker Hub, Kubernetes, and SSH-based deployment.

### Big Picture Architecture

```
┌─────────────────────────────────────────┐
│         doq CLI (doq.py)                │
│    Main entry point, argparse setup     │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌──────────────┐  ┌─────────────────┐
│ RancherAPI   │  │ PluginManager   │
│ kubernetes   │  │ (devops-ci,     │
│ management   │  │  docker-utils,  │
│              │  │  web-deployer,  │
│              │  │  k8s-deployer)  │
└──────────────┘  └────────┬────────┘
                           │
         ┌─────────────────┴──────────────┐
         │                                │
         ▼                                ▼
    ┌──────────────────┐    ┌─────────────────────┐
    │ Bitbucket API    │    │ shared_helpers.py   │
    │ fetch files,     │    │ (auth, docker,      │
    │ get commits,     │    │  notifications)     │
    │ manage repos     │    └─────────────────────┘
    └──────────────────┘

Config Flow:
~/.doq/
├── auth.json          (credentials: GIT_USER, GIT_PASSWORD, DOCKERHUB_*)
├── .env               (core CLI config: Rancher URL, token)
└── plugins/
    ├── devops-ci.json
    ├── docker-utils.json
    ├── web-deployer.json
    └── k8s-deployer.json
```

### Key Service Boundaries

1. **Rancher Integration** (`rancher_api.py`)
   - Manages Kubernetes contexts and cluster operations
   - Handles kube-config generation and token validation

2. **DevOps CI/CD** (`plugins/devops_ci.py`)
   - Dual-mode operation: API mode (default) or Helper mode (no API)
   - Builds Docker images with SBOM, provenance, resource limits
   - Two authentication paths: Bitbucket for source repos, Docker Hub for registry

3. **Deployment Orchestration** (`plugins/web_deployer.py`, `plugins/k8s_deployer.py`)
   - Web: Docker Compose over SSH to remote servers
   - Kubernetes: Image updates via kubectl with context switching
   - Both use commit hash to image tag logic via `doq image` command

4. **Shared Utilities** (`plugins/shared_helpers.py`)
   - Centralized auth loading (from `~/.doq/auth.json`, `~/.netrc`, env vars)
   - Docker Hub image existence checking (JWT token + tag lookup)
   - Bitbucket API interactions (branches, tags, file fetching)
   - Teams webhook notifications

## Critical Developer Workflows

### Build and Test Commands

```bash
# Run CLI directly
python3 -m doq --help

# Run specific plugin tests
python3 -m pytest plugins/tests/ -v

# Check for errors (no formal test suite, but plugins are testable)
python3 -c "from plugins import devops_ci; devops_ci.show_help()"
```

### Installation and Development

```bash
# Install in editable mode
uv pip install -e .
# or
pip install -e .

# Update after code changes
./install.sh
```

### Common Debugging Patterns

- **Auth Issues**: Check `~/.doq/auth.json` (GIT_USER, GIT_PASSWORD, DOCKERHUB_USER, DOCKERHUB_PASSWORD)
- **Docker Build Failures**: See `plugins/devops_ci.py` for builder setup logic; common issue: Docker attestation support
- **Deployment Failures**: Check namespace format (`{refs}-{project}`), image existence via `doq image`, and kubectl context
- **SSH Deployment Issues**: Verify SSH key at `~/.ssh/id_rsa`, devops user permissions on target host

### Key Commands for Development

```bash
# List all available commands
doq --help

# Check auth setup
doq check

# Verify image exists
doq image saas-apigateway develop

# Dry-run deployments with --json for inspection
doq deploy-web saas-fe develop --json
doq deploy-k8s saas-apigateway develop --json
```

## Project-Specific Conventions

### Configuration Management

**Priority Order** (highest → lowest):
1. CLI arguments (`--image-name`, `--registry`, `--port`)
2. Environment variables (e.g., `DEFAULT_MEMORY=4g`, `DEVOPS_CI_MODE=helper`)
3. Plugin config files (`~/.doq/plugins/*.json`)
4. Hardcoded defaults in code

**Example**: DevOps CI builder memory
```python
# In devops_ci.py:
memory = get_env_override("DEFAULT_MEMORY") or config.get("builder", {}).get("memory", "2g")
```

### Image Naming Convention

```
Format: {namespace}/{repo}:{tag}
Example: loyaltolpi/saas-apigateway:660cbcf
         └─ namespace (from config)
                      └─ repo name (input)
                                   └─ short commit hash (from Bitbucket)
```

**Helper Mode Template** (no API dependency):
```
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{short_hash}
# Variables: {repo}, {refs}, {timestamp}, {short_hash}
```

### Namespace Convention for Deployments

```
Format: {refs}-{project}
Example: develop-saas (refs=develop, project=saas)
         staging-saas
         production-saas
```

Used in:
- Kubernetes context switching (`doq ns develop-saas`)
- Deployment lookups in `deploy-k8s.py`

### Error Handling Pattern

```python
# Consistent exit codes
sys.exit(0)  # success
sys.exit(1)  # error/failure

# Consistent error output to stderr
print(f"❌ Error: {message}", file=sys.stderr)

# JSON error responses (for --json mode)
{
  "status": "error",
  "message": "specific error details",
  "error": "error_code"
}
```

### Authentication Pattern

```python
# From shared_helpers.py - three-level fallback:
auth = load_auth_file()  # Try ~/.doq/auth.json first
auth = auth or _load_auth_from_docker()  # Fallback to ~/.docker/config.json
auth = auth or _load_auth_from_netrc()   # Fallback to ~/.netrc
auth = auth or _load_auth_from_env()     # Fallback to env vars

# Required keys: GIT_USER, GIT_PASSWORD, DOCKERHUB_USER, DOCKERHUB_PASSWORD
```

## Integration Points and Cross-Component Communication

### 1. Bitbucket → Docker Build Flow

```python
# plugins/devops_ci.py:
1. get_commit_hash_from_bitbucket(repo, refs)  # Get short hash
2. Construct image: {namespace}/{repo}:{hash}
3. check_docker_image_exists(image)            # Skip if ready
4. fetch_bitbucket_file(repo, refs, "cicd/cicd.json")  # Get build config
5. Run docker buildx with config from cicd.json
```

### 2. Image Check → Deployment Flow

```python
# plugins/deploy_k8s.py, plugins/web_deployer.py:
1. doq image {repo} {refs} --json            # Check if image exists
2. If ready: Extract image name
3. Get current deployment image via kubectl
4. Compare: if different → update deployment
5. If same → Skip (smart deployment)
```

### 3. Kubernetes Context Switching

```python
# In deploy-k8s and web-deployer:
namespace = f"{refs}-{project}"  # e.g., develop-saas
cmd_ns(namespace)                 # Switch context via doq ns
doq set-image/kubectl update      # Deploy with new context
```

### 4. Notification Flow (Optional)

```python
# plugins/shared_helpers.py:
resolve_teams_webhook(webhook_url)      # Get webhook endpoint
send_teams_notification(message, data)   # Send build results
```

## External Dependencies and Configuration

### Required Tools

- **git**: Cloning repos, getting commit info
- **docker** + **docker buildx**: Building multi-platform images
- **kubectl**: Kubernetes deployments
- **ssh**: Remote web deployment via Docker Compose
- **python3**: Runtime (3.8+)
- **uv**: Package manager (installed by `install.sh`)

### External APIs

- **Bitbucket API**: Fetch commits, branches, files (`https://api.bitbucket.org/2.0/`)
- **Docker Hub API**: Check image existence (`https://hub.docker.com/v2/`)
- **Rancher API**: Manage clusters/projects (`{RANCHER_URL}/v3/`)
- **Teams Webhook** (optional): Send notifications

### Configuration Files

```
~/.doq/
├── auth.json                    # Credentials (GIT_USER, DOCKERHUB_*)
├── .env                         # Core config (Rancher URL, token)
├── version.json                 # Version tracking (commit hash)
├── plugins.json                 # Plugin registry and status
└── plugins/
    ├── devops-ci.json          # Build config (memory, CPU, registry)
    ├── docker-utils.json       # Image checking config
    ├── web-deployer.json       # SSH deployment config
    └── k8s-deployer.json       # K8s deployment config
```

## Debugging Tips

### Enable Verbose Output

- DevOps CI: Use `--json` flag to see full progress + JSON result
- Deployments: Use `--json` flag for structured output
- Plugin load issues: Check `~/.doq/plugins.json` exists and is valid JSON

### Common Issues and Solutions

1. **"Attestation is not supported for the docker driver"**
   - Issue: Docker buildx using `docker` driver instead of `docker-container`
   - Fix: Script auto-creates `container-builder` with `docker-container` driver in `devops_ci.py`

2. **"Image not found in Docker Hub"**
   - Check: `doq image {repo} {refs}` - verify auth in `~/.doq/auth.json`
   - Root cause: DOCKERHUB_USER/PASSWORD invalid or image not pushed

3. **SSH Deployment Fails**
   - Check: SSH key exists at `~/.ssh/id_rsa`
   - Verify: devops user can access target host and ~/repo/ directory
   - Inspect: cicd/cicd.json has HOST, PORT fields

4. **Kubernetes Deployment Skipped**
   - Normal: If image is same as current deployment (smart feature)
   - Check: `doq get-image {ns} {deployment}` to see current image
   - Force: Rebuild with different commit or use `--image` flag

## Quick Reference for Implementation

### Adding a New Deployment Plugin

1. Create `plugins/my_deployer.py` with `register_commands(subparsers)` function
2. Add to `~/.doq/plugins.json` entry
3. Create config: `~/.doq/plugins/my-deployer.json`
4. Implement: Use `load_auth_file()`, `fetch_bitbucket_file()` from `shared_helpers.py`
5. Use: `doq my-deploy {args}` - automatically loaded by PluginManager

### Modifying Build Process

- Edit `plugins/devops_ci.py`: BuildConfig class, cmd_devops_ci function
- Config priority: CLI args → env vars → `~/.doq/plugins/devops-ci.json` → defaults
- Docker command: Lines ~800-900 in `devops_ci.py`, uses `docker buildx build`

### Extending Authentication

- All plugins use `load_auth_file()` from `shared_helpers.py`
- Add fields to `~/.doq/auth.json` (no schema validation currently)
- Consider env var fallback: `get_env_override("FIELD_NAME")`
