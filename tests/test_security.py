"""Tests for Lcore secure defaults."""

import unittest
import json as json_mod
import re
import sys
import os
import warnings
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import create_environ, run_request
from lcore import (Lcore, Request, SecurityHeadersMiddleware, CSRFMiddleware,
                   ProxyFixMiddleware, rate_limit, validate_request)


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

    def test_token_accepted_in_form_field(self):
        """The form fallback is what every non-AJAX HTML form relies on."""
        app = self._make_app()
        _, get_headers, _ = run_request(app, 'GET', '/form')
        set_cookie = get_headers.get('Set-Cookie', '')
        signed = self._extract_csrf_cookie(set_cookie)
        token = self._extract_csrf_token(set_cookie)

        status, _, body = run_request(
            app, 'POST', '/form',
            body=('_csrf_token=%s' % token).encode(),
            headers={'Cookie': '_csrf_token=%s' % signed},
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'submitted')

    def test_custom_form_field_is_used(self):
        """A renamed form_field is the one actually read."""
        app = Lcore()
        app.use(CSRFMiddleware(secret='fixed', form_field='authenticity_token'))

        @app.route('/form', method=['GET', 'POST'])
        def form():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/form')
        set_cookie = headers.get('Set-Cookie', '')
        signed = self._extract_csrf_cookie(set_cookie)
        token = self._extract_csrf_token(set_cookie)

        # The default field name must no longer work.
        status, _, _ = run_request(
            app, 'POST', '/form',
            body=('_csrf_token=%s' % token).encode(),
            headers={'Cookie': '_csrf_token=%s' % signed},
            content_type='application/x-www-form-urlencoded')
        self.assertIn('403', status)

        status, _, _ = run_request(
            app, 'POST', '/form',
            body=('authenticity_token=%s' % token).encode(),
            headers={'Cookie': '_csrf_token=%s' % signed},
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(status, '200 OK')

    def test_custom_cookie_name_is_used(self):
        """A renamed cookie_name is the one written and read."""
        app = Lcore()
        app.use(CSRFMiddleware(secret='fixed', cookie_name='xsrf'))

        @app.route('/form')
        def form():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/form')
        self.assertIn('xsrf=', headers.get('Set-Cookie', ''))
        self.assertNotIn('_csrf_token=', headers.get('Set-Cookie', ''))

    def test_secure_flag_is_applied(self):
        """secure=True marks the CSRF cookie HTTPS-only."""
        app = Lcore()
        app.use(CSRFMiddleware(secret='fixed', secure=True))

        @app.route('/form')
        def form():
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/form')
        self.assertIn('secure', headers.get('Set-Cookie', '').lower())

    def test_custom_safe_methods_are_honoured(self):
        """Narrowing safe_methods makes a previously exempt method validated."""
        app = Lcore()
        app.use(CSRFMiddleware(secret='fixed', safe_methods=('GET',)))

        @app.route('/thing', method=['GET', 'OPTIONS'])
        def thing():
            return 'ok'

        self.assertEqual(run_request(app, 'GET', '/thing')[0], '200 OK')
        # OPTIONS is no longer in safe_methods, so it now needs a token.
        self.assertIn('403', run_request(app, 'OPTIONS', '/thing')[0])

    def test_missing_secret_warns(self):
        """Omitting secret= warns: each worker process would sign with its own
        random secret, so tokens fail verification across workers."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            CSRFMiddleware()
        messages = [str(w.message) for w in caught
                    if issubclass(w.category, UserWarning)]
        self.assertTrue(messages, 'A UserWarning should be raised')
        self.assertIn('secret', messages[0])

    def test_explicit_secret_does_not_warn(self):
        """Passing an explicit secret= raises no warning."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            CSRFMiddleware(secret='fixed-secret')
        self.assertEqual(
            [w for w in caught if issubclass(w.category, UserWarning)], [])


# ---------------------------------------------------------------------------
# ProxyFixMiddleware
# ---------------------------------------------------------------------------

class TestProxyFixMiddleware(unittest.TestCase):
    """Tests for the two X-Forwarded-* trust modes."""

    def _resolve(self, middleware, remote_addr, forwarded_for=None):
        """Return request.remote_addr as resolved for the given environ."""
        app = Lcore()
        app.use(middleware)
        headers = {'X-Forwarded-For': forwarded_for} if forwarded_for else None
        environ = create_environ('GET', '/', headers=headers)
        environ['REMOTE_ADDR'] = remote_addr
        app._handle(environ)
        return Request(environ).remote_addr

    def test_num_proxies_trusts_hop_count(self):
        """num_proxies=N trusts the last N X-Forwarded-For entries regardless
        of the connecting peer's IP."""
        addr = self._resolve(ProxyFixMiddleware(num_proxies=1),
                             remote_addr='203.0.113.9',
                             forwarded_for='9.9.9.9')
        self.assertEqual(addr, '9.9.9.9')

    def test_num_proxies_two_hops(self):
        """num_proxies=2 skips two proxy hops to find the client."""
        addr = self._resolve(ProxyFixMiddleware(num_proxies=2),
                             remote_addr='203.0.113.9',
                             forwarded_for='9.9.9.9, 10.0.0.7')
        self.assertEqual(addr, '9.9.9.9')

    def test_num_proxies_short_chain_falls_back(self):
        """A chain shorter than num_proxies falls back to REMOTE_ADDR rather
        than trusting a forged header."""
        addr = self._resolve(ProxyFixMiddleware(num_proxies=3),
                             remote_addr='203.0.113.9',
                             forwarded_for='9.9.9.9')
        self.assertEqual(addr, '203.0.113.9')

    def test_trusted_proxies_allowlist(self):
        """trusted_proxies=[...] resolves the client behind a known proxy."""
        addr = self._resolve(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']),
                             remote_addr='10.0.0.1',
                             forwarded_for='9.9.9.9, 6.6.6.6')
        self.assertEqual(addr, '6.6.6.6')

    def test_untrusted_peer_cannot_spoof(self):
        """A peer that is not a trusted proxy cannot spoof its address via
        X-Forwarded-For."""
        addr = self._resolve(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']),
                             remote_addr='6.6.6.6',
                             forwarded_for='9.9.9.9, 10.0.0.1')
        self.assertEqual(addr, '6.6.6.6')

    def test_forwarded_proto_trusted_by_hop_count(self):
        """Hop-count mode also trusts X-Forwarded-Proto for request.urlparts."""
        app = Lcore()
        app.use(ProxyFixMiddleware(num_proxies=1))
        environ = create_environ('GET', '/', headers={
            'X-Forwarded-For': '9.9.9.9',
            'X-Forwarded-Proto': 'https',
        })
        environ['REMOTE_ADDR'] = '203.0.113.9'
        app._handle(environ)
        self.assertEqual(Request(environ).urlparts.scheme, 'https')


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
