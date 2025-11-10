# GitOps Workflow - Complete Deployment Flow

> **Automated GitOps workflow for Kubernetes deployment updates**

## 📋 Table of Contents

- [Overview](#overview)
- [Workflow Diagram](#workflow-diagram)
- [Prerequisites](#prerequisites)
- [Complete Workflow](#complete-workflow)
- [Step-by-Step Guide](#step-by-step-guide)
- [Real-World Example](#real-world-example)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

GitOps workflow menggunakan `doq` commands untuk mengotomatisasi proses update deployment Kubernetes melalui Git repository. Workflow ini memungkinkan Anda untuk:

- ✅ Membuat branch untuk perubahan deployment
- ✅ Update image di YAML file secara otomatis
- ✅ Membuat pull request
- ✅ Merge pull request secara otomatis
- ✅ Cleanup branch setelah merge

Semua dilakukan melalui CLI tanpa perlu manual Git operations atau akses ke Bitbucket web interface.

---

## 🔄 Workflow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: Create Branch                                       │
│  ────────────────────────────────────────────────────────── │
│  doq create-branch <repo> <src_branch> <dest_branch>       │
│                                                               │
│  Example:                                                    │
│  doq create-branch gitops-k8s master \                       │
│    staging-qoinplus/plus-apigateway_deployment.yaml        │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: Update Image in YAML                                │
│  ────────────────────────────────────────────────────────── │
│  doq set-image-yaml <repo> <branch> <yaml_path> <image>     │
│                                                               │
│  Example:                                                    │
│  doq set-image-yaml gitops-k8s \                             │
│    staging-qoinplus/plus-apigateway_deployment.yaml \        │
│    staging-qoinplus/plus-apigateway_deployment.yaml \        │
│    loyaltolpi/plus-apigateway:98bccc93-test1                 │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: Create Pull Request                                 │
│  ────────────────────────────────────────────────────────── │
│  doq pull-request <repo> <src_branch> <dest_branch> \       │
│    [--delete]                                                │
│                                                               │
│  Example:                                                    │
│  doq pull-request gitops-k8s \                               │
│    staging-qoinplus/plus-apigateway_deployment.yaml master \ │
│    --delete                                                  │
│                                                               │
│  Output: Pull Request URL                                    │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Merge Pull Request                                  │
│  ────────────────────────────────────────────────────────── │
│  doq merge <pr_url> [--delete]                              │
│                                                               │
│  Example:                                                    │
│  doq merge https://bitbucket.org/loyaltoid/gitops-k8s/ \     │
│    pull-requests/483                                         │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  RESULT: Deployment Updated                                  │
│  ────────────────────────────────────────────────────────── │
│  ✅ Image updated in master branch                           │
│  ✅ Source branch deleted (if --delete used)                 │
│  ✅ Ready for deployment                                     │
└──────────────────────────────────────────────────────────────┘
```

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

### 2. Repository Access

- ✅ Read/Write access to GitOps repository (gitops-k8s)
- ✅ Read access to application repository (for commit info)
- ✅ Read access to Docker Hub (for image validation)

### 3. Network Access

- ✅ Internet connection required
- ✅ Access to `api.bitbucket.org`
- ✅ Access to `hub.docker.com`

---

## 🚀 Complete Workflow

### Step-by-Step Guide

#### Step 1: Create Branch

Buat branch baru dari branch master untuk perubahan deployment.

```bash
doq create-branch <repo> <src_branch> <dest_branch>
```

**Example:**
```bash
doq create-branch gitops-k8s master staging-qoinplus/plus-apigateway_deployment.yaml
```

**Output:**
```
🔍 Creating branch 'staging-qoinplus/plus-apigateway_deployment.yaml' from 'master' in repository 'gitops-k8s'...
✅ Source branch 'master' found (commit: 15a608f)
✅ Branch 'staging-qoinplus/plus-apigateway_deployment.yaml' created successfully!
   Repository: gitops-k8s
   Source branch: master
   Commit: 15a608f
```

**What happens:**
- Validates source branch exists
- Creates new branch pointing to same commit as source
- Prevents overwriting existing branches

---

#### Step 2: Update Image in YAML

Update image reference dalam YAML file deployment.

```bash
doq set-image-yaml <repo> <branch> <yaml_path> <image>
```

**Example:**
```bash
doq set-image-yaml gitops-k8s \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  loyaltolpi/plus-apigateway:98bccc93-test1
```

**Output:**
```
🔍 Updating image in YAML file
   Repository : gitops-k8s
   Branch     : staging-qoinplus/plus-apigateway_deployment.yaml
   YAML Path  : staging-qoinplus/plus-apigateway_deployment.yaml
   New Image  : loyaltolpi/plus-apigateway:98bccc93-test1
🔍 Memeriksa ketersediaan image: loyaltolpi/plus-apigateway:98bccc93-test1
✅ Image ready: loyaltolpi/plus-apigateway:98bccc93-test1
✅ Image berhasil diperbarui dan dipush.
[staging-qoinplus/plus-apigateway_deployment.yaml 6c39f37] chore: update image to loyaltolpi/plus-apigateway:98bccc93-test1
 1 file changed, 1 insertion(+), 1 deletion(-)
```

**What happens:**
- Validates Docker image exists in Docker Hub
- Clones repository branch
- Updates image field in YAML file
- Commits and pushes changes automatically

---

#### Step 3: Create Pull Request

Buat pull request dari branch perubahan ke branch master.

```bash
doq pull-request <repo> <src_branch> <dest_branch> [--delete]
```

**Example:**
```bash
doq pull-request gitops-k8s \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  master --delete
```

**Output:**
```
🔍 Creating pull request from 'staging-qoinplus/plus-apigateway_deployment.yaml' to 'master' in repository 'gitops-k8s'...
   ⚠️  Source branch 'staging-qoinplus/plus-apigateway_deployment.yaml' will be deleted after merge
✅ Source branch 'staging-qoinplus/plus-apigateway_deployment.yaml' validated
✅ Destination branch 'master' validated
✅ Pull request created successfully!
   Repository: gitops-k8s
   Source branch: staging-qoinplus/plus-apigateway_deployment.yaml
   Destination branch: master
   ⚠️  Source branch will be deleted after merge
   Pull Request URL: https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

**What happens:**
- Validates both branches exist
- Creates pull request with automatic title
- Returns PR URL for next step
- Sets `close_source_branch` flag if `--delete` used

---

#### Step 4: Merge Pull Request

Merge pull request secara otomatis menggunakan URL yang didapat dari step sebelumnya.

```bash
doq merge <pr_url> [--delete]
```

**Example:**
```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

**Output:**
```
🔍 Merging pull request #483 in repository 'gitops-k8s'...
✅ Pull request validated
   Source branch: staging-qoinplus/plus-apigateway_deployment.yaml
   Destination branch: master
✅ Pull request #483 merged successfully!
   Repository: gitops-k8s
   Source branch: staging-qoinplus/plus-apigateway_deployment.yaml
   Destination branch: master
   Merge commit: a1b2c3d
   ⚠️  Source branch 'staging-qoinplus/plus-apigateway_deployment.yaml' will be deleted
```

**What happens:**
- Parses PR URL to extract repository and PR ID
- Validates PR exists and is mergeable
- Merges pull request automatically
- Deletes source branch if `--delete` flag used or PR was created with it
- Returns merge commit hash

---

## 💡 Real-World Example

### Complete GitOps Deployment Workflow

Berikut adalah contoh lengkap workflow GitOps untuk update deployment:

```bash
#!/bin/bash

# Configuration
REPO="gitops-k8s"
SRC_BRANCH="master"
BRANCH_NAME="staging-qoinplus/plus-apigateway_deployment.yaml"
YAML_PATH="staging-qoinplus/plus-apigateway_deployment.yaml"
IMAGE="loyaltolpi/plus-apigateway:98bccc93-test1"

# Step 1: Create branch
echo "Step 1: Creating branch..."
doq create-branch $REPO $SRC_BRANCH $BRANCH_NAME

# Step 2: Update image in YAML
echo "Step 2: Updating image in YAML..."
doq set-image-yaml $REPO $BRANCH_NAME $YAML_PATH $IMAGE

# Step 3: Create pull request
echo "Step 3: Creating pull request..."
PR_OUTPUT=$(doq pull-request $REPO $BRANCH_NAME $SRC_BRANCH --delete 2>&1)
PR_URL=$(echo "$PR_OUTPUT" | grep "Pull Request URL:" | awk '{print $4}')

if [ -z "$PR_URL" ]; then
    echo "❌ Failed to get PR URL"
    exit 1
fi

echo "Pull Request created: $PR_URL"

# Step 4: Merge pull request
echo "Step 4: Merging pull request..."
doq merge $PR_URL

echo "✅ Deployment update completed!"
```

### One-Liner Version

Untuk penggunaan cepat, semua step bisa digabungkan:

```bash
# Create branch, update image, create PR, and merge
BRANCH="staging-qoinplus/plus-apigateway_deployment.yaml"
IMAGE="loyaltolpi/plus-apigateway:98bccc93-test1"

doq create-branch gitops-k8s master $BRANCH && \
doq set-image-yaml gitops-k8s $BRANCH $BRANCH $IMAGE && \
doq merge $(doq pull-request gitops-k8s $BRANCH master --delete 2>&1 | grep "Pull Request URL:" | awk '{print $4}')
```

---

## 📝 Step-by-Step Guide

### Complete Workflow with Explanations

#### 1. Create Branch for Deployment Update

**Purpose:** Membuat branch terpisah untuk perubahan deployment agar tidak langsung ke master.

```bash
doq create-branch gitops-k8s master staging-qoinplus/plus-apigateway_deployment.yaml
```

**Why:**
- Isolates changes from master branch
- Allows review before merging
- Follows GitOps best practices

**Branch Naming Convention:**
- Use descriptive names: `{environment}-{service}/{deployment_file}`
- Example: `staging-qoinplus/plus-apigateway_deployment.yaml`

---

#### 2. Update Image in YAML File

**Purpose:** Update image reference dalam deployment YAML dengan image baru.

```bash
doq set-image-yaml gitops-k8s \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  loyaltolpi/plus-apigateway:98bccc93-test1
```

**What it does:**
- Validates image exists in Docker Hub
- Clones the branch
- Updates image field in YAML
- Commits with message: `chore: update image to {image}`
- Pushes changes automatically

**Image Format:**
- Format: `{namespace}/{image}:{tag}`
- Example: `loyaltolpi/plus-apigateway:98bccc93-test1`

---

#### 3. Create Pull Request

**Purpose:** Membuat pull request untuk review dan merge ke master.

```bash
doq pull-request gitops-k8s \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  master --delete
```

**Flags:**
- `--delete`: Delete source branch after merge (recommended for temporary branches)

**Output includes:**
- Pull Request URL (save this for next step)
- PR number
- Source and destination branch info

---

#### 4. Merge Pull Request

**Purpose:** Merge pull request secara otomatis setelah validasi.

```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

**What it does:**
- Validates PR exists and is mergeable
- Checks if PR is already merged
- Merges PR automatically
- Deletes source branch if configured
- Returns merge commit hash

**With delete flag:**
```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483 --delete
```

---

## ✨ Best Practices

### 1. Branch Naming

**Good:**
```bash
staging-qoinplus/plus-apigateway_deployment.yaml
production-saas/api-gateway_deployment.yaml
```

**Bad:**
```bash
branch1
test
update
```

### 2. Image Tagging

**Use descriptive tags:**
- Commit hash: `loyaltolpi/api:fc0bd25`
- Version + commit: `loyaltolpi/api:v1.2.3-fc0bd25`
- Environment + commit: `loyaltolpi/api:staging-fc0bd25`

### 3. Always Use --delete Flag

Untuk branch temporary (seperti deployment branches), selalu gunakan `--delete`:

```bash
doq pull-request repo branch master --delete
```

### 4. Validate Image Before Update

Pastikan image sudah tersedia di Docker Hub sebelum update:

```bash
# Check image first
doq image saas-apigateway develop

# Then update
doq set-image-yaml gitops-k8s branch path image
```

### 5. Use Scripts for Automation

Buat script untuk workflow yang sering digunakan:

```bash
#!/bin/bash
# deploy.sh

REPO=$1
BRANCH=$2
IMAGE=$3

doq create-branch gitops-k8s master $BRANCH && \
doq set-image-yaml gitops-k8s $BRANCH $BRANCH $IMAGE && \
doq pull-request gitops-k8s $BRANCH master --delete
```

---

## 🔧 Troubleshooting

### Common Issues

#### 1. Branch Already Exists

**Problem:**
```
❌ Error: Destination branch 'staging-qoinplus/plus-apigateway_deployment.yaml' already exists
```

**Solution:**
- Delete existing branch manually via Bitbucket web interface
- Or use different branch name
- Or reuse existing branch (skip create-branch step)

#### 2. Image Not Found

**Problem:**
```
⚠️  Image not ready: loyaltolpi/api:abc1234
```

**Solution:**
- Verify image exists: `doq image repo branch`
- Build image first: `doq devops-ci repo branch`
- Check image tag spelling

#### 3. YAML File Not Found

**Problem:**
```
⚠️  Tidak dapat memeriksa YAML dari Bitbucket: File not found
```

**Solution:**
- Verify YAML path is correct
- Check if file exists in repository
- Ensure branch was created successfully

#### 4. Pull Request Already Exists

**Problem:**
```
❌ Error: Pull request already exists
```

**Solution:**
- Check existing PRs in Bitbucket
- Use existing PR URL for merge step
- Or close existing PR and create new one

#### 5. Merge Conflicts

**Problem:**
```
❌ Error: Merge conflicts detected
```

**Solution:**
- Resolve conflicts manually in Bitbucket web interface
- Or update branch: `doq create-branch` again from latest master
- Re-apply changes: `doq set-image-yaml`

#### 6. PR Already Merged

**Problem:**
```
✅ Pull request #483 is already merged
```

**Solution:**
- This is normal if PR was merged manually
- Check merge commit hash
- Verify deployment was updated

---

## 📚 Related Commands

| Command | Description | Use Case |
|---------|-------------|----------|
| `doq create-branch` | Create new branch | Step 1: Isolate changes |
| `doq set-image-yaml` | Update image in YAML | Step 2: Update deployment |
| `doq pull-request` | Create PR | Step 3: Request merge |
| `doq merge` | Merge PR | Step 4: Complete deployment |
| `doq image` | Check image availability | Validate before update |
| `doq commit` | View commit history | Verify changes |

---

## 💻 Script Examples

### Basic Deployment Script

```bash
#!/bin/bash
# deploy-image.sh

set -e

REPO="${1:-gitops-k8s}"
BRANCH="${2}"
IMAGE="${3}"

if [ -z "$BRANCH" ] || [ -z "$IMAGE" ]; then
    echo "Usage: $0 <repo> <branch> <image>"
    echo "Example: $0 gitops-k8s staging-qoinplus/plus-apigateway_deployment.yaml loyaltolpi/api:tag"
    exit 1
fi

YAML_PATH="$BRANCH"

echo "🚀 Starting deployment workflow..."
echo "   Repository: $REPO"
echo "   Branch: $BRANCH"
echo "   Image: $IMAGE"
echo ""

# Step 1: Create branch
echo "📦 Step 1: Creating branch..."
doq create-branch $REPO master $BRANCH

# Step 2: Update image
echo "🔄 Step 2: Updating image..."
doq set-image-yaml $REPO $BRANCH $YAML_PATH $IMAGE

# Step 3: Create PR
echo "📝 Step 3: Creating pull request..."
PR_OUTPUT=$(doq pull-request $REPO $BRANCH master --delete 2>&1)
PR_URL=$(echo "$PR_OUTPUT" | grep "Pull Request URL:" | awk '{print $4}')

if [ -z "$PR_URL" ]; then
    echo "❌ Failed to extract PR URL"
    exit 1
fi

echo "   PR URL: $PR_URL"

# Step 4: Merge PR
echo "✅ Step 4: Merging pull request..."
doq merge $PR_URL

echo ""
echo "🎉 Deployment completed successfully!"
echo "   Image $IMAGE is now in master branch"
```

### Advanced Script with Error Handling

```bash
#!/bin/bash
# deploy-with-validation.sh

REPO="gitops-k8s"
BRANCH="staging-qoinplus/plus-apigateway_deployment.yaml"
IMAGE="loyaltolpi/plus-apigateway:98bccc93-test1"

# Function to check if command succeeded
check_result() {
    if [ $? -ne 0 ]; then
        echo "❌ Command failed. Stopping workflow."
        exit 1
    fi
}

# Validate image exists
echo "🔍 Validating image exists..."
doq image plus-apigateway develop | jq -e '.ready == true' > /dev/null
check_result
echo "✅ Image validated"

# Create branch
echo "📦 Creating branch..."
doq create-branch $REPO master $BRANCH
check_result

# Update image
echo "🔄 Updating image..."
doq set-image-yaml $REPO $BRANCH $BRANCH $IMAGE
check_result

# Create PR and extract URL
echo "📝 Creating pull request..."
PR_OUTPUT=$(doq pull-request $REPO $BRANCH master --delete 2>&1)
check_result

PR_URL=$(echo "$PR_OUTPUT" | grep "Pull Request URL:" | awk '{print $4}')
if [ -z "$PR_URL" ]; then
    echo "❌ Could not extract PR URL from output"
    exit 1
fi

echo "   PR created: $PR_URL"

# Wait for user confirmation (optional)
read -p "Press Enter to merge PR, or Ctrl+C to cancel..."

# Merge PR
echo "✅ Merging pull request..."
doq merge $PR_URL
check_result

echo "🎉 Deployment workflow completed!"
```

---

## 🔗 Integration with CI/CD

### GitHub Actions Example

```yaml
name: GitOps Deployment

on:
  workflow_dispatch:
    inputs:
      image:
        description: 'Docker image to deploy'
        required: true
      branch:
        description: 'Branch name for deployment'
        required: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup doq
        run: |
          curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash
      
      - name: Deploy Image
        env:
          GIT_USER: ${{ secrets.BITBUCKET_USER }}
          GIT_PASSWORD: ${{ secrets.BITBUCKET_TOKEN }}
        run: |
          doq create-branch gitops-k8s master ${{ github.event.inputs.branch }} && \
          doq set-image-yaml gitops-k8s ${{ github.event.inputs.branch }} \
            ${{ github.event.inputs.branch }} ${{ github.event.inputs.image }} && \
          doq merge $(doq pull-request gitops-k8s ${{ github.event.inputs.branch }} master --delete 2>&1 | \
            grep "Pull Request URL:" | awk '{print $4}')
```

---

## 📝 Notes

### Exit Codes

```
0 = Success
1 = Error (branch exists, image not found, merge conflict, etc.)
```

### Performance

- **Average execution time**: 5-10 seconds per workflow
- **API calls**: 5-8 calls per complete workflow
- **Network**: Required for all operations

### Security

- Credentials stored in `~/.doq/auth.json` with 600 permissions
- Use Bitbucket App Passwords (not account password)
- Rotate credentials regularly

---

## 🆘 Support

### Getting Help

```bash
# Show help for each command
doq create-branch --help
doq set-image-yaml --help
doq pull-request --help
doq merge --help
```

### Common Workflows

**Quick Deployment:**
```bash
BRANCH="staging-service/deployment.yaml"
IMAGE="loyaltolpi/service:tag"

doq create-branch gitops-k8s master $BRANCH && \
doq set-image-yaml gitops-k8s $BRANCH $BRANCH $IMAGE && \
doq merge $(doq pull-request gitops-k8s $BRANCH master --delete 2>&1 | \
  grep "Pull Request URL:" | awk '{print $4}')
```

**With Validation:**
```bash
# 1. Check image exists
doq image service develop

# 2. Deploy
doq create-branch gitops-k8s master branch && \
doq set-image-yaml gitops-k8s branch branch image && \
doq pull-request gitops-k8s branch master --delete
```

---

## 📖 Related Documentation

- **[GIT-COMMANDS.md](GIT-COMMANDS.md)** - Detailed Git command documentation
- **[DOQ-IMAGE.md](DOQ-IMAGE.md)** - Docker image checker
- **[AUTHENTICATION.md](AUTHENTICATION.md)** - Authentication setup

