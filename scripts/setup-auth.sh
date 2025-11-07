#!/bin/bash
# DevOps Q - Authentication Setup Script
# Auto-create ~/.doq/auth.json from existing credentials
# Sources: ~/.docker/config.json and ~/.netrc

set -e

DOQDIR="$HOME/.doq"
AUTHFILE="$DOQDIR/auth.json"

echo "🔐 DevOps Q Authentication Setup"
echo "=================================="
echo ""

# Create directory if not exists
mkdir -p "$DOQDIR"

# Check if auth.json already exists
if [ -f "$AUTHFILE" ]; then
    echo "⚠️  Auth file already exists: $AUTHFILE"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Cancelled"
        exit 0
    fi
    echo ""
fi

# Initialize credentials
DOCKERHUB_USER=""
DOCKERHUB_PASSWORD=""
GIT_USER=""
GIT_PASSWORD=""

# Try to get Docker Hub credentials from ~/.docker/config.json
echo "🔍 Checking ~/.docker/config.json..."
if [ -f ~/.docker/config.json ]; then
    if command -v jq &> /dev/null; then
        AUTH_STRING=$(jq -r '.auths["https://index.docker.io/v1/"].auth' ~/.docker/config.json 2>/dev/null)
        if [ -n "$AUTH_STRING" ] && [ "$AUTH_STRING" != "null" ]; then
            DECODED=$(echo "$AUTH_STRING" | base64 -d 2>/dev/null)
            DOCKERHUB_USER=$(echo "$DECODED" | cut -d: -f1)
            DOCKERHUB_PASSWORD=$(echo "$DECODED" | cut -d: -f2-)
            echo "   ✅ Found Docker Hub credentials (user: $DOCKERHUB_USER)"
        else
            echo "   ⚠️  No credentials found in Docker config"
        fi
    else
        echo "   ⚠️  jq not installed, skipping Docker config parsing"
        echo "      Install: sudo apt install jq"
    fi
else
    echo "   ⚠️  File not found. Run 'docker login' to create it."
fi

# Try to get Bitbucket credentials from ~/.netrc
echo ""
echo "🔍 Checking ~/.netrc..."
if [ -f ~/.netrc ]; then
    GIT_USER=$(grep -A1 "machine bitbucket.org" ~/.netrc 2>/dev/null | grep login | awk '{print $2}')
    GIT_PASSWORD=$(grep -A2 "machine bitbucket.org" ~/.netrc 2>/dev/null | grep password | awk '{print $2}')
    
    if [ -n "$GIT_USER" ] && [ -n "$GIT_PASSWORD" ]; then
        echo "   ✅ Found Bitbucket credentials (user: $GIT_USER)"
    else
        echo "   ⚠️  No Bitbucket credentials found"
    fi
else
    echo "   ⚠️  File not found"
fi

# Check if we have any credentials
if [ -z "$DOCKERHUB_USER" ] && [ -z "$GIT_USER" ]; then
    echo ""
    echo "❌ Error: No credentials found in ~/.docker/config.json or ~/.netrc"
    echo ""
    echo "Setup instructions:"
    echo "1. For Docker Hub: docker login"
    echo "2. For Bitbucket: Create ~/.netrc with:"
    echo ""
    echo "   machine bitbucket.org"
    echo "     login your-username"
    echo "     password your-app-password"
    echo ""
    echo "   chmod 600 ~/.netrc"
    exit 1
fi

# Create auth.json
echo ""
echo "📝 Creating $AUTHFILE..."

cat > "$AUTHFILE" << EOF
{
EOF

# Add Docker Hub credentials if found
if [ -n "$DOCKERHUB_USER" ]; then
    cat >> "$AUTHFILE" << EOF
  "DOCKERHUB_USER": "$DOCKERHUB_USER",
  "DOCKERHUB_PASSWORD": "$DOCKERHUB_PASSWORD"
EOF
fi

# Add comma if both credentials exist
if [ -n "$DOCKERHUB_USER" ] && [ -n "$GIT_USER" ]; then
    echo "," >> "$AUTHFILE"
fi

# Add Git credentials if found
if [ -n "$GIT_USER" ]; then
    cat >> "$AUTHFILE" << EOF
  "GIT_USER": "$GIT_USER",
  "GIT_PASSWORD": "$GIT_PASSWORD"
EOF
fi

# Close JSON
cat >> "$AUTHFILE" << EOF

}
EOF

# Set secure permissions
chmod 600 "$AUTHFILE"

echo "   ✅ Created with permissions 600 (read/write owner only)"

# Display summary
echo ""
echo "✅ Setup Complete!"
echo ""
echo "Credentials saved to: $AUTHFILE"
echo ""
echo "Contents:"
if [ -n "$DOCKERHUB_USER" ]; then
    echo "  ✅ DOCKERHUB_USER: $DOCKERHUB_USER"
    echo "  ✅ DOCKERHUB_PASSWORD: ***"
fi
if [ -n "$GIT_USER" ]; then
    echo "  ✅ GIT_USER: $GIT_USER"
    echo "  ✅ GIT_PASSWORD: ***"
fi

echo ""
echo "Test with:"
echo "  doq image <repository> <branch>"
echo ""

