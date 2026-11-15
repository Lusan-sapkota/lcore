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


def test_accept_json_gets_json_errors():
    from lcore import Lcore, TestClient, abort
    app = Lcore()

    @app.get('/e')
    def e(): abort(400, 'bad field x')

    @app.get('/boom')
    def boom(): 1 / 0

    c, h = TestClient(app), {'Accept': 'application/json'}
    for path, code, msg in (('/e', 400, 'bad field x'), ('/nope', 404, None), ('/boom', 500, None)):
        r = c.get(path, headers=h)
        assert r.status_code == code and r.headers['Content-Type'] == 'application/json'
        assert r.json['status'] == code and (msg is None or r.json['error'] == msg)
    assert c.get('/e', headers={'Accept': 'text/html,application/json'}).headers['Content-Type'].startswith('text/html')


def test_client_cookie_jar_and_repeated_headers():
    from lcore import Lcore, TestClient, request, response
    app = Lcore()

    @app.get('/login')
    def login():
        response.set_cookie('a', '1'); response.set_cookie('b', '2')
        return 'ok'

    @app.get('/me')
    def me(): return request.get_cookie('a', '') + request.get_cookie('b', '')

    c = TestClient(app)
    assert len(c.get('/login').get_all('Set-Cookie')) == 2
    assert c.get('/me').text == '12'
    assert TestClient(app, cookies=False).get('/me').text == ''


def test_rate_limit_single_process_is_silent():
    import warnings
    from lcore import rate_limit
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        rate_limit(5, single_process=True)


def test_validate_request_returns_json_fields_and_rejects_empty_body():
    from lcore import Lcore, TestClient, validate_request, request
    app = Lcore()

    @app.post('/u')
    @validate_request(body={'name': str, 'age': int})
    def u(): return request.json

    c = TestClient(app)
    r = c.post('/u', json={'name': 'x', 'age': 'z'})
    assert r.status_code == 422 and r.json['fields'] == {'age': 'age must be int'}
    r = c.post('/u', body=b'', content_type='application/json')
    assert r.status_code == 422 and set(r.json['fields']) == {'name', 'age'}
    assert c.post('/u', json={'name': ' x ', 'age': '3'}).json == {'name': 'x', 'age': 3}


def test_query_types_json_or_redirects_and_dev_server_guard():
    import pytest
    from lcore import Lcore, TestClient, validate_request, request, redirect, run
    app = Lcore()

    @app.get('/q')
    @validate_request(query={'n': int})
    def q(): return 'ok'

    @app.post('/j')
    def j(): return {'v': request.json_or({'d': 1})}

    @app.get('/go')
    def go(): redirect('/q?n=1')

    c = TestClient(app)
    r = c.get('/q', query_string='n=abc')
    assert r.status_code == 400 and r.json['fields'] == {'n': 'n must be int'}
    assert c.post('/j', body=b'', content_type='application/json').json == {'v': {'d': 1}}
    assert c.get('/go').status_code in (302, 303)
    assert TestClient(app, follow_redirects=True).get('/go').text == 'ok'
    with pytest.raises(RuntimeError, match='development server'):
        run(app, host='0.0.0.0')
