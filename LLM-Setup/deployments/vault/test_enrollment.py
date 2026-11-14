import json
import unittest
from unittest.mock import patch
import enrollment as e
from vault_common import VaultError

class EnrollmentTests(unittest.TestCase):
    def test_rotation_preserves_metadata_and_uses_cas(self):
        existing = {'value': 'old-test-value', 'service_metadata': {'purpose': 'example'}}
        with patch.object(e, 'current', return_value=(existing, 7)), patch.object(e, 'api') as api:
            e.save('example', 'test-token', secret='new-test-value')
        self.assertEqual(api.call_args.args[1], {'options': {'cas': 7}, 'data': {'value': 'new-test-value', 'service_metadata': {'purpose': 'example'}}})

    def test_catalog_drops_unknown_and_secret_fields(self):
        with patch.object(e, 'api', return_value={'data': {'keys': ['example']}}), patch.object(e, 'current', return_value=({'value': 'sentinel-private-value', 'refresh_token': 'another-private-value', 'service_metadata': {'purpose': 'testing', 'password': 'hidden'}}, 1)):
            output = json.dumps(e.directory('test-token'))
        for value in ('sentinel-private-value', 'another-private-value', 'hidden', 'refresh_token'):
            self.assertNotIn(value, output)
        self.assertIn('connector setup required', output)

    def test_no_credential_or_query_in_endpoint(self):
        meta = dict(service='Example', purpose='Testing', username='operator', auth_type='password')
        for endpoint in ('https://user:secret@example.com', 'https://example.com/?token=secret', 'https://example.com/#secret'):
            with self.assertRaises(VaultError):
                e.validate_metadata(dict(meta, endpoint=endpoint))

    def test_non_404_never_becomes_new_secret(self):
        with patch.object(e, 'api', side_effect=VaultError('Denied', status=403)):
            with self.assertRaises(VaultError):
                e.current('example', 'test-token')

    def test_paths_and_noninteractive_enrollment_refused(self):
        for name in ('../root', 'example/other', 'Example', ''):
            with self.assertRaises(VaultError):e.valid_name(name)
        with patch.object(e.sys.stdin, 'isatty', return_value=False), patch.object(e, 'api') as api:
            with self.assertRaises(VaultError):e.enroll('example', 'test-token')
            api.assert_not_called()

if __name__ == '__main__':unittest.main()
