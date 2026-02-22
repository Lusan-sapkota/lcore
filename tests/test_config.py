"""Tests for Lcore configuration system."""

import unittest
import os
import tempfile

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import ConfigDict


class TestConfigDictBasic(unittest.TestCase):
    def test_set_and_get(self):
        config = ConfigDict()
        config['key'] = 'value'
        self.assertEqual(config['key'], 'value')

    def test_missing_key(self):
        config = ConfigDict()
        with self.assertRaises(KeyError):
            _ = config['missing']

    def test_get_default(self):
        config = ConfigDict()
        self.assertEqual(config.get('missing', 'default'), 'default')

    def test_contains(self):
        config = ConfigDict()
        config['exists'] = True
        self.assertIn('exists', config)
        self.assertNotIn('missing', config)

    def test_delete(self):
        config = ConfigDict()
        config['key'] = 'value'
        del config['key']
        self.assertNotIn('key', config)

    def test_update(self):
        config = ConfigDict()
        config.update({'a': 1, 'b': 2})
        self.assertEqual(config['a'], 1)
        self.assertEqual(config['b'], 2)


class TestConfigDictNamespace(unittest.TestCase):
    def test_dot_namespace(self):
        config = ConfigDict()
        config['db.host'] = 'localhost'
        config['db.port'] = 5432
        self.assertEqual(config['db.host'], 'localhost')
        self.assertEqual(config['db.port'], 5432)


class TestConfigDictLoadDict(unittest.TestCase):
    def test_load_flat_dict(self):
        config = ConfigDict()
        config.load_dict({'debug': True, 'port': 8080})
        self.assertEqual(config['debug'], True)
        self.assertEqual(config['port'], 8080)

    def test_load_nested_dict(self):
        config = ConfigDict()
        config.load_dict({
            'database': {
                'host': 'localhost',
                'port': 5432
            }
        })
        self.assertEqual(config['database.host'], 'localhost')
        self.assertEqual(config['database.port'], 5432)


class TestConfigDictLoadINI(unittest.TestCase):
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(mode='w', suffix='.ini',
                                                    delete=False)
        self.tmpfile.write("""[lcore]
debug = true
port = 8080

[database]
host = localhost
port = 5432
""")
        self.tmpfile.close()

    def tearDown(self):
        os.unlink(self.tmpfile.name)

    def test_load_config_file(self):
        config = ConfigDict()
        config.load_config(self.tmpfile.name)
        self.assertEqual(config['debug'], 'true')
        self.assertEqual(config['port'], '8080')
        self.assertEqual(config['database.host'], 'localhost')
        self.assertEqual(config['database.port'], '5432')


class TestConfigDictChangeListener(unittest.TestCase):
    def test_change_listener(self):
        config = ConfigDict()
        changes = []

        def on_change(conf, key, value):
            changes.append((key, value))

        config._change_listener.append(on_change)
        config['key'] = 'first'
        config['key'] = 'second'

        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0], ('key', 'first'))
        self.assertEqual(changes[1], ('key', 'second'))


class TestAppConfig(unittest.TestCase):
    def test_app_has_config(self):
        from lcore import Lcore
        app = Lcore()
        self.assertIsInstance(app.config, ConfigDict)

    def test_app_config_set_get(self):
        from lcore import Lcore
        app = Lcore()
        app.config['my.setting'] = 'hello'
        self.assertEqual(app.config['my.setting'], 'hello')


if __name__ == '__main__':
    unittest.main()
