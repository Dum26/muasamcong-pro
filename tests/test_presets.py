import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_app import PresetStore


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'saved_queries.json'
        self.store = PresetStore(self.path)
        self.params = {'mode': 'Thông báo mời thầu', 'keyword': 'thuốc',
                       'use_dates': False, 'detail': True, 'fast_mode': False,
                       'remove_duplicates': False, 'pages': 20}

    def save(self, name='Thuốc'):
        return self.store.update({'action': 'save', 'name': name, 'params': self.params})

    def test_restart_preserves_query_and_same_name_updates(self):
        original = self.save()[0]
        self.assertEqual(PresetStore(self.path).read()[0]['params'], self.params)
        self.params['pages'] = 50
        updated = self.save('THUỐC')
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]['id'], original['id'])
        self.assertEqual(updated[0]['params']['pages'], 50)
        self.assertEqual(self.store.update({'action': 'delete', 'id': original['id']}), [])

    def test_failed_atomic_write_preserves_original(self):
        self.save()
        original = self.path.read_bytes()
        with patch('web_app.os.replace', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                self.save('Khác')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_corrupt_file_is_not_overwritten(self):
        self.path.write_text('{corrupt', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.save()
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{corrupt')

    def test_limit_and_invalid_mode(self):
        for index in range(30):
            self.save(str(index))
        with self.assertRaises(ValueError):
            self.save('Extra')
        self.assertEqual(len(json.loads(self.path.read_text(encoding='utf-8'))), 30)
        self.params['mode'] = 'Invalid'
        with self.assertRaises(ValueError):
            self.save()


if __name__ == '__main__':
    unittest.main()
