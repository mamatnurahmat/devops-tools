# DoQ Deploy-K8s Documentation

Comprehensive guide for the `doq deploy-k8s` command - automated Kubernetes deployment with smart image validation and context switching.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)
- [FAQ](#faq)

---

## Overview

`doq deploy-k8s` is a powerful command that automates the deployment of applications to Kubernetes clusters. It intelligently validates Docker images, manages kubectl contexts, and ensures idempotent deployments by comparing current and target images.

### Key Capabilities

- 🔍 **Image Validation**: Verifies image exists in Docker Hub before deployment
- 🎯 **Smart Deployment**: Skips deployment if image is already deployed (idempotent)
- 🔄 **Auto Context Switching**: Automatically switches kubectl context based on namespace
- 📋 **Config-Driven**: Uses `cicd.json` from Bitbucket for configuration
- 🚀 **Integration**: Leverages existing doq commands for seamless workflow
- 🎨 **Custom Images**: Support for manual image specification and rollbacks
- 📊 **JSON Output**: Machine-readable output for CI/CD automation

---

## Features

### ✅ Core Features

- **Automated Image Validation**: Uses `doq image` to verify image readiness
- **Namespace Auto-Detection**: Constructs namespace from refs and PROJECT field
- **Deployment Comparison**: Checks current deployment to avoid unnecessary updates
- **kubectl Integration**: Seamless kubectl context switching via `doq ns`
- **Idempotent Operations**: Safe to run multiple times without side effects
- **Custom Image Support**: Deploy specific versions for rollbacks or testing
- **First-Time Deployment**: Handles new deployments gracefully
- **Error Handling**: Comprehensive validation and error messages
- **Manual Overrides**: Force namespace/deployment values with CLI flags
- **Teams Notifications**: Send deployment summaries to Microsoft Teams via webhook (auto-detects `TEAMS_WEBHOOK`)

### 🎯 Smart Deployment Logic

```
1. Validate image exists in Docker Hub
2. Get configuration from cicd.json
3. Construct namespace: {refs}-{PROJECT}
4. Check current deployment image
5. Compare images → Skip if same
6. Switch kubectl context
7. Deploy using kubectl set image
```

---

## Prerequisites

### Required Software

- **Python 3.7+**
- **kubectl** - Kubernetes command-line tool
- **Git** - For repository operations
- **DoQ CLI** - The main tool (install via `install.sh`)

### Access Requirements

- **Bitbucket Access**: API credentials for fetching cicd.json
- **Kubernetes Access**: kubectl configured with cluster access
- **Docker Hub Access**: Credentials for image validation (optional but recommended)

### Repository Requirements

Your repository must have `cicd/cicd.json` with these required fields:

```json
{
  "PROJECT": "saas",              // Required for namespace
  "DEPLOYMENT": "saas-apigateway", // Required for deployment name
  "IMAGE": "saas-apigateway"       // Required for image name
}
```

---

## Installation & Setup

### 1. Install DoQ CLI

If not already installed:

```bash
# Clone repository
git clone <repository-url>
cd devops-tools

# Run installer
./install.sh
```

The installer will automatically:
- Install dependencies
- Create plugin structure
- Initialize k8s-deployer plugin
- Add `doq` to PATH

### 2. Configure Authentication

Create or update `~/.doq/auth.json`:

```bash
cat > ~/.doq/auth.json << 'EOF'
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password",
  "DOCKERHUB_USER": "your-dockerhub-username",
  "DOCKERHUB_PASSWORD": "your-dockerhub-password"
}
EOF

# Set proper permissions
chmod 600 ~/.doq/auth.json
```

**Get Bitbucket App Password:**
1. Go to Bitbucket Settings → App passwords
2. Create new with `repository:read` permission
3. Use the generated password in auth.json

### 3. Verify kubectl Configuration

```bash
# Check kubectl is installed
kubectl version --client

# Verify cluster access
kubectl cluster-info

# List available contexts
kubectl config get-contexts

# Test context switching
kubectl config use-context <context-name>
```

### 4. Initialize Plugin (If Not Auto-Created)

If the plugin wasn't auto-created during installation:

```bash
# Create plugin directory structure
mkdir -p ~/.doq/plugins

# Create k8s-deployer config
cat > ~/.doq/plugins/k8s-deployer.json << 'EOF'
{
  "docker": {
    "namespace": "loyaltolpi"
  },
  "bitbucket": {
    "organization": "qoin-digital-indonesia",
    "cicd_path": "cicd/cicd.json"
  },
  "deployment": {
    "use_deployment_field": true
  }
}
EOF
```

**Add to plugins.json:**

Edit `~/.doq/plugins.json` and add:

```json
{
  "version": "1.0",
  "plugins": [
    {
      "name": "k8s-deployer",
      "enabled": true,
      "version": "1.0.0",
      "module": "plugins.k8s_deployer",
      "config_file": "plugins/k8s-deployer.json",
      "commands": ["deploy-k8s"],
      "description": "Kubernetes application deployment"
    }
  ]
}
```

### 5. Verify Installation

```bash
# Check if command is available
doq deploy-k8s --help

# List all plugins
doq plugin list

# Verify k8s-deployer is enabled
doq plugin list | grep k8s-deployer
```

Expected output:
```
k8s-deployer (v1.0.0) - ✅ enabled
Description: Kubernetes application deployment
Module: plugins.k8s_deployer
Config: plugins/k8s-deployer.json
Commands: deploy-k8s
```

---

## Quick Start

### Your First Deployment

```bash
# Step 1: Verify image exists
doq image saas-apigateway develop

# Step 2: Deploy to Kubernetes
doq deploy-k8s saas-apigateway develop
```

**Expected Output:**
```
🔍 Checking image status...
✅ Image ready: loyaltolpi/saas-apigateway:660cbcf
🎯 Target: develop-saas / saas-apigateway
🔍 Checking current deployment...
📦 New deployment (not found)
🔄 Switching context to develop-saas...
✅ Context switched
🚀 Deploying image...
✅ Deployment successful!
```

---

## How It Works

### Deployment Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    doq deploy-k8s START                     │
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
         │ 3. Extract Config      │
         │  - PROJECT field       │
         │  - DEPLOYMENT field    │
         │  - IMAGE field         │
         └────────┬───────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │ 4. Construct Namespace │
         │  {refs}-{PROJECT}      │
         │  Example: develop-saas │
         └────────┬───────────────┘
                  │
                  ▼
         ┌────────────────────────┐
         │ 5. Check Image Status  │◄─────────┐
         │  Run: doq image        │          │
         │       repo refs --json │          │
         └────────┬───────────────┘          │
                  │                           │
         ┌────────┴────────┐                 │
         │                 │                 │
         ▼                 ▼                 │
    ┌────────┐      ┌─────────────┐        │
    │ Ready  │      │  Not Ready  │        │
    └───┬────┘      └──────┬──────┘        │
        │                  │                │
        │                  ▼                │
        │            ┌──────────┐          │
        │            │  ERROR   │          │
        │            │   EXIT   │          │
        │            └──────────┘          │
        │                                   │
        ▼                                   │
┌────────────────────────┐                │
│ 6. Get Commit Hash     │                │
│  From Bitbucket API    │                │
│  short_hash: 660cbcf   │                │
└────────┬───────────────┘                │
         │                                  │
         ▼                                  │
┌────────────────────────┐                │
│ 7. Construct Image     │                │
│  {namespace}/{IMAGE}:  │                │
│  {short_hash}          │                │
└────────┬───────────────┘                │
         │                                  │
         ▼                                  │
┌────────────────────────┐                │
│ 8. Get Current Image   │                │
│  Run: doq get-image    │                │
│       namespace        │                │
│       deployment       │                │
└────────┬───────────────┘                │
         │                                  │
    ┌────┴────┐                           │
    │         │                           │
    ▼         ▼                           │
┌────────┐ ┌─────────┐                  │
│ Found  │ │Not Found│                  │
└───┬────┘ └────┬────┘                  │
    │           │                        │
    ▼           │                        │
┌────────┐      │                        │
│Compare │      │                        │
│Images  │      │                        │
└───┬────┘      │                        │
    │           │                        │
┌───┴──┐        │                        │
│ Same?│        │                        │
└───┬──┘        │                        │
    │           │                        │
Yes │  No       │                        │
    │  │        │                        │
    ▼  └────────┘                        │
┌─────┐        │                        │
│SKIP │        │                        │
│ ✓   │        │                        │
└─────┘        │                        │
               ▼                        │
      ┌──────────────┐                │
      │ 9. Switch    │                │
      │    Context   │                │
      │ Run: doq ns  │                │
      │   namespace  │                │
      └──────┬───────┘                │
             │                         │
             ▼                         │
      ┌──────────────┐                │
      │ 10. Deploy   │                │
      │  Run: doq    │                │
      │  set-image   │                │
      │  namespace   │                │
      │  deployment  │                │
      │  image       │                │
      └──────┬───────┘                │
             │                         │
             ▼                         │
      ┌──────────────┐                │
      │   SUCCESS    │                │
      │      ✓       │                │
      └──────────────┘                │
                                       │
          ERROR? ─────────────────────┘
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

# From ~/.doq/plugins/k8s-deployer.json
config = {
    "docker": {
        "namespace": "loyaltolpi"
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
    "IMAGE": "saas-apigateway",
    "CLUSTER": "qoin",
    "PROJECT": "saas",
    "DEPLOYMENT": "saas-apigateway",
    "NODETYPE": "front",
    "PORT": "8005"
}
```

#### **STEP 3: Extract Configuration**

Extracts required fields:
- `PROJECT`: Used for namespace construction
- `DEPLOYMENT`: Kubernetes deployment name
- `IMAGE`: Docker image base name

#### **STEP 4: Construct Namespace**

Namespace format: `{refs}-{PROJECT}`

| refs        | PROJECT | Namespace        |
|-------------|---------|------------------|
| develop     | saas    | develop-saas     |
| staging     | saas    | staging-saas     |
| production  | saas    | production-saas  |
| v1.0.0      | saas    | v1.0.0-saas      |

#### **STEP 5: Check Image Status**

Runs subprocess command:

```bash
doq image saas-apigateway develop --json
```

Parses JSON output:

```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": true,
  "status": "ready"
}
```

If `ready: false`, exits with error message.

#### **STEP 6: Get Commit Hash**

Fetches commit hash from Bitbucket API:

```python
commit_info = get_commit_hash_from_bitbucket(repo, refs, auth_data)
# Result: {'hash': '660cbcf123...', 'short_hash': '660cbcf'}
```

#### **STEP 7: Construct Image Name**

Builds full image name:

```python
namespace = config.get('docker.namespace', 'loyaltolpi')
image_name = cicd_config.get('IMAGE', repo)
tag = commit_info['short_hash']
full_image = f"{namespace}/{image_name}:{tag}"
# Result: "loyaltolpi/saas-apigateway:660cbcf"
```

#### **STEP 8: Get Current Deployment Image**

Runs subprocess command:

```bash
doq get-image develop-saas saas-apigateway
```

Parses JSON output:

```json
{
  "namespace": "develop-saas",
  "deployment": "saas-apigateway",
  "containers": [
    {
      "container": "saas-apigateway",
      "image": "loyaltolpi/saas-apigateway:abc1234",
      "tag": "abc1234"
    }
  ]
}
```

#### **STEP 9: Compare Images**

```python
if current_image == target_image:
    print("✅ Already deployed with same image")
    print(f"   Current: {current_image}")
    print("   Skipping deployment")
    exit(0)
else:
    print("🔄 Different image detected")
    print(f"   Current: {current_image}")
    print(f"   New: {target_image}")
    # Continue to deployment
```

#### **STEP 10: Switch Context**

Runs subprocess command:

```bash
doq ns develop-saas
```

This internally:
1. Parses namespace format
2. Finds matching kubectl context
3. Switches to the context

#### **STEP 11: Deploy Image**

Runs subprocess command:

```bash
doq set-image develop-saas saas-apigateway loyaltolpi/saas-apigateway:660cbcf
```

This internally:
1. Verifies kubectl context
2. Gets container names from deployment
3. Runs `kubectl set image deployment/saas-apigateway ...`

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

File: `~/.doq/plugins/k8s-deployer.json`

```json
{
  "docker": {
    "namespace": "loyaltolpi"
  },
  "bitbucket": {
    "organization": "qoin-digital-indonesia",
    "cicd_path": "cicd/cicd.json"
  },
  "deployment": {
    "use_deployment_field": true
  }
}
```

### Configuration Options

| Option | Description | Default | Required |
|--------|-------------|---------|----------|
| `docker.namespace` | Docker Hub namespace | `loyaltolpi` | No |
| `bitbucket.organization` | Bitbucket organization/workspace | `qoin-digital-indonesia` | Yes |
| `bitbucket.cicd_path` | Path to cicd.json in repo | `cicd/cicd.json` | No |
| `deployment.use_deployment_field` | Use DEPLOYMENT field from cicd.json | `true` | No |

### Environment Variables

Override configuration with environment variables:

```bash
export DOQ_DOCKER_NAMESPACE="mycompany"
export DOQ_BITBUCKET_ORG="my-org"

doq deploy-k8s myapp develop
```

---

## Usage Examples

### Basic Usage

#### Deploy to Development

```bash
doq deploy-k8s saas-apigateway develop
```

#### Deploy to Staging

```bash
doq deploy-k8s saas-apigateway staging
```

#### Deploy to Production

```bash
doq deploy-k8s saas-apigateway production
```

#### Deploy Tagged Release

```bash
doq deploy-k8s saas-apigateway v1.0.0
```

#### Override Namespace and Deployment

```bash
doq deploy-k8s saas-apigateway develop \
  --namespace custom-namespace \
  --deployment custom-deployment
```

### Custom Image Deployment

#### Deploy Specific Version

```bash
doq deploy-k8s saas-apigateway production --image loyaltolpi/saas-apigateway:v1.2.3
```

#### Rollback to Previous Version

```bash
# Get previous version
doq get-image production-saas saas-apigateway

# Rollback
doq deploy-k8s saas-apigateway production --image loyaltolpi/saas-apigateway:abc1234
```

#### Deploy from Different Registry

```bash
doq deploy-k8s myapp develop --image registry.company.com/myapp:latest
```

### JSON Output

```bash
doq deploy-k8s saas-apigateway develop --json
```

Output:

```json
{
  "success": true,
  "action": "updated",
  "repository": "saas-apigateway",
  "refs": "develop",
  "namespace": "develop-saas",
  "deployment": "saas-apigateway",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "previous_image": "loyaltolpi/saas-apigateway:abc1234",
  "message": "Deployment successful",
  "custom_image_mode": false
}
```

---

## Advanced Usage

### Complete CI/CD Pipeline

Build and deploy in one script:

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="develop"

# Step 1: Build image
echo "🔨 Building image..."
doq devops-ci "$REPO" "$BRANCH"

if [ $? -ne 0 ]; then
    echo "❌ Build failed"
    exit 1
fi

# Step 2: Verify image is ready
echo "🔍 Verifying image..."
READY=$(doq image "$REPO" "$BRANCH" --json | jq -r '.ready')

if [ "$READY" != "true" ]; then
    echo "❌ Image not ready"
    exit 1
fi

# Step 3: Deploy to Kubernetes
echo "🚀 Deploying to Kubernetes..."
doq deploy-k8s "$REPO" "$BRANCH"

if [ $? -eq 0 ]; then
    echo "✅ Pipeline successful"
else
    echo "❌ Deployment failed"
    exit 1
fi
```

### Auto-Build and Deploy

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="develop"

# Check image, build if not ready, then deploy
doq image "$REPO" "$BRANCH" --force-build && \
doq deploy-k8s "$REPO" "$BRANCH"
```

### Multi-Environment Deployment

Deploy same version to all environments:

```bash
#!/bin/bash
REPO="saas-apigateway"
VERSION="v2.0.0"

# Build once
doq devops-ci "$REPO" "$VERSION"

# Get image name
IMAGE=$(doq image "$REPO" "$VERSION" --json | jq -r '.image')

# Deploy to all environments
for ENV in develop staging production; do
    echo "📦 Deploying to $ENV..."
    doq deploy-k8s "$REPO" "$ENV" --image "$IMAGE"
done
```

### Health Check After Deployment

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="production"

# Deploy
echo "🚀 Deploying..."
RESULT=$(doq deploy-k8s "$REPO" "$BRANCH" --json)
SUCCESS=$(echo "$RESULT" | jq -r '.success')

if [ "$SUCCESS" != "true" ]; then
    echo "❌ Deployment failed"
    exit 1
fi

NAMESPACE=$(echo "$RESULT" | jq -r '.namespace')
DEPLOYMENT=$(echo "$RESULT" | jq -r '.deployment')

# Wait for rollout
echo "⏳ Waiting for rollout..."
kubectl rollout status deployment/"$DEPLOYMENT" -n "$NAMESPACE" --timeout=5m

if [ $? -eq 0 ]; then
    echo "✅ Deployment successful and healthy"
else
    echo "⚠️  Deployment completed but rollout failed"
    exit 1
fi
```

### Slack Notification Integration

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="production"
SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Deploy
echo "🚀 Deploying..."
RESULT=$(doq deploy-k8s "$REPO" "$BRANCH" --json)
SUCCESS=$(echo "$RESULT" | jq -r '.success')
IMAGE=$(echo "$RESULT" | jq -r '.image')
ACTION=$(echo "$RESULT" | jq -r '.action')
NAMESPACE=$(echo "$RESULT" | jq -r '.namespace')

# Notify Slack
if [ "$SUCCESS" == "true" ]; then
    MESSAGE="✅ *K8s Deployment Successful*\n\n*Repo:* $REPO\n*Branch:* $BRANCH\n*Namespace:* $NAMESPACE\n*Image:* \`$IMAGE\`\n*Action:* $ACTION"
    COLOR="good"
else
    MESSAGE="❌ *K8s Deployment Failed*\n\n*Repo:* $REPO\n*Branch:* $BRANCH\n*Namespace:* $NAMESPACE"
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

### Microsoft Teams Notification

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="production"
TEAMS_WEBHOOK="https://qoinid.webhook.office.com/webhookb2/63088020-7311-4b72-89eb-bc9f58447c9f@e38b30ee-ec18-44bd-8385-08e0acf73344/IncomingWebhook/bda6ddbee1994ed2889eef787ec2eb3e/3609c769-241b-4a44-86c7-f95526b7b84c/V2_ldAc5LeB3fhZC8wtt8TIDqaMKOZf15jYNcH4gl1V4c1"

echo "🚀 Deploying..."
RESULT=$(doq deploy-k8s "$REPO" "$BRANCH" \
  --namespace production-saas \
  --deployment saas-apigateway \
  --webhook "$TEAMS_WEBHOOK" \
  --json)

SUCCESS=$(echo "$RESULT" | jq -r '.success')
IMAGE=$(echo "$RESULT" | jq -r '.image')
ACTION=$(echo "$RESULT" | jq -r '.action')
NAMESPACE=$(echo "$RESULT" | jq -r '.namespace')

if [ "$SUCCESS" == "true" ]; then
  echo "✅ Deployment succeeded ($ACTION → $IMAGE @ $NAMESPACE)"
else
  echo "❌ Deployment failed ($NAMESPACE)"
fi
```

> **Tip:** You can skip the `--webhook` flag if you export the webhook URL:
>
> ```bash
> export TEAMS_WEBHOOK="https://qoinid.webhook.office.com/webhookb2/63088020-7311-4b72-89eb-bc9f58447c9f@e38b30ee-ec18-44bd-8385-08e0acf73344/IncomingWebhook/bda6ddbee1994ed2889eef787ec2eb3e/3609c769-241b-4a44-86c7-f95526b7b84c/V2_ldAc5LeB3fhZC8wtt8TIDqaMKOZf15jYNcH4gl1V4c1"
> ```
>
> The CLI also reads `TEAMS_WEBHOOK` from `~/.doq/.env` if present.

### Rollback Script

Quick rollback to previous version:

```bash
#!/bin/bash
REPO="saas-apigateway"
BRANCH="production"

# Get current image
echo "🔍 Getting current deployment..."
CURRENT=$(doq get-image production-saas "$REPO" | jq -r '.containers[0].image')
echo "Current: $CURRENT"

# Prompt for previous version
read -p "Enter image version to rollback to: " PREVIOUS_IMAGE

# Confirm rollback
read -p "Rollback from $CURRENT to $PREVIOUS_IMAGE? (yes/no): " CONFIRM

if [ "$CONFIRM" == "yes" ]; then
    echo "🔄 Rolling back..."
    doq deploy-k8s "$REPO" "$BRANCH" --image "$PREVIOUS_IMAGE"
    
    if [ $? -eq 0 ]; then
        echo "✅ Rollback successful"
    else
        echo "❌ Rollback failed"
        exit 1
    fi
else
    echo "⏭️  Rollback cancelled"
fi
```

---

## Troubleshooting

### Common Issues

#### 1. Command Not Found

**Error:**
```
doq: command not found
```

**Solution:**
```bash
# Add to PATH
export PATH="${HOME}/.local/bin:${PATH}"

# Make permanent
echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> ~/.bashrc
source ~/.bashrc
```

#### 2. Plugin Not Loaded

**Error:**
```
doq.py: error: argument command: invalid choice: 'deploy-k8s'
```

**Solution:**
```bash
# Check if plugin is registered
cat ~/.doq/plugins.json

# If missing, add k8s-deployer to plugins.json
# See Installation & Setup section

# Verify plugin is enabled
doq plugin list
```

#### 3. Image Not Ready

**Error:**
```
❌ Image not ready in Docker Hub
   Please build the image first using: doq devops-ci saas-apigateway develop
```

**Solution:**
```bash
# Build the image first
doq devops-ci saas-apigateway develop

# Verify image exists
doq image saas-apigateway develop

# Then deploy
doq deploy-k8s saas-apigateway develop
```

#### 4. cicd.json Not Found

**Error:**
```
❌ Error fetching cicd.json: 404 Not Found
```

**Solution:**
```bash
# Check if cicd.json exists in repo
doq get-file saas-apigateway develop cicd/cicd.json

# Create cicd.json in your repo
cat > cicd/cicd.json << 'EOF'
{
    "IMAGE": "saas-apigateway",
    "CLUSTER": "qoin",
    "PROJECT": "saas",
    "DEPLOYMENT": "saas-apigateway",
    "PORT": "8005"
}
EOF

git add cicd/cicd.json
git commit -m "Add cicd.json"
git push
```

#### 5. Missing PROJECT or DEPLOYMENT Field

**Error:**
```
❌ Error: PROJECT field not found in cicd.json
```

**Solution:**
```bash
# Add required fields to cicd.json
{
    "IMAGE": "saas-apigateway",
    "PROJECT": "saas",           ← Add this
    "DEPLOYMENT": "saas-apigateway"  ← Add this
}
```

#### 6. kubectl Context Not Found

**Error:**
```
❌ Failed to switch context
```

**Solution:**
```bash
# List available contexts
kubectl config get-contexts

# Verify context naming matches namespace pattern
# Expected: context name should contain env (develop/staging/production)

# Manually switch context
kubectl config use-context <context-name>
```

#### 7. Deployment Not Found

**Error:**
```
Error: Deployment 'saas-apigateway' not found in namespace 'develop-saas'
```

**Solution:**
```bash
# This is OK for first-time deployment
# The command will proceed with deployment

# Verify deployment after first run
kubectl get deployment -n develop-saas

# Check if deployment was created
doq get-image develop-saas saas-apigateway
```

#### 8. Authentication Failed

**Error:**
```
❌ Error: Authentication not found
```

**Solution:**
```bash
# Create auth.json
cat > ~/.doq/auth.json << 'EOF'
{
  "GIT_USER": "your-username",
  "GIT_PASSWORD": "your-app-password"
}
EOF

chmod 600 ~/.doq/auth.json
```

### Debug Mode

Enable verbose output:

```bash
# Set debug environment variable
export DOQ_DEBUG=1

# Run deployment
doq deploy-k8s saas-apigateway develop
```

---

## Best Practices

### 1. Always Verify Image First

```bash
# Check image status before deploying
doq image saas-apigateway develop

# If not ready, build it
doq devops-ci saas-apigateway develop

# Then deploy
doq deploy-k8s saas-apigateway develop
```

### 2. Use Semantic Versioning for Tags

```bash
# Tag your releases
git tag v1.0.0
git push origin v1.0.0

# Deploy tagged version
doq deploy-k8s myapp production --image loyaltolpi/myapp:v1.0.0
```

### 3. Test in Development First

```bash
# Always test in dev before prod
doq deploy-k8s myapp develop
# Verify functionality

doq deploy-k8s myapp staging
# Final verification

doq deploy-k8s myapp production
```

### 4. Keep cicd.json Updated

Ensure your `cicd.json` has all required fields:

```json
{
  "IMAGE": "saas-apigateway",
  "CLUSTER": "qoin",
  "PROJECT": "saas",
  "DEPLOYMENT": "saas-apigateway",
  "NODETYPE": "front",
  "PORT": "8005"
}
```

### 5. Use JSON Output for Automation

```bash
# Capture deployment result
RESULT=$(doq deploy-k8s myapp production --json)

# Parse and act
SUCCESS=$(echo "$RESULT" | jq -r '.success')
if [ "$SUCCESS" == "true" ]; then
    # Send notification
    # Update database
    # Trigger next step
fi
```

### 6. Implement Rollback Strategy

```bash
# Before deploying, save current version
CURRENT=$(doq get-image production-saas myapp | jq -r '.containers[0].image')
echo "$CURRENT" > .last-known-good

# If deployment fails
ROLLBACK_IMAGE=$(cat .last-known-good)
doq deploy-k8s myapp production --image "$ROLLBACK_IMAGE"
```

### 7. Monitor After Deployment

```bash
# Deploy
doq deploy-k8s myapp production

# Watch rollout status
kubectl rollout status deployment/myapp -n production-saas

# Check pod logs
kubectl logs -f deployment/myapp -n production-saas

# Monitor metrics
```

### 8. Use Environment-Specific Branches

```
develop branch → develop environment
staging branch → staging environment
production branch → production environment
tags (v*.*.*)  → production environment
```

---

## FAQ

### Q: How does namespace construction work?

A: The namespace is constructed as `{refs}-{PROJECT}`:
- `refs`: Branch or tag name (e.g., `develop`, `staging`, `production`)
- `PROJECT`: Value from `cicd.json` (e.g., `saas`)
- Result: `develop-saas`, `staging-saas`, `production-saas`

### Q: What if the deployment doesn't exist yet?

A: The command handles first-time deployments gracefully. It will:
1. Detect that `doq get-image` returns no deployment
2. Mark as "new deployment"
3. Proceed with deployment using `doq set-image`

### Q: Can I deploy to multiple namespaces?

A: Each deployment targets one namespace based on the PROJECT field. For multi-namespace deployment, run the command multiple times with different configurations.

### Q: Does it support different kubectl contexts?

A: Yes! The command automatically switches kubectl context based on the namespace using `doq ns`. Make sure your kubectl contexts are properly configured.

### Q: What happens if I deploy the same image twice?

A: The command is idempotent. It compares the current and target images:
- If **same**: Skips deployment with a message
- If **different**: Proceeds with update

### Q: Can I use custom image tags?

A: Yes! Use the `--image` flag:
```bash
doq deploy-k8s myapp develop --image myregistry/myapp:custom-tag
```

### Q: How do I rollback a deployment?

A: Use the `--image` flag with a previous version:
```bash
# Get previous version
doq get-image production-saas myapp

# Rollback
doq deploy-k8s myapp production --image loyaltolpi/myapp:previous-tag
```

### Q: Does it validate images before deploying?

A: Yes! In auto mode, it runs `doq image` to verify the image exists in Docker Hub. In custom mode (`--image`), validation is skipped (assumes you know the image is ready).

### Q: Can I deploy from private registries?

A: Yes! Make sure:
1. kubectl has imagePullSecrets configured
2. Use `--image` with the full registry URL
```bash
doq deploy-k8s myapp develop --image registry.company.com/myapp:v1.0.0
```

### Q: What if cicd.json is missing required fields?

A: The command will exit with an error message indicating which field is missing. Required fields:
- `PROJECT`
- `DEPLOYMENT`
- `IMAGE`

### Q: How do I debug deployment issues?

A: Enable debug mode and check logs:
```bash
export DOQ_DEBUG=1
doq deploy-k8s myapp develop

# Check kubectl logs
kubectl logs -f deployment/myapp -n develop-saas
```

---

## Related Commands

- **`doq devops-ci`** - Build Docker images
- **`doq image`** - Check image readiness in Docker Hub
- **`doq get-cicd`** - View cicd.json configuration
- **`doq get-file`** - Fetch any file from repository
- **`doq get-image`** - Get current deployed image info
- **`doq ns`** - Switch kubectl context by namespace
- **`doq set-image`** - Update deployment image
- **`doq deploy-web`** - Deploy to Docker Compose (alternative for web apps)

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

### v1.0.0 (Latest)
- 🎉 Initial release
- ✅ Auto mode with commit hash
- ✅ Image validation via doq image
- ✅ Smart deployment (skip if same)
- ✅ kubectl context auto-switching
- ✅ Custom image support
- ✅ JSON output for automation
- ✅ Comprehensive error handling

---

## License

MIT License - See [LICENSE](LICENSE) file for details.

---

**Happy Deploying to Kubernetes! 🚀**

