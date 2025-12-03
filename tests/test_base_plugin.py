import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.base import BasePlugin

class TestBasePlugin(unittest.TestCase):
    def setUp(self):
        self.plugin = BasePlugin('test-plugin')

    @patch('plugins.base.load_json_config')
    def test_load_config(self, mock_load_json):
        mock_load_json.return_value = {'foo': 'bar'}
        with patch.object(Path, 'exists', return_value=True):
            config = self.plugin._load_config()
            self.assertEqual(config['foo'], 'bar')

    @patch('plugins.base.load_auth_file')
    def test_load_auth(self, mock_load_auth):
        mock_load_auth.return_value = {'user': 'test'}
        self.assertTrue(self.plugin.load_auth())
        self.assertEqual(self.plugin.auth_data['user'], 'test')

    @patch('subprocess.run')
    def test_run_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='ok')
        result = self.plugin.run_command(['echo', 'hello'])
        self.assertEqual(result.stdout, 'ok')

    @patch('plugins.base.send_teams_notification')
    def test_send_notification(self, mock_send):
        self.plugin.send_notification('Title', [], True, 'http://webhook')
        mock_send.assert_called_once()

if __name__ == '__main__':
    unittest.main()
