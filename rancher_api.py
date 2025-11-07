"""Rancher API client."""
import requests
import urllib3
from config import load_config

# Suppress SSL warnings when insecure mode is used
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def check_token(url, token, insecure=True):
    """Check token validity and expiration status.
    
    Args:
        url: Rancher API URL
        token: Rancher API token to check
        insecure: Skip SSL verification (default: True)
    
    Returns:
        dict: Validation result with 'valid', 'expired', 'expires_at', 'error' keys
    """
    api = RancherAPI(url=url, token=token, insecure=insecure)
    return api.validate_token()


def login(url, username, password, insecure=True):
    """Login to Rancher API and get token.
    
    Args:
        url: Rancher API URL
        username: Username for authentication
        password: Password for authentication
        insecure: Skip SSL verification (default: True)
    
    Returns:
        str: Authentication token
    """
    import base64
    
    url = url.rstrip('/')
    verify = not insecure
    
    # Try multiple login methods
    # Method 1: Local provider login endpoint
    endpoints = [
        ("/v3-public/localProviders/local?action=login", {"username": username, "password": password}),
    ]
    
    # Try Basic Auth method first (common for Rancher)
    try:
        auth_str = base64.b64encode(f"{username}:{password}".encode()).decode()
        token_url = f"{url}/v3-public/tokens"
        headers = {
            "Authorization": f"Basic {auth_str}",
            "Content-Type": "application/json"
        }
        response = requests.post(token_url, headers=headers, json={}, verify=verify, timeout=30)
        if response.status_code == 201:
            data = response.json()
            token = data.get('token') or (data.get('data', {}).get('token') if isinstance(data.get('data'), dict) else None)
            if token:
                return token
    except Exception:
        pass
    
    # Method 2: Try local provider login
    for endpoint, payload in endpoints:
        try:
            login_url = f"{url}{endpoint}"
            response = requests.post(login_url, json=payload, verify=verify, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Try different token locations in response
            token = (
                data.get('token') or
                data.get('data', {}).get('token') or
                data.get('userToken')
            )
            
            # If token is in response.data format
            if not token and 'data' in data:
                if isinstance(data['data'], str):
                    token = data['data']
                elif isinstance(data['data'], dict):
                    token = data['data'].get('token')
            
            if token:
                return token
        except requests.exceptions.RequestException as e:
            continue
    
    raise ValueError("Login failed: Unable to authenticate. Please check your credentials and URL.")


class RancherAPI:
    """Client for Rancher API."""
    
    def __init__(self, url=None, token=None, insecure=True):
        """Initialize Rancher API client.
        
        Args:
            url: Rancher API URL (optional, loaded from config if not provided)
            token: Rancher API token (optional, loaded from config if not provided)
            insecure: Skip SSL verification (default: True)
        """
        if url is None or token is None:
            config = load_config()
            url = url or config['url']
            token = token or config['token']
            insecure = insecure if url is not None else config['insecure']
        
        if not url or not token:
            raise ValueError("Rancher URL and token must be provided or configured")
        
        self.url = url.rstrip('/')
        self.token = token
        self.verify = not insecure
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
    
    def _request(self, method, endpoint, **kwargs):
        """Make API request."""
        url = f"{self.url}{endpoint}"
        kwargs.setdefault('verify', self.verify)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def _request_raw(self, method, endpoint, **kwargs):
        """Make API request and return raw response."""
        url = f"{self.url}{endpoint}"
        kwargs.setdefault('verify', self.verify)
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response
    
    def get(self, endpoint, **kwargs):
        """GET request."""
        return self._request('GET', endpoint, **kwargs)
    
    def post(self, endpoint, **kwargs):
        """POST request."""
        return self._request('POST', endpoint, **kwargs)
    
    def list_clusters(self):
        """List all clusters."""
        data = self.get('/v3/clusters')
        return data.get('data', [])
    
    def list_projects(self, cluster_id=None):
        """List all projects.
        
        Args:
            cluster_id: Optional cluster ID to filter projects
        """
        if cluster_id:
            endpoint = f'/v3/projects?clusterId={cluster_id}'
        else:
            endpoint = '/v3/projects'
        data = self.get(endpoint)
        return data.get('data', [])
    
    def list_namespaces(self, project_id=None, cluster_id=None):
        """List all namespaces.
        
        Args:
            project_id: Optional project ID to filter namespaces
            cluster_id: Optional cluster ID to filter namespaces
        """
        all_namespaces = []
        
        # Try different endpoint approaches
        endpoints_to_try = []
        
        if project_id:
            endpoints_to_try = [
                f'/v3/projects/{project_id}/namespaces',
                f'/v3/namespaces?projectId={project_id}',
                f'/v1/namespaces?projectId={project_id}'
            ]
        elif cluster_id:
            endpoints_to_try = [
                f'/v3/clusters/{cluster_id}/namespaces',
                f'/v3/namespaces?clusterId={cluster_id}',
                f'/k8s/clusters/{cluster_id}/v1/namespaces',
                f'/v1/namespaces?clusterId={cluster_id}'
            ]
        else:
            endpoints_to_try = [
                '/v3/namespaces',
                '/v1/namespaces',
                '/k8s/clusters/local/v1/namespaces'
            ]
        
        # Try each endpoint
        for endpoint in endpoints_to_try:
            try:
                data = self.get(endpoint)
                # Handle different response formats
                if isinstance(data, dict):
                    if 'data' in data:
                        namespaces = data['data']
                    elif 'items' in data:
                        namespaces = data['items']
                    else:
                        namespaces = [data]
                elif isinstance(data, list):
                    namespaces = data
                else:
                    namespaces = []
                
                if namespaces:
                    all_namespaces.extend(namespaces)
                    break  # Success, stop trying other endpoints
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    continue  # Try next endpoint
                else:
                    raise  # Re-raise other HTTP errors
            except Exception:
                continue  # Try next endpoint
        
        # If still no namespaces and no project/cluster specified, 
        # try getting namespaces from all projects
        if not all_namespaces and not project_id and not cluster_id:
            try:
                projects = self.list_projects()
                for project in projects:
                    try:
                        proj_id = project.get('id')
                        if proj_id:
                            # Try to get namespaces for this project
                            try:
                                ns_data = self.get(f'/v3/projects/{proj_id}/namespaces')
                                if isinstance(ns_data, dict) and 'data' in ns_data:
                                    all_namespaces.extend(ns_data['data'])
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                pass
        
        return all_namespaces
    
    def get_project_info(self, project_id):
        """Get project information by project ID.
        
        Args:
            project_id: Project ID
            
        Returns:
            dict: Project information
        """
        return self.get(f'/v3/projects/{project_id}')
    
    def generate_kubeconfig(self, cluster_id, flatten=False):
        """Generate kubeconfig for a cluster.
        
        Args:
            cluster_id: Cluster ID
            flatten: Whether to flatten the kubeconfig (default: False)
            
        Returns:
            str: Kubeconfig content
        """
        endpoint = f'/v3/clusters/{cluster_id}?action=generateKubeconfig'
        
        if flatten:
            # Try to get flattened kubeconfig
            # Some Rancher versions support ?flatten=true parameter
            endpoint = f'/v3/clusters/{cluster_id}?action=generateKubeconfig&flatten=true'
        
        try:
            # POST request to generate kubeconfig
            response = self._request_raw('POST', endpoint)
            data = response.json()
            
            # Kubeconfig is usually in data.config or data field
            kubeconfig = data.get('config') or data.get('data', {}).get('config') or data.get('data')
            
            if isinstance(kubeconfig, dict):
                # If it's a dict, try to extract YAML or convert to string
                import yaml
                kubeconfig = yaml.dump(kubeconfig, default_flow_style=False)
            elif not isinstance(kubeconfig, str):
                # If it's not a string, try to convert
                kubeconfig = str(kubeconfig)
            
            return kubeconfig
        except Exception as e:
            # Try alternative endpoint
            try:
                endpoint_alt = f'/v3/clusters/{cluster_id}/generateKubeconfig'
                response = self._request_raw('POST', endpoint_alt)
                data = response.json()
                kubeconfig = data.get('config') or data.get('data', {}).get('config') or data.get('data')
                
                if isinstance(kubeconfig, dict):
                    import yaml
                    kubeconfig = yaml.dump(kubeconfig, default_flow_style=False)
                elif not isinstance(kubeconfig, str):
                    kubeconfig = str(kubeconfig)
                
                return kubeconfig
            except Exception:
                raise ValueError(f"Failed to generate kubeconfig: {str(e)}")
    
    def get_kubeconfig_from_project(self, project_id, flatten=False):
        """Get kubeconfig from project ID.
        
        Args:
            project_id: Project ID (can be in format "cluster-id:project-id" or just "project-id")
            flatten: Whether to flatten the kubeconfig (default: False)
            
        Returns:
            str: Kubeconfig content
        """
        # Handle project ID format: "cluster-id:project-id" or just "project-id"
        if ':' in project_id:
            parts = project_id.split(':', 1)
            cluster_id = parts[0]
            project_id_actual = parts[1]
            
            # Use cluster_id directly if provided
            return self.generate_kubeconfig(cluster_id, flatten=flatten)
        else:
            # Get project info to find cluster ID
            project_info = self.get_project_info(project_id)
            cluster_id = project_info.get('clusterId')
            
            if not cluster_id:
                raise ValueError(f"Project {project_id} does not have a cluster ID")
            
            # Generate kubeconfig from cluster
            return self.generate_kubeconfig(cluster_id, flatten=flatten)
    
    def validate_token(self):
        """Validate token and check if it's expired.
        
        Returns:
            dict: Validation result with 'valid', 'expired', 'expires_at', 'error', 'user_id', 'username', 'name' keys
        """
        result = {
            'valid': False,
            'expired': False,
            'expires_at': None,
            'error': None,
            'user_id': None,
            'username': None,
            'name': None
        }
        
        # Try multiple endpoints to validate token
        validation_endpoints = [
            '/v3/users/me',
            '/v3/clusters',
            '/v3/settings',
            '/v3/projects',
            '/v3/nodes'
        ]
        
        token_validated = False
        
        # Try to validate token using various endpoints
        for endpoint in validation_endpoints:
            try:
                self.get(endpoint)
                # If successful, token is valid
                result['valid'] = True
                token_validated = True
                break
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 401:
                    result['error'] = 'Token is invalid or expired'
                    result['expired'] = True
                    return result
                elif e.response.status_code == 403:
                    result['error'] = 'Token is invalid or expired'
                    result['expired'] = True
                    return result
                elif e.response.status_code == 404:
                    # Endpoint not found, try next endpoint
                    continue
                else:
                    # Other HTTP error, try next endpoint
                    continue
            except Exception:
                # Other error, try next endpoint
                continue
        
        # If no endpoint worked but we didn't get 401/403, token might be invalid
        if not token_validated:
            result['error'] = 'Unable to validate token - all endpoints returned errors'
            return result
        
        # Token is valid, now try to get expiry information and user details
        # Method 1: Try to get token info from API
        try:
            # Extract token ID from current token (first part before colon if exists)
            token_id = self.token.split(':')[0] if ':' in self.token else self.token
            
            # Try to get token details
            token_info = self.get(f'/v3/tokens/{token_id}')
            
            # Check expiry
            expires_at = token_info.get('expiresAt') or token_info.get('expiration')
            if expires_at:
                from datetime import datetime
                try:
                    # Parse ISO format datetime
                    exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    now = datetime.now(exp_time.tzinfo)
                    result['expires_at'] = expires_at
                    result['expired'] = exp_time < now
                except Exception:
                    pass
            
            # Get user information
            user_id = token_info.get('userId')
            if user_id:
                result['user_id'] = user_id
                try:
                    user_info = self.get(f'/v3/users/{user_id}')
                    if isinstance(user_info, dict):
                        result['username'] = user_info.get('username')
                        result['name'] = user_info.get('name')
                except Exception:
                    pass
        except Exception:
            # Method 2: Try to decode JWT if it's a JWT token
            try:
                import base64
                import json
                
                # JWT tokens have 3 parts separated by dots
                if '.' in self.token:
                    parts = self.token.split('.')
                    if len(parts) >= 2:
                        # Decode payload (second part)
                        payload = parts[1]
                        # Add padding if needed
                        payload += '=' * (4 - len(payload) % 4)
                        decoded = base64.urlsafe_b64decode(payload)
                        jwt_data = json.loads(decoded)
                        
                        # Check exp claim
                        if 'exp' in jwt_data:
                            from datetime import datetime
                            exp_timestamp = jwt_data['exp']
                            exp_time = datetime.fromtimestamp(exp_timestamp)
                            now = datetime.now()
                            result['expires_at'] = exp_time.isoformat()
                            result['expired'] = exp_time < now
            except Exception:
                pass
        
        return result
