"""Tests for Lcore routing system."""

import unittest
from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, HTTPError


class TestBasicRouting(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_simple_route(self):
        @self.app.route('/hello')
        def hello():
            return 'Hello World'

        status, headers, body = run_request(self.app, 'GET', '/hello')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'Hello World')

    def test_root_route(self):
        @self.app.route('/')
        def index():
            return 'Index'

        status, _, body = run_request(self.app, 'GET', '/')
        self.assertEqual(body, b'Index')

    def test_404_on_missing_route(self):
        @self.app.route('/exists')
        def exists():
            return 'yes'

        status, _, body = run_request(self.app, 'GET', '/not-here')
        self.assertIn('404', status)

    def test_multiple_routes(self):
        @self.app.route('/one')
        def one():
            return 'one'

        @self.app.route('/two')
        def two():
            return 'two'

        _, _, body1 = run_request(self.app, 'GET', '/one')
        _, _, body2 = run_request(self.app, 'GET', '/two')
        self.assertEqual(body1, b'one')
        self.assertEqual(body2, b'two')


class TestHTTPMethods(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_get_method(self):
        @self.app.get('/data')
        def get_data():
            return 'get-data'

        status, _, body = run_request(self.app, 'GET', '/data')
        self.assertEqual(body, b'get-data')

    def test_post_method(self):
        @self.app.post('/data')
        def post_data():
            return 'posted'

        status, _, body = run_request(self.app, 'POST', '/data')
        self.assertEqual(body, b'posted')

    def test_put_method(self):
        @self.app.put('/data')
        def put_data():
            return 'put'

        status, _, body = run_request(self.app, 'PUT', '/data')
        self.assertEqual(body, b'put')

    def test_delete_method(self):
        @self.app.delete('/data')
        def delete_data():
            return 'deleted'

        status, _, body = run_request(self.app, 'DELETE', '/data')
        self.assertEqual(body, b'deleted')

    def test_patch_method(self):
        @self.app.patch('/data')
        def patch_data():
            return 'patched'

        status, _, body = run_request(self.app, 'PATCH', '/data')
        self.assertEqual(body, b'patched')

    def test_method_not_allowed(self):
        @self.app.get('/only-get')
        def only_get():
            return 'ok'

        status, _, _ = run_request(self.app, 'POST', '/only-get')
        self.assertIn('405', status)


class TestDynamicRoutes(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_string_parameter(self):
        @self.app.route('/user/<name>')
        def user(name):
            return f'Hello {name}'

        _, _, body = run_request(self.app, 'GET', '/user/lusan')
        self.assertEqual(body, b'Hello lusan')

    def test_int_filter(self):
        @self.app.route('/item/<id:int>')
        def item(id):
            return f'Item {id} type {type(id).__name__}'

        _, _, body = run_request(self.app, 'GET', '/item/42')
        self.assertEqual(body, b'Item 42 type int')

    def test_int_filter_rejects_non_int(self):
        @self.app.route('/item/<id:int>')
        def item(id):
            return f'Item {id}'

        status, _, _ = run_request(self.app, 'GET', '/item/abc')
        self.assertIn('404', status)

    def test_float_filter(self):
        @self.app.route('/price/<amount:float>')
        def price(amount):
            return f'{amount:.2f}'

        _, _, body = run_request(self.app, 'GET', '/price/9.99')
        self.assertEqual(body, b'9.99')

    def test_path_filter(self):
        @self.app.route('/files/<filepath:path>')
        def files(filepath):
            return filepath

        _, _, body = run_request(self.app, 'GET', '/files/docs/readme.md')
        self.assertEqual(body, b'docs/readme.md')

    def test_multiple_params(self):
        @self.app.route('/api/<version>/<resource>/<id:int>')
        def api(version, resource, id):
            return f'{version}/{resource}/{id}'

        _, _, body = run_request(self.app, 'GET', '/api/v1/users/5')
        self.assertEqual(body, b'v1/users/5')


class TestURLBuilding(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_get_url(self):
        @self.app.route('/user/<name>', name='user_profile')
        def user(name):
            return name

        url = self.app.get_url('user_profile', name='lusan')
        self.assertEqual(url, '/user/lusan')


if __name__ == '__main__':
    unittest.main()
