# DevOps Q

Simple CLI tool untuk mengelola Rancher resources menggunakan Python.

## Instalasi

### Quick Install (Cara Tercepat - Recommended)

Instalasi langsung dalam satu command tanpa perlu clone repository manual:

```bash
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes
```

**Apa yang terjadi:**
1. ✅ Script otomatis clone repository ke `/opt/devops-q`
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
- `--prefix DIR`: Direktori untuk clone repository (default: /opt/devops-q)
- `--skip-clone`: Skip auto-clone jika sudah di dalam project directory

**Menggunakan Environment Variables:**

```bash
REPO_URL=https://github.com/mamatnurahmat/devops-tools \
REPO_REF=main \
PREFIX=/opt/devops-q \
curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/main/install.sh | bash -s -- --yes
```

#### 2. Manual Clone (Jika Lebih Suka Clone Manual)

Jika ingin clone repository secara manual terlebih dahulu:

```bash
# Clone repository
git clone https://github.com/mamatnurahmat/devops-tools.git /opt/devops-q
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

### List Clusters

```bash
doq cluster
```

Output JSON:

```bash
doq cluster --json
```

### List Projects

```bash
doq project
```

Filter by cluster:

```bash
doq project --cluster <cluster-id>
```

### List Namespaces

```bash
doq namespace
```

Filter by project:

```bash
doq namespace --project <project-id>
```

Filter by cluster:

```bash
doq namespace --cluster <cluster-id>
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

## Struktur File

- `doq.py` - Main CLI entry point
- `rancher_api.py` - Rancher API client
- `config.py` - Configuration management
- `version.py` - Version tracking dan update management
- `pyproject.toml` - Project configuration untuk uv package manager
- `install.sh` - Installer script menggunakan uv

## Package Manager

DevOps Q menggunakan `uv` sebagai package manager. Keuntungan menggunakan `uv`:

- **Lebih Cepat**: Instalasi dependencies 10-100x lebih cepat dibanding pip
- **Reliable**: Dependency resolution yang lebih baik
- **Isolated**: Environment management yang lebih baik
- **Auto-install**: Installer script akan otomatis menginstall uv jika belum tersedia

Installer script (`install.sh`) akan otomatis menginstall `uv` jika belum tersedia di sistem Anda.

## Quick Reference

### Rancher Management
- `doq login` - Login ke Rancher API
- `doq token-check` - Cek validitas token
- `doq cluster` - List clusters
- `doq project` - List projects
- `doq namespace` - List namespaces
- `doq kube-config <project-id>` - Get kubeconfig dari project

### Kubernetes Resource Management
- `doq ns <namespace>` - Switch kubectl context berdasarkan namespace
- `doq set-image <ns> <deploy> <image>` - Set image untuk deployment
- `doq get-image <ns> <deploy>` - Get image info dari deployment
- `doq get-deploy <ns> <deploy>` - Get deployment resource (JSON)
- `doq get-svc <ns> <svc>` - Get service resource (JSON)
- `doq get-cm <ns> <cm>` - Get configmap resource (JSON)
- `doq get-secret <ns> <secret>` - Get secret resource dengan base64 decoded (JSON)

### Update Management
- `doq check-update` - Cek update tersedia
- `doq update` - Update ke versi terbaru
- `doq update <commit>` - Update ke commit tertentu
- `doq version` - Tampilkan versi terinstall

### Configuration
- `doq config` - Lihat/mengatur konfigurasi
- `doq config --url <url> --token <token>` - Set konfigurasi manual

