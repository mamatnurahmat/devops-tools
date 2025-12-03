import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.k8s_deployer import K8sDeployer

class TestK8sDeployer(unittest.TestCase):
    def setUp(self):
        self.deployer = K8sDeployer('repo', 'refs')

    @patch('plugins.k8s_deployer.K8sDeployer.fetch_bitbucket_file')
    def test_fetch_cicd_config(self, mock_fetch):
        mock_fetch.return_value = '{"PROJECT": "test"}'
        config = self.deployer.fetch_cicd_config()
        self.assertEqual(config['PROJECT'], 'test')

    def test_determine_namespace(self):
        config = {'PROJECT': 'test', 'DEPLOYMENT': 'dep'}
        ns, dep = self.deployer.determine_namespace(config)
        self.assertEqual(ns, 'refs-test')
        self.assertEqual(dep, 'dep')

    @patch('plugins.base.BasePlugin.run_command')
    def test_check_image_ready(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"ready": true}')
        info = self.deployer.check_image_ready()
        self.assertTrue(info['ready'])

    @patch('plugins.base.BasePlugin.run_command')
    def test_deploy_success(self, mock_run):
        # Mocking the sequence of calls
        # 1. check_image_ready -> doq image
        # 2. get_current_image -> doq get-image
        # 3. switch_context -> doq ns
        # 4. set_image -> doq set-image
        
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='{"ready": true}'), # check_image_ready
            MagicMock(returncode=0, stdout='{"containers": [{"image": "old"}]}'), # get_current_image
            MagicMock(returncode=0), # switch_context
            MagicMock(returncode=0)  # set_image
        ]
        
        with patch.object(self.deployer, 'load_auth', return_value=True), \
             patch.object(self.deployer, 'fetch_cicd_config', return_value={'PROJECT': 'p', 'DEPLOYMENT': 'd', 'IMAGE': 'i'}), \
             patch.object(self.deployer, 'get_commit_hash', return_value={'short_hash': 'abc', 'ref_type': 'branch'}):
            
            exit_code = self.deployer.deploy()
            self.assertEqual(exit_code, 0)
            self.assertTrue(self.deployer.result['success'])

if __name__ == '__main__':
    unittest.main()
