# DevOps Tools

Simple CLI tool untuk mengelola Rancher resources menggunakan Python.

## Instalasi

### Metode Instalasi (Menggunakan uv)

#### Installer Script (Recommended)

```bash
./install.sh
```

Script ini akan:
- Menginstall `uv` package manager jika belum tersedia (otomatis)
- Menginstall dependencies menggunakan `uv` (lebih cepat dan reliable dibanding pip)
- Membuat executable `devops` di `~/.local/bin`
- Menambahkan ke PATH (jika belum ada)
- Menyimpan commit hash ke file version tracking

Setelah instalasi, jalankan:
```bash
devops --help
```

Jika `~/.local/bin` belum ada di PATH, tambahkan ke `~/.bashrc` atau `~/.zshrc`:
```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

#### Alternatif: Menggunakan uv secara langsung

Jika Anda sudah memiliki `uv` terinstall, Anda bisa menginstall dependencies secara langsung:

```bash
# Install uv jika belum ada
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv pip install -e .
```

**Catatan:** Proyek ini menggunakan `uv` sebagai package manager default untuk instalasi yang lebih cepat dan reliable.

## Konfigurasi

### Login (Recommended)

Jika file `.env` belum ada, gunakan command `login` untuk melakukan autentikasi:

```bash
devops login
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
- Menyimpan config ke `$HOME/.devops/.env` (folder/file akan dibuat otomatis jika belum ada)

Contoh dengan parameter:

```bash
devops login --url https://193.1.1.4 --username admin --password secret
```

Atau dengan prompt interaktif:

```bash
devops login --url https://193.1.1.4
# Username: admin
# Password: (hidden)
```

Force re-login:

```bash
devops login --force
```

### Manual Config

Set konfigurasi Rancher API secara manual (disimpan di `$HOME/.devops/.env`):

```bash
devops config --url https://rancher.example.com --token <your-token>
```

Secara default, mode insecure (skip SSL verification) diaktifkan. Untuk menggunakan SSL verification:

```bash
devops config --url https://rancher.example.com --token <your-token> --secure
```

Lihat konfigurasi saat ini:

```bash
devops config
```

### Check Token

Cek validitas dan status expired token:

```bash
devops token-check
```

Command ini akan:
- Menggunakan token dari config file
- Mengecek apakah token valid
- Mengecek apakah token sudah expired
- Menampilkan waktu expired jika tersedia

Output JSON:

```bash
devops token-check --json
```

Check token dengan URL/token custom:

```bash
devops token-check --url https://rancher.example.com --token <token>
```

## Penggunaan

### List Clusters

```bash
devops cluster
```

Output JSON:

```bash
devops cluster --json
```

### List Projects

```bash
devops project
```

Filter by cluster:

```bash
devops project --cluster <cluster-id>
```

### List Namespaces

```bash
devops namespace
```

Filter by project:

```bash
devops namespace --project <project-id>
```

Filter by cluster:

```bash
devops namespace --cluster <cluster-id>
```

### Get Kubeconfig

Get kubeconfig dari project dan simpan ke `~/.kube/config`:

```bash
devops kube-config <project-id>
```

Dengan default, kubeconfig akan di-flatten. Opsi tambahan:

```bash
# Tanpa flatten
devops kube-config <project-id> --no-flatten

# Replace existing config (default: merge)
devops kube-config <project-id> --replace

# Set sebagai current context
devops kube-config <project-id> --set-context
```

## Update Management

DevOps Tools menggunakan sistem version tracking berbasis commit hash untuk mengelola update. Setiap instalasi akan menyimpan commit hash yang terinstall ke file `~/.devops/version.json`.

### Check Update

Cek apakah ada update tersedia di repository:

```bash
devops check-update
```

Command ini akan:
- Membandingkan commit hash terinstall dengan commit hash terbaru di repository
- Menampilkan informasi versi saat ini dan versi terbaru
- Memberikan instruksi untuk update jika tersedia

Output JSON:

```bash
devops check-update --json
```

### Update ke Versi Terbaru

Ada beberapa cara untuk melakukan update:

#### 1. Update Otomatis ke Latest (Recommended)

```bash
devops update
```

Command ini akan:
- Otomatis mengecek apakah ada update tersedia
- Jika sudah latest, menampilkan pesan bahwa sudah up-to-date
- Jika ada update, akan otomatis update ke commit terbaru

#### 2. Update ke Latest Commit Secara Eksplisit

```bash
devops update --latest
```

Command ini akan:
- Langsung mengambil latest commit hash dari repository
- Update ke commit terbaru tanpa mengecek versi saat ini

#### 3. Update ke Commit Tertentu

```bash
devops update <commit_hash>
```

Command ini akan:
- Clone repository dari `https://github.com/mamatnurahmat/devops-tools`
- Checkout ke commit hash yang ditentukan
- Menjalankan installer script (`install.sh`) menggunakan `uv`
- Update installation ke versi commit tersebut
- Menyimpan commit hash baru ke file version tracking

Contoh:

```bash
# Update ke commit tertentu
devops update abc123def4567890123456789012345678901234

# Update otomatis ke latest
devops update

# Update ke latest commit secara eksplisit
devops update --latest
```

### Version Information

Lihat informasi versi yang terinstall:

```bash
devops version
```

Output JSON:

```bash
devops version --json
```

Informasi yang ditampilkan:
- Commit Hash: Hash commit yang terinstall
- Installed At: Waktu instalasi terakhir
- Repository: URL repository
- Branch: Branch yang digunakan (default: main)

### Cara Kerja Update Management

1. **Version Tracking**: Setiap instalasi menyimpan commit hash ke `~/.devops/version.json`
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

- `devops.py` - Main CLI entry point
- `rancher_api.py` - Rancher API client
- `config.py` - Configuration management
- `version.py` - Version tracking dan update management
- `pyproject.toml` - Project configuration untuk uv package manager
- `install.sh` - Installer script menggunakan uv

## Package Manager

DevOps Tools menggunakan `uv` sebagai package manager. Keuntungan menggunakan `uv`:

- **Lebih Cepat**: Instalasi dependencies 10-100x lebih cepat dibanding pip
- **Reliable**: Dependency resolution yang lebih baik
- **Isolated**: Environment management yang lebih baik
- **Auto-install**: Installer script akan otomatis menginstall uv jika belum tersedia

Installer script (`install.sh`) akan otomatis menginstall `uv` jika belum tersedia di sistem Anda.

