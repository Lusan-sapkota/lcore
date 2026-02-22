"""Tests for Lcore error handling."""

import unittest

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, abort, redirect, HTTPError, HTTPResponse


class TestAbort(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_abort_404(self):
        @self.app.route('/find')
        def find():
            abort(404, 'Not found here')

        status, _, body = run_request(self.app, 'GET', '/find')
        self.assertIn('404', status)

    def test_abort_403(self):
        @self.app.route('/secret')
        def secret():
            abort(403, 'Forbidden')

        status, _, _ = run_request(self.app, 'GET', '/secret')
        self.assertIn('403', status)

    def test_abort_500(self):
        @self.app.route('/crash')
        def crash():
            abort(500, 'Server error')

        status, _, _ = run_request(self.app, 'GET', '/crash')
        self.assertIn('500', status)


class TestRedirect(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_redirect_302(self):
        @self.app.route('/old')
        def old():
            redirect('/new')

        status, headers, _ = run_request(self.app, 'GET', '/old')
        self.assertIn('30', status)
        self.assertIn('/new', headers.get('Location', ''))

    def test_redirect_301(self):
        @self.app.route('/moved')
        def moved():
            redirect('/permanent', 301)

        status, headers, _ = run_request(self.app, 'GET', '/moved')
        self.assertIn('301', status)
        self.assertIn('/permanent', headers.get('Location', ''))


class TestCustomErrorHandler(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_custom_404_handler(self):
        @self.app.error(404)
        def error404(err):
            return 'Custom 404: Page not found'

        status, _, body = run_request(self.app, 'GET', '/nonexistent')
        self.assertIn('404', status)
        self.assertEqual(body, b'Custom 404: Page not found')

    def test_custom_500_handler(self):
        app = Lcore(catchall=True)

        @app.error(500)
        def error500(err):
            return 'Oops, server broke'

        @app.route('/fail')
        def fail():
            raise Exception('unhandled')

        status, _, body = run_request(app, 'GET', '/fail')
        self.assertIn('500', status)
        self.assertEqual(body, b'Oops, server broke')


class TestExceptionHandling(unittest.TestCase):
    def setUp(self):
        self.app = Lcore(catchall=True)

    def test_unhandled_exception_returns_500(self):
        @self.app.route('/error')
        def error():
            raise ValueError('something went wrong')

        status, _, body = run_request(self.app, 'GET', '/error')
        self.assertIn('500', status)
        self.assertTrue(len(body) > 0)

    def test_http_error_preserves_status(self):
        @self.app.route('/forbidden')
        def forbidden():
            raise HTTPError(403, 'No access')

        status, _, _ = run_request(self.app, 'GET', '/forbidden')
        self.assertIn('403', status)


if __name__ == '__main__':
    unittest.main()
