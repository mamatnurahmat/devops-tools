# Enhanced Error Messaging Guide

## Overview

The `doq image` command now provides detailed error messages and suggestions when an image check fails. This guide explains the error types, their meanings, and how to resolve them.

## Error Types

### 1. credentials_missing

**Cause**: Docker Hub credentials are not configured in `~/.doq/auth.json`

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Docker Hub credentials missing in ~/.doq/auth.json",
  "error_type": "credentials_missing",
  "suggestion": "Add DOCKERHUB_USER and DOCKERHUB_PASSWORD to ~/.doq/auth.json"
}
```

**Solution**:
```bash
# Login to configure credentials
doq login

# Or manually edit auth.json
cat > ~/.doq/auth.json << 'JSON'
{
  "DOCKERHUB_USER": "your_username",
  "DOCKERHUB_PASSWORD": "your_password",
  "GIT_USER": "your_git_user",
  "GIT_PASSWORD": "your_git_password"
}
JSON
```

---

### 2. auth_failed

**Cause**: Docker Hub login failed (wrong credentials or API issue)

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Docker Hub login failed (status: 401)",
  "error_type": "auth_failed",
  "suggestion": "Check Docker Hub credentials in ~/.doq/auth.json"
}
```

**Solution**:
```bash
# Verify credentials are correct
cat ~/.doq/auth.json

# Test login manually
docker login -u YOUR_USERNAME

# Reconfigure with doq login
doq login
```

---

### 3. not_found

**Cause**: Image does not exist in Docker Hub registry

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Image not found in Docker Hub",
  "error_type": "not_found",
  "suggestion": "Build image first: doq devops-ci saas-apigateway develop"
}
```

**Solution**:
```bash
# Build the image
doq devops-ci saas-apigateway develop

# Or with auto-build flag
doq image saas-apigateway develop --force-build
```

---

### 4. network_timeout

**Cause**: Connection to Docker Hub timed out

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Docker Hub API timeout - check network connectivity",
  "error_type": "network_timeout",
  "suggestion": "Check network connectivity and firewall settings"
}
```

**Solution**:
```bash
# Check internet connectivity
ping hub.docker.com

# Test curl to Docker Hub API
curl -I https://hub.docker.com/v2/users/login/

# Check proxy settings if applicable
echo $HTTP_PROXY
echo $HTTPS_PROXY
```

---

### 5. network_error

**Cause**: Cannot connect to Docker Hub (firewall, proxy, or network issue)

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Cannot connect to Docker Hub - check network/firewall",
  "error_type": "network_error",
  "suggestion": "Check network connectivity and firewall settings"
}
```

**Solution**:
```bash
# Check firewall rules
sudo iptables -L | grep docker

# Check if Docker Hub is accessible
curl -I https://hub.docker.com

# For corporate networks, configure proxy
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
```

---

### 6. invalid_format

**Cause**: Image name format is incorrect

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "invalid-format",
  "ready": false,
  "status": "not-ready",
  "error": "Invalid image format (missing tag): invalid-format",
  "error_type": "invalid_format",
  "suggestion": "Check image name format"
}
```

**Solution**:
Ensure image follows format: `namespace/repository:tag`
- ✅ `loyaltolpi/saas-apigateway:660cbcf`
- ❌ `saas-apigateway:660cbcf` (missing namespace)
- ❌ `loyaltolpi/saas-apigateway` (missing tag)

---

### 7. unknown

**Cause**: Unexpected error occurred

**Example Output**:
```json
{
  "repository": "saas-apigateway",
  "reference": "develop",
  "image": "loyaltolpi/saas-apigateway:660cbcf",
  "ready": false,
  "status": "not-ready",
  "error": "Error checking image: [error details]",
  "error_type": "unknown",
  "suggestion": "Check error message for details"
}
```

**Solution**:
Check the error message for specific details and contact support if needed.

---

## Automation with Error Types

The `error_type` field makes it easy to handle errors programmatically:

### Bash Script Example

```bash
#!/bin/bash

RESULT=$(doq image saas-apigateway develop 2>&1)
ERROR_TYPE=$(echo "$RESULT" | jq -r '.error_type // empty')

case "$ERROR_TYPE" in
  credentials_missing)
    echo "Please configure Docker Hub credentials"
    doq login
    ;;
  not_found)
    echo "Image not found, building..."
    doq devops-ci saas-apigateway develop
    ;;
  network_*)
    echo "Network issue detected, retrying in 30 seconds..."
    sleep 30
    doq image saas-apigateway develop
    ;;
  *)
    if [ -z "$ERROR_TYPE" ]; then
      echo "Image is ready!"
    else
      echo "Error: $ERROR_TYPE"
      echo "$RESULT" | jq -r '.suggestion // .error'
    fi
    ;;
esac
```

### Python Script Example

```python
import subprocess
import json

result = subprocess.run(
    ['doq', 'image', 'saas-apigateway', 'develop'],
    capture_output=True,
    text=True
)

data = json.loads(result.stdout)

if data['ready']:
    print(f"✅ Image ready: {data['image']}")
else:
    error_type = data.get('error_type', 'unknown')
    error_msg = data.get('error', 'Unknown error')
    suggestion = data.get('suggestion', '')
    
    print(f"❌ Image not ready: {error_msg}")
    
    if error_type == 'credentials_missing':
        # Handle missing credentials
        setup_credentials()
    elif error_type == 'not_found':
        # Trigger build
        build_image('saas-apigateway', 'develop')
    elif error_type in ['network_timeout', 'network_error']:
        # Retry with backoff
        retry_with_backoff()
    
    if suggestion:
        print(f"💡 Suggestion: {suggestion}")
```

---

## Troubleshooting Different Environments

### Local Development

Most common issues:
1. **credentials_missing**: Run `doq login`
2. **not_found**: Build image with `doq devops-ci`

### CI/CD Pipeline

Configure credentials in environment:
```yaml
# .gitlab-ci.yml or similar
variables:
  DOCKERHUB_USER: $CI_DOCKERHUB_USER
  DOCKERHUB_PASSWORD: $CI_DOCKERHUB_PASSWORD
```

### Production/VM

Common issues:
1. **network_error**: Check firewall rules
2. **auth_failed**: Verify credentials are correctly deployed

Verify credentials:
```bash
# Check auth.json exists and has correct permissions
ls -la ~/.doq/auth.json
cat ~/.doq/auth.json | jq .

# Test Docker Hub access
curl -X POST https://hub.docker.com/v2/users/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"'$DOCKERHUB_USER'","password":"'$DOCKERHUB_PASSWORD'"}'
```

---

## Configuration Validation

Use the `validate_auth_file()` helper (for developers):

```python
from plugins.shared_helpers import validate_auth_file

validation = validate_auth_file()
if not validation['valid']:
    print(f"❌ {validation['message']}")
    print(f"Missing: {', '.join(validation['missing_fields'])}")
else:
    print("✅ All credentials configured")
```

---

## Summary

The enhanced error messaging provides:
- ✅ **Clear error messages** - Know exactly what went wrong
- ✅ **Specific error types** - Easy automation and scripting
- ✅ **Actionable suggestions** - Quick guidance on how to fix
- ✅ **Consistent format** - Machine-readable JSON output

This makes debugging faster and reduces support requests! 🚀
