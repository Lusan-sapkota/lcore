"""Tests for Lcore secure defaults."""

import unittest
import json as json_mod
import re
import sys
import os
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import create_environ, run_request
from lcore import (Lcore, SecurityHeadersMiddleware, CSRFMiddleware,
                   rate_limit, validate_request)


def _run_environ(app, environ):
    """Execute a WSGI request with a pre-built environ dict."""
    status_holder = {}
    headers_holder = {}

    def start_response(status, response_headers, exc_info=None):
        status_holder['status'] = status
        headers_holder['headers'] = dict(response_headers)

    body_chunks = app(environ, start_response)
    response_body = b''.join(body_chunks)
    if hasattr(body_chunks, 'close'):
        body_chunks.close()
    return status_holder['status'], headers_holder['headers'], response_body


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware(unittest.TestCase):
    """Tests for the SecurityHeadersMiddleware."""

    def test_default_headers_are_added(self):
        """SecurityHeadersMiddleware adds all four default security headers."""
        app = Lcore()
        app.use(SecurityHeadersMiddleware())

        @app.route('/test')
        def handler():
            return 'ok'

        status, headers, body = run_request(app, 'GET', '/test')
        self.assertEqual(status, '200 OK')
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertEqual(headers.get('X-Frame-Options'), 'SAMEORIGIN')
        self.assertEqual(headers.get('X-Xss-Protection'), '1; mode=block')
        self.assertEqual(headers.get('Referrer-Policy'),
                         'strict-origin-when-cross-origin')

    def test_hsts_enabled(self):
        """SecurityHeadersMiddleware includes Strict-Transport-Security when
        hsts=True."""
        app = Lcore()
        app.use(SecurityHeadersMiddleware(hsts=True))

        @app.route('/test')
        def handler():
            return 'ok'

        status, headers, body = run_request(app, 'GET', '/test')
        self.assertEqual(status, '200 OK')
        sts = headers.get('Strict-Transport-Security', '')
        self.assertIn('max-age=31536000', sts)
        self.assertIn('includeSubDomains', sts)

    def test_hsts_custom_max_age(self):
        """SecurityHeadersMiddleware respects a custom hsts_max_age value."""
        app = Lcore()
        app.use(SecurityHeadersMiddleware(hsts=True, hsts_max_age=86400))

        @app.route('/test')
        def handler():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/test')
        sts = headers.get('Strict-Transport-Security', '')
        self.assertIn('max-age=86400', sts)

    def test_hsts_disabled_by_default(self):
        """HSTS header is absent when hsts is not explicitly enabled."""
        app = Lcore()
        app.use(SecurityHeadersMiddleware())

        @app.route('/test')
        def handler():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/test')
        self.assertNotIn('Strict-Transport-Security', headers)

    def test_custom_overrides(self):
        """SecurityHeadersMiddleware allows overriding default header values
        and adding new headers via keyword arguments."""
        app = Lcore()
        app.use(SecurityHeadersMiddleware(**{
            'X-Frame-Options': 'DENY',
            'X-Custom-Header': 'custom-value',
        }))

        @app.route('/test')
        def handler():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/test')
        # Overridden default
        self.assertEqual(headers.get('X-Frame-Options'), 'DENY')
        # Additional custom header
        self.assertEqual(headers.get('X-Custom-Header'), 'custom-value')
        # Other defaults still present
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')


# ---------------------------------------------------------------------------
# CSRFMiddleware
# ---------------------------------------------------------------------------

class TestCSRFMiddleware(unittest.TestCase):
    """Tests for the CSRFMiddleware."""

    def _make_app(self):
        app = Lcore()
        app.use(CSRFMiddleware())

        @app.route('/form', method='GET')
        def get_form():
            return 'form'

        @app.route('/form', method='POST')
        def post_form():
            return 'submitted'

        return app

    @staticmethod
    def _extract_csrf_cookie(set_cookie_header):
        """Extract the full signed _csrf_token cookie value."""
        match = re.search(r'_csrf_token=([a-f0-9]+\.[a-f0-9]+)', set_cookie_header)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_csrf_token(set_cookie_header):
        """Extract the unsigned token part from a signed _csrf_token cookie."""
        match = re.search(r'_csrf_token=([a-f0-9]+)\.[a-f0-9]+', set_cookie_header)
        if match:
            return match.group(1)
        return None

    def test_get_request_allowed(self):
        """GET requests are safe and pass through the CSRF middleware."""
        app = self._make_app()
        status, headers, body = run_request(app, 'GET', '/form')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'form')

    def test_get_sets_csrf_cookie(self):
        """A GET request sets a signed _csrf_token cookie when none exists."""
        app = self._make_app()
        _, headers, _ = run_request(app, 'GET', '/form')
        set_cookie = headers.get('Set-Cookie', '')
        self.assertIn('_csrf_token=', set_cookie)
        # Verify the cookie contains a signed token (token.signature format)
        signed = self._extract_csrf_cookie(set_cookie)
        self.assertIsNotNone(signed, 'Cookie should contain signed token')

    def test_post_without_token_returns_403(self):
        """POST without a CSRF token is rejected with 403."""
        app = self._make_app()
        status, headers, body = run_request(app, 'POST', '/form')
        self.assertIn('403', status)

    def test_post_with_valid_token_succeeds(self):
        """POST with a valid CSRF token (matching signed cookie) succeeds."""
        app = self._make_app()

        # Step 1: GET to obtain the CSRF cookie
        _, get_headers, _ = run_request(app, 'GET', '/form')
        set_cookie = get_headers.get('Set-Cookie', '')
        signed_cookie = self._extract_csrf_cookie(set_cookie)
        token = self._extract_csrf_token(set_cookie)
        self.assertIsNotNone(signed_cookie, 'Signed CSRF cookie should be set')
        self.assertIsNotNone(token, 'CSRF token should be extractable')

        # Step 2: POST with the signed cookie and the unsigned token in header
        status, _, body = run_request(
            app, 'POST', '/form',
            headers={
                'Cookie': '_csrf_token=%s' % signed_cookie,
                'X-CSRF-Token': token,
            },
        )
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'submitted')

    def test_post_with_wrong_token_returns_403(self):
        """POST with a mismatched CSRF token is rejected with 403."""
        app = self._make_app()

        # GET to obtain the real cookie
        _, get_headers, _ = run_request(app, 'GET', '/form')
        set_cookie = get_headers.get('Set-Cookie', '')
        signed_cookie = self._extract_csrf_cookie(set_cookie)
        self.assertIsNotNone(signed_cookie)

        # POST with the correct signed cookie but a wrong token in the header
        status, _, _ = run_request(
            app, 'POST', '/form',
            headers={
                'Cookie': '_csrf_token=%s' % signed_cookie,
                'X-CSRF-Token': 'wrong_token_value',
            },
        )
        self.assertIn('403', status)

    def test_head_and_options_are_safe(self):
        """HEAD and OPTIONS requests pass through without a CSRF token."""
        app = Lcore()
        app.use(CSRFMiddleware())

        @app.route('/safe', method=['GET', 'HEAD', 'OPTIONS'])
        def safe_handler():
            return 'ok'

        for method in ('HEAD', 'OPTIONS'):
            status, _, _ = run_request(app, method, '/safe')
            self.assertIn('200', status,
                          '%s should be a safe method' % method)


# ---------------------------------------------------------------------------
# rate_limit
# ---------------------------------------------------------------------------

class TestRateLimit(unittest.TestCase):
    """Tests for the rate_limit decorator."""

    def test_allows_requests_under_limit(self):
        """Requests within the rate limit succeed with 200."""
        app = Lcore()

        @app.route('/limited')
        @rate_limit(3, per=60)
        def limited():
            return 'ok'

        for i in range(3):
            status, _, body = run_request(
                app, 'GET', '/limited',
                headers={'X-Forwarded-For': '10.0.0.1'},
            )
            self.assertEqual(status, '200 OK',
                             'Request %d should succeed' % (i + 1))
            self.assertEqual(body, b'ok')

    def test_returns_429_when_exceeded(self):
        """Exceeding the rate limit returns a 429 status."""
        app = Lcore()

        @app.route('/limited')
        @rate_limit(2, per=60)
        def limited():
            return 'ok'

        # Use up the allowed quota
        for _ in range(2):
            status, _, _ = run_request(
                app, 'GET', '/limited',
                headers={'X-Forwarded-For': '10.0.0.2'},
            )
            self.assertEqual(status, '200 OK')

        # Third request should be rate-limited
        status, _, body = run_request(
            app, 'GET', '/limited',
            headers={'X-Forwarded-For': '10.0.0.2'},
        )
        self.assertIn('429', status)

    def test_separate_buckets_per_client(self):
        """Different remote addresses have independent rate-limit buckets."""
        app = Lcore()

        @app.route('/limited')
        @rate_limit(1, per=60)
        def limited():
            return 'ok'

        # Client A uses its single token (use REMOTE_ADDR for safe IP source)
        environ_a = create_environ('GET', '/limited')
        environ_a['REMOTE_ADDR'] = '10.0.0.10'
        status, _, _ = _run_environ(app, environ_a)
        self.assertEqual(status, '200 OK')

        # Client B should still have its own token available
        environ_b = create_environ('GET', '/limited')
        environ_b['REMOTE_ADDR'] = '10.0.0.11'
        status, _, _ = _run_environ(app, environ_b)
        self.assertEqual(status, '200 OK')


# ---------------------------------------------------------------------------
# validate_request
# ---------------------------------------------------------------------------

@dataclass
class CreateItem:
    name: str
    price: float


@dataclass
class SearchQuery:
    q: str
    page: int


class TestValidateRequest(unittest.TestCase):
    """Tests for the validate_request decorator."""

    def test_valid_body_passes(self):
        """A POST with all required fields succeeds."""
        app = Lcore()

        @app.route('/items', method='POST')
        @validate_request(body=CreateItem)
        def create_item():
            return 'created'

        payload = json_mod.dumps({'name': 'Widget', 'price': 9.99}).encode()
        status, _, body = run_request(
            app, 'POST', '/items',
            body=payload,
            content_type='application/json',
        )
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'created')

    def test_missing_body_field_returns_422(self):
        """A POST missing a required field returns 422."""
        app = Lcore()

        @app.route('/items', method='POST')
        @validate_request(body=CreateItem)
        def create_item():
            return 'created'

        # Missing 'price'
        payload = json_mod.dumps({'name': 'Widget'}).encode()
        status, _, body = run_request(
            app, 'POST', '/items',
            body=payload,
            content_type='application/json',
        )
        self.assertIn('422', status)

    def test_wrong_body_field_type_returns_422(self):
        """A POST with a field of the wrong type returns 422."""
        app = Lcore()

        @app.route('/items', method='POST')
        @validate_request(body=CreateItem)
        def create_item():
            return 'created'

        # 'price' should be float, not string
        payload = json_mod.dumps({'name': 'Widget', 'price': 'free'}).encode()
        status, _, body = run_request(
            app, 'POST', '/items',
            body=payload,
            content_type='application/json',
        )
        self.assertIn('422', status)

    def test_missing_query_param_returns_400(self):
        """A request missing a required query parameter returns 400."""
        app = Lcore()

        @app.route('/search')
        @validate_request(query=SearchQuery)
        def search():
            return 'results'

        # Missing both 'q' and 'page'
        status, _, body = run_request(app, 'GET', '/search')
        self.assertIn('400', status)

    def test_partial_query_params_returns_400(self):
        """A request with only some required query params returns 400."""
        app = Lcore()

        @app.route('/search')
        @validate_request(query=SearchQuery)
        def search():
            return 'results'

        # Only 'q', missing 'page'
        status, _, _ = run_request(
            app, 'GET', '/search',
            query_string='q=hello',
        )
        self.assertIn('400', status)

    def test_valid_query_params_pass(self):
        """A request with all required query parameters succeeds."""
        app = Lcore()

        @app.route('/search')
        @validate_request(query=SearchQuery)
        def search():
            return 'results'

        status, _, body = run_request(
            app, 'GET', '/search',
            query_string='q=hello&page=1',
        )
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'results')

    def test_valid_body_and_query_together(self):
        """Both body and query validation pass when all fields are present."""
        app = Lcore()

        @dataclass
        class Filter:
            category: str

        @app.route('/items', method='POST')
        @validate_request(body=CreateItem, query=Filter)
        def create_item():
            return 'ok'

        payload = json_mod.dumps({'name': 'Gadget', 'price': 19.99}).encode()
        status, _, body = run_request(
            app, 'POST', '/items',
            body=payload,
            content_type='application/json',
            query_string='category=electronics',
        )
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'ok')


if __name__ == '__main__':
    unittest.main()
