"""Tests for Lcore cookie handling."""

import unittest

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, request, response


class TestSetCookie(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_set_simple_cookie(self):
        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('name', 'lusan')
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/set')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('name=lusan', set_cookie)

    def test_set_cookie_with_path(self):
        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('token', 'abc', path='/api')
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/set')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('Path=/api', set_cookie)

    def test_set_cookie_httponly(self):
        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('session', 'xyz', httponly=True)
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/set')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('httponly', set_cookie.lower())

    def test_set_cookie_secure(self):
        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('session', 'xyz', secure=True)
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/set')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('Secure', set_cookie)


class TestReadCookie(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_read_cookie(self):
        @self.app.route('/read')
        def read_cookie():
            return request.get_cookie('name', 'missing')

        _, _, body = run_request(self.app, 'GET', '/read',
                                 headers={'Cookie': 'name=lusan'})
        self.assertEqual(body, b'lusan')

    def test_missing_cookie(self):
        @self.app.route('/read')
        def read_cookie():
            return request.get_cookie('nonexistent', 'fallback')

        _, _, body = run_request(self.app, 'GET', '/read')
        self.assertEqual(body, b'fallback')


class TestSignedCookie(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()
        self.secret = 'my-secret-key-123'

    def test_signed_cookie_roundtrip(self):
        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('auth', 'user123', secret=self.secret)
            return 'ok'

        @self.app.route('/get')
        def get_cookie():
            val = request.get_cookie('auth', secret=self.secret)
            return val or 'none'

        # Set the cookie
        _, headers, _ = run_request(self.app, 'GET', '/set')
        cookie_header = headers.get('Set-Cookie', '')
        # Extract cookie value
        cookie_val = cookie_header.split(';')[0]  # "auth=..."

        # Read it back
        _, _, body = run_request(self.app, 'GET', '/get',
                                 headers={'Cookie': cookie_val})
        self.assertEqual(body, b'user123')

    def test_tampered_signed_cookie(self):
        @self.app.route('/get')
        def get_cookie():
            val = request.get_cookie('auth', secret=self.secret)
            return val or 'invalid'

        _, _, body = run_request(self.app, 'GET', '/get',
                                 headers={'Cookie': 'auth=tampered-value'})
        self.assertEqual(body, b'invalid')


class TestDeleteCookie(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_delete_cookie(self):
        @self.app.route('/delete')
        def delete():
            response.delete_cookie('session')
            return 'deleted'

        _, headers, _ = run_request(self.app, 'GET', '/delete')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('session=', set_cookie)
        self.assertIn('Max-Age', set_cookie)


if __name__ == '__main__':
    unittest.main()
