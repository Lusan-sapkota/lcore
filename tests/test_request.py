"""Tests for Lcore request handling."""

import unittest
import json

from helpers import create_environ, run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, request, BaseRequest


class TestQueryParameters(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_single_query_param(self):
        @self.app.route('/search')
        def search():
            return request.query.get('q', '')

        _, _, body = run_request(self.app, 'GET', '/search', query_string='q=hello')
        self.assertEqual(body, b'hello')

    def test_multiple_query_params(self):
        @self.app.route('/search')
        def search():
            q = request.query.get('q', '')
            page = request.query.get('page', '1')
            return f'{q}:{page}'

        _, _, body = run_request(self.app, 'GET', '/search', query_string='q=test&page=3')
        self.assertEqual(body, b'test:3')

    def test_missing_query_param(self):
        @self.app.route('/search')
        def search():
            return request.query.get('missing', 'default')

        _, _, body = run_request(self.app, 'GET', '/search')
        self.assertEqual(body, b'default')


class TestRequestHeaders(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_read_custom_header(self):
        @self.app.route('/headers')
        def headers():
            return request.get_header('X-Custom', 'none')

        _, _, body = run_request(self.app, 'GET', '/headers',
                                 headers={'X-Custom': 'myvalue'})
        self.assertEqual(body, b'myvalue')

    def test_content_type(self):
        @self.app.route('/ct')
        def ct():
            return request.content_type or 'none'

        _, _, body = run_request(self.app, 'GET', '/ct',
                                 content_type='application/json')
        self.assertEqual(body, b'application/json')

    def test_host_header(self):
        @self.app.route('/host')
        def host():
            return request.get_header('Host', '')

        _, _, body = run_request(self.app, 'GET', '/host')
        self.assertEqual(body, b'localhost:8080')


class TestRequestMethod(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_method_property(self):
        @self.app.route('/method', method=['GET', 'POST'])
        def method():
            return request.method

        _, _, body_get = run_request(self.app, 'GET', '/method')
        self.assertEqual(body_get, b'GET')

        _, _, body_post = run_request(self.app, 'POST', '/method')
        self.assertEqual(body_post, b'POST')


class TestRequestPath(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_path_property(self):
        @self.app.route('/some/path')
        def path():
            return request.path

        _, _, body = run_request(self.app, 'GET', '/some/path')
        self.assertEqual(body, b'/some/path')

    def test_url_property(self):
        @self.app.route('/page')
        def page():
            return request.url

        _, _, body = run_request(self.app, 'GET', '/page')
        self.assertIn(b'http://localhost:8080/page', body)


class TestJSONBody(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_json_body_parsing(self):
        @self.app.post('/api')
        def api():
            data = request.json
            return f"name={data['name']}"

        payload = json.dumps({'name': 'lusan'}).encode()
        _, _, body = run_request(self.app, 'POST', '/api', body=payload,
                                 content_type='application/json')
        self.assertEqual(body, b'name=lusan')

    def test_json_none_without_content_type(self):
        @self.app.post('/api')
        def api():
            data = request.json
            return 'none' if data is None else 'has-data'

        _, _, body = run_request(self.app, 'POST', '/api', body=b'{}')
        self.assertEqual(body, b'none')


class TestFormData(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_urlencoded_form(self):
        @self.app.post('/login')
        def login():
            return f"user={request.forms.get('username')}"

        body = b'username=lusan&password=secret'
        _, _, resp = run_request(self.app, 'POST', '/login', body=body,
                                 content_type='application/x-www-form-urlencoded')
        self.assertEqual(resp, b'user=lusan')


class TestRequestEnviron(unittest.TestCase):
    def test_environ_access(self):
        env = create_environ('GET', '/test', query_string='a=1')
        req = BaseRequest(env)
        self.assertEqual(req.method, 'GET')
        self.assertEqual(req.path, '/test')
        self.assertEqual(req.query_string, 'a=1')

    def test_content_length(self):
        body = b'hello world'
        env = create_environ('POST', '/data', body=body)
        req = BaseRequest(env)
        self.assertEqual(req.content_length, len(body))


if __name__ == '__main__':
    unittest.main()
