"""Tests for Lcore app mounting and merging."""

import unittest

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore


class TestAppMounting(unittest.TestCase):
    def test_mount_sub_app(self):
        main_app = Lcore()
        sub_app = Lcore()

        @sub_app.route('/hello')
        def hello():
            return 'Hello from sub app'

        main_app.mount('/sub', sub_app)

        status, _, body = run_request(main_app, 'GET', '/sub/hello')
        self.assertIn('200', status)
        self.assertEqual(body, b'Hello from sub app')

    def test_mount_preserves_main_routes(self):
        main_app = Lcore()
        sub_app = Lcore()

        @main_app.route('/main')
        def main():
            return 'main'

        @sub_app.route('/sub')
        def sub():
            return 'sub'

        main_app.mount('/api', sub_app)

        _, _, body = run_request(main_app, 'GET', '/main')
        self.assertEqual(body, b'main')

    def test_mount_multiple_sub_apps(self):
        main_app = Lcore()
        api_v1 = Lcore()
        api_v2 = Lcore()

        @api_v1.route('/users')
        def users_v1():
            return 'v1-users'

        @api_v2.route('/users')
        def users_v2():
            return 'v2-users'

        main_app.mount('/api/v1', api_v1)
        main_app.mount('/api/v2', api_v2)

        _, _, body1 = run_request(main_app, 'GET', '/api/v1/users')
        _, _, body2 = run_request(main_app, 'GET', '/api/v2/users')
        self.assertEqual(body1, b'v1-users')
        self.assertEqual(body2, b'v2-users')


class TestAppMerge(unittest.TestCase):
    def test_merge_routes(self):
        app1 = Lcore()
        app2 = Lcore()

        @app2.route('/merged')
        def merged():
            return 'from merged'

        app1.merge(app2)

        _, _, body = run_request(app1, 'GET', '/merged')
        self.assertEqual(body, b'from merged')


if __name__ == '__main__':
    unittest.main()
