# DOQ Images - Docker Image Status Checker

> **Check Docker image availability in Docker Hub for your repositories**

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Usage](#usage)
- [Configuration](#configuration)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [API References](#api-references)

---

## 🎯 Overview

`doq images` adalah command untuk mengecek apakah Docker image untuk repository dan branch/tag tertentu sudah tersedia di Docker Hub. Tool ini sangat berguna untuk:

- ✅ Verifikasi image availability sebelum deployment
- ✅ CI/CD pipeline validation
- ✅ Auto-build image yang belum tersedia
- ✅ Integration dengan workflow automation

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Image Existence Check** | Cek apakah Docker image ada di Docker Hub |
| **Commit Hash Tracking** | Generate image tag dari commit hash Bitbucket |
| **Auto-Build** | Trigger build otomatis jika image belum ada |
| **JSON Output** | Support JSON format untuk automation |
| **Pretty Display** | Human-readable output dengan status clear |
| **API Integration** | Integration dengan Bitbucket & Docker Hub API |

---

## 📦 Prerequisites

### 1. Credentials Required

File: `~/.doq/auth.json`

```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password",
  "DOCKERHUB_USER": "your-dockerhub-username",
  "DOCKERHUB_PASSWORD": "your-dockerhub-password"
}
```

### 2. Network Access

- ✅ Internet connection required
- ✅ Access to `api.bitbucket.org`
- ✅ Access to `hub.docker.com`

### 3. Permissions

- ✅ Bitbucket: Read access to repositories
- ✅ Docker Hub: Read access to repositories

---

## 🚀 Installation

`doq images` sudah terinstall otomatis sebagai bagian dari `doq` CLI tool:

```bash
# Install doq (if not already installed)
cd devops-tools
./install.sh

# Verify installation
doq images --help
```

---

## ⚡ Quick Start

### Basic Usage

```bash
# Check image status
doq images <repository> <branch/tag>

# Example
doq images saas-apigateway develop
```

### Output Example

```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": true,
  "status": "ready"
}
```

---

## 🔄 How It Works

### Process Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  USER INPUT: doq images saas-apigateway develop             │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: Load Credentials                                    │
│  ────────────────────────────────────────────────────────── │
│  File: ~/.doq/auth.json                                      │
│  Read:                                                        │
│    • GIT_USER & GIT_PASSWORD (Bitbucket)                    │
│    • DOCKERHUB_USER & DOCKERHUB_PASSWORD (Docker Hub)       │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: Get Commit Hash from Bitbucket                     │
│  ────────────────────────────────────────────────────────── │
│  API Call: Bitbucket API                                     │
│  URL: https://api.bitbucket.org/2.0/repositories/           │
│       loyaltoid/saas-apigateway/refs/branches/develop       │
│                                                               │
│  Authentication: HTTP Basic Auth                             │
│  Authorization: Basic base64(GIT_USER:GIT_PASSWORD)         │
│                                                               │
│  Response:                                                    │
│  {                                                            │
│    "target": {                                               │
│      "hash": "660cbcf1234567890abcdef..."                   │
│    }                                                          │
│  }                                                            │
│                                                               │
│  Extract: short_hash = "660cbcf" (first 7 chars)            │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: Generate Docker Image Name                          │
│  ────────────────────────────────────────────────────────── │
│  Format: {namespace}/{repository}:{tag}                      │
│                                                               │
│  Components:                                                  │
│    • namespace  = "loyaltolpi" (from config)                │
│    • repository = "saas-apigateway" (from input)            │
│    • tag        = "660cbcf" (from step 2)                   │
│                                                               │
│  Result: loyaltolpi/saas-apigateway:660cbcf                 │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Check Image in Docker Hub                          │
│  ────────────────────────────────────────────────────────── │
│  Sub-Step 4a: Login to Docker Hub                           │
│  ──────────────────────────────────────                     │
│  API Call: Docker Hub Login                                  │
│  URL: https://hub.docker.com/v2/users/login/                │
│  Method: POST                                                │
│  Body: {                                                      │
│    "username": "DOCKERHUB_USER",                            │
│    "password": "DOCKERHUB_PASSWORD"                         │
│  }                                                            │
│                                                               │
│  Response:                                                    │
│  {                                                            │
│    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."      │
│  }                                                            │
│                                                               │
│  Sub-Step 4b: Check Tag Existence                           │
│  ──────────────────────────────────────                     │
│  API Call: Docker Hub Tag Check                              │
│  URL: https://hub.docker.com/v2/repositories/               │
│       loyaltolpi/saas-apigateway/tags/660cbcf/              │
│  Method: GET                                                 │
│  Headers: {                                                   │
│    "Authorization": "JWT {token}"                           │
│  }                                                            │
│                                                               │
│  Response:                                                    │
│    • 200 OK       → Image EXISTS ✅                          │
│    • 404 Not Found → Image NOT FOUND ❌                      │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 5: Return Result                                       │
│  ────────────────────────────────────────────────────────── │
│  Output Format: JSON (pretty-printed)                        │
│  {                                                            │
│    "repository": "saas-apigateway",                         │
│    "reference": "develop",                                   │
│    "image": "loyaltolpi/saas-apigateway:660cbcf",          │
│    "ready": true,                                            │
│    "status": "ready"                                         │
│  }                                                            │
│                                                               │
│  Exit Code:                                                   │
│    • 0 → Image ready                                         │
│    • 1 → Image not ready                                     │
└──────────────────────────────────────────────────────────────┘
```

### Technical Details

#### 1. Commit Hash Detection

Bitbucket API automatically determines ref type:
- **Branches**: `develop`, `development`, `staging`, `bash`, `master`
- **Tags**: Everything else

API Endpoints:
```
Branches: /refs/branches/{branch-name}
Tags:     /refs/tags/{tag-name}
```

#### 2. Image Name Generation

Formula:
```
image_name = {namespace}/{repo}:{short_hash}
```

Example:
```
namespace   = loyaltolpi (config)
repo        = saas-apigateway (input)
short_hash  = 660cbcf (from commit)
───────────────────────────────────────
image       = loyaltolpi/saas-apigateway:660cbcf
```

#### 3. Docker Hub Authentication

Two-step process:
1. **Login**: Get JWT token using username/password
2. **Check**: Use JWT token to query tag existence

---

## 📖 Usage

### Command Syntax

```bash
doq images <repo> <refs> [options]
```

### Arguments

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `repo` | ✅ Yes | Repository name | `saas-apigateway` |
| `refs` | ✅ Yes | Branch or tag name | `develop`, `v1.0.0` |

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--json` | Output in JSON format | `false` |
| `--force-build` | Auto-build if image not ready | `false` |

### Basic Commands

#### 1. Check Image Status (Branch)

```bash
doq images saas-apigateway develop
```

**Output (Ready):**
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": true,
  "status": "ready"
}
```

**Output (Not Ready):**
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready"
}
```

#### 2. Check Image Status (Tag)

```bash
doq images saas-apigateway v1.0.0
```

#### 3. JSON Output for Automation

```bash
doq images saas-apigateway develop --json
```

**Output:**
```json
{
  "ready": true,
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "build-image": null
}
```

#### 4. Auto-Build if Not Ready

```bash
doq images saas-apigateway develop --force-build
```

**Behavior:**
- If `ready: true` → Display status and exit
- If `ready: false` → Automatically run `doq devops-ci saas-apigateway develop`

**Output Example (Not Ready):**
```
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready"
}

🔨 Image not ready, starting build...
   Running: doq devops-ci saas-apigateway develop

[devops-ci build process starts...]
```

---

## ⚙️ Configuration

### Plugin Config File

Location: `~/.doq/plugins/docker-utils.json`

```json
{
  "registry": {
    "namespace": "loyaltolpi",
    "default_registry": "docker.io"
  },
  "bitbucket": {
    "org": "loyaltoid",
    "api_base": "https://api.bitbucket.org/2.0/repositories",
    "default_cicd_path": "cicd/cicd.json"
  },
  "force_build": {
    "enabled": true,
    "trigger_command": "devops-ci"
  }
}
```

### Environment Variable Overrides

Override config via environment variables:

```bash
# Override namespace
export DOCKER_UTILS_REGISTRY_NAMESPACE="mycompany"

# Override registry
export DOCKER_UTILS_REGISTRY="registry.example.com"

# Override Bitbucket org
export DOCKER_UTILS_BITBUCKET_ORG="myorg"

# Override Bitbucket API base
export DOCKER_UTILS_BITBUCKET_API_BASE="https://api.bitbucket.org/2.0/repositories"
```

### Configuration Priority

```
Environment Variables (highest)
    ↓
Plugin Config File (~/.doq/plugins/docker-utils.json)
    ↓
Default Values (lowest)
```

---

## 💡 Examples

### Example 1: CI/CD Pipeline Check

```bash
#!/bin/bash
# Check if image is ready before deployment

REPO="saas-apigateway"
BRANCH="develop"

echo "Checking image status for $REPO:$BRANCH..."
if doq images "$REPO" "$BRANCH" --json | jq -e '.ready == true' > /dev/null; then
    echo "✅ Image is ready, proceeding with deployment"
    IMAGE=$(doq images "$REPO" "$BRANCH" --json | jq -r '.image')
    kubectl set image deployment/api-gateway api-gateway="$IMAGE"
else
    echo "❌ Image not ready, aborting deployment"
    exit 1
fi
```

### Example 2: Auto-Build in CI Pipeline

```bash
#!/bin/bash
# Auto-build image if not available

doq images saas-apigateway develop --force-build

# If image was not ready, --force-build will trigger build automatically
# Script will continue after build completes
```

### Example 3: Multiple Repository Check

```bash
#!/bin/bash
# Check multiple repositories

REPOS=("saas-apigateway" "saas-be-core" "saas-fe")
BRANCH="develop"

for repo in "${REPOS[@]}"; do
    echo "Checking $repo..."
    STATUS=$(doq images "$repo" "$BRANCH" --json | jq -r '.status')
    echo "  Status: $STATUS"
done
```

### Example 4: Get Image Name for Deployment

```bash
#!/bin/bash
# Extract image name for use in deployment

IMAGE=$(doq images saas-apigateway develop --json | jq -r '.image')
echo "Image to deploy: $IMAGE"

# Use in docker-compose.yml or kubernetes manifest
docker pull "$IMAGE"
docker run -d "$IMAGE"
```

### Example 5: Conditional Build

```bash
#!/bin/bash
# Build only if image doesn't exist

RESULT=$(doq images saas-apigateway develop --json)
READY=$(echo "$RESULT" | jq -r '.ready')

if [ "$READY" = "false" ]; then
    echo "Image not found, building..."
    doq devops-ci saas-apigateway develop
else
    echo "Image already exists, skipping build"
fi
```

---

## 🔧 Troubleshooting

### Issue 1: "Docker Hub credentials not found"

**Error:**
```
⚠️  Docker Hub credentials not found in auth.json
   Required: DOCKERHUB_USER and DOCKERHUB_PASSWORD
   Unable to verify image existence in Docker Hub
```

**Solution:**
1. Create/update `~/.doq/auth.json`:
```json
{
  "DOCKERHUB_USER": "your-username",
  "DOCKERHUB_PASSWORD": "your-password"
}
```

2. Verify file permissions:
```bash
chmod 600 ~/.doq/auth.json
```

### Issue 2: "GIT_USER and GIT_PASSWORD required"

**Error:**
```
❌ Error: GIT_USER and GIT_PASSWORD required in auth.json
```

**Solution:**
Add Bitbucket credentials to `~/.doq/auth.json`:
```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-app-password"
}
```

**Note:** Use Bitbucket App Password, not your account password!

### Issue 3: "Image not ready" but image exists in Docker Hub

**Possible Causes:**
1. **Wrong credentials**: Docker Hub login failed silently
2. **Wrong namespace**: Check config namespace matches Docker Hub
3. **Wrong commit hash**: Branch moved to newer commit

**Debug Steps:**
```bash
# 1. Check current commit hash
doq images saas-apigateway develop

# 2. Manually check Docker Hub
# Visit: https://hub.docker.com/r/loyaltolpi/saas-apigateway/tags

# 3. Verify credentials
cat ~/.doq/auth.json | jq '.DOCKERHUB_USER, .DOCKERHUB_PASSWORD'

# 4. Check namespace in config
cat ~/.doq/plugins/docker-utils.json | jq '.registry.namespace'
```

### Issue 4: Network/API Timeout

**Error:**
```
❌ Error: HTTPSConnectionPool: Max retries exceeded
```

**Solution:**
1. Check internet connection
2. Verify firewall/proxy settings
3. Check API status:
   - Bitbucket: https://bitbucket.status.atlassian.com/
   - Docker Hub: https://status.docker.com/

### Issue 5: 404 Not Found for Repository

**Error:**
```
❌ Error: 404 Client Error: Not Found for url
```

**Possible Causes:**
1. Repository name incorrect
2. No access permission to repository
3. Branch/tag name incorrect

**Solution:**
```bash
# Verify repository exists
curl -u "$GIT_USER:$GIT_PASSWORD" \
  "https://api.bitbucket.org/2.0/repositories/loyaltoid/saas-apigateway"

# List branches
curl -u "$GIT_USER:$GIT_PASSWORD" \
  "https://api.bitbucket.org/2.0/repositories/loyaltoid/saas-apigateway/refs/branches"
```

---

## 📚 API References

### Bitbucket API

**Documentation:** https://developer.atlassian.com/cloud/bitbucket/rest/

**Endpoints Used:**

```
Get Branch Info:
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/refs/branches/{branch}
Auth: Basic {base64(username:password)}

Get Tag Info:
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/refs/tags/{tag}
Auth: Basic {base64(username:password)}
```

**Response Example:**
```json
{
  "name": "develop",
  "target": {
    "hash": "660cbcf1234567890abcdef123456789",
    "author": {
      "user": {
        "display_name": "John Doe"
      }
    },
    "date": "2024-01-15T10:30:00+00:00"
  }
}
```

### Docker Hub API

**Documentation:** https://docs.docker.com/docker-hub/api/latest/

**Endpoints Used:**

```
Login:
POST https://hub.docker.com/v2/users/login/
Body: {"username": "...", "password": "..."}
Response: {"token": "JWT_TOKEN"}

Check Tag:
GET https://hub.docker.com/v2/repositories/{namespace}/{repo}/tags/{tag}/
Headers: {"Authorization": "JWT {token}"}
Response: 200 (exists) or 404 (not found)
```

---

## 🔗 Related Commands

| Command | Description |
|---------|-------------|
| `doq devops-ci` | Build and push Docker images |
| `doq get-cicd` | Fetch cicd.json configuration |
| `doq plugin list` | List available plugins |

---

## 📝 Notes

### Exit Codes

```
0 = Image ready (success)
1 = Image not ready or error
```

### Use in Scripts

```bash
# Capture exit code
doq images saas-apigateway develop
if [ $? -eq 0 ]; then
    echo "Image ready"
else
    echo "Image not ready"
fi
```

### Performance

- **Average execution time**: 2-4 seconds
- **API calls**: 2 (Bitbucket + Docker Hub)
- **Network**: Required

---

## 🆘 Support

### Getting Help

```bash
# Show help
doq images --help

# Plugin info
doq plugin list

# View logs
doq images saas-apigateway develop 2>&1 | tee check.log
```

### Reporting Issues

When reporting issues, include:
1. Command executed
2. Full error output
3. `~/.doq/plugins/docker-utils.json` content (redacted)
4. `doq --version`

---

## 📄 License

Part of the `doq` DevOps Tools suite.

---

**Last Updated:** 2024-01-15
**Version:** 1.0.0
**Author:** DevOps Tools Team

