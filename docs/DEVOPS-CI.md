# DevOps CI - Docker Image Builder

Comprehensive guide untuk DevOps CI/CD Build Tool yang terintegrasi dengan `doq` CLI.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Modes](#modes)
  - [API Mode](#api-mode)
  - [Helper Mode](#helper-mode)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)
- [Best Practices](#best-practices)

---

## Overview

DevOps CI adalah Docker image builder tool yang mendukung:
- **Multi-platform builds** dengan Docker Buildx
- **SBOM** (Software Bill of Materials) generation
- **Provenance attestation** untuk supply chain security
- **Deterministic rebuilds** dengan cache-disabled build steps
- **Resource management** (CPU dan memory limits)
- **Dual-mode operation**: API mode dan Helper mode
- **Auto image caching** untuk skip unnecessary rebuilds
- **Real-time notifications** via ntfy.sh & Microsoft Teams

### Why DevOps CI?

- ✅ **Unified CLI** - Single tool untuk semua build operations
- ✅ **Flexible** - Support API mode dan standalone helper mode
- ✅ **Automated** - Auto-skip jika image sudah ready
- ✅ **Secure** - SBOM dan provenance untuk compliance
- ✅ **Efficient** - Resource limits dan caching
- ✅ **Observable** - Real-time notifications dan JSON output

---

## Features

### Core Features

| Feature | Description |
|---------|-------------|
| **Multi-platform Build** | Build untuk berbagai platform/arsitektur |
| **SBOM Generation** | Software Bill of Materials untuk security compliance |
| **Provenance Attestation** | Cryptographic attestation untuk supply chain security |
| **Deterministic Build** | Buildx otomatis menggunakan `--attest type=provenance,mode=max` dan `--no-cache` untuk jaminan integritas |
| **Resource Management** | CPU dan memory limits untuk builder container |
| **Auto Skip Existing Image** | Skip build jika image sudah ready (API mode) sehingga tetap efisien meski build dijalankan tanpa cache |
| **Git Submodule Workaround** | Pre-clone dengan `--no-recurse-submodules` |
| **Buildx Permission Fix** | Auto-fix permission issues di Docker buildx directory |
| **Real-time Notifications** | Send build status ke ntfy.sh atau Microsoft Teams webhook |

### Output Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Default** | Full progress dengan emoji dan messages | Interactive builds |
| **JSON** | Progress + JSON result di akhir | Automation dengan monitoring |
| **Short** | Silent, hanya output image name | Scripting dan variable assignment |

### Operating Modes

| Mode | API Dependency | Config Source | Auto-Skip | Use Case |
|------|---------------|---------------|-----------|----------|
| **API Mode** | ✅ Required | API endpoint | ✅ Yes | Production CI/CD |
| **Helper Mode** | ❌ Not required | Local config | ❌ No | Development/Testing |

---

## Installation

DevOps CI terintegrasi dengan `doq` CLI. Install menggunakan installer script:

```bash
cd /home/mamat/devops-tools
./install.sh
```

Installer akan:
- Install `uv` package manager (jika belum ada)
- Install semua dependencies termasuk devops-ci module
- Create executable `doq` di `~/.local/bin`
- Setup version tracking

### Verify Installation

```bash
doq devops-ci --version-devops-ci
# Output: 🔧 DevOps CI/CD Build Tool v2.0.1

doq devops-ci --help
# Show all available options
```

---

## Quick Start

### Prerequisites

1. **Docker dan Docker Buildx** terinstall
2. **Git** terinstall
3. **Authentication file** di `~/.doq/auth.json`:

```json
{
  "BITBUCKET_USER": "your-username",
  "BITBUCKET_TOKEN": "your-token",
  "GITHUB_USER": "your-github-username",
  "GITHUB_TOKEN": "your-github-token",
  "GITUSERTOKEN": "your-git-token"
}
```

### Your First Build

#### Siapkan Docker Buildx Builder (sekali)
```bash
# Buat builder dedicated untuk DevOps CI
docker buildx create --name doq-builder --use

# Bootstrap builder agar fitur BuildKit (attestation, SBOM) aktif
docker buildx inspect --bootstrap
```
> Builder ini dapat dipilih langsung saat build dengan flag `--use-builder doq-builder`.

#### API Mode (Default):
```bash
doq devops-ci saas-be-core develop
```

> Catatan: Setiap eksekusi buildx akan otomatis menambahkan `--attest type=provenance,mode=max` dan `--no-cache` untuk menghasilkan provenance SLSA maksimal dan menghindari reuse cache lama.

Output:
```
🌐 Running in API MODE
📦 Fetching build metadata for repo=saas-be-core, refs=develop ...
✅ Image already ready: loyaltolpi/saas-be-core:develop-abc123. Skipping build.
📤 Notification sent to ntfy.sh
```

#### Helper Mode (No API):
```bash
doq devops-ci saas-be-core develop --helper
```

Output:
```
🔧 Running in HELPER MODE (no API dependency)
🔧 Helper mode: Generating metadata locally...
📝 Generated image name: loyaltolpi/saas-be-core:develop-20241106143022
🚧 Starting build process...
```

---

## Modes

### API Mode

**Default mode** yang fetch metadata dan configuration dari API endpoint.

#### How It Works

1. **Fetch Metadata** dari `DEFAULT_URL_API/v1/image/fe`
   - Check apakah image sudah ready
   - Get existing image name atau build-image name

2. **Fetch Config** dari `DEFAULT_URL_API/v1/file`
   - Load `cicd/cicd.json` dari repository
   - Get build args (registry, port, dll)

3. **Auto-Skip** jika image sudah ready (kecuali `--rebuild`)

4. **Build** dengan config dari API
   - Docker Buildx dijalankan dengan `--attest type=provenance,mode=max` dan `--no-cache` untuk menghasilkan provenance maksimal dan mencegah reuse layer lama

#### When to Use

- ✅ Production CI/CD pipelines
- ✅ Team collaboration dengan shared metadata
- ✅ Butuh auto-skip capability
- ✅ Centralized configuration management

#### Configuration

Set API URL via environment variable:
```bash
export DEFAULT_URL_API=http://your-api-endpoint:5000
doq devops-ci saas-be-core develop
```

#### Example

```bash
# Basic API mode build
doq devops-ci saas-be-core develop

# Force rebuild dengan API mode
doq devops-ci saas-be-core develop --rebuild

# API mode dengan JSON output
doq devops-ci saas-be-core develop --json
```

---

### Helper Mode

**Standalone mode** yang tidak memerlukan API eksternal.

#### How It Works

1. **Generate Metadata** locally dari config files
   - Always set ready=false (always build)
   - Generate image name dari template

2. **Load Config** dari local files:
   - `~/.doq/.env`
   - `~/.doq/helper-config.json`
   - Environment variables
   - CLI arguments

3. **Build** dengan config lokal (no API calls)
   - Buildx juga menjalankan `--attest type=provenance,mode=max` dan `--no-cache` untuk konsistensi dengan API mode

#### When to Use

- ✅ Development/testing di local machine
- ✅ Environment tanpa access ke API
- ✅ Custom workflows tanpa API dependency
- ✅ Portability - bisa jalan dimana saja

#### Activation

3 cara untuk activate helper mode:

**1. Via CLI Flag:**
```bash
doq devops-ci saas-be-core develop --helper
```

**2. Via Environment Variable:**
```bash
export DEVOPS_CI_MODE=helper
doq devops-ci saas-be-core develop
```

**3. Via Config File `~/.doq/.env`:**
```bash
# Add to ~/.doq/.env
DEVOPS_CI_MODE=helper
```

Kemudian jalankan tanpa flag:
```bash
doq devops-ci saas-be-core develop
```

#### Configuration

**Option 1: Environment Variables**
```bash
export DEVOPS_CI_MODE=helper
export HELPER_IMAGE_TEMPLATE="loyaltolpi/{repo}:{refs}-{timestamp}"
export HELPER_REGISTRY01="registry.example.com"
export HELPER_DEFAULT_PORT="3000"
```

**Option 2: Config File `~/.doq/.env`**
```bash
# DevOps CI Mode
DEVOPS_CI_MODE=helper

# Helper Mode Settings
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{timestamp}
HELPER_REGISTRY01=registry.example.com
HELPER_DEFAULT_PORT=3000
HELPER_DEFAULT_PORT2=
```

**Option 3: JSON Config `~/.doq/helper-config.json`**
```json
{
  "mode": "helper",
  "image_template": "loyaltolpi/{repo}:{refs}-{timestamp}",
  "registry01": "registry.example.com",
  "default_port": "3000",
  "default_port2": ""
}
```

#### Image Name Template

Template variables yang didukung:

| Variable | Description | Example |
|----------|-------------|---------|
| `{repo}` | Repository name | `saas-be-core` |
| `{refs}` | Branch/tag name | `develop` |
| `{timestamp}` | Current timestamp | `20241106143022` |
| `{short_hash}` | Git short hash (future) | `abc123d` |

**Examples:**
```bash
# Template 1: Standard versioning
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{timestamp}
# Result: loyaltolpi/saas-be-core:develop-20241106143022

# Template 2: Simple latest
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:latest
# Result: loyaltolpi/saas-be-core:latest

# Template 3: With registry prefix
HELPER_IMAGE_TEMPLATE=registry.io/project/{repo}:{refs}
# Result: registry.io/project/saas-be-core:develop
```

---

## Configuration

### Configuration Priority

Settings di-load dengan priority (highest to lowest):

1. **CLI Arguments** - `--image-name`, `--registry`, `--port`
2. **Environment Variables** - `HELPER_*`, `DEFAULT_*`
3. **~/.doq/.env** file
4. **~/.doq/helper-config.json** file
5. **Default Values**

### Environment Variables

#### General Settings
```bash
# Mode selection
DEVOPS_CI_MODE=api          # atau "helper"

# API settings (API mode)
DEFAULT_URL_API=http://193.1.1.3:5000
DEFAULT_MEMORY=2g
DEFAULT_CPUS=1
DEFAULT_CPU_PERIOD=100000
DEFAULT_CPU_QUOTA=100000

# Notification
NTFY_URL=https://ntfy.sh/doi-notif
TEAMS_WEBHOOK="https://qoinid.webhook.office.com/..."
```

#### Helper Mode Settings
```bash
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{timestamp}
HELPER_REGISTRY01=registry.example.com
HELPER_DEFAULT_PORT=3000
HELPER_DEFAULT_PORT2=
```

#### Authentication (Required for both modes)
```bash
# Stored in ~/.doq/auth.json
BITBUCKET_USER=your-username
BITBUCKET_TOKEN=your-token
GITHUB_USER=your-github-user
GITHUB_TOKEN=your-github-token
GITUSERTOKEN=your-git-token
```

---

## Usage Examples

### Basic Usage

#### Build dengan API Mode (Default)
```bash
doq devops-ci saas-be-core develop
```

#### Force Rebuild
```bash
doq devops-ci saas-be-core develop --rebuild
```

#### Build dengan Custom Image Name
```bash
doq devops-ci saas-be-core develop loyaltolpi/saas-be-core:custom-v1.0
```

### Helper Mode Examples

#### Basic Helper Mode
```bash
doq devops-ci saas-be-core develop --helper
```

#### Helper Mode dengan Custom Image
```bash
doq devops-ci saas-be-core develop --helper \
  --image-name loyaltolpi/saas-be-core:test-123
```

#### Helper Mode dengan Full Custom Settings
```bash
doq devops-ci saas-be-core develop --helper \
  --image-name loyaltolpi/saas-be-core:feature-auth \
  --registry registry.example.com \
  --port 8080
```

### Output Mode Examples

#### Default Output (Interactive)
```bash
doq devops-ci saas-be-core develop
```
Output menampilkan full progress dengan emoji dan messages.

#### JSON Output (for Automation)
```bash
doq devops-ci saas-be-core develop --json
```
Output:
```json
{
  "status": "success",
  "repository": "saas-be-core",
  "branch": "develop",
  "image": "loyaltolpi/saas-be-core:develop-abc123",
  "build_time": {
    "start_unix": 1704067200,
    "end_unix": 1704067800,
    "duration": {
      "seconds": 600,
      "formatted": "10m 0s"
    }
  },
  "config": {
    "memory": "2g",
    "cpus": "1"
  }
}
```

#### Short Output (for Scripting)
```bash
IMAGE=$(doq devops-ci saas-be-core develop --short)
echo "Built: $IMAGE"
```
Output hanya nama image:
```
loyaltolpi/saas-be-core:develop-abc123
```

### Notifications

#### Microsoft Teams Webhook
```bash
# Optional: set once in your shell or ~/.doq/.env
export TEAMS_WEBHOOK="https://qoinid.webhook.office.com/webhookb2/63088020-7311-4b72-89eb-bc9f58447c9f@e38b30ee-ec18-44bd-8385-08e0acf73344/IncomingWebhook/bda6ddbee1994ed2889eef787ec2eb3e/3609c769-241b-4a44-86c7-f95526b7b84c/V2_ldAc5LeB3fhZC8wtt8TIDqaMKOZf15jYNcH4gl1V4c1"

# Trigger build with Teams notification (env or flag)
doq devops-ci saas-be-core develop --json
# or
doq devops-ci saas-be-core develop --webhook "$TEAMS_WEBHOOK"
```

Pesan akan dikirim setiap build selesai (success, skipped, atau failed) dengan ringkasan repository, branch, dan image yang dibangun.

### Resource Management

#### Custom Memory dan CPU
```bash
DEFAULT_MEMORY=4g DEFAULT_CPUS=2 doq devops-ci saas-be-core develop
```

#### CPU Quota Control
```bash
DEFAULT_CPU_PERIOD=100000 DEFAULT_CPU_QUOTA=200000 \
  doq devops-ci saas-be-core develop
```

---

## Advanced Usage

### Scenario 1: Development Workflow

Gunakan helper mode untuk rapid iteration tanpa API dependency:

```bash
# Set helper mode di config
cat >> ~/.doq/.env << EOF
DEVOPS_CI_MODE=helper
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:dev-{timestamp}
HELPER_REGISTRY01=registry.dev.example.com
HELPER_DEFAULT_PORT=3000
EOF

# Build dengan config
doq devops-ci my-service develop

# Override untuk testing
doq devops-ci my-service develop --helper \
  --image-name loyaltolpi/my-service:test-feature-x
```

### Scenario 2: CI/CD Pipeline

Gunakan API mode dengan JSON output untuk automation:

```bash
#!/bin/bash
# ci-pipeline.sh

set -e

# Build dengan JSON output
BUILD_RESULT=$(doq devops-ci $REPO $BRANCH --json)

# Parse result
STATUS=$(echo $BUILD_RESULT | jq -r '.status')
IMAGE=$(echo $BUILD_RESULT | jq -r '.image')

if [ "$STATUS" = "success" ]; then
    echo "✅ Build successful: $IMAGE"
    # Deploy image
    kubectl set image deployment/my-app app=$IMAGE
else
    echo "❌ Build failed"
    exit 1
fi
```

### Scenario 3: Multi-Environment Builds

Build untuk berbagai environment dengan template:

```bash
# Development
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:dev-{timestamp} \
  doq devops-ci saas-be-core develop --helper

# Staging
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:staging-{refs} \
  doq devops-ci saas-be-core staging --helper

# Production
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs} \
  doq devops-ci saas-be-core main --helper
```

### Scenario 4: Batch Builds

Build multiple services secara parallel:

```bash
#!/bin/bash
# batch-build.sh

SERVICES=("saas-be-core" "saas-apigateway" "saas-fe")
BRANCH="develop"

for service in "${SERVICES[@]}"; do
    echo "Building $service..."
    doq devops-ci $service $BRANCH --short &
done

# Wait for all builds
wait

echo "All builds completed!"
```

### Scenario 5: Build dengan Custom Dockerfile Location

Jika Dockerfile tidak di root directory, pre-clone dulu:

```bash
# Helper mode akan pre-clone repository
# Docker build akan jalan dari clone directory
doq devops-ci my-service develop --helper
```

### Scenario 6: Builder Resource Limits (Advanced)
Untuk workload besar, gunakan builder `docker-container` dengan batas resource:

```bash
# Buat builder dengan driver docker-container
docker buildx create --name doq-builder-heavy --driver docker-container --use

# Bootstrap builder agar siap pakai
docker buildx inspect --bootstrap

# Batasi resource container builder (Docker 20.10+)
docker update --cpus=4 --memory=6g buildx_buildkit_doq-builder-heavy0

# Jalankan build menggunakan builder tersebut
doq devops-ci saas-be-core develop --rebuild --use-builder doq-builder-heavy
```

Tips:
- Sesuaikan nilai `--cpus` dan `--memory` dengan kapasitas host.
- Gunakan `docker buildx ls` untuk memastikan builder aktif.
- Pisahkan builder ringan vs berat (misal `doq-builder`, `doq-builder-heavy`) dan pilih lewat `--use-builder`.

---

## Troubleshooting

### Problem 1: Permission Issues

**Error:**
```
⚠️ Warning: Could not apply resource limits to builder container
```

**Solution:**
Script otomatis fix permissions, tapi jika masih error:
```bash
# Manual fix
sudo chown -R $USER:$USER ~/.docker/buildx
chmod -R u+rw ~/.docker/buildx
```

### Problem 2: Git Submodule Errors

**Error:**
```
fatal: No url found for submodule path '...' in .gitmodules
```

**Solution:**
DevOps CI otomatis handle ini dengan pre-clone menggunakan `--no-recurse-submodules`. Jika masih error, check authentication:
```bash
# Verify auth file
cat ~/.doq/auth.json

# Test git access
git clone --no-recurse-submodules \
  https://$BITBUCKET_USER:$BITBUCKET_TOKEN@bitbucket.org/loyaltoid/repo.git
```

### Problem 3: Builder Not Found

**Error:**
```
⚠️ Warning: Could not create builder 'container-builder'
```

**Solution:**
```bash
# Remove existing builder
docker buildx rm container-builder

# Run build lagi (akan create builder otomatis)
doq devops-ci saas-be-core develop
```

### Problem 4: API Endpoint Unreachable

**Error:**
```
❌ Error: Failed to fetch build metadata from API: Connection refused
```

**Solution:**
```bash
# Option 1: Check API URL
echo $DEFAULT_URL_API

# Option 2: Test API
curl -v http://193.1.1.3:5000/v1/image/fe?repo=test&refs=develop

# Option 3: Use helper mode
doq devops-ci saas-be-core develop --helper
```

### Problem 5: Authentication File Not Found

**Error:**
```
❌ Error: Authentication file /home/user/.devops/auth.json not found
```

**Solution:**
```bash
# Create auth file
mkdir -p ~/.devops
cat > ~/.doq/auth.json << EOF
{
  "BITBUCKET_USER": "your-username",
  "BITBUCKET_TOKEN": "your-token",
  "GITHUB_USER": "your-github-user",
  "GITHUB_TOKEN": "your-github-token",
  "GITUSERTOKEN": "your-git-token"
}
EOF

chmod 600 ~/.doq/auth.json
```

### Problem 6: Build Timeout

**Error:**
```
❌ Error: Docker build timed out (1 hour limit)
```

**Solution:**
```bash
# Check builder resources
docker ps --filter name=buildx_buildkit_container-builder

# Increase resources
docker update --cpus=4 --memory=4g buildx_buildkit_container-builder0

# Retry build
doq devops-ci saas-be-core develop --rebuild
```

---

## Best Practices

### 1. Use Appropriate Mode

- **Production CI/CD**: Use API mode untuk consistency
- **Local Development**: Use helper mode untuk flexibility
- **Testing**: Use helper mode dengan custom image names

### 2. Image Naming Convention

```bash
# Good practices:
# - Include environment/branch
# - Include version atau timestamp
# - Use semantic versioning untuk production

# Development
loyaltolpi/{repo}:dev-{timestamp}

# Staging
loyaltolpi/{repo}:staging-{refs}

# Production
loyaltolpi/{repo}:v{version}
```

### 3. Resource Limits

```bash
# Default (light workload)
DEFAULT_MEMORY=2g DEFAULT_CPUS=1

# Medium workload
DEFAULT_MEMORY=4g DEFAULT_CPUS=2

# Heavy workload (large projects)
DEFAULT_MEMORY=8g DEFAULT_CPUS=4
```

### 4. Output Modes

```bash
# Interactive development
doq devops-ci ... 

# CI/CD automation
doq devops-ci ... --json

# Simple scripting
IMAGE=$(doq devops-ci ... --short)
```

### 5. Security

```bash
# Protect auth file
chmod 600 ~/.doq/auth.json

# Don't commit auth file to git
echo ".devops/" >> .gitignore

# Use environment-specific auth
# ~/.doq/auth.json untuk masing-masing environment
```

### 6. Monitoring

```bash
# Enable notifications
export NTFY_URL=https://ntfy.sh/your-private-topic

# Use JSON output untuk logging
doq devops-ci $REPO $BRANCH --json | tee build.log

# Parse dan store metrics
jq '.build_time.duration.seconds' build.log
```

### 7. Error Handling

```bash
#!/bin/bash
# robust-build.sh

set -euo pipefail

if ! doq devops-ci $REPO $BRANCH --json > build.log 2>&1; then
    echo "❌ Build failed"
    # Send alert
    curl -d "Build failed for $REPO:$BRANCH" $ALERT_URL
    # Cleanup
    docker system prune -f
    exit 1
fi

echo "✅ Build successful"
```

### 8. Config Management

```bash
# Use separate configs per environment
~/.doq/
├── auth.json           # Shared auth
├── .env.development    # Dev config
├── .env.staging        # Staging config
└── .env.production     # Prod config

# Load appropriate config
source ~/.doq/.env.$ENVIRONMENT
doq devops-ci $REPO $BRANCH
```

---

## FAQ

### Q: Apa perbedaan antara API mode dan Helper mode?

**A:** API mode fetch metadata dari API eksternal dan bisa auto-skip jika image sudah ready. Helper mode generate metadata locally dan selalu build tanpa API dependency.

### Q: Kapan sebaiknya menggunakan Helper mode?

**A:** Gunakan helper mode untuk:
- Local development/testing
- Environment tanpa API access
- Custom workflows
- Portable builds

### Q: Bagaimana cara switch dari API mode ke Helper mode?

**A:** 3 cara:
1. Tambahkan flag `--helper`
2. Set `DEVOPS_CI_MODE=helper` di environment
3. Tambahkan `DEVOPS_CI_MODE=helper` di `~/.doq/.env`

### Q: Apakah Helper mode memerlukan auth file?

**A:** Ya, baik API mode maupun Helper mode tetap memerlukan `~/.doq/auth.json` untuk git authentication.

### Q: Bagaimana cara custom image name di Helper mode?

**A:** 2 cara:
1. Gunakan `--image-name`: `doq devops-ci repo branch --helper --image-name custom:tag`
2. Set template di config: `HELPER_IMAGE_TEMPLATE=your/{repo}:template`

### Q: Apakah bisa menggunakan kedua mode secara bersamaan?

**A:** Tidak, setiap build hanya menggunakan satu mode. Tapi anda bisa switch mode per-build dengan flag atau config.

### Q: Bagaimana cara debugging jika build gagal?

**A:** 
1. Check logs dengan mode verbose (default)
2. Verify auth file: `cat ~/.doq/auth.json`
3. Test builder: `docker buildx ls`
4. Check resources: `docker stats`
5. Gunakan `--json` untuk detailed error info

---

## Support & Contributing

### Get Help

- **Documentation**: Baca README.md untuk overview
- **Issues**: Report bugs atau request features
- **CLI Help**: `doq devops-ci --help-devops-ci`

### Version Information

```bash
doq devops-ci --version-devops-ci
doq version
```

---

## License

Part of DevOps Q CLI tools.

## Changelog

### v2.0.1 (2024-11-06)
- Added Helper Mode (no API dependency)
- Added dual-mode support (API and Helper)
- Added image name template system
- Added multiple config file support
- Fixed notification encoding issues
- Improved documentation

### v2.0.0
- Initial Python implementation
- SBOM and provenance support
- Resource management
- Auto permission fixes
- Multiple output modes

---

**Happy Building! 🚀**

