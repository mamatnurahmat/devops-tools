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
    if [[ ":$PATH:" != *":${HOME}/.local/bin:"* ]]; then
        export PATH="${HOME}/.local/bin:${PATH}"
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

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "?? Membuat virtual environment..."
    uv venv || {
        echo "?? Error: Gagal membuat virtual environment"
        echo "   Pastikan uv sudah terinstall dan tersedia di PATH"
        echo "   Coba jalankan: export PATH=\"\${HOME}/.local/bin:\${PATH}\""
        exit 1
    }
    echo "? Virtual environment dibuat"
else
    echo "? Virtual environment sudah ada"
fi

# Install project dependencies using UV_LINK_MODE=copy for user installation
# This avoids permission issues and works in all environments without root
# uv pip install will automatically use .venv if it exists in the current directory
export UV_LINK_MODE=copy
uv pip install -q -e . || {
    echo "?? Error: Gagal menginstall dependencies"
    echo "   Pastikan uv sudah terinstall dan tersedia di PATH"
    echo "   Coba jalankan: export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    exit 1
}

echo "? Dependencies terinstall"

# Install package to user site-packages for global module availability
echo ""
echo "? Menginstall package ke user site-packages (global) menggunakan pip..."

# Check if we're in a temporary directory (doq update scenario)
# If so, install non-editable to avoid broken symlinks after temp dir cleanup
CURRENT_DIR="$(pwd)"
if [[ "${CURRENT_DIR}" =~ ^/tmp/doq-update- ]]; then
    echo "   Detected temporary directory - installing non-editable copy..."
    python3 -m pip install --user . || {
        echo "?? Warning: Gagal menginstall dengan 'python3 -m pip install --user .'"
        echo "   Anda masih bisa menggunakan doq via wrapper jika modul tersedia."
    }
else
    # For normal installation, use editable install
    python3 -m pip install --user -e . || {
        echo "?? Warning: Gagal menginstall dengan 'python3 -m pip install --user -e .'"
        echo "   Anda masih bisa menggunakan doq via wrapper jika modul tersedia."
    }
fi

# Ensure ~/.local/bin is on PATH for future shells
if ! echo "$PATH" | tr ':' '\n' | grep -qx "${HOME}/.local/bin"; then
    # Choose rc file: prefer .zshrc if exists, else .bashrc
    RC_FILE=""
    if [ -f "${HOME}/.zshrc" ]; then
        RC_FILE="${HOME}/.zshrc"
    elif [ -f "${HOME}/.bashrc" ]; then
        RC_FILE="${HOME}/.bashrc"
    else
        # Default to .bashrc if neither exists
        RC_FILE="${HOME}/.bashrc"
    fi

    echo "? Menambahkan ~/.local/bin ke PATH di ${RC_FILE}"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${RC_FILE}"
    echo "   -> Tambahan PATH ditulis ke ${RC_FILE} (restart shell agar aktif)"
fi

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

# Initialize plugin directory structure
echo "? Initializing plugin directory structure..."
python3 << 'EOF'
import os
import json
from pathlib import Path

# Create plugin directories
doq_dir = Path.home() / ".doq"
plugins_dir = doq_dir / "plugins"

doq_dir.mkdir(parents=True, exist_ok=True)
plugins_dir.mkdir(parents=True, exist_ok=True)

# Create default plugins.json if not exists
plugins_file = doq_dir / "plugins.json"
if not plugins_file.exists():
    default_plugins = {
        "version": "1.0",
        "plugins": [
            {
                "name": "devops-ci",
                "enabled": True,
                "version": "2.0.1",
                "module": "plugins.devops_ci",
                "config_file": "plugins/devops-ci.json",
                "commands": ["devops-ci"],
                "description": "DevOps CI/CD Docker image builder"
            },
            {
                "name": "docker-utils",
                "enabled": True,
                "version": "1.0.0",
                "module": "plugins.docker_utils",
                "config_file": "plugins/docker-utils.json",
                "commands": ["image", "get-cicd", "get-file"],
                "description": "Docker image checking and CI/CD config utilities"
            },
            {
                "name": "web-deployer",
                "enabled": True,
                "version": "1.0.0",
                "module": "plugins.web_deployer",
                "config_file": "plugins/web-deployer.json",
                "commands": ["deploy-web"],
                "description": "Web application deployment via Docker Compose"
            },
            {
                "name": "k8s-deployer",
                "enabled": True,
                "version": "1.0.0",
                "module": "plugins.k8s_deployer",
                "config_file": "plugins/k8s-deployer.json",
                "commands": ["deploy-k8s"],
                "description": "Kubernetes application deployment"
            },
            {
                "name": "sast",
                "enabled": True,
                "version": "1.0.0",
                "module": "plugins.sast",
                "config_file": "plugins/sast.json",
                "commands": ["sast"],
                "description": "Static Application Security Testing using Semgrep"
            }
        ]
    }
    with open(plugins_file, 'w') as f:
        json.dump(default_plugins, f, indent=2)
    print(f"   Created {plugins_file}")

# Create default devops-ci.json if not exists
devops_ci_config = plugins_dir / "devops-ci.json"
if not devops_ci_config.exists():
    default_config = {
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
            "enabled": True
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
    with open(devops_ci_config, 'w') as f:
        json.dump(default_config, f, indent=2)
    print(f"   Created {devops_ci_config}")

# Create default docker-utils.json if not exists
docker_utils_config = plugins_dir / "docker-utils.json"
if not docker_utils_config.exists():
    default_config = {
        "registry": {
            "namespace": "loyaltolpi",
            "default_registry": "docker.io"
        },
        "bitbucket": {
            "org": "loyaltoid",
            "api_base": "https://api.bitbucket.org/2.0/repositories",
            "default_cicd_path": "cicd/cicd.json"
        },
        "force_build": {
            "enabled": True,
            "trigger_command": "devops-ci"
        }
    }
    with open(docker_utils_config, 'w') as f:
        json.dump(default_config, f, indent=2)
    print(f"   Created {docker_utils_config}")

# Create default web-deployer.json if not exists
web_deployer_config = plugins_dir / "web-deployer.json"
if not web_deployer_config.exists():
    default_config = {
        "ssh": {
            "user": "devops",
            "key_file": "~/.ssh/id_rsa",
            "timeout": 30
        },
        "docker": {
            "namespace": "loyaltolpi",
            "target_port": 3000
        },
        "bitbucket": {
            "org": "loyaltoid",
            "cicd_path": "cicd/cicd.json"
        }
    }
    with open(web_deployer_config, 'w') as f:
        json.dump(default_config, f, indent=2)
    print(f"   Created {web_deployer_config}")

# Create default k8s-deployer.json if not exists
k8s_deployer_config = plugins_dir / "k8s-deployer.json"
if not k8s_deployer_config.exists():
    default_config = {
        "docker": {
            "namespace": "loyaltolpi"
        },
        "bitbucket": {
            "organization": "qoin-digital-indonesia",
            "cicd_path": "cicd/cicd.json"
        },
        "deployment": {
            "use_deployment_field": True
        }
    }
    with open(k8s_deployer_config, 'w') as f:
        json.dump(default_config, f, indent=2)
    print(f"   Created {k8s_deployer_config}")

print("? Plugin structure initialized")
EOF

# Save current commit hash and branch to version file
if command -v git &> /dev/null; then
    if git rev-parse --git-dir > /dev/null 2>&1; then
        CURRENT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
        python3 << EOF
import sys
import os
sys.path.insert(0, "${PROJECT_DIR}")
from version import save_version
save_version("${CURRENT_COMMIT}", "${CURRENT_BRANCH}")
EOF
        echo "? Version tracking diupdate: ${CURRENT_COMMIT} (${CURRENT_BRANCH})"
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
echo "  ${BIN_NAME} project"
