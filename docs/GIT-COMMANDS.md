# Git Commands - Bitbucket Repository Management

> **Manage Git branches, commits, and pull requests directly from CLI**

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Commands](#commands)
  - [doq commit](#doq-commit)
  - [doq create-branch](#doq-create-branch)
  - [doq pull-request](#doq-pull-request)
  - [doq merge](#doq-merge)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [API References](#api-references)

---

## 🎯 Overview

Git Commands module provides three powerful commands to interact with Bitbucket repositories:

- **`doq commit`** - View commit information and history
- **`doq create-branch`** - Create new branches from existing branches
- **`doq pull-request`** - Create pull requests with optional branch deletion
- **`doq merge`** - Merge pull requests automatically from PR URL

These commands streamline Git workflow operations without requiring local repository clones or manual Git operations.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Commit History** | View commit details and last 5 commits from any branch/tag |
| **Tag Support** | Automatically detect tags and show associated branch information |
| **Branch Creation** | Create new branches with validation and conflict prevention |
| **Pull Request** | Create PRs with automatic URL generation and branch management |
| **JSON Output** | Support JSON format for automation and scripting |
| **Error Handling** | Comprehensive error messages and validation |

---

## 📦 Prerequisites

### 1. Credentials Required

File: `~/.doq/auth.json`

```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password"
}
```

### 2. Network Access

- ✅ Internet connection required
- ✅ Access to `api.bitbucket.org`

### 3. Permissions

- ✅ Bitbucket: Read/Write access to repositories (for create-branch and pull-request)
- ✅ Bitbucket: Read access to repositories (for commit)

---

## ⚡ Quick Start

### View Commit History

```bash
# View last 5 commits
doq commit saas-apigateway develop

# View specific commit
doq commit saas-apigateway develop fc0bd25
```

### Create Branch

```bash
# Create new branch from existing branch
doq create-branch saas-apigateway develop feature/new-feature
```

### Create Pull Request

```bash
# Create PR without deleting source branch
doq pull-request saas-apigateway feature/new-feature develop

# Create PR and delete source branch after merge
doq pull-request saas-apigateway feature/new-feature develop --delete

# Merge pull request
doq merge https://bitbucket.org/loyaltoid/saas-apigateway/pull-requests/123
```

---

## 📚 Commands

### doq commit

View commit information and history from Bitbucket repository.

#### Usage

```bash
doq commit <repo> <ref> [commit_id] [--json]
```

#### Arguments

- `repo` - Repository name (e.g., `saas-apigateway`)
- `ref` - Branch or tag name (e.g., `develop`, `main`, `v1.0.0`)
- `commit_id` - (Optional) Short commit ID (e.g., `fc0bd25`). If omitted, shows last 5 commits
- `--json` - (Optional) Output as JSON format

#### Features

- **Single Commit View**: Display detailed information about a specific commit
- **Commit History**: View last 5 commits when commit_id is not provided
- **Tag Support**: Automatically detects tags and shows associated branch information
- **JSON Output**: Optional JSON format for automation

#### Examples

**View Last 5 Commits:**

```bash
doq commit saas-apigateway develop
```

Output:
```
Last 5 commits on 'develop':
======================================================================
[1] fc0bd25 - Mapping 1 endpoint for audittrail
     Author: hegi
     Date:   Fri Nov 07 04:40:16 2025 +0000
[2] 6b31b3b - Mapping 1 endpoint for audittrail
     Author: hegi
     Date:   Fri Nov 07 04:36:22 2025 +0000
...
```

**View Specific Commit:**

```bash
doq commit saas-apigateway develop fc0bd25
```

Output:
```
commit fc0bd25357e11231fca74bd9c9fe39afdfa95407
Author: hegi
Date:   Fri Nov 07 04:40:16 2025 +0000

    Mapping 1 endpoint for audittrail
```

**View Commit from Tag:**

```bash
doq commit saas-apigateway v1.0.0
```

Output:
```
commit f90f48a6fb4be30c59e87cdf99b508a9c148747f
Branch: develop
Author: hegi
Date:   Wed Mar 29 04:25:15 2023 +0000

    3 endpoint for workspaceclient
```

**JSON Output:**

```bash
doq commit saas-apigateway develop fc0bd25 --json
```

Output:
```json
{
  "commit": "fc0bd25357e11231fca74bd9c9fe39afdfa95407",
  "author": {
    "name": "hegi",
    "email": null
  },
  "date": "Fri Nov 07 04:40:16 2025 +0000",
  "message": "Mapping 1 endpoint for audittrail"
}
```

---

### doq create-branch

Create a new branch in Bitbucket repository from an existing source branch.

#### Usage

```bash
doq create-branch <repo> <src_branch> <dest_branch>
```

#### Arguments

- `repo` - Repository name (e.g., `saas-apigateway`)
- `src_branch` - Source branch name (e.g., `develop`, `main`)
- `dest_branch` - Destination branch name (new branch to create)

#### Features

- **Validation**: Validates source branch exists before creating
- **Conflict Prevention**: Prevents overwriting existing branches
- **Same Commit**: New branch points to the same commit as source branch

#### Examples

**Create Feature Branch:**

```bash
doq create-branch saas-apigateway develop feature/new-endpoint
```

Output:
```
🔍 Creating branch 'feature/new-endpoint' from 'develop' in repository 'saas-apigateway'...
✅ Source branch 'develop' found (commit: fc0bd25)
✅ Branch 'feature/new-endpoint' created successfully!
   Repository: saas-apigateway
   Source branch: develop
   Commit: fc0bd25
```

**Create Branch from Master:**

```bash
doq create-branch gitops-k8s master staging-qoinplus/plus-apigateway_deployment.yaml
```

Output:
```
🔍 Creating branch 'staging-qoinplus/plus-apigateway_deployment.yaml' from 'master' in repository 'gitops-k8s'...
✅ Source branch 'master' found (commit: 15a608f)
✅ Branch 'staging-qoinplus/plus-apigateway_deployment.yaml' created successfully!
   Repository: gitops-k8s
   Source branch: master
   Commit: 15a608f
```

#### Error Handling

**Source Branch Not Found:**
```
❌ Error: Source branch 'nonexistent' not found in repository 'saas-apigateway'
   Check if branch name is correct
```

**Destination Branch Already Exists:**
```
❌ Error: Destination branch 'feature/existing' already exists in repository 'saas-apigateway'
   Use a different branch name or delete the existing branch first
```

---

### doq pull-request

Create a pull request in Bitbucket repository from source branch to destination branch.

#### Usage

```bash
doq pull-request <repo> <src_branch> <dest_branch> [--delete]
```

#### Arguments

- `repo` - Repository name (e.g., `saas-apigateway`)
- `src_branch` - Source branch name (e.g., `feature-branch`)
- `dest_branch` - Destination branch name (e.g., `develop`, `main`)
- `--delete` - (Optional) Delete source branch after merge (default: False)

#### Features

- **Branch Validation**: Validates both source and destination branches exist
- **PR Creation**: Creates pull request with automatic title generation
- **Branch Management**: Optional deletion of source branch after merge
- **URL Return**: Returns pull request URL for easy access

#### Examples

**Create Pull Request:**

```bash
doq pull-request saas-apigateway feature/new-endpoint develop
```

Output:
```
🔍 Creating pull request from 'feature/new-endpoint' to 'develop' in repository 'saas-apigateway'...
✅ Source branch 'feature/new-endpoint' validated
✅ Destination branch 'develop' validated
✅ Pull request created successfully!
   Repository: saas-apigateway
   Source branch: feature/new-endpoint
   Destination branch: develop
   Pull Request URL: https://bitbucket.org/loyaltoid/saas-apigateway/pull-requests/123
```

**Create Pull Request with Branch Deletion:**

```bash
doq pull-request gitops-k8s staging-qoinplus/plus-apigateway_deployment.yaml master --delete
```

Output:
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
   Pull Request URL: https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/484
```

#### Error Handling

**Source Branch Not Found:**
```
❌ Error: Source branch 'feature/nonexistent' not found in repository 'saas-apigateway'
   Check if branch name is correct
```

**Destination Branch Not Found:**
```
❌ Error: Destination branch 'nonexistent' not found in repository 'saas-apigateway'
   Check if branch name is correct
```

**Pull Request Already Exists:**
```
❌ Error: Pull request already exists
   A pull request from 'feature/branch' to 'develop' might already exist
```

---

### doq merge

Merge a pull request automatically from Bitbucket PR URL.

#### Usage

```bash
doq merge <pr_url> [--delete]
```

#### Arguments

- `pr_url` - Pull request URL (e.g., `https://bitbucket.org/loyaltoid/repo/pull-requests/123`)
- `--delete` - (Optional) Delete source branch after merge (default: False)

#### Features

- **URL Parsing**: Automatically extracts repository and PR ID from URL
- **State Validation**: Checks if PR is already merged or declined
- **Automatic Merge**: Merges PR with single command
- **Branch Management**: Optional deletion of source branch after merge
- **Merge Commit**: Returns merge commit hash

#### Examples

**Merge Pull Request:**

```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

Output:
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
```

**Merge Pull Request with Branch Deletion:**

```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483 --delete
```

Output:
```
🔍 Merging pull request #483 in repository 'gitops-k8s'...
   ⚠️  Source branch will be deleted after merge
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

**Already Merged PR:**

```bash
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

Output:
```
🔍 Merging pull request #483 in repository 'gitops-k8s'...
✅ Pull request #483 is already merged
   Merge commit: a1b2c3d
```

#### Error Handling

**Invalid PR URL Format:**
```
❌ Error: Invalid pull request URL format
   Expected format: https://bitbucket.org/loyaltoid/<repo>/pull-requests/<id>
   Got: invalid-url
```

**PR Not Found:**
```
❌ Error: Pull request #999 not found in repository 'gitops-k8s'
   Check if PR URL is correct
```

**PR Already Declined:**
```
❌ Error: Pull request #483 is declined
   Cannot merge a declined pull request
```

**Merge Conflicts:**
```
❌ Error: Merge conflicts detected
   Merge conflicts detected. Please resolve conflicts manually.
```

---

## 💡 Examples

### Complete Workflow Example

```bash
# 1. View commits on develop branch
doq commit saas-apigateway develop

# 2. Create feature branch from develop
doq create-branch saas-apigateway develop feature/audit-trail

# 3. (Make changes, commit, push via Git)

# 4. View specific commit
doq commit saas-apigateway feature/audit-trail fc0bd25 --json

# 5. Create pull request with auto-delete
doq pull-request saas-apigateway feature/audit-trail develop --delete
```

### GitOps Workflow Example

```bash
# 1. Create branch for deployment update
doq create-branch gitops-k8s master staging-qoinplus/plus-apigateway_deployment.yaml

# 2. Update image in YAML (using set-image-yaml command)
doq set-image-yaml gitops-k8s staging-qoinplus/plus-apigateway_deployment.yaml \
  staging-qoinplus/plus-apigateway_deployment.yaml \
  loyaltolpi/plus-apigateway:98bccc93-test2

# 3. Create pull request
doq pull-request gitops-k8s staging-qoinplus/plus-apigateway_deployment.yaml master --delete

# 4. Merge pull request
doq merge https://bitbucket.org/loyaltoid/gitops-k8s/pull-requests/483
```

---

## 🔧 Troubleshooting

### Common Issues

#### 1. Authentication Errors

**Problem:**
```
❌ Error: GIT_USER and GIT_PASSWORD required in ~/.doq/auth.json
```

**Solution:**
1. Create `~/.doq/auth.json` file:
```json
{
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password"
}
```

2. Or set environment variables:
```bash
export GIT_USER="your-username"
export GIT_PASSWORD="your-app-password"
```

#### 2. Branch Not Found

**Problem:**
```
❌ Error: Source branch 'develop' not found in repository 'saas-apigateway'
```

**Solution:**
- Verify branch name is correct (case-sensitive)
- Check if branch exists in Bitbucket repository
- Ensure you have read access to the repository

#### 3. Pull Request Creation Failed

**Problem:**
```
❌ Error: Failed to create pull request
```

**Solution:**
- Ensure source and destination branches exist
- Check if a PR from source to destination already exists
- Verify you have write permissions to create pull requests
- Check if branches have diverged significantly

#### 4. Commit Not Found

**Problem:**
```
❌ Error: Commit 'abc1234' not found in repository 'saas-apigateway'
```

**Solution:**
- Verify commit ID is correct (can use short or full hash)
- Ensure commit exists in the specified branch/tag
- Check if commit is accessible in the repository

---

## 📚 API References

### Bitbucket API

**Documentation:** https://developer.atlassian.com/cloud/bitbucket/rest/

**Endpoints Used:**

#### Get Commit Information
```
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/commit/{commit_id}
Auth: Basic {base64(username:password)}
```

#### Get Commits List
```
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/commits/{branch}?pagelen=5
Auth: Basic {base64(username:password)}
```

#### Get Branch Information
```
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/refs/branches/{branch}
Auth: Basic {base64(username:password)}
```

#### Create Branch
```
POST https://api.bitbucket.org/2.0/repositories/{org}/{repo}/refs/branches
Auth: Basic {base64(username:password)}
Content-Type: application/json
Body: {
  "name": "branch-name",
  "target": {
    "hash": "commit-hash"
  }
}
```

#### Create Pull Request
```
POST https://api.bitbucket.org/2.0/repositories/{org}/{repo}/pullrequests
Auth: Basic {base64(username:password)}
Content-Type: application/json
Body: {
  "title": "Merge {src} into {dest}",
  "source": {
    "branch": {
      "name": "src-branch"
    }
  },
  "destination": {
    "branch": {
      "name": "dest-branch"
    }
  },
  "close_source_branch": false
}
```

#### Get Pull Request Details
```
GET https://api.bitbucket.org/2.0/repositories/{org}/{repo}/pullrequests/{id}
Auth: Basic {base64(username:password)}
```

#### Merge Pull Request
```
POST https://api.bitbucket.org/2.0/repositories/{org}/{repo}/pullrequests/{id}/merge
Auth: Basic {base64(username:password)}
Content-Type: application/json
Body: {
  "message": "Merged via doq merge",
  "close_source_branch": true/false
}
```

**Response Example (Pull Request):**
```json
{
  "id": 123,
  "links": {
    "html": {
      "href": "https://bitbucket.org/loyaltoid/repo/pull-requests/123"
    }
  },
  "title": "Merge feature-branch into develop",
  "source": {
    "branch": {
      "name": "feature-branch"
    }
  },
  "destination": {
    "branch": {
      "name": "develop"
    }
  }
}
```

---

## 🔗 Related Commands

| Command | Description |
|---------|-------------|
| `doq set-image-yaml` | Update image in YAML file and commit |
| `doq clone` | Clone Git repository |
| `doq image` | Check Docker image availability |
| `doq merge` | Merge pull request automatically |

---

## 📝 Notes

### Exit Codes

```
0 = Success
1 = Error (branch not found, authentication failed, etc.)
```

### Use in Scripts

```bash
# Create branch and check result
doq create-branch saas-apigateway develop feature/test
if [ $? -eq 0 ]; then
    echo "Branch created successfully"
else
    echo "Failed to create branch"
fi
```

### Performance

- **Average execution time**: 1-3 seconds per command
- **API calls**: 1-3 calls per command depending on validation steps
- **Network**: Required for all operations

---

## 🆘 Support

### Getting Help

```bash
# Show help for commit command
doq commit --help

# Show help for create-branch command
doq create-branch --help

# Show help for pull-request command
doq pull-request --help

# Show help for merge command
doq merge --help
```

### Common Workflows

**Feature Development:**
1. Create branch: `doq create-branch repo develop feature/name`
2. Make changes and commit
3. Create PR: `doq pull-request repo feature/name develop --delete`

**Hotfix:**
1. Create branch: `doq create-branch repo master hotfix/issue`
2. Fix and commit
3. Create PR: `doq pull-request repo hotfix/issue master --delete`

**GitOps Deployment:**
1. Create branch: `doq create-branch gitops-k8s master env/service`
2. Update YAML: `doq set-image-yaml ...`
3. Create PR: `doq pull-request gitops-k8s env/service master --delete`

