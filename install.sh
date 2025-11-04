#!/usr/bin/env bash
# DevOps Q Installer
# Instalasi DevOps Q CLI tools untuk mengelola Rancher resources
# Menggunakan uv package manager untuk instalasi yang lebih cepat dan reliable

set -e

# Default values
REPO_URL="${REPO_URL:-https://github.com/mamatnurahmat/devops-tools}"
REPO_REF="${REPO_REF:-main}"
PREFIX="${PREFIX:-${HOME}/.local/share/devops-q}"
INSTALL_DIR="${HOME}/.local/bin"
BIN_NAME="doq"
SKIP_CLONE="${SKIP_CLONE:-}"

# Parse arguments
YES_FLAG=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --yes)
            YES_FLAG="yes"
            shift
            ;;
        --repo)
            REPO_URL="$2"
            shift 2
            ;;
        --ref)
            REPO_REF="$2"
            shift 2
            ;;
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --skip-clone)
            SKIP_CLONE="yes"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--yes] [--repo URL] [--ref BRANCH] [--prefix DIR] [--skip-clone]"
            exit 1
            ;;
    esac
done

echo "?? DevOps Q Installer"
echo "=========================="
echo ""

# Detect if running from stdin (pipe mode)
IS_PIPE_MODE=false
if [ -t 0 ]; then
    # Running from terminal (not pipe)
    IS_PIPE_MODE=false
else
    # Running from pipe
    IS_PIPE_MODE=true
fi

# Detect if we're in a project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null || pwd)"
if [ -f "${SCRIPT_DIR}/pyproject.toml" ]; then
    PROJECT_DIR="${SCRIPT_DIR}"
elif [ -f "./pyproject.toml" ]; then
    PROJECT_DIR="$(pwd)"
else
    PROJECT_DIR=""
fi

# Auto-clone if needed
if [ -z "$PROJECT_DIR" ] && [ -z "$SKIP_CLONE" ]; then
    echo "?? Tidak menemukan pyproject.toml di direktori saat ini"
    
    if [ "$IS_PIPE_MODE" = true ] || [ "$YES_FLAG" = "yes" ]; then
        echo "?? Meng-clone repository ke ${PREFIX}..."
        echo "   Repository: ${REPO_URL}"
        echo "   Branch/Ref: ${REPO_REF}"
        
        # Create parent directory if it doesn't exist
        mkdir -p "$(dirname "${PREFIX}")" || {
            echo "?? Error: Gagal membuat parent directory $(dirname "${PREFIX}")"
            echo "   Pastikan Anda memiliki permission untuk menulis di direktori tersebut"
            exit 1
        }
        
        # Clone repository
        if [ -d "${PREFIX}" ]; then
            if [ "$YES_FLAG" = "yes" ]; then
                echo "?? Directory ${PREFIX} sudah ada, melakukan update..."
                cd "${PREFIX}"
                git fetch origin "${REPO_REF}" || true
                git checkout "${REPO_REF}" || true
            else
                echo "?? Error: Directory ${PREFIX} sudah ada"
                echo "   Gunakan --yes untuk update, atau hapus direktori tersebut terlebih dahulu"
                exit 1
            fi
        else
            git clone --branch "${REPO_REF}" --single-branch "${REPO_URL}" "${PREFIX}" || {
                echo "?? Error: Gagal meng-clone repository ke ${PREFIX}"
                echo ""
                echo "Kemungkinan penyebab:"
                echo "  1. Tidak memiliki permission untuk menulis di $(dirname "${PREFIX}")"
                echo "  2. Git tidak terinstall"
                echo "  3. Tidak ada koneksi internet"
                echo ""
                echo "Solusi:"
                echo "  1. Gunakan --prefix untuk mengubah lokasi instalasi:"
                echo "     curl -fsSL ... | bash -s -- --yes --prefix ${HOME}/.local/share/devops-q"
                echo ""
                echo "  2. Atau clone manual dengan sudo (jika ingin di /opt):"
                echo "     sudo git clone ${REPO_URL} ${PREFIX}"
                echo "     sudo chown -R \$(whoami):\$(whoami) ${PREFIX}"
                echo "     cd ${PREFIX} && ./install.sh"
                exit 1
            }
        fi
        
        PROJECT_DIR="${PREFIX}"
        cd "${PROJECT_DIR}"
    else
        echo ""
        echo "?? Perlu clone repository terlebih dahulu."
        echo ""
        echo "Pilihan:"
        echo "1. Clone repository manual:"
        echo "   git clone ${REPO_URL} ${PREFIX}"
        echo "   cd ${PREFIX}"
        echo "   ./install.sh"
        echo ""
        echo "2. Atau jalankan installer dengan --yes untuk auto-clone:"
        echo "   curl -fsSL https://raw.githubusercontent.com/mamatnurahmat/devops-tools/${REPO_REF}/install.sh | bash -s -- --yes"
        echo ""
        echo "3. Atau gunakan opsi kustom:"
        echo "   curl -fsSL ... | bash -s -- --yes --repo ${REPO_URL} --ref ${REPO_REF} --prefix ${PREFIX}"
        exit 1
    fi
elif [ -n "$PROJECT_DIR" ]; then
    echo "?? Menggunakan project directory: ${PROJECT_DIR}"
    cd "${PROJECT_DIR}"
fi

# Verify pyproject.toml exists
if [ ! -f "pyproject.toml" ]; then
    echo "?? Error: pyproject.toml tidak ditemukan di ${PROJECT_DIR}"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "? Python3 tidak ditemukan. Silakan install Python3 terlebih dahulu."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "? Python3 ditemukan: ${PYTHON_VERSION}"

# Check uv - install if not available
if ! command -v uv &> /dev/null; then
    echo "? uv tidak ditemukan. Menginstall uv..."
    
    # Install uv using official installer
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add uv to PATH - check both common locations
    # uv installer installs to ~/.local/bin or ~/.cargo/bin depending on version
    if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
        export PATH="${HOME}/.local/bin:${PATH}"
    fi
    if [[ ":$PATH:" != *":${HOME}/.cargo/bin:"* ]]; then
        export PATH="${HOME}/.cargo/bin:${PATH}"
    fi
    
    # Source env file if exists (uv installer creates this)
    if [ -f "${HOME}/.local/bin/env" ]; then
        source "${HOME}/.local/bin/env" 2>/dev/null || true
    fi
    
    # Verify uv installation
    if ! command -v uv &> /dev/null; then
        echo "? Error: Gagal menginstall uv."
        echo "   uv mungkin terinstall di ${HOME}/.local/bin atau ${HOME}/.cargo/bin"
        echo "   Silakan tambahkan ke PATH atau install manual dari https://github.com/astral-sh/uv"
        echo ""
        echo "   Coba jalankan:"
        echo "   export PATH=\"\${HOME}/.local/bin:\${PATH}\""
        echo "   export PATH=\"\${HOME}/.cargo/bin:\${PATH}\""
        exit 1
    fi
    
    echo "? uv berhasil diinstall"
else
    echo "? uv ditemukan: $(uv --version)"
fi

# Install dependencies menggunakan uv
echo ""
echo "?? Menginstall dependencies dengan uv..."
echo "   Working directory: $(pwd)"

# Install project dependencies dengan --system flag untuk non-root user
# --system installs to user site-packages (~/.local/lib/python3.x/site-packages)
uv pip install --system -q -e . || {
    echo "?? Error: Gagal menginstall dependencies"
    echo "   Pastikan uv sudah terinstall dan tersedia di PATH"
    echo "   Coba jalankan: export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    exit 1
}

echo "? Dependencies terinstall"

# Create install directory
mkdir -p "${INSTALL_DIR}"
echo "? Directory ${INSTALL_DIR} siap"

# Create wrapper script menggunakan python langsung (package sudah diinstall di user site-packages)
WRAPPER_SCRIPT="${INSTALL_DIR}/${BIN_NAME}"
cat > "${WRAPPER_SCRIPT}" << 'EOF'
#!/usr/bin/env bash
# DevOps Q CLI Wrapper
# Package sudah diinstall di user site-packages dengan --system flag
# Jadi bisa langsung menggunakan python3 tanpa perlu uv run

python3 -m doq "$@"
EOF

chmod +x "${WRAPPER_SCRIPT}"
echo "? Wrapper script dibuat: ${WRAPPER_SCRIPT}"

# Save current commit hash to version file
if command -v git &> /dev/null; then
    if git rev-parse --git-dir > /dev/null 2>&1; then
        CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
        python3 << EOF
import sys
import os
sys.path.insert(0, "${PROJECT_DIR}")
from version import save_version
save_version("${CURRENT_COMMIT}")
EOF
        echo "? Version tracking diupdate: ${CURRENT_COMMIT}"
    fi
fi

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo ""
    echo "??  Warning: ${INSTALL_DIR} tidak ada di PATH"
    echo ""
    echo "Tambahkan ke ~/.bashrc atau ~/.zshrc:"
    echo "export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    echo ""
    echo "Atau jalankan:"
    echo "export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    echo ""
else
    echo "? ${INSTALL_DIR} sudah ada di PATH"
fi

echo ""
echo "? Instalasi selesai!"
echo ""
echo "Gunakan command berikut untuk menjalankan DevOps Q:"
echo "  ${BIN_NAME} --help"
echo ""
echo "Contoh:"
echo "  ${BIN_NAME} login"
echo "  ${BIN_NAME} cluster"
echo "  ${BIN_NAME} project"
echo "  ${BIN_NAME} namespace"
