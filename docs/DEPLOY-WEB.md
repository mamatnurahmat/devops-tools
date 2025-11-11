# DoQ Deploy-Web Documentation

Comprehensive guide for the `doq deploy-web` command - automated web application deployment using Docker Compose over SSH.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Deployment Modes](#deployment-modes)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [FAQ](#faq)

---

## Overview

`doq deploy-web` is a powerful command that automates the deployment of web applications to remote servers using Docker Compose. It handles everything from fetching configuration, checking image availability, creating Docker Compose files, to executing deployment over SSH.

### Key Capabilities

- 🚀 **Automated Deployment**: Deploy web apps with a single command
- 🔄 **Smart Updates**: Only redeploy when image changes
- 🎯 **Environment-Aware**: Auto-selects host based on branch/tag
- 🐳 **Docker Compose**: Uses Docker Compose for container management
- 🔐 **SSH Automation**: Secure remote execution via SSH
- 📦 **Image Validation**: Verifies image exists before deployment (auto mode)
- 🎨 **Custom Images**: Support for custom image deployment
- 📋 **JSON Output**: Machine-readable output for automation
- 📢 **Teams Notifications**: Optional Microsoft Teams alerts for deployment status

---

## Features

### ✅ Core Features

- **Auto-Generated Images**: Automatically uses commit-hash-based images
- **Custom Image Mode**: Deploy any Docker image you specify
- **Environment Detection**: Maps branches to environments (dev/staging/prod)
- **SSH Integration**: Executes commands on remote hosts securely
- **Docker Hub Validation**: Verifies image exists (in auto mode)
- **Idempotent Deployment**: Skips if already deployed with same image
- **Remote Directory Creation**: Auto-creates deployment directories
- **Docker Compose Generation**: Creates optimized compose files
- **Container Management**: Handles pull, up, and restart operations
- **Teams Webhook Alerts**: Kirim status deployment ke Microsoft Teams secara otomatis

### 🎯 Smart Deployment Logic

```
1. Fetch cicd.json from Bitbucket
2. Determine target host based on branch/tag
3. Check/validate Docker image
4. Check existing deployment
5. Deploy or skip based on current state
```

---

## Prerequisites

### Required

- Python 3.7+
- SSH access to target servers
- Bitbucket API credentials
- Docker installed on target servers
- Docker Compose installed on target servers

### Target Server Requirements

- SSH server running
- User `devops` (or custom user) with permissions
- Docker daemon running
- Docker Compose v2+ installed
- Network access to image registry

---

## Installation

The `deploy-web` command is included as a plugin in the DoQ CLI tools.

```bash
# Install/Update DoQ tools
curl -sSL https://raw.githubusercontent.com/your-org/devops-tools/main/install.sh | bash

# Verify installation
doq deploy-web --help
```

---

## Quick Start

### 1. Configure Authentication

Create `~/.doq/auth.json`:

```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password",
  "DOCKERHUB_USER": "your-dockerhub-username",
  "DOCKERHUB_PASSWORD": "your-dockerhub-password"
}
```

### 2. Setup SSH Key

```bash
# Generate SSH key if not exists
ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa

# Copy public key to target servers
ssh-copy-id devops@193.2.3.3
```

### 3. Deploy Your Application

```bash
# Auto mode - uses commit hash
doq deploy-web saas-fe-webadmin development

# Custom mode - specific version
doq deploy-web saas-fe-webadmin development --image loyaltolpi/saas-fe-webadmin:v1.0.0
```

---

## How It Works

### Deployment Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    doq deploy-web START                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │ 1. Load Configuration  │
         │  - Load auth.json      │
         │  - Load plugin config  │
         └────────┬───────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │ 2. Fetch cicd.json     │
         │  From Bitbucket        │
         │  repo/refs/cicd/       │
         │  cicd.json             │
         └────────┬───────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │ 3. Determine Target    │
         │  - development → DEV   │
         │  - staging → STAGING   │
         │  - production → PROD   │
         │  - tags → PRODUCTION   │
         └────────┬───────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │ 4. Determine Image     │◄─────────┐
         │  AUTO or CUSTOM mode   │          │
         └────────┬───────────────┘          │
                  │                           │
         ┌────────┴────────┐                 │
         │                 │                 │
         ▼                 ▼                 │
    ┌────────┐      ┌─────────────┐        │
    │  AUTO  │      │   CUSTOM    │        │
    │  MODE  │      │    MODE     │        │
    └───┬────┘      └──────┬──────┘        │
        │                  │                │
        ▼                  ▼                │
  ┌──────────┐      ┌──────────────┐      │
  │ Get Commit│      │ Use Provided │      │
  │   Hash    │      │    Image     │      │
  └─────┬────┘      └──────┬───────┘      │
        │                  │                │
        ▼                  │                │
  ┌──────────┐            │                │
  │ Generate │            │                │
  │  Image   │            │                │
  │  Name    │            │                │
  └─────┬────┘            │                │
        │                  │                │
        ▼                  │                │
  ┌──────────┐            │                │
  │ Validate │            │                │
  │  in Hub  │            │                │
  └─────┬────┘            │                │
        │                  │                │
        └────────┬─────────┘                │
                 │                           │
                 ▼                           │
         ┌────────────────────────┐        │
         │ 5. Check Remote Host   │        │
         │  SSH to devops@HOST    │        │
         │  Check ~/repo/         │        │
         │  docker-compose.yaml   │        │
         └────────┬───────────────┘        │
                  │                         │
         ┌────────┴────────┐               │
         │                 │               │
         ▼                 ▼               │
    ┌─────────┐      ┌─────────┐         │
    │  Exists │      │   New   │         │
    └────┬────┘      └────┬────┘         │
         │                │               │
         ▼                ▼               │
    ┌─────────┐      ┌─────────┐        │
    │ Parse   │      │ Create  │        │
    │ Current │      │  Dir    │        │
    │ Image   │      └────┬────┘        │
    └────┬────┘           │              │
         │                │              │
         ▼                │              │
    ┌─────────┐          │              │
    │  Same?  │          │              │
    └────┬────┘          │              │
         │                │              │
    Yes  │  No            │              │
    │    │                │              │
    ▼    └────────────────┘              │
┌─────┐                 │                │
│SKIP │                 ▼                │
└─────┘         ┌──────────────┐        │
                │ 6. Deploy    │        │
                │  - Create    │        │
                │    compose   │        │
                │  - Upload    │        │
                │  - Pull      │        │
                │  - Up -d     │        │
                └──────┬───────┘        │
                       │                 │
                       ▼                 │
                ┌──────────────┐        │
                │   SUCCESS    │        │
                └──────────────┘        │
                                         │
                    ERROR? ──────────────┘
```

### Step-by-Step Process

#### **STEP 1: Load Configuration**

Loads authentication and plugin configuration:

```python
# From ~/.doq/auth.json
auth_data = {
    "GIT_USER": "username",
    "GIT_PASSWORD": "app-password",
    "DOCKERHUB_USER": "dockerhub-user",
    "DOCKERHUB_PASSWORD": "dockerhub-pass"
}

# From ~/.doq/plugins/web-deployer.json
config = {
    "ssh": {
        "user": "devops",
        "key_file": "~/.ssh/id_rsa",
        "timeout": 30
    },
    "docker": {
        "namespace": "loyaltolpi",
        "target_port": 3000
    },
    "bitbucket": {
        "organization": "qoin-digital-indonesia",
        "cicd_path": "cicd/cicd.json"
    }
}
```

#### **STEP 2: Fetch cicd.json**

Fetches deployment configuration from Bitbucket:

```bash
# API Call
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/src/{refs}/cicd/cicd.json
```

Example `cicd.json`:

```json
{
    "IMAGE": "saas-fe-webadmin",
    "DEVDOMAIN": "dev-admin.qoinservice.id",
    "STADOMAIN": "staging-admin.qoinservice.id",
    "PRODOMAIN": "admin.qoinservice.id",
    "DEVHOST": "193.2.3.3",
    "STAHOST": "193.3.3.3",
    "PROHOST": "193.6.3.3",
    "PORT": "8052"
}
```

#### **STEP 3: Determine Target Environment**

Maps branch/tag to environment:

| refs                  | Environment | Host Field | Domain Field |
|-----------------------|-------------|------------|--------------|
| `development`, `develop` | development | DEVHOST    | DEVDOMAIN    |
| `staging`             | staging     | STAHOST    | STADOMAIN    |
| `production`          | production  | PROHOST    | PRODOMAIN    |
| `v1.0.0` (tags)       | production  | PROHOST    | PRODOMAIN    |

#### **STEP 4A: AUTO MODE - Image Generation**

When `--image` is NOT provided:

```python
# 1. Get commit hash from Bitbucket
commit_hash = get_commit_hash_from_bitbucket(repo, refs, auth_data)
# Result: {'hash': '660cbcf123...', 'short_hash': '660cbcf'}

# 2. Generate image name
namespace = config.get('docker.namespace', 'loyaltolpi')
image_name = cicd_config['IMAGE']
tag = commit_hash['short_hash']
full_image = f"{namespace}/{image_name}:{tag}"
# Result: "loyaltolpi/saas-fe-webadmin:660cbcf"

# 3. Validate image exists in Docker Hub
image_exists = check_docker_image_exists(full_image, auth_data)
if not image_exists:
    exit("Image not found. Build first using: doq devops-ci")
```

#### **STEP 4B: CUSTOM MODE - Use Provided Image**

When `--image` is provided:

```python
# Use provided image directly
full_image = args.image
# Result: "loyaltolpi/saas-fe-webadmin:v1.0.0"

# Skip Docker Hub validation
# (might be from different registry or local build)
```

#### **STEP 5: Check Existing Deployment**

Connects to remote host and checks current state:

```bash
# SSH connection
ssh devops@193.2.3.3

# Check if directory exists
test -d ~/saas-fe-webadmin

# If exists, read docker-compose.yaml
cat ~/saas-fe-webadmin/docker-compose.yaml

# Parse current image using PyYAML
current_image = yaml.safe_load(compose_content)['services']['saas-fe-webadmin']['image']
# Result: "loyaltolpi/saas-fe-webadmin:dd3ecc9"
```

#### **STEP 6A: Skip if Same Image**

```python
if current_image == full_image:
    print("✅ Already deployed with same image")
    print(f"   Current: {current_image}")
    print("   Skipping deployment")
    return 0
```

#### **STEP 6B: Deploy New**

When no existing deployment:

```bash
# 1. Create directory
ssh devops@193.2.3.3 'mkdir -p ~/saas-fe-webadmin'

# 2. Upload docker-compose.yaml
scp docker-compose.yaml devops@193.2.3.3:~/saas-fe-webadmin/

# 3. Pull image
ssh devops@193.2.3.3 'cd ~/saas-fe-webadmin && docker compose pull'

# 4. Start container
ssh devops@193.2.3.3 'cd ~/saas-fe-webadmin && docker compose up -d'
```

#### **STEP 6C: Update Existing**

When image differs:

```bash
# 1. Update docker-compose.yaml
scp docker-compose.yaml devops@193.2.3.3:~/saas-fe-webadmin/

# 2. Pull new image
ssh devops@193.2.3.3 'cd ~/saas-fe-webadmin && docker compose pull'

# 3. Restart with new image
ssh devops@193.2.3.3 'cd ~/saas-fe-webadmin && docker compose up -d'
```

---

## Deployment Modes

### AUTO MODE (Default)

Automatically generates image name from commit hash and validates it.

**When to Use:**
- Standard CI/CD workflow
- Images built with `doq devops-ci`
- Need validation before deployment
- Following commit-based versioning

**Example:**

```bash
doq deploy-web saas-fe-webadmin development
```

**Output:**

```
🔍 Fetching deployment configuration...
🎯 Target: development (193.2.3.3)
📦 Image: loyaltolpi/saas-fe-webadmin:660cbcf
🔍 Checking if image exists in Docker Hub...
✅ Image found in Docker Hub
🔍 Checking existing deployment on devops@193.2.3.3...
🆕 New deployment to 193.2.3.3
📁 Creating directory ~/saas-fe-webadmin...
📤 Uploading docker-compose.yaml...
🐳 Pulling image...
🚀 Starting container...
✅ Deployment successful!
```

**Generated docker-compose.yaml:**

```yaml
name: saas-fe-webadmin

services:
  saas-fe-webadmin:
    container_name: saas-fe-webadmin
    image: loyaltolpi/saas-fe-webadmin:660cbcf
    network_mode: bridge
    ports:
      - mode: ingress
        target: 3000
        published: "8052"
        protocol: tcp
    restart: always
```

### CUSTOM MODE

Deploy any specified Docker image, skipping auto-generation and validation.

**When to Use:**
- Deploy specific versions (v1.0.0, v2.0.0)
- Rollback to previous version
- Deploy from different registry
- Test experimental builds
- Use `latest` tag

**Example:**

```bash
doq deploy-web saas-fe-webadmin development --image loyaltolpi/saas-fe-webadmin:v1.0.0
```

**Output:**

```
🔍 Fetching deployment configuration...
🎯 Target: development (193.2.3.3)
📦 Using custom image: loyaltolpi/saas-fe-webadmin:v1.0.0
ℹ️  Custom image mode - skipping Docker Hub validation
🔍 Checking existing deployment on devops@193.2.3.3...
🔄 Updating deployment on 193.2.3.3
   Previous: loyaltolpi/saas-fe-webadmin:660cbcf
   New: loyaltolpi/saas-fe-webadmin:v1.0.0
📤 Uploading docker-compose.yaml...
🐳 Pulling image...
🚀 Restarting container...
✅ Deployment successful!
```

---

## Configuration

### Global Configuration

File: `~/.doq/auth.json`

```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password",
  "DOCKERHUB_USER": "your-dockerhub-username",
  "DOCKERHUB_PASSWORD": "your-dockerhub-password"
}
```

### Plugin Configuration

File: `~/.doq/plugins/web-deployer.json`

```json
{
  "ssh": {
    "user": "devops",
    "key_file": "~/.ssh/id_rsa",
    "timeout": 30
  },
  "docker": {
    "namespace": "loyaltolpi",
    "target_port": 3000
  },
  "bitbucket": {
    "organization": "qoin-digital-indonesia",
    "cicd_path": "cicd/cicd.json"
  }
}
```

### Configuration Options

| Option | Description | Default | Required |
|--------|-------------|---------|----------|
| `ssh.user` | SSH username for remote host | `devops` | No |
| `ssh.key_file` | Path to SSH private key | `~/.ssh/id_rsa` | No |
| `ssh.timeout` | SSH connection timeout (seconds) | `30` | No |
| `docker.namespace` | Docker Hub namespace | `loyaltolpi` | No |
| `docker.target_port` | Container internal port | `3000` | No |
| `bitbucket.organization` | Bitbucket organization/workspace | `qoin-digital-indonesia` | Yes |
| `bitbucket.cicd_path` | Path to cicd.json in repo | `cicd/cicd.json` | No |

### Environment Variables

Override configuration with environment variables:

```bash
export DOQ_SSH_USER="customuser"
export DOQ_DOCKER_NAMESPACE="mycompany"
export DOQ_BITBUCKET_ORG="my-org"
export TEAMS_WEBHOOK="https://qoinid.webhook.office.com/webhookb2/63088020-7311-4b72-89eb-bc9f58447c9f@e38b30ee-ec18-44bd-8385-08e0acf73344/IncomingWebhook/bda6ddbee1994ed2889eef787ec2eb3e/3609c769-241b-4a44-86c7-f95526b7b84c/V2_ldAc5LeB3fhZC8wtt8TIDqaMKOZf15jYNcH4gl1V4c1"

doq deploy-web myapp development
```

---

## Usage Examples

### Basic Usage

#### Deploy to Development

```bash
doq deploy-web saas-fe-webadmin development
```

#### Deploy to Staging

```bash
doq deploy-web saas-fe-webadmin staging
```

#### Deploy to Production

```bash
doq deploy-web saas-fe-webadmin production
```

#### Deploy Tagged Release

```bash
doq deploy-web saas-fe-webadmin v1.0.0
```

### Custom Image Deployment

#### Deploy Specific Version

```bash
doq deploy-web saas-fe-webadmin production --image loyaltolpi/saas-fe-webadmin:v1.2.3
```

#### Deploy Latest Tag

```bash
doq deploy-web saas-fe-webadmin development --image loyaltolpi/saas-fe-webadmin:latest
```

#### Deploy from Different Namespace

```bash
doq deploy-web myapp development --image mycompany/myapp:v1.0.0
```

#### Deploy from Private Registry

```bash
doq deploy-web myapp production --image registry.company.com/myapp:v2.0.0
```

### JSON Output

```bash
doq deploy-web saas-fe-webadmin development --json
```

Output:

```json
{
  "success": true,
  "action": "deployed",
  "repository": "saas-fe-webadmin",
  "refs": "development",
  "environment": "development",
  "host": "193.2.3.3",
  "image": "loyaltolpi/saas-fe-webadmin:660cbcf",
  "previous_image": null,
  "message": "Deployment successful",
  "custom_image_mode": false
}
```

---

## Advanced Usage

### Complete CI/CD Pipeline

Build and deploy in one go:

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
BRANCH="development"

# Step 1: Build image
echo "Building image..."
doq devops-ci "$REPO" "$BRANCH"

if [ $? -ne 0 ]; then
    echo "❌ Build failed"
    exit 1
fi

# Step 2: Verify image is ready
echo "Verifying image..."
READY=$(doq image "$REPO" "$BRANCH" --json | jq -r '.ready')

if [ "$READY" != "true" ]; then
    echo "❌ Image not ready"
    exit 1
fi

# Step 3: Deploy
echo "Deploying..."
doq deploy-web "$REPO" "$BRANCH"

if [ $? -eq 0 ]; then
    echo "✅ Pipeline successful"
else
    echo "❌ Deployment failed"
    exit 1
fi
```

### Rollback Script

Quickly rollback to previous version:

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
ENV="production"
PREVIOUS_VERSION="v1.1.0"

echo "🔄 Rolling back to $PREVIOUS_VERSION..."
doq deploy-web "$REPO" "$ENV" --image "loyaltolpi/$REPO:$PREVIOUS_VERSION"

if [ $? -eq 0 ]; then
    echo "✅ Rollback successful"
    echo "📋 Verify at: https://admin.qoinservice.id"
else
    echo "❌ Rollback failed"
    exit 1
fi
```

### Multi-Environment Deployment

Deploy same version to all environments:

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
VERSION="v2.0.0"
IMAGE="loyaltolpi/$REPO:$VERSION"

echo "🚀 Deploying $VERSION to all environments..."

# Development
echo "📦 Development..."
doq deploy-web "$REPO" development --image "$IMAGE"

# Staging
echo "📦 Staging..."
doq deploy-web "$REPO" staging --image "$IMAGE"

# Production (with confirmation)
read -p "Deploy to production? (yes/no): " CONFIRM
if [ "$CONFIRM" == "yes" ]; then
    echo "📦 Production..."
    doq deploy-web "$REPO" production --image "$IMAGE"
    echo "✅ All environments updated to $VERSION"
else
    echo "⏭️  Skipped production"
fi
```

### Health Check After Deployment

Deploy and verify:

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
BRANCH="production"

# Deploy
echo "🚀 Deploying..."
RESULT=$(doq deploy-web "$REPO" "$BRANCH" --json)
SUCCESS=$(echo "$RESULT" | jq -r '.success')

if [ "$SUCCESS" != "true" ]; then
    echo "❌ Deployment failed"
    exit 1
fi

# Get domain from cicd.json
DOMAIN=$(doq get-cicd "$REPO" "$BRANCH" | jq -r '.PRODOMAIN')

# Wait for container to start
echo "⏳ Waiting 10 seconds for container startup..."
sleep 10

# Health check
echo "🔍 Checking health..."
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://$DOMAIN/health")

if [ "$STATUS" == "200" ]; then
    echo "✅ Deployment successful and healthy"
else
    echo "⚠️  Deployment completed but health check returned $STATUS"
    exit 1
fi
```

### Deployment with Slack Notification

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
BRANCH="production"
SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Deploy
echo "🚀 Deploying..."
RESULT=$(doq deploy-web "$REPO" "$BRANCH" --json)
SUCCESS=$(echo "$RESULT" | jq -r '.success')
IMAGE=$(echo "$RESULT" | jq -r '.image')
ACTION=$(echo "$RESULT" | jq -r '.action')

# Notify Slack
if [ "$SUCCESS" == "true" ]; then
    MESSAGE="✅ *Deployment Successful*\n\n*Repo:* $REPO\n*Branch:* $BRANCH\n*Image:* \`$IMAGE\`\n*Action:* $ACTION"
    COLOR="good"
else
    MESSAGE="❌ *Deployment Failed*\n\n*Repo:* $REPO\n*Branch:* $BRANCH"
    COLOR="danger"
fi

curl -X POST "$SLACK_WEBHOOK" \
  -H 'Content-Type: application/json' \
  -d "{
    \"attachments\": [{
      \"color\": \"$COLOR\",
      \"text\": \"$MESSAGE\"
    }]
  }"
```

### Deployment with Teams Notification

```bash
#!/bin/bash
REPO="saas-fe-webadmin"
BRANCH="production"
TEAMS_WEBHOOK="https://qoinid.webhook.office.com/webhookb2/63088020-7311-4b72-89eb-bc9f58447c9f@e38b30ee-ec18-44bd-8385-08e0acf73344/IncomingWebhook/bda6ddbee1994ed2889eef787ec2eb3e/3609c769-241b-4a44-86c7-f95526b7b84c/V2_ldAc5LeB3fhZC8wtt8TIDqaMKOZf15jYNcH4gl1V4c1"

echo "🚀 Deploying..."
RESULT=$(doq deploy-web "$REPO" "$BRANCH" \
  --webhook "$TEAMS_WEBHOOK" \
  --json)

SUCCESS=$(echo "$RESULT" | jq -r '.success')
ACTION=$(echo "$RESULT" | jq -r '.action')
IMAGE=$(echo "$RESULT" | jq -r '.image')
HOST=$(echo "$RESULT" | jq -r '.host')

if [ "$SUCCESS" == "true" ]; then
  echo "✅ Deployment succeeded ($ACTION → $IMAGE @ $HOST)"
else
  echo "❌ Deployment failed ($HOST)"
fi
```

> **Tip:** Set `TEAMS_WEBHOOK` in your environment or `~/.doq/.env` to skip the `--webhook` flag.

### Automated Version Bumping

Deploy with semantic versioning:

```bash
#!/bin/bash
REPO="saas-fe-webadmin"

# Get current version
CURRENT=$(doq get-image production-saas "$REPO" | jq -r '.containers[0].tag')
echo "Current version: $CURRENT"

# Bump version
IFS='.' read -ra PARTS <<< "${CURRENT#v}"
MAJOR="${PARTS[0]}"
MINOR="${PARTS[1]}"
PATCH="${PARTS[2]}"

# Increment patch
PATCH=$((PATCH + 1))
NEW_VERSION="v$MAJOR.$MINOR.$PATCH"

echo "New version: $NEW_VERSION"

# Build with new version
doq devops-ci "$REPO" "$NEW_VERSION" --helper --image-name "$REPO:$NEW_VERSION"

# Deploy
doq deploy-web "$REPO" production --image "loyaltolpi/$REPO:$NEW_VERSION"
```

---

## Troubleshooting

### Common Issues

#### 1. SSH Connection Failed

**Error:**

```
❌ Error: SSH connection failed to devops@193.2.3.3
   Permission denied (publickey)
```

**Solution:**

```bash
# Check SSH key
ls -la ~/.ssh/id_rsa

# Test SSH connection
ssh -i ~/.ssh/id_rsa devops@193.2.3.3

# Copy SSH key to server
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@193.2.3.3

# Or add key to ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
```

#### 2. Image Not Found in Docker Hub

**Error:**

```
❌ Error: Image loyaltolpi/saas-fe-webadmin:660cbcf not found in Docker Hub
   Please build the image first using: doq devops-ci saas-fe-webadmin development
```

**Solution:**

```bash
# Build the image first
doq devops-ci saas-fe-webadmin development

# Verify image exists
doq image saas-fe-webadmin development

# Then deploy
doq deploy-web saas-fe-webadmin development
```

#### 3. cicd.json Not Found

**Error:**

```
❌ Error fetching cicd.json: 404 Not Found
```

**Solution:**

```bash
# Check if cicd.json exists in repo
doq get-file saas-fe-webadmin development cicd/cicd.json

# Create cicd.json in your repo
cat > cicd/cicd.json << 'EOF'
{
    "IMAGE": "saas-fe-webadmin",
    "DEVHOST": "193.2.3.3",
    "STAHOST": "193.3.3.3",
    "PROHOST": "193.6.3.3",
    "PORT": "8052"
}
EOF

git add cicd/cicd.json
git commit -m "Add cicd.json"
git push
```

#### 4. Docker Compose Not Found on Remote

**Error:**

```
❌ Error: docker: 'compose' is not a docker command
```

**Solution:**

```bash
# SSH to remote server
ssh devops@193.2.3.3

# Install Docker Compose v2
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Verify installation
docker compose version
```

#### 5. Permission Denied on Remote Directory

**Error:**

```
❌ Error: mkdir: cannot create directory '/home/devops/saas-fe-webadmin': Permission denied
```

**Solution:**

```bash
# SSH to remote server
ssh devops@193.2.3.3

# Check permissions
ls -la ~

# Fix ownership
sudo chown -R devops:devops /home/devops

# Or create directory manually
mkdir -p ~/saas-fe-webadmin
```

#### 6. Port Already in Use

**Error:**

```
Error response from daemon: driver failed programming external connectivity on endpoint
saas-fe-webadmin: Bind for 0.0.0.0:8052 failed: port is already allocated
```

**Solution:**

```bash
# SSH to remote server
ssh devops@193.2.3.3

# Check what's using the port
sudo netstat -tulpn | grep 8052

# Stop the conflicting container
docker ps | grep 8052
docker stop <container-id>

# Or change PORT in cicd.json
```

### Debug Mode

Enable verbose output:

```bash
# Set debug environment variable
export DOQ_DEBUG=1

# Run deployment
doq deploy-web saas-fe-webadmin development
```

### Dry Run Mode

Preview deployment without executing (coming soon):

```bash
doq deploy-web saas-fe-webadmin development --dry-run
```

---

## Best Practices

### 1. Use Semantic Versioning

```bash
# Tag your releases
git tag v1.0.0
git push origin v1.0.0

# Deploy tagged version
doq deploy-web myapp production --image loyaltolpi/myapp:v1.0.0
```

### 2. Test in Development First

```bash
# Always test in dev before prod
doq deploy-web myapp development
# Verify functionality
doq deploy-web myapp staging
# Final verification
doq deploy-web myapp production
```

### 3. Keep cicd.json Updated

```json
{
    "IMAGE": "saas-fe-webadmin",
    "DEVDOMAIN": "dev-admin.qoinservice.id",
    "DEVHOST": "193.2.3.3",
    "PORT": "8052",
    "HEALTHCHECK": "/health",
    "TIMEOUT": "30s"
}
```

### 4. Use JSON Output for Automation

```bash
# Capture deployment result
RESULT=$(doq deploy-web myapp production --json)

# Parse and act
SUCCESS=$(echo "$RESULT" | jq -r '.success')
if [ "$SUCCESS" == "true" ]; then
    # Send notification
    # Update database
    # Trigger next step
fi
```

### 5. Implement Rollback Strategy

```bash
# Before deploying, save current version
CURRENT=$(doq get-image production-saas myapp | jq -r '.containers[0].tag')
echo "$CURRENT" > .last-known-good

# If deployment fails
ROLLBACK_VERSION=$(cat .last-known-good)
doq deploy-web myapp production --image "loyaltolpi/myapp:$ROLLBACK_VERSION"
```

### 6. Monitor After Deployment

```bash
# Deploy
doq deploy-web myapp production

# Monitor logs
ssh devops@193.6.3.3 'docker logs -f myapp'

# Check metrics
# Check error rate
# Check response time
```

### 7. Use Environment-Specific Branches

```
development branch → dev environment
staging branch → staging environment
production branch → prod environment
tags (v*.*.*)  → prod environment
```

### 8. Secure Your Credentials

```bash
# Restrict permissions
chmod 600 ~/.doq/auth.json
chmod 600 ~/.ssh/id_rsa

# Use SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa

# Rotate credentials regularly
```

---

## FAQ

### Q: Can I deploy to multiple hosts?

A: Currently, one deployment targets one host based on cicd.json. For multi-host deployment, run the command multiple times with different configurations or use a script.

### Q: Does it support Docker Swarm or Kubernetes?

A: No, currently only Docker Compose is supported. Kubernetes support is planned for future releases.

### Q: Can I use custom docker-compose.yaml?

A: The tool generates a standard docker-compose.yaml. For custom configurations, you can manually edit the file on the remote host after first deployment.

### Q: How do I deploy to a custom port?

A: Update the `PORT` field in your repository's `cicd/cicd.json` file.

### Q: Can I deploy images from private registries?

A: Yes, use custom mode with `--image`. Ensure the target host has access to your private registry (docker login on remote host).

### Q: What happens if deployment fails mid-way?

A: The tool will report the error. The previous container state is preserved. You can retry the deployment or rollback.

### Q: Can I deploy without stopping the current container?

A: Docker Compose handles this with a rolling update by default. There's minimal downtime as it starts the new container before stopping the old one.

### Q: How do I deploy to a non-standard SSH port?

A: Currently, you need to configure this in your `~/.ssh/config`:

```
Host 193.2.3.3
    Port 2222
    User devops
    IdentityFile ~/.ssh/id_rsa
```

### Q: Can I see what will be deployed before executing?

A: Use `doq image <repo> <refs>` to check what image will be deployed, or check manually:

```bash
doq get-cicd saas-fe-webadmin development
```

### Q: How do I undeploy/remove an application?

A: SSH to the remote host and run:

```bash
ssh devops@193.2.3.3
cd ~/saas-fe-webadmin
docker compose down
cd ~
rm -rf saas-fe-webadmin
```

---

## Related Commands

- **`doq devops-ci`** - Build Docker images
- **`doq image`** - Check image readiness in Docker Hub
- **`doq get-cicd`** - View cicd.json configuration
- **`doq get-file`** - Fetch any file from repository
- **`doq get-image`** - Get current deployed image info

---

## Support & Contributing

### Getting Help

- GitHub Issues: [Report bugs or request features](https://github.com/your-org/devops-tools/issues)
- Documentation: [Full docs](https://github.com/your-org/devops-tools/blob/main/README.md)
- Slack: #devops-tools

### Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Changelog

### v1.1.0 (Latest)
- ✨ Added custom image mode (`--image` option)
- ✨ Added `custom_image_mode` field to JSON output
- 🔧 Skip Docker Hub validation in custom mode
- 📝 Enhanced documentation

### v1.0.0
- 🎉 Initial release
- ✅ Auto mode with commit hash
- ✅ SSH automation
- ✅ Docker Compose integration
- ✅ Environment detection

---

## License

MIT License - See [LICENSE](LICENSE) file for details.

---

**Happy Deploying! 🚀**

