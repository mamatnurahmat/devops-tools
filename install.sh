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

# Use UV_LINK_MODE=copy to avoid permission issues and install to user space
# uv automatically uses user site-packages when not in a virtual environment
export UV_LINK_MODE=copy
uv pip install -q -e .

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
