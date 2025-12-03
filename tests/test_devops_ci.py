import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.devops_ci import DevOpsCIBuilder

class TestDevOpsCIBuilder(unittest.TestCase):
    def setUp(self):
        self.builder = DevOpsCIBuilder('repo', 'refs')

    @patch('plugins.devops_ci.DevOpsCIBuilder.run_command')
    def test_build_docker_image(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        
        metadata = {'image_name': 'test:tag'}
        config = {}
        
        # Mock _setup_builder to return True
        with patch.object(self.builder, '_setup_builder', return_value=True):
            with patch.object(self.builder, 'build_dir', '/tmp/build'):
                success = self.builder._build_docker_image(metadata, config)
                self.assertTrue(success)

    def test_parse_custom_image(self):
        commit_info = {'short_hash': 'abc', 'ref_type': 'branch'}
        
        # Case 1: Explicit tag
        self.assertEqual(self.builder._parse_custom_image('img:tag', commit_info), 'img:tag')
        
        # Case 2: No tag, adds hash
        self.builder.config['docker']['namespace'] = 'ns'
        self.assertEqual(self.builder._parse_custom_image('img', commit_info), 'ns/img:abc')

    @patch('plugins.devops_ci.DevOpsCIBuilder.load_auth')
    @patch('plugins.devops_ci.DevOpsCIBuilder._fetch_build_metadata_local')
    @patch('plugins.devops_ci.DevOpsCIBuilder._fetch_build_config_local')
    @patch('plugins.devops_ci.DevOpsCIBuilder._clone_repository')
    @patch('plugins.devops_ci.DevOpsCIBuilder._build_docker_image')
    @patch('plugins.devops_ci.DevOpsCIBuilder._push_docker_image')
    @patch('plugins.devops_ci.DevOpsCIBuilder.check_image_exists')
    def test_build_api_mode_success(self, mock_check_exists, mock_push, mock_build, mock_clone, mock_config, mock_meta, mock_auth):
        mock_auth.return_value = True
        self.builder.auth_data = {'GIT_USER': 'test', 'GIT_PASSWORD': 'pwd'}
        mock_meta.return_value = {'image_name': 'test:tag'}
        mock_check_exists.return_value = {'exists': False}
        mock_config.return_value = {}
        mock_clone.return_value = True
        mock_build.return_value = True
        mock_push.return_value = True
        
        exit_code = self.builder._build_api_mode()
        self.assertEqual(exit_code, 0)

if __name__ == '__main__':
    unittest.main()
