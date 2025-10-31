# Rancher CLI

Simple CLI tool untuk mengelola Rancher resources menggunakan Python.

## Instalasi

```bash
pip install -r requirements.txt
```

## Konfigurasi

### Login (Recommended)

Jika file `.env` belum ada, gunakan command `login` untuk melakukan autentikasi:

```bash
python rancher_cli.py login
```

Command ini akan:
- Default URL: `https://193.1.1.4`
- Default insecure mode: `true` (skip SSL verification)
- Meminta username dan password
- Mengambil token dari Rancher API
- Menyimpan config ke `$HOME/.devops/.env` (folder/file akan dibuat otomatis jika belum ada)

Contoh dengan parameter:

```bash
python rancher_cli.py login --url https://193.1.1.4 --username admin --password secret
```

Atau dengan prompt interaktif:

```bash
python rancher_cli.py login --url https://193.1.1.4
# Username: admin
# Password: (hidden)
```

### Manual Config

Set konfigurasi Rancher API secara manual (disimpan di `$HOME/.devops/.env`):

```bash
python rancher_cli.py config --url https://rancher.example.com --token <your-token>
```

Secara default, mode insecure (skip SSL verification) diaktifkan. Untuk menggunakan SSL verification:

```bash
python rancher_cli.py config --url https://rancher.example.com --token <your-token> --secure
```

Lihat konfigurasi saat ini:

```bash
python rancher_cli.py config
```

### Check Token

Cek validitas dan status expired token:

```bash
python rancher_cli.py token-check
```

Command ini akan:
- Menggunakan token dari config file
- Mengecek apakah token valid
- Mengecek apakah token sudah expired
- Menampilkan waktu expired jika tersedia

Output JSON:

```bash
python rancher_cli.py token-check --json
```

Check token dengan URL/token custom:

```bash
python rancher_cli.py token-check --url https://rancher.example.com --token <token>
```

## Penggunaan

### List Clusters

```bash
python rancher_cli.py cluster
```

Output JSON:

```bash
python rancher_cli.py cluster --json
```

### List Projects

```bash
python rancher_cli.py project
```

Filter by cluster:

```bash
python rancher_cli.py project --cluster <cluster-id>
```

### List Namespaces

```bash
python rancher_cli.py namespace
```

Filter by project:

```bash
python rancher_cli.py namespace --project <project-id>
```

Filter by cluster:

```bash
python rancher_cli.py namespace --cluster <cluster-id>
```

## Struktur File

- `rancher_cli.py` - Main CLI entry point
- `rancher_api.py` - Rancher API client
- `config.py` - Configuration management
- `requirements.txt` - Python dependencies
