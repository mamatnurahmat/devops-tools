#!/usr/bin/env bash
# DevOps Q Installer
# Instalasi DevOps Q CLI tools untuk mengelola Rancher resources
# Menggunakan uv package manager untuk instalasi yang lebih cepat dan reliable

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/bin"
BIN_NAME="doq"

echo "?? DevOps Q Installer"
echo "=========================="
echo ""

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
    
    # Add possible uv installation paths to PATH
    # uv can be installed in ~/.cargo/bin or ~/.local/bin
    if [[ ":$PATH:" != *":${HOME}/.cargo/bin:"* ]]; then
        export PATH="${HOME}/.cargo/bin:${PATH}"
    fi
    if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
        export PATH="${HOME}/.local/bin:${PATH}"
    fi
    
    # Verify uv installation
    if ! command -v uv &> /dev/null; then
        echo "? Error: Gagal menginstall uv. Silakan install manual dari https://github.com/astral-sh/uv"
        exit 1
    fi
    
    echo "? uv berhasil diinstall"
else
    echo "? uv ditemukan: $(uv --version)"
fi

# Install dependencies menggunakan uv
echo ""
echo "?? Menginstall dependencies dengan uv..."
cd "${SCRIPT_DIR}"

# Install project dependencies to user space (--user flag)
uv pip install -q --user -e .

echo "? Dependencies terinstall"

# Create install directory
mkdir -p "${INSTALL_DIR}"
echo "? Directory ${INSTALL_DIR} siap"

# Create wrapper script menggunakan uv run
WRAPPER_SCRIPT="${INSTALL_DIR}/${BIN_NAME}"
cat > "${WRAPPER_SCRIPT}" << 'EOF'
#!/usr/bin/env bash
# DevOps Q CLI Wrapper
# Menggunakan uv untuk menjalankan CLI dengan environment yang terisolasi

# Check if uv is available
if command -v uv &> /dev/null; then
    # Use uv run to execute doq module directly
    # Package is already installed via 'uv pip install -e .', so we can run it directly
    uv run python -m doq "$@"
else
    # Fallback to direct python execution
    python3 -m doq "$@"
fi
EOF

chmod +x "${WRAPPER_SCRIPT}"
echo "? Wrapper script dibuat: ${WRAPPER_SCRIPT}"

# Save current commit hash to version file
if command -v git &> /dev/null; then
    cd "${SCRIPT_DIR}"
    if git rev-parse --git-dir > /dev/null 2>&1; then
        CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
        python3 << EOF
import sys
import os
sys.path.insert(0, "${SCRIPT_DIR}")
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
