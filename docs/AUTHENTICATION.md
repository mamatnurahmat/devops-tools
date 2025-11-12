# Authentication Guide

## Overview

DevOps Q tools support multiple authentication methods for accessing Docker Hub and Bitbucket APIs. Authentication credentials can be provided via:

1. **Auth File** (Primary): `~/.doq/auth.json`
2. **Environment Variables** (Fallback): Auto-detected and auto-creates auth.json
3. **Login Command**: Interactive setup via `doq login`

### Auth API Bootstrap (Automatic)

Starting with the current release, `doq login` will attempt to populate `~/.doq/auth.json` automatically when it is missing or incomplete:

1. The command logs in to Rancher and obtains a bearer token.
2. If `~/.doq/auth.json` does not exist, is empty, or is missing required fields, the CLI performs an HTTPS GET to:

   ```
   {RANCHER_URL}/api/v1/namespaces/default/services/http:auth-api:8080/proxy/v1/auth/{username}
   ```

   - `{RANCHER_URL}` is the URL passed to `doq login` (default `https://193.1.1.4`)
   - `{username}` is the login username (e.g., `doq`)
   - The request includes the Rancher bearer token in the `Authorization: Bearer …` header and honours the `--insecure/--no-insecure` flag (`-k` behaviour).

3. The API response resembles:

   ```json
   {
     "name": "doq",
     "value": "{\r\n  \"DOCKERHUB_USER\": \"newrahmat\",\r\n  \"DOCKERHUB_PASSWORD\": \"87d1df79...\",\r\n  \"GIT_USER\": \"newrahmat\",\r\n  \"GIT_PASSWORD\": \"bTYhLgGf...\"\r\n}"
   }
   ```

4. The CLI parses the `value` payload, writes it to `~/.doq/auth.json` with `0600` permissions, and prints:

   ```
   ✅ Bootstrapped credentials to ~/.doq/auth.json
   ```

5. **Force Mode**: Use `doq login --force` to skip user confirmation and automatically create `~/.doq/auth.json` without prompting.

If the request fails (network error, 404, invalid payload), the CLI prints a warning and continues without aborting the login flow.

#### Manual verification steps

1. Backup and remove existing credentials:

   ```bash
   mv ~/.doq/auth.json ~/.doq/auth.json.bak 2>/dev/null || true
   ```

2. Run `doq login` with valid Rancher credentials.
3. Observe the bootstrap process:
   - `ℹ️  auth.json not found.`
   - `🔍 Attempting to fetch credentials from auth-api...`
   - `✅ Successfully fetched credentials from auth-api`
   - `📋 Found credentials for: Docker Hub, Bitbucket`
   - `Save credentials to ~/.doq/auth.json? (y/N):`
4. Type `y` to confirm saving, or `n` to skip.

**For automated scripts**: Use `doq login --force` to skip confirmation and automatically create `~/.doq/auth.json`.

**To update existing credentials**: Use `doq login --update-auth` to refresh `~/.doq/auth.json` with the latest credentials from auth-api without re-login.

5. Inspect the generated file:

   ```bash
   cat ~/.doq/auth.json
   ```

6. (Optional) Call the same API manually to confirm the payload:

   ```bash
   curl -k -H "Authorization: Bearer <token>" \
     "https://193.1.1.4/api/v1/namespaces/default/services/http:auth-api:8080/proxy/v1/auth/<username>"
   ```

#### Fallback behavior

If auth-api is unavailable, the system falls back to local sources:

1. **~/.docker/config.json** - Docker Hub credentials
2. **~/.netrc** - Bitbucket credentials
3. **Environment variables** - DOCKERHUB_USER/PASSWORD, GIT_USER/PASSWORD

The system will show what credentials were found and ask for confirmation before saving.

#### Remote-only mode

Jika ingin memaksa penggunaan auth-api (tanpa fallback lokal), set flag `RANCHER_AUTH`:

- Via environment variable:

  ```bash
  export RANCHER_AUTH=true
  ```

- Atau tambahkan ke `~/.doq/.env`:

  ```env
  RANCHER_AUTH=true
  ```

Jika `RANCHER_AUTH=true`, `doq login`:

1. Hanya mencoba mengambil kredensial dari auth-api berdasarkan username login.
2. Berhenti dengan error jika fetch gagal (tidak menggunakan fallback lokal).
3. Tetap meminta konfirmasi sebelum menyimpan ke `~/.doq/auth.json`.

### Verifying stored credentials

Gunakan perintah berikut untuk memastikan `auth.json`, kredensial Docker Hub/Bitbucket, dan token Rancher masih valid:

```bash
doq check
```

Perintah ini:

- Mengecek kelengkapan `~/.doq/auth.json`
- Melakukan login ke Docker Hub API dengan `DOCKERHUB_USER/DOCKERHUB_PASSWORD`
- Melakukan autentikasi ke Bitbucket API dengan `GIT_USER/GIT_PASSWORD`
- Mengecek status token Rancher (valid/expired) dengan menghormati opsi `--insecure/--secure`

Output `--json` menyajikan status terstruktur untuk tiap layanan.

## Priority & Auto-Creation

The authentication system follows this priority:

```
1. Load from ~/.doq/auth.json (if exists)
   └─> Success: Use credentials from file

2. File not found or incomplete? Check RANCHER_AUTH setting
   └─> RANCHER_AUTH=true?
       ├─> Yes: Try auth-api (during doq login)
       │   ├─> Fetched from API: Ask user confirmation, then save to ~/.doq/auth.json
       │   └─> API failed: Error - remote-only mode requires auth-api
       └─> No: Try local sources (~/.docker/config.json, ~/.netrc, environment)
           ├─> Found: Ask user confirmation, then save to ~/.doq/auth.json
           └─> None found: Error - provide guidance on credential sources

3. Commands requiring auth when ~/.doq/auth.json missing
   └─> RANCHER_AUTH=true: Error directing user to run 'doq login'
   └─> RANCHER_AUTH=false/unset: Error with local credential guidance
```

## Environment Variables

### RANCHER_AUTH

**Purpose**: Controls credential bootstrap behavior when `~/.doq/auth.json` is missing.

**Values**:
- `true`: Enable remote-only authentication mode
  - Commands requiring credentials will fail with instructions to run `doq login`
  - `doq login` will only fetch from auth-api, skipping local fallbacks
  - `doq check` can run without auth.json (skips credential validation)
- `false` or unset: Standard mode (default)
  - Fallback to local sources when auth-api unavailable

**Usage**:
```bash
export RANCHER_AUTH='true'
doq login  # Only tries auth-api
doq check  # Works without ~/.doq/auth.json
```

**Configuration**: Set via environment variable or `~/.doq/.env`:
```bash
# ~/.doq/.env
RANCHER_AUTH=true
```

## Login Command Options

The `doq login` command supports several flags for different authentication scenarios:

### --force
Forces re-login even when a valid token exists. Automatically creates `~/.doq/auth.json` without user confirmation.

```bash
doq login --force  # Automated login for scripts
```

### --update-auth
Updates `~/.doq/auth.json` with the latest credentials from auth-api using the existing Rancher configuration. Does not perform re-login.

```bash
doq login --update-auth  # Refresh credentials without re-login
```

### --username / --password
Provide credentials directly (useful for automated scripts):

```bash
doq login --username myuser --password mypass
```

### --url / --insecure
Override default Rancher URL and SSL settings:

```bash
doq login --url https://my-rancher.com --insecure
```

## Auth File Format

**Location**: `~/.doq/auth.json`

```json
{
  "DOCKERHUB_USER": "your-dockerhub-username",
  "DOCKERHUB_PASSWORD": "your-dockerhub-password-or-pat",
  "GIT_USER": "your-bitbucket-username",
  "GIT_PASSWORD": "your-bitbucket-app-password"
}
```

**Permissions**: Auto-set to `0600` (read/write for owner only)

## Alternative Authentication Methods

### Using ~/.netrc for Git (Bitbucket/GitHub)

The `~/.netrc` file is a standard Unix configuration file for storing credentials used by Git and other tools.

**Location**: `~/.netrc`

**Format**:
```
machine bitbucket.org
  login newrahmat
  password bTYhLgGfDzC4YhVrzwXk

machine github.com
  login mamatnurahmat
  password ghp_yourGitHubToken
```

**Setup**:
```bash
# Create .netrc file
cat > ~/.netrc << 'EOF'
machine bitbucket.org
  login your-bitbucket-username
  password your-bitbucket-app-password

machine github.com
  login your-github-username
  password your-github-token
EOF

# Set secure permissions (REQUIRED)
chmod 600 ~/.netrc
```

**Benefits**:
- ✅ Used automatically by `git clone`, `git push`, `git pull`
- ✅ No need to enter credentials for each operation
- ✅ Standard Unix/Linux credential management
- ✅ Works with multiple services (Bitbucket, GitHub, etc.)

**Integration with doq**:
The `doq` tools can read credentials from `~/.netrc` if `~/.doq/auth.json` is not present. Set environment variables to use netrc credentials:

```bash
# Extract from .netrc and export
export GIT_USER=$(grep -A1 "machine bitbucket.org" ~/.netrc | grep login | awk '{print $2}')
export GIT_PASSWORD=$(grep -A2 "machine bitbucket.org" ~/.netrc | grep password | awk '{print $2}')
```

### Using ~/.docker/config.json for Docker Hub

Docker CLI stores authentication credentials in `~/.docker/config.json` after running `docker login`.

**Location**: `~/.docker/config.json`

**Setup**:
```bash
# Login to Docker Hub
docker login

# Enter username and password when prompted
# Credentials are automatically saved
```

**Check stored credentials**:
```bash
cat ~/.docker/config.json
```

**Example output**:
```json
{
  "auths": {
    "https://index.docker.io/v1/": {
      "auth": "bmV3cmFobWF0OjhlN2QxZGY3OS0wZDIxLTQ3YzgtYjgwOC04OWEwYWM3M2MzYjE="
    }
  }
}
```

**Extract credentials from Docker config**:
```bash
# Decode the base64 auth string to get username:password
AUTH_STRING=$(jq -r '.auths["https://index.docker.io/v1/"].auth' ~/.docker/config.json)
echo "$AUTH_STRING" | base64 -d
# Output: username:password

# Export as environment variables
export DOCKERHUB_USER=$(echo "$AUTH_STRING" | base64 -d | cut -d: -f1)
export DOCKERHUB_PASSWORD=$(echo "$AUTH_STRING" | base64 -d | cut -d: -f2)
```

**Integration with doq**:
Create a helper script to load credentials from Docker config:

```bash
#!/bin/bash
# File: ~/.doq/load-docker-creds.sh

if [ -f ~/.docker/config.json ]; then
    AUTH_STRING=$(jq -r '.auths["https://index.docker.io/v1/"].auth' ~/.docker/config.json 2>/dev/null)
    if [ -n "$AUTH_STRING" ]; then
        DECODED=$(echo "$AUTH_STRING" | base64 -d 2>/dev/null)
        export DOCKERHUB_USER=$(echo "$DECODED" | cut -d: -f1)
        export DOCKERHUB_PASSWORD=$(echo "$DECODED" | cut -d: -f2-)
        echo "✅ Docker credentials loaded from ~/.docker/config.json"
    fi
fi
```

Usage:
```bash
source ~/.doq/load-docker-creds.sh
doq image saas-apigateway develop
```

## Environment Variables

If `~/.doq/auth.json` doesn't exist, the system will automatically detect credentials from these environment variables:

### Docker Hub Credentials

Checked in order (first match wins):
- `DOCKERHUB_USER` (preferred)
- `REGISTY_USER` (legacy)
- `REGISTRY_USER` (legacy)

Password:
- `DOCKERHUB_PASSWORD` (preferred)
- `REGISTY_PASSWORD` (legacy)
- `REGISTRY_PASSWORD` (legacy)

### Bitbucket Credentials

Username:
- `GIT_USER` (preferred)
- `BITBUCKET_USER`
- `BB_USER`

Password/Token:
- `GIT_PASSWORD` (preferred)
- `BITBUCKET_TOKEN`
- `BB_PASSWORD`

## Quick Setup Scripts

### All-in-One Setup from Existing Credentials

If you already have `~/.netrc` and `~/.docker/config.json`, use the provided setup script:

```bash
# Run the setup script
./scripts/setup-auth.sh
```

This will automatically:
1. ✅ Detect credentials from `~/.docker/config.json`
2. ✅ Detect credentials from `~/.netrc`
3. ✅ Create `~/.doq/auth.json` with found credentials
4. ✅ Set secure permissions (600)

**Manual Script** (if you prefer to customize):

```bash
#!/bin/bash
# File: ~/.doq/setup-auth.sh
# Auto-create doq auth.json from existing credentials

DOQDIR="$HOME/.doq"
AUTHFILE="$DOQDIR/auth.json"

mkdir -p "$DOQDIR"

# Initialize empty JSON
echo "{" > "$AUTHFILE"

# Try to get Docker Hub credentials from ~/.docker/config.json
if [ -f ~/.docker/config.json ]; then
    AUTH_STRING=$(jq -r '.auths["https://index.docker.io/v1/"].auth' ~/.docker/config.json 2>/dev/null)
    if [ -n "$AUTH_STRING" ] && [ "$AUTH_STRING" != "null" ]; then
        DECODED=$(echo "$AUTH_STRING" | base64 -d 2>/dev/null)
        DOCKERHUB_USER=$(echo "$DECODED" | cut -d: -f1)
        DOCKERHUB_PASSWORD=$(echo "$DECODED" | cut -d: -f2-)
        
        echo "  \"DOCKERHUB_USER\": \"$DOCKERHUB_USER\"," >> "$AUTHFILE"
        echo "  \"DOCKERHUB_PASSWORD\": \"$DOCKERHUB_PASSWORD\"," >> "$AUTHFILE"
        echo "✅ Loaded Docker Hub credentials from ~/.docker/config.json"
    fi
fi

# Try to get Bitbucket credentials from ~/.netrc
if [ -f ~/.netrc ]; then
    GIT_USER=$(grep -A1 "machine bitbucket.org" ~/.netrc | grep login | awk '{print $2}' 2>/dev/null)
    GIT_PASSWORD=$(grep -A2 "machine bitbucket.org" ~/.netrc | grep password | awk '{print $2}' 2>/dev/null)
    
    if [ -n "$GIT_USER" ] && [ -n "$GIT_PASSWORD" ]; then
        echo "  \"GIT_USER\": \"$GIT_USER\"," >> "$AUTHFILE"
        echo "  \"GIT_PASSWORD\": \"$GIT_PASSWORD\"" >> "$AUTHFILE"
        echo "✅ Loaded Bitbucket credentials from ~/.netrc"
    fi
fi

# Close JSON
echo "}" >> "$AUTHFILE"

# Clean up trailing commas (invalid JSON)
sed -i 's/,\([[:space:]]*}\)/\1/' "$AUTHFILE"

# Set secure permissions
chmod 600 "$AUTHFILE"

echo ""
echo "✅ Created $AUTHFILE"
echo "Run: doq image <repo> <branch> to test"
```

**Run the script**:
```bash
chmod +x ~/.doq/setup-auth.sh
~/.doq/setup-auth.sh
```

### Load Credentials Helper Functions

Add these functions to your `~/.bashrc` or `~/.zshrc`:

```bash
# Load Docker Hub credentials from ~/.docker/config.json
load-docker-creds() {
    if [ -f ~/.docker/config.json ]; then
        AUTH_STRING=$(jq -r '.auths["https://index.docker.io/v1/"].auth' ~/.docker/config.json 2>/dev/null)
        if [ -n "$AUTH_STRING" ] && [ "$AUTH_STRING" != "null" ]; then
            DECODED=$(echo "$AUTH_STRING" | base64 -d 2>/dev/null)
            export DOCKERHUB_USER=$(echo "$DECODED" | cut -d: -f1)
            export DOCKERHUB_PASSWORD=$(echo "$DECODED" | cut -d: -f2-)
            echo "✅ Docker Hub credentials loaded"
        else
            echo "⚠️  No Docker Hub credentials found in ~/.docker/config.json"
        fi
    else
        echo "⚠️  File ~/.docker/config.json not found. Run 'docker login' first."
    fi
}

# Load Git credentials from ~/.netrc
load-git-creds() {
    if [ -f ~/.netrc ]; then
        export GIT_USER=$(grep -A1 "machine bitbucket.org" ~/.netrc | grep login | awk '{print $2}')
        export GIT_PASSWORD=$(grep -A2 "machine bitbucket.org" ~/.netrc | grep password | awk '{print $2}')
        
        if [ -n "$GIT_USER" ] && [ -n "$GIT_PASSWORD" ]; then
            echo "✅ Bitbucket credentials loaded from ~/.netrc"
        else
            echo "⚠️  No Bitbucket credentials found in ~/.netrc"
        fi
    else
        echo "⚠️  File ~/.netrc not found"
    fi
}

# Load all credentials
load-doq-creds() {
    load-docker-creds
    load-git-creds
}
```

**Usage**:
```bash
# Load all credentials before using doq
load-doq-creds
doq image saas-apigateway develop
```

## Usage Examples

### Method 1: Using Auth File (Recommended)

Create `~/.doq/auth.json` manually:

```bash
cat > ~/.doq/auth.json << 'EOF'
{
  "DOCKERHUB_USER": "myuser",
  "DOCKERHUB_PASSWORD": "mypassword",
  "GIT_USER": "myuser",
  "GIT_PASSWORD": "mytoken"
}
EOF

chmod 600 ~/.doq/auth.json
```

### Method 2: Using Environment Variables (Auto-Creation)

Set environment variables and run any doq command:

```bash
export DOCKERHUB_USER="myuser"
export DOCKERHUB_PASSWORD="mypassword"
export GIT_USER="myuser"
export GIT_PASSWORD="mytoken"

# Run any doq command - auth.json will be auto-created
doq image saas-apigateway develop
```

Output:
```
✅ Auto-created /home/user/.doq/auth.json from environment variables
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:abc123",
  "ready": true,
  "status": "ready"
}
```

### Method 3: Persistent Environment Variables

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# Docker Hub credentials
export DOCKERHUB_USER="myuser"
export DOCKERHUB_PASSWORD="mypassword"

# Bitbucket credentials
export GIT_USER="myuser"
export GIT_PASSWORD="mytoken"
```

Then reload shell:
```bash
source ~/.bashrc
```

## Security Best Practices

1. **Never commit auth.json to version control**
   - Already in `.gitignore` by default

2. **Use secure permissions**
   - Auth file is auto-set to `0600` (owner read/write only)

3. **Use App Passwords/Tokens**
   - Docker Hub: Use Personal Access Tokens (PAT)
   - Bitbucket: Use App Passwords (not account password)

4. **Rotate credentials regularly**
   - Update `auth.json` or environment variables when rotating

## Troubleshooting

### Issue: "Authentication file not found"

**Solution 1**: Create auth.json manually
```bash
mkdir -p ~/.doq
cat > ~/.doq/auth.json << 'EOF'
{
  "DOCKERHUB_USER": "your-user",
  "DOCKERHUB_PASSWORD": "your-pass",
  "GIT_USER": "your-user",
  "GIT_PASSWORD": "your-token"
}
EOF
chmod 600 ~/.doq/auth.json
```

**Solution 2**: Set environment variables
```bash
export DOCKERHUB_USER="your-user"
export DOCKERHUB_PASSWORD="your-pass"
export GIT_USER="your-user"
export GIT_PASSWORD="your-token"

# Run any command - file will be auto-created
doq image myrepo develop
```

### Issue: "Docker Hub credentials missing"

Check your auth.json has the required fields:

```bash
cat ~/.doq/auth.json | jq 'keys'
```

Should output:
```json
[
  "DOCKERHUB_PASSWORD",
  "DOCKERHUB_USER",
  "GIT_PASSWORD",
  "GIT_USER"
]
```

### Issue: Auto-creation doesn't work

Requirements for auto-creation:
- At least 2 credentials must be found in environment variables
- Docker Hub OR Bitbucket credentials (at minimum)

Check your environment:
```bash
env | grep -E "(DOCKERHUB|GIT_|BITBUCKET|REGISTRY)"
```

## Commands That Require Authentication

### Docker Hub (DOCKERHUB_USER + DOCKERHUB_PASSWORD)
- `doq image` - Check image availability
- `doq devops-ci` - Build and push images
- `doq deploy-web` - Deploy via Docker Compose
- `doq deploy-k8s` - Deploy to Kubernetes

### Bitbucket (GIT_USER + GIT_PASSWORD)
- `doq get-cicd` - Fetch cicd.json from repository
- `doq get-file` - Fetch files from repository
- `doq devops-ci` - Clone repository for build
- `doq deploy-web` - Fetch deployment config
- `doq deploy-k8s` - Fetch deployment config

## Migration from Old Locations

If you have auth files in old locations, they are automatically migrated:

- Old: `~/.devops-q/auth.json`
- New: `~/.doq/auth.json`

Migration happens automatically on first use.

