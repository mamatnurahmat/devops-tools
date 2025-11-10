# DevOps Q

Simple CLI tool untuk mengelola Rancher resources menggunakan Python.

## 📚 Documentation

- **[AUTHENTICATION.md](docs/AUTHENTICATION.md)** - Complete authentication guide
  - Setup credentials from `~/.netrc` and `~/.docker/config.json`
  - Auto-creation of `~/.doq/auth.json`
  - Environment variable fallback
  - Quick setup scripts
- **[DEVOPS-CI.md](docs/DEVOPS-CI.md)** - DevOps CI/CD build system
- **[DOQ-IMAGE.md](docs/DOQ-IMAGE.md)** - Docker image checker
- **[DEPLOY-WEB.md](docs/DEPLOY-WEB.md)** - Web deployment via Docker Compose
- **[DEPLOY-K8S.md](docs/DEPLOY-K8S.md)** - Kubernetes deployment

## Instalasi

### Quick Install (Cara Tercepat - Recommended)

Instalasi langsung dalam satu command tanpa perlu clone repository manual dan **tanpa perlu root permission**:

```bash
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes
```

**Apa yang terjadi:**
1. ✅ Script otomatis clone repository ke `~/.local/share/devops-q` (user directory, tidak perlu root)
2. ✅ Menginstall `uv` package manager jika belum tersedia
3. ✅ Menginstall semua dependencies menggunakan `uv`
4. ✅ Membuat executable `doq` di `~/.local/bin`
5. ✅ Menyimpan commit hash untuk version tracking

**Setelah instalasi:**
```bash
# Tambahkan ke PATH jika belum ada (untuk shell saat ini)
export PATH="${HOME}/.local/bin:${PATH}"

# Atau tambahkan ke ~/.bashrc atau ~/.zshrc untuk permanen
echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> ~/.bashrc

# Verifikasi instalasi
doq --help
```

### Membuat doq tersedia secara global (user site)

Agar `doq` bisa dipanggil dari direktori manapun dan Python mengenali modul `doq` saat menjalankan `python3 -m doq`, install juga ke user site-packages dan pastikan `~/.local/bin` ada di PATH:

```bash
# Install ke user site-packages (editable)
python3 -m pip install --user -e .

# Pastikan ~/.local/bin ada di PATH untuk shell berikutnya (Zsh)
echo $PATH | tr ':' '\n' | grep -x "$HOME/.local/bin" || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
```

Catatan:
- Perubahan PATH pada `~/.zshrc` berlaku setelah Anda membuka shell baru atau menjalankan `source ~/.zshrc`.
- Installer juga mencoba melakukan langkah ini secara otomatis.

**Catatan:** Default instalasi menggunakan direktori user (`~/.local/share/devops-q`) sehingga tidak memerlukan root permission. Jika ingin install ke `/opt` atau lokasi sistem lainnya, gunakan `--prefix` dengan sudo.

### Metode Instalasi Lainnya

#### 1. Instalasi dengan Opsi Kustom

Jika ingin mengubah lokasi instalasi atau menggunakan branch/commit tertentu:

```bash
# Install ke direktori custom
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes --prefix /opt/my-devops-q

# Install dari branch atau commit tertentu
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes --ref develop

# Install dengan semua opsi kustom
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes \
  --repo https://github.com/mamatnurahmat/devops-tools \
  --ref main \
  --prefix /opt/devops-q
```

**Opsi yang Tersedia:**
- `--yes`: Auto-clone repository tanpa konfirmasi (diperlukan untuk pipe mode)
- `--repo URL`: URL repository GitHub (default: https://github.com/mamatnurahmat/devops-tools)
- `--ref BRANCH`: Branch atau commit hash (default: main)
- `--prefix DIR`: Direktori untuk clone repository (default: `~/.local/share/devops-q` - tidak perlu root)
- `--skip-clone`: Skip auto-clone jika sudah di dalam project directory

**Tips:**
- Default `--prefix` menggunakan user directory (`~/.local/share/devops-q`) sehingga tidak memerlukan root permission
- Jika ingin install ke `/opt` atau lokasi sistem lainnya yang memerlukan root, gunakan `sudo` atau ubah ownership setelah clone:
  ```bash
  curl -fsSL ... | bash -s -- --yes --prefix /opt/devops-q
  # Jika error permission, gunakan:
  sudo mkdir -p /opt/devops-q
  sudo chown -R $(whoami):$(whoami) /opt/devops-q
  curl -fsSL ... | bash -s -- --yes --prefix /opt/devops-q
  ```

**Menggunakan Environment Variables:**

```bash
# Menggunakan user directory (default, tidak perlu root)
REPO_URL=https://github.com/mamatnurahmat/devops-tools \
REPO_REF=main \
PREFIX="${HOME}/.local/share/devops-q" \
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes

# Atau ke lokasi sistem (memerlukan root)
REPO_URL=https://github.com/mamatnurahmat/devops-tools \
REPO_REF=main \
PREFIX=/opt/devops-q \
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes
```

#### 2. Manual Clone (Jika Lebih Suka Clone Manual)

Jika ingin clone repository secara manual terlebih dahulu:

```bash
# Clone repository ke user directory (tidak perlu root)
git clone https://github.com/mamatnurahmat/devops-tools.git ~/.local/share/devops-q
cd ~/.local/share/devops-q

# Jalankan installer
./install.sh
```

Atau jika ingin clone ke lokasi sistem (membutuhkan root):

```bash
# Clone repository ke /opt (membutuhkan root)
sudo git clone https://github.com/mamatnurahmat/devops-tools.git /opt/devops-q
sudo chown -R $(whoami):$(whoami) /opt/devops-q
cd /opt/devops-q

# Jalankan installer
./install.sh
```

Script installer akan:
- Menginstall `uv` package manager jika belum tersedia (otomatis)
- Menginstall dependencies menggunakan `uv` (lebih cepat dan reliable dibanding pip)
- Membuat executable `doq` di `~/.local/bin`
- Menyimpan commit hash ke file version tracking

#### 3. Menggunakan uv Langsung (Advanced)

Jika Anda sudah memiliki `uv` terinstall dan ingin kontrol lebih:

```bash
# Install uv jika belum ada
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/mamatnurahmat/devops-tools.git /opt/devops-q
cd /opt/devops-q

# Install project dependencies
uv pip install -e .
```

**Catatan:** Proyek ini menggunakan `uv` sebagai package manager default untuk instalasi yang lebih cepat dan reliable.

## Konfigurasi

### Login (Recommended)

Jika file `.env` belum ada, gunakan command `login` untuk melakukan autentikasi:

```bash
doq login
```

**Fitur Smart Login:**
- Jika config sudah ada dan token masih valid (tidak expired), akan menampilkan info existing dan tidak perlu login lagi
- Jika token expired atau invalid, akan otomatis melakukan login
- Gunakan `--force` untuk force re-login meskipun token masih valid

Command ini akan:
- Default URL: `https://193.1.1.4`
- Default insecure mode: `true` (skip SSL verification)
- Meminta username dan password (jika perlu login)
- Mengambil token dari Rancher API
- Menyimpan config ke `$HOME/.doq/.env` (folder/file akan dibuat otomatis jika belum ada)

Contoh dengan parameter:

```bash
doq login --url https://193.1.1.4 --username admin --password secret
```

Atau dengan prompt interaktif:

```bash
doq login --url https://193.1.1.4
# Username: admin
# Password: (hidden)
```

Force re-login:

```bash
doq login --force
```

### Manual Config

Set konfigurasi Rancher API secara manual (disimpan di `$HOME/.doq/.env`):

```bash
doq config --url https://rancher.example.com --token <your-token>
```

Secara default, mode insecure (skip SSL verification) diaktifkan. Untuk menggunakan SSL verification:

```bash
doq config --url https://rancher.example.com --token <your-token> --secure
```

Lihat konfigurasi saat ini:

```bash
doq config
```

### Check Token

Cek validitas dan status expired token:

```bash
doq token-check
```

Command ini akan:
- Menggunakan token dari config file
- Mengecek apakah token valid
- Mengecek apakah token sudah expired
- Menampilkan waktu expired jika tersedia

Output JSON:

```bash
doq token-check --json
```

Check token dengan URL/token custom:

```bash
doq token-check --url https://rancher.example.com --token <token>
```

## Penggunaan

### List Projects

```bash
doq project
```

Filter by cluster:

```bash
doq project --cluster <cluster-id>
```

### Get Kubeconfig

Get kubeconfig dari project dan simpan ke `~/.kube/config`:

```bash
doq kube-config <project-id>
```

Dengan default, kubeconfig akan di-flatten. Opsi tambahan:

```bash
# Tanpa flatten
doq kube-config <project-id> --no-flatten

# Replace existing config (default: merge)
doq kube-config <project-id> --replace

# Set sebagai current context
doq kube-config <project-id> --set-context
```

## Kubernetes Resource Management

DevOps Q menyediakan berbagai command untuk mengelola Kubernetes resources dengan dukungan automatic context switching.

### Switch Context by Namespace

Switch kubectl context berdasarkan namespace format `{project}-{env}`:

```bash
doq ns <namespace>
```

Command ini akan:
- Parse namespace format `{project}-{env}` (contoh: `develop-saas`)
- Mencari context yang sesuai dengan environment menggunakan regex matching
- Otomatis switch ke context yang cocok (contoh: `develop-saas` → `rke2-develop-qoin`)

Contoh:

```bash
# Switch ke context untuk develop environment
doq ns develop-saas

# Switch ke context untuk production environment
doq ns production-saas
```

### Set Image for Deployment

Set image untuk deployment dengan automatic context switching:

```bash
doq set-image <namespace> <deployment> <image>
```

Command ini akan:
- Otomatis switch context berdasarkan namespace
- Mendeteksi container name dari deployment (mendukung multiple containers)
- Update image untuk container yang sesuai

Contoh:

```bash
# Set image untuk deployment
doq set-image develop-doq doq-nginx-proxy nginx:1.25

# Set image dengan registry URL
doq set-image develop-doq my-app registry.example.com/app:v1.0.0
```

### Get Image Information

Get informasi image yang digunakan deployment:

```bash
doq get-image <namespace> <deployment>
```

Output human-readable:

```bash
doq get-image develop-doq doq-nginx-proxy
```

Output JSON:

```bash
doq get-image develop-doq doq-nginx-proxy --json
```

### Get Resource Information (JSON Format)

Semua command berikut mengembalikan output dalam format JSON (silent mode) dan otomatis switch context:

#### Get Deployment

```bash
doq get-deploy <namespace> <deployment>
```

Contoh:

```bash
# Get deployment info
doq get-deploy develop-doq doq-nginx-proxy

# Pipe ke jq untuk filtering
doq get-deploy develop-doq doq-nginx-proxy | jq '.spec.template.spec.containers[0].image'
```

#### Get Service

```bash
doq get-svc <namespace> <service>
```

Contoh:

```bash
# Get service info
doq get-svc develop-doq doq-nginx-proxy

# Get service port
doq get-svc develop-doq doq-nginx-proxy | jq '.spec.ports[0].port'
```

#### Get ConfigMap

```bash
doq get-cm <namespace> <configmap>
```

Contoh:

```bash
# Get configmap info
doq get-cm develop-doq nginx-proxy-config

# Get specific data value
doq get-cm develop-doq nginx-proxy-config | jq '.data.nginx.conf'
```

#### Get Secret (with Base64 Decoding)

```bash
doq get-secret <namespace> <secret>
```

Command ini akan:
- Otomatis decode semua values di field `data` dari base64
- Menambahkan annotation `_doq.decoded: true` untuk menandai bahwa data sudah di-decode
- Output langsung readable tanpa perlu decode manual

Contoh:

```bash
# Get secret dengan decoded values
doq get-secret develop-doq s3www-secret

# Get specific secret value (sudah decoded)
doq get-secret develop-doq s3www-secret | jq -r '.data.MINIO_ACCESS_KEY'

# Get secret dengan key yang memiliki karakter khusus (misalnya .env)
doq get-secret develop-saas file-config-saas-be-admin-manager | jq -r '.data[".env"]'
```

**Catatan:** Semua command `get-*` menggunakan silent mode (hanya output JSON), sehingga cocok untuk scripting dan piping ke tools lain seperti `jq`.

## Update Management

DevOps Q menggunakan sistem version tracking berbasis commit hash untuk mengelola update. Setiap instalasi akan menyimpan commit hash yang terinstall ke file `~/.doq/version.json`.

### Check Update

Cek apakah ada update tersedia di repository:

```bash
doq check-update
```

Command ini akan:
- Membandingkan commit hash terinstall dengan commit hash terbaru di repository
- Menampilkan informasi versi saat ini dan versi terbaru
- Memberikan instruksi untuk update jika tersedia

Output JSON:

```bash
doq check-update --json
```

### Update ke Versi Terbaru

Ada beberapa cara untuk melakukan update:

#### 1. Update Otomatis ke Latest (Recommended)

```bash
doq update
```

Command ini akan:
- Otomatis mengecek apakah ada update tersedia
- Jika sudah latest, menampilkan pesan bahwa sudah up-to-date
- Jika ada update, akan otomatis update ke commit terbaru

#### 2. Update ke Latest Commit Secara Eksplisit

```bash
doq update --latest
```

Command ini akan:
- Langsung mengambil latest commit hash dari repository
- Update ke commit terbaru tanpa mengecek versi saat ini

#### 3. Update ke Commit Tertentu

```bash
doq update <commit_hash>
```

Command ini akan:
- Clone repository dari `https://github.com/mamatnurahmat/doq-tools`
- Checkout ke commit hash yang ditentukan
- Menjalankan installer script (`install.sh`) menggunakan `uv`
- Update installation ke versi commit tersebut
- Menyimpan commit hash baru ke file version tracking

Contoh:

```bash
# Update ke commit tertentu
doq update abc123def4567890123456789012345678901234

# Update otomatis ke latest
doq update

# Update ke latest commit secara eksplisit
doq update --latest
```

### Version Information

Lihat informasi versi yang terinstall:

```bash
doq version
```

Output JSON:

```bash
doq version --json
```

Informasi yang ditampilkan:
- Commit Hash: Hash commit yang terinstall
- Installed At: Waktu instalasi terakhir
- Repository: URL repository
- Branch: Branch yang digunakan (default: main)

### Cara Kerja Update Management

1. **Version Tracking**: Setiap instalasi menyimpan commit hash ke `~/.doq/version.json`
2. **Update Check**: Command `check-update` menggunakan `git ls-remote` untuk mendapatkan commit hash terbaru tanpa perlu clone repository
3. **Update Process**: 
   - Clone repository ke temporary directory
   - Checkout ke commit yang ditentukan
   - Jalankan installer script yang akan menggunakan `uv` untuk install dependencies
   - Update version tracking setelah instalasi berhasil
   - Cleanup temporary files

**Catatan:** 
- Perlu git terinstall di sistem untuk menggunakan fitur update
- Update akan menggunakan `uv` package manager untuk instalasi yang lebih cepat
- Version tracking berbasis commit hash memastikan update berdasarkan commit yang tepat

## DevOps CI/CD - Docker Image Builder

DevOps Q sekarang terintegrasi dengan Docker image builder untuk build otomatis dari Bitbucket repositories dengan fitur SBOM, provenance attestation, dan resource management.

> 📖 **Detailed Documentation**: Lihat [DEVOPS-CI.md](docs/DEVOPS-CI.md) untuk comprehensive guide dengan contoh lengkap

## Web Application Deployment

DevOps Q menyediakan automated web application deployment menggunakan Docker Compose over SSH dengan smart image management dan environment detection.

> 📖 **Detailed Documentation**: Lihat [DEPLOY-WEB.md](docs/DEPLOY-WEB.md) untuk comprehensive guide dengan contoh lengkap

### Requirements

- Docker dan Docker Buildx terinstall
- Git terinstall
- File authentication di `~/.doq/auth.json` dengan format:
```json
{
  "BITBUCKET_USER": "your-username",
  "BITBUCKET_TOKEN": "your-token",
  "GITHUB_USER": "your-github-username",
  "GITHUB_TOKEN": "your-github-token",
  "GITUSERTOKEN": "your-git-token"
}
```

### Basic Usage

Build Docker image dari repository:

```bash
doq devops-ci <REPO> <REFS>
```

Contoh:

```bash
# Build dari branch develop
doq devops-ci saas-be-core develop

# Build dari tag
doq devops-ci saas-apigateway v1.2.0

# Build dari branch main
doq devops-ci saas-fe main
```

### Advanced Options

#### Force Rebuild

Force rebuild meskipun image sudah ada:

```bash
doq devops-ci saas-be-core develop --rebuild
```

#### Custom Image Name

Override nama/tag image:

```bash
doq devops-ci saas-be-core develop --rebuild loyaltolpi/saas-be-core:dev-123
```

#### Output Modes

**Default Mode** - Progress lengkap dengan emoji:
```bash
doq devops-ci saas-be-core develop
```

**JSON Mode** - Progress + JSON result di akhir (untuk automation):
```bash
doq devops-ci saas-be-core develop --json
```

Parse JSON dari output:
```bash
doq devops-ci saas-be-core develop --json | tee build.log
grep "BUILD RESULT" build.log -A 5 | grep '^{' | jq .
```

**Short Mode** - Silent, hanya output nama image (untuk scripting):
```bash
IMAGE=$(doq devops-ci saas-be-core develop --short)
echo "Built: $IMAGE"
```

### Environment Variables

#### Resource Limits
```bash
# Custom memory dan CPU
DEFAULT_MEMORY=4g DEFAULT_CPUS=2 doq devops-ci saas-be-core develop

# CPU quota dan period
DEFAULT_CPU_PERIOD=100000 DEFAULT_CPU_QUOTA=200000 doq devops-ci saas-be-core develop
```

#### API Configuration
```bash
# Custom API endpoint
DEFAULT_URL_API=http://custom-api:5000 doq devops-ci saas-be-core develop
```

#### Notification
```bash
# Custom ntfy.sh URL
NTFY_URL=https://ntfy.sh/my-custom-topic doq devops-ci saas-be-core develop
```

### Features

✅ **Multi-platform Build Support** - Build untuk berbagai platform/arsitektur  
✅ **SBOM Generation** - Software Bill of Materials untuk security compliance  
✅ **Provenance Attestation** - Cryptographic attestation untuk supply chain security  
✅ **Resource Management** - CPU dan memory limits untuk builder container (default: 4 CPUs, 4GB RAM)  
✅ **Auto Image Caching** - Skip build jika image sudah ready  
✅ **Git Submodule Workaround** - Pre-clone dengan `--no-recurse-submodules` untuk menghindari error submodule  
✅ **Real-time Notifications** - Kirim status build ke ntfy.sh otomatis  
✅ **Buildx Permission Fix** - Auto-fix permission issues di Docker buildx directory  

### Build Process

1. **Fetch Metadata** - Ambil metadata build dari API
2. **Check Image Status** - Cek apakah image sudah ready (skip jika sudah ada, kecuali --rebuild)
3. **Fetch Configuration** - Load `cicd/cicd.json` dari repository
4. **Load Authentication** - Baca credentials dari `~/.doq/auth.json`
5. **Setup Builder** - Setup/verify Docker buildx builder dengan resource limits
6. **Pre-clone Repository** - Clone dengan `--no-recurse-submodules` untuk avoid error
7. **Execute Build** - Run docker buildx dengan SBOM dan provenance
8. **Push Image** - Push ke registry otomatis
9. **Send Notification** - Kirim build result ke ntfy.sh

### Build Result (JSON)

Contoh JSON output dengan `--json`:

```json
{
  "status": "success",
  "repository": "saas-be-core",
  "branch": "develop",
  "image": "loyaltolpi/saas-be-core:develop-abc123",
  "rebuild": false,
  "build_time": {
    "start_unix": 1704067200,
    "end_unix": 1704067800,
    "start_iso": "2024-01-01T00:00:00Z",
    "end_iso": "2024-01-01T00:10:00Z",
    "duration": {
      "seconds": 600,
      "formatted": "10m 0s"
    }
  },
  "config": {
    "memory": "2g",
    "cpus": "1",
    "cpu_period": "100000",
    "cpu_quota": "100000",
    "builder": "container-builder"
  },
  "metadata": {
    "ready": false,
    "custom_image": "",
    "api_url": "http://193.1.1.3:5000"
  },
  "error": "",
  "timestamp": "2024-01-01T00:10:00Z"
}
```

### Troubleshooting

#### Permission Issues
Script otomatis fix permission issues di `~/.docker/buildx`:
- Activity directory permissions
- Refs directory permissions  
- Root-owned files dari previous builds

#### Git Submodule Errors
Build menggunakan pre-clone approach dengan `--no-recurse-submodules` untuk menghindari error:
```
fatal: No url found for submodule path '...' in .gitmodules
```

#### Builder Not Found
Script otomatis create builder `container-builder` jika belum ada dengan konfigurasi:
- Driver: docker-container
- Metrics: enabled (port 9333)
- Resource limits: 4 CPUs, 4GB RAM

### Help

Untuk detail lengkap tentang DevOps CI:

```bash
doq devops-ci --help
```

Show versi:

```bash
doq devops-ci --version
```

## Helper Mode - No API Dependency

DevOps CI mendukung **dual mode**: API mode (default) dan Helper mode (no API dependency).

### Kenapa Helper Mode?

Helper mode berguna ketika:
- Tidak ada akses ke API eksternal
- Development/testing di local environment
- Custom workflow tanpa dependency pada API metadata
- Portability - bisa jalan dimana saja

### Mode Configuration

#### Via Environment Variable:
```bash
export DEVOPS_CI_MODE=helper  # atau "api" untuk default
doq devops-ci saas-be-core develop
```

#### Via Config File `~/.doq/.env`:
```bash
# DevOps CI Mode
DEVOPS_CI_MODE=helper

# Helper Mode Settings
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{timestamp}
HELPER_REGISTRY01=registry.example.com
HELPER_DEFAULT_PORT=3000
HELPER_DEFAULT_PORT2=
```

#### Via Config File `~/.doq/helper-config.json`:
```json
{
  "mode": "helper",
  "image_template": "loyaltolpi/{repo}:{refs}-{timestamp}",
  "registry01": "registry.example.com",
  "default_port": "3000",
  "default_port2": ""
}
```

### Usage Examples

#### API Mode (Default):
```bash
# Default: fetch metadata dari API
doq devops-ci saas-be-core develop

# Output:
# 🌐 Running in API MODE
# 📦 Fetching build metadata...
```

#### Helper Mode via CLI Flag:
```bash
# Force helper mode dengan --helper flag
doq devops-ci saas-be-core develop --helper

# Output:
# 🔧 Running in HELPER MODE (no API dependency)
# 🔧 Helper mode: Generating metadata locally...
```

#### Helper Mode dengan Custom Settings:
```bash
# Helper mode dengan custom image name
doq devops-ci saas-be-core develop --helper \
  --image-name loyaltolpi/saas-be-core:test-20240101

# Helper mode dengan registry dan port
doq devops-ci saas-be-core develop --helper \
  --registry registry.example.com \
  --port 8080
```

#### Helper Mode via Config:
```bash
# Set DEVOPS_CI_MODE=helper di ~/.doq/.env
# Kemudian jalankan tanpa flag --helper
doq devops-ci saas-be-core develop

# Output:
# 🔧 Running in HELPER MODE (no API dependency)
```

### Image Name Template

Template variables yang didukung:
- `{repo}` - Repository name
- `{refs}` - Branch/tag name
- `{timestamp}` - Current timestamp (YYYYMMDDHHmmss)
- `{short_hash}` - Git short hash (jika tersedia)

Contoh template:
```bash
HELPER_IMAGE_TEMPLATE=loyaltolpi/{repo}:{refs}-{timestamp}
# Hasil: loyaltolpi/saas-be-core:develop-20240615143022

HELPER_IMAGE_TEMPLATE=registry.io/{repo}:latest
# Hasil: registry.io/saas-be-core:latest
```

### Configuration Priority

Settings di-load dengan priority (tertinggi ke terendah):
1. **CLI arguments** (`--image-name`, `--registry`, `--port`)
2. **Environment variables** (`HELPER_IMAGE_TEMPLATE`, `HELPER_REGISTRY01`, etc.)
3. **~/.doq/.env** file
4. **~/.doq/helper-config.json** file
5. **Default values**

### Comparison: API Mode vs Helper Mode

| Feature | API Mode | Helper Mode |
|---------|----------|-------------|
| **API Dependency** | ✅ Required | ❌ Not required |
| **Auto Skip if Ready** | ✅ Yes | ❌ No (always build) |
| **Config Source** | API endpoint | Local config files |
| **Image Name** | From API metadata | From template/custom |
| **Use Case** | Production CI/CD | Development/Testing |

### Best Practices

1. **Production**: Use API mode untuk consistency dan auto-skip capability
2. **Development**: Use helper mode untuk flexibility dan no external dependency
3. **Config Files**: Gunakan `~/.doq/.env` untuk consistency dengan `auth.json`
4. **CLI Override**: Gunakan CLI args untuk quick testing atau one-time builds

## Struktur File

### Core Modules
- `doq.py` - Main CLI entry point
- `rancher_api.py` - Rancher API client
- `config.py` - Configuration management
- `version.py` - Version tracking dan update management

### Plugin System
- `plugin_manager.py` - Plugin management and loading system
- `config_utils.py` - Configuration utilities for plugins
- `devops_ci.py` - DevOps CI/CD Docker image builder (plugin)

### Configuration
- `pyproject.toml` - Project configuration untuk uv package manager
- `install.sh` - Installer script menggunakan uv

### Documentation
- `README.md` - Main documentation
- `DEVOPS-CI.md` - Comprehensive DevOps CI documentation
- `UPDATE_GUIDE.md` - Update management guide

### Configuration Directory (`~/.doq/`)
```
~/.doq/
├── plugins.json           # Plugin registry
├── plugins/               # Plugin configurations
│   └── devops-ci.json    # DevOps CI plugin config
├── auth.json             # Shared authentication
├── .env                  # Core CLI config
└── version.json          # Version tracking
```

## Package Manager

DevOps Q menggunakan `uv` sebagai package manager. Keuntungan menggunakan `uv`:

- **Lebih Cepat**: Instalasi dependencies 10-100x lebih cepat dibanding pip
- **Reliable**: Dependency resolution yang lebih baik
- **Isolated**: Environment management yang lebih baik
- **Auto-install**: Installer script akan otomatis menginstall uv jika belum tersedia

## Plugin System

DevOps Q menggunakan sistem plugin yang modular dan scalable untuk manajemen fitur.

### Architecture

Plugin system menggunakan:
- **Plugin Registry** (`~/.doq/plugins.json`) - Daftar semua plugin yang terinstall
- **Plugin Configs** (`~/.doq/plugins/*.json`) - Konfigurasi per-plugin
- **Plugin Manager** - Core system untuk load dan manage plugins
- **Config Utilities** - Centralized config loading dengan priority levels

### Configuration Priority

Untuk setiap setting, priority order adalah:
1. **CLI Arguments** (highest priority)
2. **Environment Variables**
3. **Plugin Config File** (`~/.doq/plugins/<plugin>.json`)
4. **Hardcoded Defaults** (lowest priority)

### Plugin Management Commands

#### List Plugins
```bash
# Show all plugins with status
doq plugin list

# Example output:
📦 Installed Plugins:
======================================================================

  devops-ci (v2.0.1) - ✅ enabled
  Description: DevOps CI/CD Docker image builder
  Module: devops_ci
  Config: plugins/devops-ci.json
  Commands: devops-ci
```

#### View Plugin Configuration
```bash
# Show plugin config
doq plugin config devops-ci

# Edit plugin config in $EDITOR
doq plugin config devops-ci --edit
```

#### Enable/Disable Plugins
```bash
# Disable a plugin
doq plugin disable devops-ci

# Enable a plugin
doq plugin enable devops-ci
```

### DevOps-CI Plugin Configuration

Location: `~/.doq/plugins/devops-ci.json`

```json
{
  "mode": "api",
  "api": {
    "url": "http://193.1.1.3:5000",
    "timeout": 30
  },
  "builder": {
    "name": "container-builder",
    "memory": "2g",
    "cpus": "1",
    "cpu_period": "100000",
    "cpu_quota": "100000"
  },
  "registry": {
    "url": "",
    "namespace": "loyaltolpi"
  },
  "notification": {
    "ntfy_url": "https://ntfy.sh/doi-notif",
    "enabled": true
  },
  "helper_mode": {
    "image_template": "loyaltolpi/{repo}:{refs}-{short_hash}",
    "default_port": "3000",
    "default_port2": ""
  },
  "build_args": {
    "registry01_url": "",
    "gitusertoken": "",
    "bitbucket_user": "",
    "github_user": "",
    "bitbucket_token": "",
    "github_token": ""
  }
}
```

**Configuration Options:**

- `mode`: Operating mode (`"api"` or `"helper"`)
- `api.url`: API endpoint URL
- `api.timeout`: API request timeout in seconds
- `builder.name`: Docker buildx builder name
- `builder.memory`: Memory limit for builds
- `builder.cpus`: CPU count for builds
- `registry.namespace`: Docker registry namespace
- `notification.ntfy_url`: Notification endpoint
- `notification.enabled`: Enable/disable notifications
- `helper_mode.image_template`: Image name template for helper mode
- `build_args.*`: Build arguments untuk Docker build

### Environment Variable Overrides

You can override any plugin config with environment variables:

```bash
# Override API URL
export DEFAULT_URL_API="http://custom-api:5000"

# Override builder resources
export DEFAULT_MEMORY="4g"
export DEFAULT_CPUS="2"

# Override notification
export NTFY_URL="https://ntfy.sh/my-custom-topic"

# Then run commands normally
doq devops-ci saas-be-core develop
```

### Adding New Plugins

To add a new plugin to DevOps Q:

1. **Create plugin module** (e.g., `my_plugin.py`)
2. **Add to plugins.json**:
```json
{
  "name": "my-plugin",
  "enabled": true,
  "version": "1.0.0",
  "module": "my_plugin",
  "config_file": "plugins/my-plugin.json",
  "commands": ["my-command"],
  "description": "My awesome plugin"
}
```
3. **Create plugin config** (`~/.doq/plugins/my-plugin.json`)
4. **Reload**: `doq plugin list` to verify

### Benefits

✅ **Scalable**: Easy to add new plugins without modifying core CLI  
✅ **Configurable**: Per-plugin configuration with multiple priority levels  
✅ **Isolated**: Plugin configs don't interfere with each other  
✅ **Flexible**: Enable/disable plugins as needed  
✅ **Maintainable**: Clear separation between core CLI and plugin functionality

Installer script (`install.sh`) akan otomatis menginstall `uv` jika belum tersedia di sistem Anda.

## DevOps Utilities

### Check Docker Image Status

> 📖 **Detailed Documentation**: See [DOQ-IMAGE.md](docs/DOQ-IMAGE.md) for comprehensive guide with flow diagrams and examples.

Command `doq image` memungkinkan Anda untuk mengecek apakah Docker image sudah tersedia di Docker Hub:

```bash
# Check image status
doq image saas-apigateway develop

# Output dengan JSON format
doq image saas-apigateway develop --json
```

**Output Example:**
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:a1b2c3d",
  "ready": true,
  "status": "ready"
}
```

**With `--json` flag (compact format):**
```json
{
  "ready": true,
  "image": "loyaltolpi/saas-apigateway:a1b2c3d",
  "build-image": null
}
```

### Get cicd.json Configuration

Command `doq get-cicd` memungkinkan Anda untuk fetch file `cicd/cicd.json` langsung dari Bitbucket repository:

```bash
# Fetch cicd.json
doq get-cicd saas-apigateway develop

# Output compact JSON
doq get-cicd saas-apigateway develop --json
```

**Output Example:**
```
📦 cicd.json for saas-apigateway/develop:

{
  "IMAGE": "saas-apigateway",
  "BUILD": "docker",
  "PORT": "3000"
}
```

**Features:**
- ✅ No API dependency (direct Bitbucket access)
- ✅ Supports all branches and tags
- ✅ Automatic authentication via `~/.doq/auth.json`
- ✅ JSON output untuk scripting
- ✅ Auto-build with `--force-build` flag

### Get Any File from Repository

Command `doq get-file` memungkinkan Anda untuk fetch file apa saja dari Bitbucket repository:

```bash
# Fetch Dockerfile
doq get-file saas-apigateway develop Dockerfile

# Fetch any file
doq get-file saas-apigateway develop package.json
doq get-file saas-apigateway develop src/config.yaml
```

### Deploy Web Application

Command `doq deploy-web` untuk automated deployment menggunakan Docker Compose over SSH:

```bash
# Auto mode - uses commit hash
doq deploy-web saas-fe-webadmin development

# Custom image mode
doq deploy-web saas-fe-webadmin development --image loyaltolpi/saas-fe-webadmin:v1.0.0

# Deploy to staging
doq deploy-web saas-fe-webadmin staging

# Deploy to production
doq deploy-web saas-fe-webadmin production

# Deploy tagged release
doq deploy-web saas-fe-webadmin v1.0.0

# Rollback to previous version
doq deploy-web saas-fe-webadmin production --image loyaltolpi/saas-fe-webadmin:v1.0.0

# JSON output for automation
doq deploy-web saas-fe-webadmin development --json
```

**Features:**
- ✅ Auto-selects host based on branch/tag
- ✅ Smart deployment (skips if same image)
- ✅ Creates Docker Compose files automatically
- ✅ SSH automation for remote execution
- ✅ Image validation (auto mode)
- ✅ Custom image support for rollback/testing
- ✅ Environment detection (dev/staging/prod)

**Requirements:**
- SSH access to target servers (user: `devops`)
- SSH key configured (`~/.ssh/id_rsa`)
- GIT_USER and GIT_PASSWORD in `~/.doq/auth.json`
- `cicd/cicd.json` in repository with HOST and PORT config

> 📖 **Detailed Documentation**: See [DEPLOY-WEB.md](docs/DEPLOY-WEB.md) for comprehensive guide with flow diagrams and examples.

### Deploy to Kubernetes

Command `doq deploy-k8s` untuk automated deployment ke Kubernetes cluster:

> 📖 **Detailed Documentation**: Lihat [DEPLOY-K8S.md](docs/DEPLOY-K8S.md) untuk comprehensive guide dengan flow diagrams, setup, dan contoh lengkap

```bash
# Auto mode - uses commit hash
doq deploy-k8s saas-apigateway develop

# Deploy to staging
doq deploy-k8s saas-apigateway staging

# Deploy to production
doq deploy-k8s saas-apigateway production

# Custom image mode
doq deploy-k8s saas-apigateway develop --image loyaltolpi/saas-apigateway:v1.0.0

# JSON output for automation
doq deploy-k8s saas-apigateway develop --json
```

**Deployment Flow:**
1. **Check Image Status** - Validates image exists in Docker Hub using `doq image`
2. **Fetch Configuration** - Gets `cicd.json` from Bitbucket for PROJECT and DEPLOYMENT fields
3. **Determine Namespace** - Constructs namespace as `{refs}-{PROJECT}` (e.g., `develop-saas`)
4. **Get Current Image** - Checks existing deployment using `doq get-image`
5. **Compare Images** - Skips deployment if image is the same
6. **Switch Context** - Uses `doq ns` to switch kubectl context
7. **Deploy Image** - Updates deployment using `doq set-image`

**Example Output:**
```
🔍 Checking image status...
✅ Image ready: loyaltolpi/saas-apigateway:660cbcf
🎯 Target: develop-saas / saas-apigateway
🔍 Checking current deployment...
🔄 Different image detected
   Current: loyaltolpi/saas-apigateway:abc1234
   New: loyaltolpi/saas-apigateway:660cbcf
🔄 Switching context to develop-saas...
✅ Context switched
🚀 Updating deployment...
✅ Deployment successful!
```

**Features:**
- ✅ Image readiness validation before deployment
- ✅ Smart deployment (skips if same image)
- ✅ Automatic kubectl context switching
- ✅ Namespace auto-detection from cicd.json
- ✅ Custom image support for rollback/testing
- ✅ Integration with existing doq commands

**Requirements:**
- `kubectl` installed and configured
- GIT_USER and GIT_PASSWORD in `~/.doq/auth.json`
- `cicd/cicd.json` in repository with PROJECT and DEPLOYMENT fields

**cicd.json Example:**
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

**Auto-Build Feature:**
```bash
# Check and automatically build if not ready
doq image saas-apigateway develop --force-build

# If image not ready:
# 1. Shows current status
# 2. Automatically runs: doq devops-ci saas-apigateway develop
# 3. Returns build result
```

This is useful for CI/CD pipelines where you want to ensure image is always available.

## Quick Reference

### Rancher Management
- `doq login` - Login ke Rancher API
- `doq token-check` - Cek validitas token
- `doq project` - List projects
- `doq kube-config <project-id>` - Get kubeconfig dari project

### Kubernetes Resource Management
- `doq ns <namespace>` - Switch kubectl context berdasarkan namespace
- `doq set-image <ns> <deploy> <image>` - Set image untuk deployment
- `doq get-image <ns> <deploy>` - Get image info dari deployment
- `doq get-deploy <ns> <deploy>` - Get deployment resource (JSON)
- `doq get-svc <ns> <svc>` - Get service resource (JSON)
- `doq get-cm <ns> <cm>` - Get configmap resource (JSON)
- `doq get-secret <ns> <secret>` - Get secret resource dengan base64 decoded (JSON)

### DevOps CI/CD - Docker Image Builder
- `doq devops-ci <repo> <refs>` - Build Docker image dari repository (API mode)
- `doq devops-ci <repo> <refs> --helper` - Build dengan helper mode (no API dependency)
- `doq devops-ci <repo> <refs> --rebuild` - Force rebuild image
- `doq devops-ci <repo> <refs> --json` - Build dengan JSON output
- `doq devops-ci <repo> <refs> --short` - Build silent mode (output image name only)
- `doq devops-ci <repo> <refs> --helper --image-name <name>` - Helper mode dengan custom image
- `doq devops-ci <repo> <refs> <custom-image>` - Build dengan custom image name

### DevOps Utilities
- `doq image <repo> <refs>` - Check Docker image status in Docker Hub
- `doq image <repo> <refs> --json` - Check image status (JSON output)
- `doq image <repo> <refs> --force-build` - Check and auto-build if not ready
- `doq get-cicd <repo> <refs>` - Fetch cicd.json from Bitbucket repository
- `doq get-cicd <repo> <refs> --json` - Fetch cicd.json (compact JSON)
- `doq get-file <repo> <refs> <file_path>` - Fetch any file from Bitbucket repository

### Web Deployment
- `doq deploy-web <repo> <refs>` - Deploy web app (auto mode with commit hash)
- `doq deploy-web <repo> <refs> --image <image>` - Deploy with custom image
- `doq deploy-web <repo> <refs> --json` - Deploy with JSON output

### Kubernetes Deployment
- `doq deploy-k8s <repo> <refs>` - Deploy to Kubernetes (auto mode with commit hash)
- `doq deploy-k8s <repo> <refs> --image <image>` - Deploy with custom image
- `doq deploy-k8s <repo> <refs> --json` - Deploy with JSON output

### Plugin Management
- `doq plugin list` - List all installed plugins
- `doq plugin list --json` - List plugins (JSON output)
- `doq plugin enable <name>` - Enable a plugin
- `doq plugin disable <name>` - Disable a plugin
- `doq plugin config <name>` - Show plugin configuration
- `doq plugin config <name> --edit` - Edit plugin configuration in $EDITOR

### Update Management
- `doq check-update` - Cek update tersedia
- `doq update` - Update ke versi terbaru (dari branch di version.json)
- `doq update --branch <branch>` - Update ke versi terbaru dari branch tertentu
- `doq update <commit>` - Update ke commit tertentu
- `doq update <commit> --branch <branch>` - Update ke commit dari branch tertentu
- `doq version` - Tampilkan versi terinstall

### Configuration
- `doq config` - Lihat/mengatur konfigurasi
- `doq config --url <url> --token <token>` - Set konfigurasi manual

