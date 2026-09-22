"""Tests for TimeoutMiddleware.

It runs the handler in a thread pool, but request, response and ctx are
thread-locals bound in the serving thread. Before the context was carried
across, any handler that touched request died with "Request context not
initialized" and returned 500. It had no tests at all, so nothing caught it.
"""

import re
import os
import sys
import time
import unittest
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import (Lcore, TimeoutMiddleware, SessionMiddleware,
                   MemorySessionBackend, HTTPError, request, response, ctx,
                   redirect)


def _shutdown_timeout_pools(app):
    """Test-only cleanup: a TimeoutMiddleware's ThreadPoolExecutor is
    normally released via atexit, which leaves it (and its worker threads)
    alive for the rest of the test run otherwise -- every test in this file
    builds its own app and its own TimeoutMiddleware, so that adds up fast.
    """
    for mw, _pattern in app.middleware._middleware:
        if isinstance(mw, TimeoutMiddleware) and mw._pool is not None:
            mw._pool.shutdown(wait=False)


class TestTimeoutMiddlewareContext(unittest.TestCase):
    """The request context must survive the hop into the worker thread."""

    def setUp(self):
        self.app = Lcore()
        self.app.use(TimeoutMiddleware(timeout=10))

    def tearDown(self):
        _shutdown_timeout_pools(self.app)

    def test_handler_can_read_request(self):
        """The original bug: request access raised inside the pool thread."""
        @self.app.route('/r')
        def handler():
            return '%s %s' % (request.method, request.path)

        status, _, body = run_request(self.app, 'GET', '/r')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'GET /r')

    def test_handler_can_read_query_and_headers(self):
        """Anything derived from environ must work too."""
        @self.app.route('/q')
        def handler():
            return '%s|%s' % (request.query.get('a'),
                              request.get_header('X-Test'))

        _, _, body = run_request(self.app, 'GET', '/q', query_string='a=1',
                                 headers={'X-Test': 'hi'})
        self.assertEqual(body, b'1|hi')

    def test_response_headers_propagate(self):
        """Headers set in the worker must reach the real response."""
        @self.app.route('/h')
        def handler():
            response.set_header('X-Custom', 'yes')
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/h')
        self.assertEqual(headers.get('X-Custom'), 'yes')

    def test_response_status_propagates(self):
        """A status set in the worker must not be lost."""
        @self.app.route('/s')
        def handler():
            response.status = 201
            return 'made'

        status, _, _ = run_request(self.app, 'GET', '/s')
        self.assertTrue(status.startswith('201'), status)

    def test_cookies_propagate(self):
        """Cookies live on the response object, which is also thread-local."""
        @self.app.route('/c')
        def handler():
            response.set_cookie('a', 'b')
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/c')
        self.assertIn('a=b', headers.get('Set-Cookie', ''))

    def test_redirect_carries_cookies_set_before_it(self):
        """A handler ending in redirect() still carries the cookie it set.

        Note: JSONPlugin (auto-installed) catches HTTPResponse -- which
        redirect() raises -- around the route callback and returns it as a
        normal value, so next_handler(ctx) does not actually raise here; see
        test_response_carried_back_even_if_handler_raises for a case where it
        genuinely does.
        """
        @self.app.route('/rd')
        def handler():
            response.set_cookie('flash', 'saved')
            redirect('/elsewhere')

        status, headers, _ = run_request(self.app, 'GET', '/rd')
        self.assertTrue(status.startswith('303') or status.startswith('302'))
        self.assertIn('flash=saved', headers.get('Set-Cookie', ''))

    def test_response_carried_back_even_if_handler_raises(self):
        """A plain exception (not caught by JSONPlugin, unlike HTTPResponse)
        genuinely propagates through the worker's try/finally, so this is
        what actually exercises response carry-back on the raising path: a
        header set before the crash is not silently lost, and the crash
        still surfaces as 500.
        """
        app = Lcore(catchall=True)
        app.use(TimeoutMiddleware(timeout=10))

        @app.route('/boom')
        def handler():
            response.set_header('X-Before-Crash', 'yes')
            raise RuntimeError('handler exploded')

        try:
            status, headers, _ = run_request(app, 'GET', '/boom')
            self.assertTrue(status.startswith('500'), status)
            self.assertEqual(headers.get('X-Before-Crash'), 'yes')
        finally:
            _shutdown_timeout_pools(app)

    def test_ctx_state_is_shared_not_copied(self):
        """ctx.state must be the same dict, so writes reach the serving thread."""
        seen = {}

        @self.app.route('/ctx')
        def handler():
            ctx.state['from_handler'] = True
            seen['state_id'] = id(ctx.state)
            return 'ok'

        @self.app.hook('on_response_build')
        def after():
            seen['visible_to_serving_thread'] = ctx.state.get('from_handler')
            seen['same_dict'] = ctx.state is not None and id(ctx.state) == seen.get('state_id')

        run_request(self.app, 'GET', '/ctx')
        self.assertTrue(seen['visible_to_serving_thread'])
        self.assertTrue(seen['same_dict'], 'ctx.state must be the identical '
                        'dict object, not a copy, in the serving thread')

    def test_ctx_user_route_request_id_carried_back(self):
        """user/route/request_id are RequestContext __slots__, not part of
        the shared state/_lazy dicts, so they only cross the thread boundary
        via TimeoutMiddleware's explicit carry-back after the worker finishes.
        """
        seen = {}

        @self.app.route('/who')
        def handler():
            ctx.user = 'alice'
            return 'ok'

        @self.app.hook('after_request')
        def after():
            seen['user'] = ctx.user
            seen['route'] = ctx.route

        run_request(self.app, 'GET', '/who')
        self.assertEqual(seen['user'], 'alice')
        self.assertIsNotNone(seen['route'])

    def test_http_error_from_handler_is_preserved(self):
        """An HTTPError raised in the worker keeps its status."""
        @self.app.route('/boom')
        def handler():
            raise HTTPError(418, "I'm a teapot")

        status, _, _ = run_request(self.app, 'GET', '/boom')
        self.assertTrue(status.startswith('418'), status)


class TestTimeoutMiddlewareBehaviour(unittest.TestCase):
    """The timeout itself still has to work."""

    def test_slow_handler_returns_503(self):
        app = Lcore()
        app.use(TimeoutMiddleware(timeout=1))

        @app.route('/slow')
        def handler():
            time.sleep(3)
            return 'never'

        try:
            started = time.time()
            status, _, _ = run_request(app, 'GET', '/slow')
            elapsed = time.time() - started
            self.assertTrue(status.startswith('503'), status)
            self.assertLess(elapsed, 2.5, 'should have given up at the limit')
        finally:
            _shutdown_timeout_pools(app)

    def test_fast_handler_is_untouched(self):
        app = Lcore()
        app.use(TimeoutMiddleware(timeout=10))

        @app.route('/fast')
        def handler():
            return 'quick'

        try:
            status, _, body = run_request(app, 'GET', '/fast')
            self.assertEqual(status, '200 OK')
            self.assertEqual(body, b'quick')
        finally:
            _shutdown_timeout_pools(app)

    def test_custom_timeout_value_is_used(self):
        """The limit reported to the client reflects the configured value."""
        app = Lcore()
        app.use(TimeoutMiddleware(timeout=1))

        @app.route('/slow')
        def handler():
            time.sleep(2)
            return 'never'

        try:
            _, _, body = run_request(app, 'GET', '/slow')
            # The exact message text, not just b'1': the 503 error page's own
            # markup/CSS incidentally contains digit '1' (e.g. "1px solid"), so
            # a bare assertIn(b'1', body) would pass for any configured timeout.
            self.assertIn(b'limit: 1s', body)
        finally:
            _shutdown_timeout_pools(app)


class TestTimeoutWithSessions(unittest.TestCase):
    """Session middleware runs inside the worker, since timeout sorts earlier."""

    def setUp(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.backend = MemorySessionBackend(warn=False)
            self.app = Lcore()
            self.app.use(TimeoutMiddleware(timeout=10))
            self.app.use(SessionMiddleware(backend=self.backend, secret='s'))

        @self.app.route('/set')
        def set_value():
            request.session['cart'] = 'sku-1'
            return 'ok'

        @self.app.route('/get')
        def get_value():
            return str(request.session.get('cart', 'none'))

    def tearDown(self):
        _shutdown_timeout_pools(self.app)

    def test_session_round_trips_through_the_worker(self):
        _, headers, _ = run_request(self.app, 'GET', '/set')
        match = re.search(r'lcore_session=([^;]*)', headers.get('Set-Cookie', ''))
        self.assertIsNotNone(match, 'session cookie should have been set')
        _, _, body = run_request(self.app, 'GET', '/get',
                                 headers={'Cookie': 'lcore_session=%s'
                                          % match.group(1)})
        self.assertEqual(body, b'sku-1')

    def test_ctx_session_and_request_session_agree(self):
        @self.app.route('/same')
        def same():
            return str(ctx.session is request.session)

        _, _, body = run_request(self.app, 'GET', '/same')
        self.assertEqual(body, b'True')


if __name__ == '__main__':
    unittest.main()
