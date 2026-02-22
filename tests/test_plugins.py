"""Tests for Lcore plugin system."""

import unittest
import json

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore


class SimplePlugin:
    """A minimal test plugin that adds a header to every response."""
    name = 'simple'
    api = 2

    def __init__(self, header_name='X-Plugin', header_value='active'):
        self.header_name = header_name
        self.header_value = header_value

    def setup(self, app):
        self.app = app

    def apply(self, callback, route):
        header_name = self.header_name
        header_value = self.header_value

        def wrapper(*args, **kwargs):
            from lcore import response
            response.set_header(header_name, header_value)
            return callback(*args, **kwargs)
        return wrapper

    def close(self):
        pass


class TimingPlugin:
    """Plugin that tracks how many times routes are called."""
    name = 'timing'
    api = 2

    def __init__(self):
        self.call_count = 0

    def setup(self, app):
        pass

    def apply(self, callback, route):
        plugin = self

        def wrapper(*args, **kwargs):
            plugin.call_count += 1
            return callback(*args, **kwargs)
        return wrapper


class TestPluginInstall(unittest.TestCase):
    def test_install_plugin(self):
        app = Lcore()
        plugin = SimplePlugin()
        app.install(plugin)
        self.assertIn(plugin, app.plugins)

    def test_uninstall_plugin(self):
        app = Lcore()
        plugin = SimplePlugin()
        app.install(plugin)
        app.uninstall(plugin)
        self.assertNotIn(plugin, app.plugins)

    def test_uninstall_by_name(self):
        app = Lcore()
        plugin = SimplePlugin()
        app.install(plugin)
        app.uninstall('simple')
        self.assertNotIn(plugin, app.plugins)


class TestPluginApply(unittest.TestCase):
    def test_plugin_modifies_response(self):
        app = Lcore()
        app.install(SimplePlugin('X-Custom', 'hello'))

        @app.route('/test')
        def test():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/test')
        self.assertEqual(headers.get('X-Custom'), 'hello')

    def test_plugin_counts_calls(self):
        app = Lcore()
        counter = TimingPlugin()
        app.install(counter)

        @app.route('/count')
        def count():
            return 'ok'

        run_request(app, 'GET', '/count')
        run_request(app, 'GET', '/count')
        run_request(app, 'GET', '/count')
        self.assertEqual(counter.call_count, 3)


class TestBuiltinJSONPlugin(unittest.TestCase):
    def test_dict_returns_json(self):
        app = Lcore()

        @app.route('/api')
        def api():
            return {'status': 'ok', 'count': 42}

        _, headers, body = run_request(app, 'GET', '/api')
        data = json.loads(body)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['count'], 42)
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_non_dict_not_jsonified(self):
        app = Lcore()

        @app.route('/text')
        def text():
            return 'plain text'

        _, headers, body = run_request(app, 'GET', '/text')
        self.assertEqual(body, b'plain text')


class TestRouteSpecificPluginSkip(unittest.TestCase):
    def test_skip_plugin_on_route(self):
        app = Lcore()
        plugin = SimplePlugin('X-Skipped', 'should-not-appear')
        app.install(plugin)

        @app.route('/skip', skip=[plugin])
        def skip():
            return 'no plugin'

        _, headers, _ = run_request(app, 'GET', '/skip')
        self.assertNotIn('X-Skipped', headers)


if __name__ == '__main__':
    unittest.main()
