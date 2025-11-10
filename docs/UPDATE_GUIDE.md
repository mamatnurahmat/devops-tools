# Panduan Update Management - DevOps Q CLI

Panduan lengkap untuk mengelola update CLI DevOps Q menggunakan sistem version tracking berbasis commit hash.

## Daftar Isi

1. [Konsep Version Tracking](#konsep-version-tracking)
2. [Check Update](#check-update)
3. [Update CLI](#update-cli)
4. [Version Information](#version-information)
5. [Troubleshooting](#troubleshooting)

## Konsep Version Tracking

DevOps Q CLI menggunakan sistem version tracking berbasis **commit hash** untuk mengelola update. Setiap instalasi akan menyimpan informasi berikut ke file `~/.doq/version.json`:

- **commit_hash**: Hash commit yang terinstall
- **installed_at**: Waktu instalasi (ISO format)
- **repo_url**: URL repository GitHub
- **branch**: Branch yang digunakan (default: main)

### Keuntungan Menggunakan Commit Hash

1. **Precise Versioning**: Setiap commit hash unik dan dapat diidentifikasi dengan tepat
2. **Reproducible**: Dapat menginstall versi spesifik yang sama di berbagai environment
3. **No Version Conflicts**: Tidak perlu manage semantic versioning secara manual
4. **Git Integration**: Terintegrasi langsung dengan Git workflow

## Check Update

### Command: `doq check-update`

Command ini digunakan untuk mengecek apakah ada update tersedia di repository remote.

#### Cara Kerja

1. Membaca commit hash terinstall dari `~/.doq/version.json`
2. Menggunakan `git ls-remote` untuk mendapatkan commit hash terbaru dari repository
3. Membandingkan kedua commit hash
4. Menampilkan hasil perbandingan

#### Penggunaan

```bash
# Check update (human-readable output)
doq check-update

# Check update (JSON output)
doq check-update --json
```

#### Output Format

**Human-readable:**
```
🔍 Checking for updates...
==================================================
Current version: abc123def4567890123456789012345678901234
Installed at: 2024-01-15T10:30:00.123456

Latest version: def456abc1237890123456789012345678901234

✅ Update tersedia!
   Current: abc123de...
   Latest:  def456ab...

Gunakan command berikut untuk update:
   doq update def456abc1237890123456789012345678901234

Atau update otomatis ke latest:
   doq update --latest
```

**JSON:**
```json
{
  "has_update": true,
  "current_hash": "abc123def4567890123456789012345678901234",
  "latest_hash": "def456abc1237890123456789012345678901234",
  "installed_at": "2024-01-15T10:30:00.123456",
  "error": null
}
```

#### Skenario

1. **Ada Update Tersedia**
   - `has_update: true`
   - Menampilkan commit hash saat ini dan terbaru
   - Memberikan instruksi untuk update

2. **Sudah Latest**
   - `has_update: false`
   - Menampilkan pesan bahwa sudah menggunakan versi terbaru

3. **Error**
   - Tidak dapat membaca version file
   - Tidak dapat connect ke repository
   - Git tidak terinstall

## Update CLI

### Command: `doq update`

Command ini digunakan untuk melakukan update CLI ke versi tertentu atau ke versi terbaru.

### Opsi Update

#### 1. Update Otomatis (Recommended)

```bash
doq update
```

**Cara Kerja:**
- Otomatis mengecek apakah ada update tersedia
- Jika sudah latest, menampilkan pesan bahwa sudah up-to-date
- Jika ada update, otomatis update ke commit terbaru

**Kapan Menggunakan:**
- Update rutin ke versi terbaru
- Tidak perlu spesifikasi commit hash tertentu

#### 2. Update ke Latest Commit

```bash
doq update --latest
```

**Cara Kerja:**
- Langsung mengambil latest commit hash dari repository
- Update ke commit terbaru tanpa mengecek versi saat ini terlebih dahulu

**Kapan Menggunakan:**
- Yakin ingin update ke latest
- Tidak perlu check version terlebih dahulu

#### 3. Update ke Commit Tertentu

```bash
doq update <commit_hash>
```

**Cara Kerja:**
- Clone repository ke temporary directory
- Checkout ke commit hash yang ditentukan
- Jalankan installer script menggunakan `uv`
- Update version tracking setelah instalasi berhasil
- Cleanup temporary files

**Kapan Menggunakan:**
- Update ke versi spesifik (bukan latest)
- Rollback ke versi sebelumnya
- Testing versi tertentu

### Proses Update

1. **Pre-flight Checks**
   - Mengecek apakah git terinstall
   - Validasi commit hash (jika diberikan)

2. **Clone Repository**
   - Clone repository ke temporary directory
   - Checkout ke commit yang ditentukan

3. **Run Installer**
   - Jalankan `install.sh` dari repository yang di-clone
   - Installer akan menggunakan `uv` untuk install dependencies
   - Membuat wrapper script baru di `~/.local/bin/doq`

4. **Update Version Tracking**
   - Menyimpan commit hash baru ke `~/.doq/version.json`
   - Menyimpan waktu instalasi

5. **Cleanup**
   - Menghapus temporary directory

### Contoh Penggunaan

```bash
# Update otomatis ke latest (jika ada update)
doq update

# Update ke latest commit secara eksplisit
doq update --latest

# Update ke commit tertentu
doq update abc123def4567890123456789012345678901234

# Update ke commit sebelumnya (rollback)
doq update def456abc1237890123456789012345678901234
```

### Output Update

```
🔍 Cloning repository from https://github.com/mamatnurahmat/doq-tools...
   Branch: main
   Commit: def456abc1237890123456789012345678901234
✅ Repository cloned successfully
🔍 Checking out commit def456abc1237890123456789012345678901234...
✅ Commit checked out successfully

🔍 Running installer...
==================================================
✅ DevOps Q Installer
==========================

✅ Python3 ditemukan: 3.10.0
✅ uv ditemukan: 0.1.0

🔍 Menginstall dependencies dengan uv...
✅ Dependencies terinstall
✅ Directory /home/user/.local/bin siap
✅ Wrapper script dibuat: /home/user/.local/bin/doq
✅ Version tracking diupdate: def456abc1237890123456789012345678901234

==================================================
✅ Update completed successfully!
   Updated to commit: def456abc1237890123456789012345678901234

🧹 Cleaned up temporary files
```

## Version Information

### Command: `doq version`

Command ini menampilkan informasi versi yang terinstall.

#### Penggunaan

```bash
# Human-readable output
doq version

# JSON output
doq version --json
```

#### Output Format

**Human-readable:**
```
🔍 DevOps Q Version Information
==================================================
Commit Hash: abc123def4567890123456789012345678901234
Installed At: 2024-01-15T10:30:00.123456
Repository: https://github.com/mamatnurahmat/doq-tools
Branch: main
```

**JSON:**
```json
{
  "commit_hash": "abc123def4567890123456789012345678901234",
  "installed_at": "2024-01-15T10:30:00.123456",
  "repo_url": "https://github.com/mamatnurahmat/doq-tools",
  "branch": "main"
}
```

## Troubleshooting

### Masalah Umum

#### 1. Git Tidak Terinstall

**Error:**
```
Error: git is not installed or not in PATH
Please install git first: https://git-scm.com/downloads
```

**Solusi:**
```bash
# Ubuntu/Debian
sudo apt-get update && sudo apt-get install git

# CentOS/RHEL
sudo yum install git

# macOS
brew install git
```

#### 2. Tidak Dapat Connect ke Repository

**Error:**
```
Error: Cannot fetch latest version from repository
```

**Solusi:**
- Cek koneksi internet
- Cek apakah repository URL benar di `version.py`
- Cek firewall/proxy settings
- Coba `git ls-remote` secara manual

#### 3. Version File Tidak Ditemukan

**Error:**
```
Error: Cannot determine current version
```

**Solusi:**
- Jalankan `doq version` untuk melihat apakah file ada
- Jika tidak ada, reinstall menggunakan `./install.sh`
- File seharusnya ada di `~/.doq/version.json`

#### 4. Commit Hash Tidak Valid

**Error:**
```
Error: Commit abc123... may not exist in branch main
```

**Solusi:**
- Cek commit hash yang digunakan
- Pastikan commit hash ada di branch main
- Gunakan `doq check-update` untuk mendapatkan commit hash terbaru

#### 5. Installer Script Gagal

**Error:**
```
Error running installer (exit code: 1)
```

**Solusi:**
- Cek log installer untuk detail error
- Pastikan `uv` terinstall dengan benar
- Pastikan Python dan dependencies tersedia
- Coba install manual: `uv pip install --system -e .`

### Best Practices

1. **Regular Update Check**
   ```bash
   # Check update secara berkala
   doq check-update
   ```

2. **Backup Sebelum Update**
   ```bash
   # Simpan version saat ini
   doq version > ~/doq-version-backup.txt
   
   # Update
   doq update
   ```

3. **Test Setelah Update**
   ```bash
   # Test basic functionality
   doq --help
   doq version
   ```

4. **Rollback jika Diperlukan**
   ```bash
   # Rollback ke commit sebelumnya
   doq update <previous_commit_hash>
   ```

## Workflow Update Management

### Workflow Harian

```bash
# 1. Check apakah ada update
doq check-update

# 2. Jika ada update, review changes di GitHub
# (buka GitHub repository dan lihat commits)

# 3. Update ke latest
doq update

# 4. Verify instalasi
doq version
doq --help
```

### Workflow Testing

```bash
# 1. Check update tersedia
doq check-update --json

# 2. Update ke latest
doq update --latest

# 3. Test functionality
doq login
doq project

# 4. Jika ada masalah, rollback
doq update <previous_commit_hash>
```

## Integrasi dengan CI/CD

Jika ingin mengintegrasikan update management ke CI/CD pipeline:

```bash
#!/bin/bash
# Script untuk auto-update di CI/CD

# Check update
UPDATE_INFO=$(doq check-update --json)
HAS_UPDATE=$(echo $UPDATE_INFO | jq -r '.has_update')

if [ "$HAS_UPDATE" = "true" ]; then
    echo "Update tersedia, melakukan update..."
    doq update --latest
    
    # Verify update
    NEW_VERSION=$(doq version --json)
    echo "Updated to: $(echo $NEW_VERSION | jq -r '.commit_hash')"
else
    echo "Sudah menggunakan versi terbaru"
fi
```

## Kesimpulan

Sistem update management berbasis commit hash memberikan kontrol yang lebih baik terhadap versi CLI yang terinstall. Dengan menggunakan `uv` sebagai package manager, proses update menjadi lebih cepat dan reliable.

**Key Takeaways:**
- ✅ Gunakan `doq check-update` untuk mengecek update tersedia
- ✅ Gunakan `doq update` untuk update otomatis ke latest
- ✅ Gunakan `doq version` untuk melihat informasi versi
- ✅ Sistem menggunakan commit hash untuk version tracking yang precise
- ✅ Update menggunakan `uv` untuk instalasi yang lebih cepat

