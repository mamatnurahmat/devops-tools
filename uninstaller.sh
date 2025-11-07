#!/usr/bin/env bash
# DevOps Q Uninstaller
# Membersihkan instalasi DevOps Q dari sistem pengguna

set -e

# Defaults
INSTALL_DIR="${HOME}/.local/bin"
BIN_NAME="doq"
PREFIX_DEFAULT="${HOME}/.local/share/devops-q"
CONFIG_DIR="${HOME}/.doq"

YES_FLAG=""
REMOVE_CONFIG=""
REMOVE_PREFIX="yes"
DRY_RUN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y)
      YES_FLAG="yes"; shift;;
    --remove-config)
      REMOVE_CONFIG="yes"; shift;;
    --keep-prefix)
      REMOVE_PREFIX=""; shift;;
    --dry-run)
      DRY_RUN="yes"; shift;;
    -h|--help)
      cat <<'EOF'
DevOps Q Uninstaller

Usage:
  ./uninstaller.sh [--yes] [--remove-config] [--keep-prefix] [--dry-run]

Options:
  --yes            Non-interactive; konfirmasi otomatis semua penghapusan
  --remove-config  Hapus direktori konfigurasi (~/.doq)
  --keep-prefix    Jangan hapus direktori clone default (~/.local/share/devops-q)
  --dry-run        Tampilkan aksi yang akan dilakukan tanpa mengeksekusi
EOF
      exit 0;;
    *)
      echo "Unknown option: $1"; exit 1;;
  esac
done

log() { echo "$@"; }

confirm() {
  local prompt="$1"
  if [[ "$YES_FLAG" == "yes" ]]; then
    return 0
  fi
  read -p "$prompt [y/N]: " -r
  echo
  [[ $REPLY =~ ^[Yy]$ ]]
}

maybe_rm() {
  local target="$1"
  if [[ -e "$target" ]]; then
    if [[ -n "$DRY_RUN" ]]; then
      log "- DRY-RUN: rm -rf $target"
    else
      rm -rf "$target"
      log "- Removed: $target"
    fi
  fi
}

log "🧹 DevOps Q Uninstaller"
log "========================"
log ""

# 1) Remove wrapper
WRAPPER_PATH="${INSTALL_DIR}/${BIN_NAME}"
if [[ -f "$WRAPPER_PATH" ]]; then
  if confirm "Hapus wrapper CLI $WRAPPER_PATH?"; then
    maybe_rm "$WRAPPER_PATH"
  else
    log "- Skip: $WRAPPER_PATH"
  fi
else
  log "- Wrapper tidak ditemukan: $WRAPPER_PATH"
fi

# 2) Uninstall pip user package
if python3 -m pip show doq >/dev/null 2>&1; then
  log "- Paket Python 'doq' terdeteksi di environment ini"
  if confirm "Uninstall 'doq' dari user site-packages?"; then
    if [[ -n "$DRY_RUN" ]]; then
      log "- DRY-RUN: python3 -m pip uninstall -y doq"
    else
      python3 -m pip uninstall -y doq || true
      log "- Uninstalled pip package 'doq'"
    fi
  else
    log "- Skip uninstall pip"
  fi
else
  log "- Paket Python 'doq' tidak terdeteksi (skip)"
fi

# 3) Remove cloned project at default prefix
if [[ "$REMOVE_PREFIX" == "yes" && -d "$PREFIX_DEFAULT" ]]; then
  if confirm "Hapus direktori project default: $PREFIX_DEFAULT?"; then
    maybe_rm "$PREFIX_DEFAULT"
  else
    log "- Skip: $PREFIX_DEFAULT"
  fi
else
  if [[ "$REMOVE_PREFIX" != "yes" ]]; then
    log "- Skip penghapusan prefix (diminta --keep-prefix)"
  else
    log "- Direktori project default tidak ditemukan: $PREFIX_DEFAULT"
  fi
fi

# 4) Optionally remove config directory
if [[ -n "$REMOVE_CONFIG" ]]; then
  if [[ -d "$CONFIG_DIR" ]]; then
    if confirm "Hapus direktori konfigurasi: $CONFIG_DIR?"; then
      maybe_rm "$CONFIG_DIR"
    else
      log "- Skip: $CONFIG_DIR"
    fi
  else
    log "- Direktori konfigurasi tidak ditemukan: $CONFIG_DIR"
  fi
else
  log "- Menyimpan konfigurasi di $CONFIG_DIR (gunakan --remove-config untuk menghapus)"
fi

log ""
log "✅ Uninstall selesai"
if [[ -n "$DRY_RUN" ]]; then
  echo "(Catatan: ini hanya simulasi; tidak ada perubahan yang dilakukan)"
fi


