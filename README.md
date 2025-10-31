# DevOps Tools

Simple CLI tool untuk mengelola Rancher resources menggunakan Python.

## Instalasi

### Metode 1: Installer Script (Recommended)

```bash
./install.sh
```

Script ini akan:
- Menginstall dependencies
- Membuat executable `devops` di `~/.local/bin`
- Menambahkan ke PATH (jika belum ada)

Setelah instalasi, jalankan:
```bash
devops --help
```

Jika `~/.local/bin` belum ada di PATH, tambahkan ke `~/.bashrc` atau `~/.zshrc`:
```bash
export PATH="${HOME}/.local/bin:${PATH}"
```

### Metode 2: Setup.py (Alternative)

```bash
pip3 install -e .
```

Atau:

```bash
pip3 install -r requirements.txt
python3 devops.py --help
```

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

## Struktur File

- `devops.py` - Main CLI entry point
- `rancher_api.py` - Rancher API client
- `config.py` - Configuration management
- `requirements.txt` - Python dependencies
- `install.sh` - Installer script
- `setup.py` - Setup script untuk pip install

