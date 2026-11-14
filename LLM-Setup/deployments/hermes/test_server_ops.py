import unittest
from unittest.mock import patch
import broker

class ServerOpsTests(unittest.TestCase):
    def test_refuses_secret_fetch_and_shell(self):
        with patch.object(broker, 'audit'):
            for body in ({'action': 'read_secret', 'name': 'amd-gpu-ssh'}, {'action': 'shell', 'command': 'id'}, {'action': 'status', 'command': 'id'}, {'action': 'catalog', 'path': '/run/secrets'}):
                with self.assertRaises(PermissionError):broker.server_ops(body)

    def test_diagnostics_cannot_select_command(self):
        with patch.object(broker, 'audit'), patch.object(broker, 'host_check') as host:
            for body in ({'action': 'diagnostics', 'target': 'amd-gpu', 'check': 'shell'}, {'action': 'diagnostics', 'target': 'external', 'check': 'gpu'}):
                with self.assertRaises(ValueError):broker.server_ops(body)
            host.assert_not_called()

    def test_homelab_only_fixed_read(self):
        with patch.object(broker, 'audit'), patch.object(broker, 'host_check', return_value={'checked': True}) as host:
            self.assertEqual(broker.server_ops({'action': 'homelab'}), {'checked': True})
            host.assert_called_once_with('/homelab-read', {})
            with self.assertRaises(PermissionError):broker.server_ops({'action': 'homelab', 'operation': 'apply'})

if __name__ == '__main__':unittest.main()
