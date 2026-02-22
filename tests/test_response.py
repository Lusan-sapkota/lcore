"""Tests for Lcore response handling."""

import unittest
import json

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, response, HTTPResponse, HTTPError, BaseResponse


class TestStatusCodes(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_default_200(self):
        @self.app.route('/ok')
        def ok():
            return 'OK'

        status, _, _ = run_request(self.app, 'GET', '/ok')
        self.assertEqual(status, '200 OK')

    def test_custom_status(self):
        @self.app.route('/created')
        def created():
            response.status = 201
            return 'Created'

        status, _, body = run_request(self.app, 'GET', '/created')
        self.assertIn('201', status)
        self.assertEqual(body, b'Created')

    def test_404_error(self):
        status, _, _ = run_request(self.app, 'GET', '/nonexistent')
        self.assertIn('404', status)


class TestResponseHeaders(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_set_header(self):
        @self.app.route('/custom')
        def custom():
            response.set_header('X-Custom', 'test-value')
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/custom')
        self.assertEqual(headers.get('X-Custom'), 'test-value')

    def test_content_type_header(self):
        @self.app.route('/json')
        def json_route():
            response.content_type = 'application/json'
            return '{"key": "value"}'

        _, headers, _ = run_request(self.app, 'GET', '/json')
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_add_header(self):
        @self.app.route('/multi')
        def multi():
            response.add_header('X-Multi', 'one')
            response.add_header('X-Multi', 'two')
            return 'ok'

        status, _, _ = run_request(self.app, 'GET', '/multi')
        self.assertIn('200', status)


class TestJSONResponse(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_dict_auto_json(self):
        @self.app.route('/api')
        def api():
            return {'name': 'lusan', 'framework': 'lcore'}

        _, headers, body = run_request(self.app, 'GET', '/api')
        data = json.loads(body)
        self.assertEqual(data['name'], 'lusan')
        self.assertEqual(data['framework'], 'lcore')
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_nested_dict(self):
        @self.app.route('/nested')
        def nested():
            return {'user': {'name': 'lusan', 'age': 25}, 'status': 'ok'}

        _, _, body = run_request(self.app, 'GET', '/nested')
        data = json.loads(body)
        self.assertEqual(data['user']['name'], 'lusan')


class TestHTTPResponse(unittest.TestCase):
    def test_http_response_exception(self):
        app = Lcore()

        @app.route('/redirect')
        def redir():
            raise HTTPResponse('', status=302, **{'Location': '/new'})

        status, headers, _ = run_request(app, 'GET', '/redirect')
        self.assertIn('302', status)

    def test_http_error(self):
        app = Lcore()

        @app.route('/fail')
        def fail():
            raise HTTPError(500, 'Something broke')

        status, _, body = run_request(app, 'GET', '/fail')
        self.assertIn('500', status)


class TestBaseResponse(unittest.TestCase):
    def test_status_code(self):
        r = BaseResponse()
        r.status = 404
        self.assertEqual(r.status_code, 404)
        self.assertIn('Not Found', r.status_line)

    def test_status_string(self):
        r = BaseResponse()
        r.status = '201 Created'
        self.assertEqual(r.status_code, 201)

    def test_body_assignment(self):
        r = BaseResponse()
        r.body = 'Hello'
        self.assertEqual(r.body, 'Hello')

    def test_charset(self):
        r = BaseResponse()
        r.content_type = 'text/html; charset=utf-8'
        self.assertEqual(r.charset, 'utf-8')


if __name__ == '__main__':
    unittest.main()
