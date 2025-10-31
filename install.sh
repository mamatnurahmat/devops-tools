#!/usr/bin/env bash
# DevOps Tools Installer
# Instalasi DevOps CLI tools untuk mengelola Rancher resources

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/bin"
BIN_NAME="devops"

echo "?? DevOps Tools Installer"
echo "=========================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "? Python3 tidak ditemukan. Silakan install Python3 terlebih dahulu."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "? Python3 ditemukan: ${PYTHON_VERSION}"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "? pip3 tidak ditemukan. Silakan install pip3 terlebih dahulu."
    exit 1
fi

echo "? pip3 ditemukan"

# Install dependencies
echo ""
echo "?? Menginstall dependencies..."
cd "${SCRIPT_DIR}"
pip3 install -q -r requirements.txt
echo "? Dependencies terinstall"

# Create install directory
mkdir -p "${INSTALL_DIR}"
echo "? Directory ${INSTALL_DIR} siap"

# Create wrapper script
WRAPPER_SCRIPT="${INSTALL_DIR}/${BIN_NAME}"
cat > "${WRAPPER_SCRIPT}" << EOF
#!/usr/bin/env python3
import sys
import os

# Add script directory to path
script_dir = "${SCRIPT_DIR}"
sys.path.insert(0, script_dir)

# Import and run main
from devops import main

if __name__ == '__main__':
    main()
EOF

chmod +x "${WRAPPER_SCRIPT}"
echo "? Wrapper script dibuat: ${WRAPPER_SCRIPT}"

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
echo "Gunakan command berikut untuk menjalankan DevOps Tools:"
echo "  ${BIN_NAME} --help"
echo ""
echo "Contoh:"
echo "  ${BIN_NAME} login"
echo "  ${BIN_NAME} cluster"
echo "  ${BIN_NAME} project"
echo "  ${BIN_NAME} namespace"
