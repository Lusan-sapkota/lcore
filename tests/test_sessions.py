"""Tests for server-side sessions."""

import unittest
import os
import re
import sys
import shutil
import tempfile
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import (Lcore, SessionMiddleware, SessionBackend,
                   MemorySessionBackend, SQLiteSessionBackend,
                   redirect, request)

SECRET = 'session-test-secret'


def _cookie(headers, name='lcore_session'):
    """Extract a cookie value from a Set-Cookie header."""
    match = re.search(r'%s=([^;]*)' % name, headers.get('Set-Cookie', ''))
    return match.group(1) if match else None


def _as(cookie, name='lcore_session'):
    """Build request headers carrying a session cookie."""
    return {'Cookie': '%s=%s' % (name, cookie)}


class SessionAppMixin:
    """Builds an app exercising the session API. Subclasses pick a backend."""

    def make_backend(self):
        raise NotImplementedError

    def setUp(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.backend = self.make_backend()
        self.app = self._build(self.backend)

    def _build(self, backend, **options):
        app = Lcore()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app.use(SessionMiddleware(backend=backend, secret=SECRET, **options))

        @app.route('/read')
        def read():
            return 'value=%s' % request.session.get('key', 'unset')

        @app.route('/write')
        def write():
            request.session['key'] = 'written'
            return 'ok'

        @app.route('/login/<uid>')
        def login(uid):
            request.session['cart'] = 'sku-1'
            request.session.bind_user(uid)
            return request.session.sid

        @app.route('/login-redirect/<uid>')
        def login_redirect(uid):
            request.session['cart'] = 'sku-9'
            request.session.bind_user(uid)
            redirect('/whoami')

        @app.route('/whoami')
        def whoami():
            session = request.session
            return '%s|%s' % (session.user_id, session.get('cart', ''))

        @app.route('/logout')
        def logout():
            request.session.destroy()
            return 'bye'

        @app.route('/devices')
        def devices():
            return str(len(request.session.list_sessions()))

        @app.route('/revoke-others')
        def revoke_others():
            return str(request.session.revoke_other_sessions())

        return app

    # -- basics ------------------------------------------------------------

    def test_read_only_request_sets_no_cookie(self):
        """Anonymous browsing must not create a session or set a cookie."""
        _, headers, body = run_request(self.app, 'GET', '/read')
        self.assertEqual(body, b'value=unset')
        self.assertIsNone(_cookie(headers))

    def test_write_persists_across_requests(self):
        """A written session survives into the next request."""
        _, headers, _ = run_request(self.app, 'GET', '/write')
        cookie = _cookie(headers)
        self.assertIsNotNone(cookie)
        _, _, body = run_request(self.app, 'GET', '/read', headers=_as(cookie))
        self.assertEqual(body, b'value=written')

    def test_cookie_is_signed(self):
        """A tampered or unsigned cookie is rejected, not trusted."""
        _, _, body = run_request(self.app, 'GET', '/read',
                                 headers=_as('not-a-real-signed-value'))
        self.assertEqual(body, b'value=unset')

    def test_cookie_defaults_are_hardened(self):
        """The session cookie is HttpOnly and SameSite by default, and carries
        no Domain attribute when none was configured."""
        _, headers, _ = run_request(self.app, 'GET', '/write')
        raw = headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', raw)
        self.assertIn('samesite=lax', raw.lower())
        self.assertNotIn('domain=none', raw.lower())

    # -- login / logout ----------------------------------------------------

    def test_bind_user_regenerates_sid(self):
        """Login must issue a new session id. Reusing it is session fixation."""
        _, headers, _ = run_request(self.app, 'GET', '/write')
        cookie = _cookie(headers)
        _, _, before = run_request(self.app, 'GET', '/read', headers=_as(cookie))

        _, login_headers, new_sid = run_request(self.app, 'GET', '/login/user-1',
                                                headers=_as(cookie))
        # The pre-login cookie must no longer resolve to a session.
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None|')
        # The post-login cookie does.
        _, _, body = run_request(self.app, 'GET', '/whoami',
                                 headers=_as(_cookie(login_headers)))
        self.assertEqual(body, b'user-1|sku-1')

    def test_cookie_survives_redirect(self):
        """A login that ends in redirect() still saves and sets its cookie.

        Note: JSONPlugin (auto-installed) catches HTTPResponse -- which
        redirect() raises -- around the route callback and returns it as a
        normal value, so this exercises the *value* SessionMiddleware.
        _persist() ends up with on a redirect, not its try/finally against a
        propagating exception; see test_persist_runs_even_if_handler_raises
        for that.
        """
        status, headers, _ = run_request(self.app, 'GET', '/login-redirect/user-7')
        self.assertTrue(status.startswith('303') or status.startswith('302'))
        cookie = _cookie(headers)
        self.assertIsNotNone(cookie, 'redirect must still carry the cookie')
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'user-7|sku-9')

    def test_persist_runs_even_if_handler_raises(self):
        """A plain exception (not caught by JSONPlugin, unlike HTTPResponse)
        genuinely propagates through SessionMiddleware's next_handler(ctx)
        call, so this is what actually exercises its try/finally: a session
        write started before the crash is not silently lost.
        """
        app = Lcore(catchall=True)
        app.use(SessionMiddleware(backend=self.backend, secret=SECRET))

        @app.route('/boom')
        def handler():
            request.session['saved'] = True
            raise RuntimeError('handler exploded')

        status, headers, _ = run_request(app, 'GET', '/boom')
        self.assertTrue(status.startswith('500'), status)
        cookie = _cookie(headers)
        self.assertIsNotNone(cookie, 'session set before the crash must still be saved')

    def test_destroy_is_server_side_logout(self):
        """destroy() kills the record, so replaying the cookie gains nothing."""
        _, headers, _ = run_request(self.app, 'GET', '/login/user-2')
        cookie = _cookie(headers)
        run_request(self.app, 'GET', '/logout', headers=_as(cookie))
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None|')

    # -- index-based revocation -------------------------------------------

    def test_list_sessions_sees_every_device(self):
        """The per-user index powers an 'active devices' account page."""
        cookies = []
        for _ in range(3):
            _, headers, _ = run_request(self.app, 'GET', '/login/user-3')
            cookies.append(_cookie(headers))
        _, _, body = run_request(self.app, 'GET', '/devices',
                                 headers=_as(cookies[-1]))
        self.assertEqual(body, b'3')

    def test_revoke_other_sessions_keeps_current(self):
        """'Sign out my other devices' leaves the current one signed in."""
        cookies = []
        for _ in range(3):
            _, headers, _ = run_request(self.app, 'GET', '/login/user-4')
            cookies.append(_cookie(headers))

        _, _, removed = run_request(self.app, 'GET', '/revoke-others',
                                    headers=_as(cookies[-1]))
        self.assertEqual(removed, b'2')

        _, _, body = run_request(self.app, 'GET', '/whoami',
                                 headers=_as(cookies[0]))
        self.assertEqual(body, b'None|')
        _, _, body = run_request(self.app, 'GET', '/whoami',
                                 headers=_as(cookies[-1]))
        self.assertEqual(body, b'user-4|sku-1')

    # -- epoch-based revocation -------------------------------------------

    def test_bump_epoch_invalidates_without_index(self):
        """The epoch kills sessions without walking the index at all."""
        _, headers, _ = run_request(self.app, 'GET', '/login/user-5')
        cookie = _cookie(headers)
        self.backend.bump_epoch('user-5')
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None|')

    def test_revoke_all_signs_out_everywhere(self):
        """revoke_all() is the password-reset call: index plus epoch."""
        cookies = []
        for _ in range(2):
            _, headers, _ = run_request(self.app, 'GET', '/login/user-6')
            cookies.append(_cookie(headers))

        removed = self.backend.revoke_all('user-6')
        self.assertEqual(removed, 2)
        self.assertEqual(self.backend.get_epoch('user-6'), 1)
        for cookie in cookies:
            _, _, body = run_request(self.app, 'GET', '/whoami',
                                     headers=_as(cookie))
            self.assertEqual(body, b'None|')

    def test_epoch_does_not_affect_other_users(self):
        """Revoking one user leaves everyone else signed in."""
        _, headers_a, _ = run_request(self.app, 'GET', '/login/user-a')
        _, headers_b, _ = run_request(self.app, 'GET', '/login/user-b')
        self.backend.revoke_all('user-a')
        _, _, body = run_request(self.app, 'GET', '/whoami',
                                 headers=_as(_cookie(headers_b)))
        self.assertEqual(body, b'user-b|sku-1')

    def test_anonymous_session_skips_epoch_lookup(self):
        """An unbound session has no user, so it costs no epoch read."""
        calls = []
        backend = self.backend
        original = backend.get_epoch

        def counting(user_key):
            calls.append(user_key)
            return original(user_key)

        backend.get_epoch = counting
        try:
            _, headers, _ = run_request(self.app, 'GET', '/write')
            run_request(self.app, 'GET', '/read', headers=_as(_cookie(headers)))
        finally:
            backend.get_epoch = original
        self.assertEqual(calls, [])

    # -- expiry ------------------------------------------------------------

    def test_absolute_ttl_expires_session(self):
        """absolute_ttl caps total lifetime regardless of activity."""
        app = self._build(self.backend, absolute_ttl=1)
        _, headers, _ = run_request(app, 'GET', '/login/user-8')
        cookie = _cookie(headers)
        _, _, body = run_request(app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'user-8|sku-1')

        time.sleep(1.1)
        _, _, body = run_request(app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None|')

    def test_idle_ttl_expires_session(self):
        """The backend drops a session once its idle TTL lapses."""
        app = self._build(self.backend, ttl=1)
        _, headers, _ = run_request(app, 'GET', '/login/user-9')
        cookie = _cookie(headers)
        time.sleep(1.1)
        _, _, body = run_request(app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None|')


class TestMemorySessions(SessionAppMixin, unittest.TestCase):
    """Session behaviour on the in-memory backend."""

    def make_backend(self):
        return MemorySessionBackend(warn=False)


class TestSQLiteSessions(SessionAppMixin, unittest.TestCase):
    """The same behaviour must hold on the SQLite backend."""

    def make_backend(self):
        self._tmpdir = tempfile.mkdtemp()
        return SQLiteSessionBackend(
            path=os.path.join(self._tmpdir, 'sessions.db'))

    def tearDown(self):
        self.backend.close()
        shutil.rmtree(getattr(self, '_tmpdir', ''), ignore_errors=True)


class TestSessionMiddlewareConfig(unittest.TestCase):
    """Configuration-level guards."""

    def test_missing_secret_warns(self):
        """No secret means random per-process signing, which logs users out."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            SessionMiddleware(backend=MemorySessionBackend(warn=False))
        messages = [str(w.message) for w in caught
                    if issubclass(w.category, UserWarning)]
        self.assertTrue(messages)
        self.assertIn('secret', messages[0])

    def test_memory_backend_warns(self):
        """The in-memory backend warns that it is not production-safe."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            MemorySessionBackend()
        messages = [str(w.message) for w in caught
                    if issubclass(w.category, UserWarning)]
        self.assertTrue(messages)
        self.assertIn('multi-worker', messages[0])

    def test_session_without_middleware_raises(self):
        """Touching request.session with no middleware fails loudly."""
        app = Lcore()

        @app.route('/boom')
        def boom():
            return str(request.session)

        status, _, _ = run_request(app, 'GET', '/boom')
        self.assertTrue(status.startswith('500'))

    def _cookie_with(self, **options):
        """Set a session under the given cookie options, return the header."""
        app = Lcore()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app.use(SessionMiddleware(backend=MemorySessionBackend(warn=False),
                                      secret=SECRET, **options))

        @app.route('/write')
        def write():
            request.session['k'] = 'v'
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/write')
        return headers.get('Set-Cookie', '')

    def test_secure_flag_is_configurable(self):
        """secure=True marks the cookie HTTPS-only."""
        self.assertIn('secure', self._cookie_with(secure=True).lower())

    def test_cookie_name_is_configurable(self):
        """A custom cookie_name is the one actually written."""
        raw = self._cookie_with(cookie_name='sid')
        self.assertTrue(raw.startswith('sid='), raw)
        self.assertNotIn('lcore_session', raw)

    def test_samesite_is_configurable(self):
        """samesite='Strict' reaches the header instead of the Lax default."""
        raw = self._cookie_with(samesite='Strict').lower()
        self.assertIn('samesite=strict', raw)
        self.assertNotIn('samesite=lax', raw)

    def test_path_and_domain_are_configurable(self):
        """Cookie scope options are rendered when set, omitted when not."""
        raw = self._cookie_with(path='/app', domain='example.com')
        self.assertIn('Path=/app', raw)
        self.assertIn('Domain=example.com', raw)

    def test_httponly_can_be_disabled(self):
        """httponly=False drops the flag rather than being ignored."""
        self.assertNotIn('httponly', self._cookie_with(httponly=False).lower())

    def test_custom_cookie_name_round_trips(self):
        """A renamed cookie is also the one read back on the next request."""
        app = Lcore()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app.use(SessionMiddleware(backend=MemorySessionBackend(warn=False),
                                      secret=SECRET, cookie_name='sid'))

        @app.route('/write')
        def write():
            request.session['k'] = 'v'
            return 'ok'

        @app.route('/read')
        def read():
            return request.session.get('k', 'unset')

        _, headers, _ = run_request(app, 'GET', '/write')
        cookie = _cookie(headers, 'sid')
        self.assertIsNotNone(cookie)
        _, _, body = run_request(app, 'GET', '/read', headers=_as(cookie, 'sid'))
        self.assertEqual(body, b'v')


class TestEpochCache(unittest.TestCase):
    """The epoch is read once per TTL, not once per authenticated request."""

    def setUp(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.backend = MemorySessionBackend(warn=False)
        self.reads = []
        self._real_get_epoch = self.backend.get_epoch

        def counting(user_key):
            self.reads.append(user_key)
            return self._real_get_epoch(user_key)

        self.backend.get_epoch = counting
        self.app = self._build()

    def _build(self, **options):
        app = Lcore()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app.use(SessionMiddleware(backend=self.backend, secret=SECRET,
                                      **options))

        @app.route('/login/<uid>')
        def login(uid):
            request.session.bind_user(uid)
            return 'ok'

        @app.route('/whoami')
        def whoami():
            return str(request.session.user_id)

        return app

    def test_repeated_requests_do_not_re_read_the_epoch(self):
        """Ten authenticated requests cost one epoch lookup, not ten.

        The first request populates the cache: bind_user() stamps via the
        uncached read so a login always sees the authoritative value.
        """
        _, headers, _ = run_request(self.app, 'GET', '/login/u1')
        cookie = _cookie(headers)
        self.reads.clear()
        for _ in range(10):
            _, _, body = run_request(self.app, 'GET', '/whoami',
                                     headers=_as(cookie))
            self.assertEqual(body, b'u1')
        self.assertEqual(len(self.reads), 1,
                         'expected one read for ten requests, got %d'
                         % len(self.reads))

    def test_anonymous_requests_never_read_the_epoch(self):
        """No user bound means no epoch check at all."""
        run_request(self.app, 'GET', '/whoami')
        self.assertEqual(self.reads, [])

    def test_local_bump_invalidates_immediately(self):
        """Revoking in this process must not wait for the cache to expire."""
        _, headers, _ = run_request(self.app, 'GET', '/login/u2')
        cookie = _cookie(headers)
        run_request(self.app, 'GET', '/whoami', headers=_as(cookie))  # warm it
        self.backend.bump_epoch('u2')
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None')

    def test_ttl_zero_reads_through(self):
        """epoch_cache_ttl = 0 restores a read on every request."""
        self.backend.epoch_cache_ttl = 0
        _, headers, _ = run_request(self.app, 'GET', '/login/u3')
        cookie = _cookie(headers)
        self.reads.clear()
        for _ in range(3):
            run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(len(self.reads), 3)

    def test_expired_entry_is_refetched(self):
        """Another process's bump is picked up once the TTL lapses."""
        self.backend.epoch_cache_ttl = 0.05
        _, headers, _ = run_request(self.app, 'GET', '/login/u4')
        cookie = _cookie(headers)
        run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        # Simulate a bump by another worker: change the store, leave our cache.
        self.backend._epochs['u4'] = 99
        time.sleep(0.06)
        _, _, body = run_request(self.app, 'GET', '/whoami', headers=_as(cookie))
        self.assertEqual(body, b'None')

    def test_cache_is_bounded(self):
        """A busy site must not grow the epoch cache without limit."""
        self.backend.epoch_cache_max = 10
        for i in range(25):
            self.backend.cached_epoch('user-%d' % i)
        self.assertLessEqual(len(self.backend._epoch_cache),
                             self.backend.epoch_cache_max)


class TestBackendFailurePolicy(unittest.TestCase):
    """Sessions cannot fail open: ignoring the store means ignoring revocation."""

    class BrokenBackend(MemorySessionBackend):
        fail = False

        def load(self, sid):
            if self.fail:
                raise RuntimeError('session store is down')
            return super().load(sid)

        def save(self, sid, record, ttl):
            if self.fail:
                raise RuntimeError('session store is down')
            return super().save(sid, record, ttl)

    def _build(self, backend, **options):
        app = Lcore()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            app.use(SessionMiddleware(backend=backend, secret=SECRET, **options))

        @app.route('/read')
        def read():
            return str(request.session.get('k', 'unset'))

        @app.route('/write')
        def write():
            request.session['k'] = 'v'
            return 'ok'

        return app

    def setUp(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.backend = self.BrokenBackend(warn=False)

    def _valid_cookie(self, app):
        """A properly signed cookie, so the backend is actually reached.

        An unsigned value is rejected by get_cookie() before any load, which
        would make an outage test pass for the wrong reason.
        """
        _, headers, _ = run_request(app, 'GET', '/write')
        cookie = _cookie(headers)
        self.assertIsNotNone(cookie)
        return cookie

    def test_default_returns_503_on_read_failure(self):
        """An outage refuses the request rather than silently logging users out."""
        app = self._build(self.backend)
        cookie = self._valid_cookie(app)
        self.backend.fail = True
        status, _, _ = run_request(app, 'GET', '/read', headers=_as(cookie))
        self.assertTrue(status.startswith('503'), status)

    def test_default_returns_503_on_write_failure(self):
        """A login that cannot be stored must not report success."""
        app = self._build(self.backend)
        self.backend.fail = True
        status, _, _ = run_request(app, 'GET', '/write')
        self.assertTrue(status.startswith('503'), status)

    def test_failed_write_sets_no_cookie(self):
        """No cookie may be issued for a session that was never stored."""
        app = self._build(self.backend)
        self.backend.fail = True
        _, headers, _ = run_request(app, 'GET', '/write')
        self.assertIsNone(_cookie(headers))

    def test_anonymous_policy_degrades(self):
        """on_backend_error='anonymous' keeps the site up, signed out."""
        app = self._build(self.backend, on_backend_error='anonymous')
        cookie = self._valid_cookie(app)
        self.backend.fail = True
        status, _, body = run_request(app, 'GET', '/read', headers=_as(cookie))
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'unset')

    def test_raise_policy_propagates(self):
        """on_backend_error='raise' leaves it to the app's error handler."""
        app = self._build(self.backend, on_backend_error='raise')
        cookie = self._valid_cookie(app)
        self.backend.fail = True
        status, _, _ = run_request(app, 'GET', '/read', headers=_as(cookie))
        self.assertTrue(status.startswith('500'), status)

    def test_invalid_policy_rejected(self):
        """A typo in the policy name fails at construction, not in production."""
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with self.assertRaises(ValueError):
                SessionMiddleware(backend=self.backend, secret=SECRET,
                                  on_backend_error='ignore')

    def test_healthy_backend_is_unaffected(self):
        """The policy costs nothing when the store is working."""
        app = self._build(self.backend)
        _, headers, _ = run_request(app, 'GET', '/write')
        _, _, body = run_request(app, 'GET', '/read',
                                 headers=_as(_cookie(headers)))
        self.assertEqual(body, b'v')


class TestCustomBackend(unittest.TestCase):
    """The ABC is the extension point for Postgres, DynamoDB and friends."""

    def test_subclass_only_implements_seven_methods(self):
        """revoke_all() and touch() come free from the base class."""
        class Dummy(SessionBackend):
            def __init__(self):
                self.records = {}
                self.epochs = {}

            def load(self, sid):
                return self.records.get(sid)

            def save(self, sid, record, ttl):
                self.records[sid] = record

            def delete(self, sid):
                return self.records.pop(sid, None) is not None

            def list_user(self, user_key):
                return [(s, r) for s, r in self.records.items()
                        if r.get('uid') == str(user_key)]

            def revoke_user(self, user_key, except_sid=None):
                doomed = [s for s, r in self.list_user(user_key)
                          if s != except_sid]
                for sid in doomed:
                    del self.records[sid]
                return len(doomed)

            def get_epoch(self, user_key):
                return self.epochs.get(str(user_key), 0)

            def bump_epoch(self, user_key):
                key = str(user_key)
                self.epochs[key] = self.epochs.get(key, 0) + 1
                return self.epochs[key]

        backend = Dummy()
        backend.save('a', {'data': {}, 'uid': 'u1'}, 60)
        backend.save('b', {'data': {}, 'uid': 'u1'}, 60)
        # touch()'s positive path: a still-live record is refreshed (via
        # load()+save()) and reports True, not just the missing-record case
        # exercised below.
        self.assertTrue(backend.touch('a', 60))
        self.assertEqual(backend.revoke_all('u1'), 2)
        self.assertEqual(backend.get_epoch('u1'), 1)
        self.assertFalse(backend.touch('a', 60))


if __name__ == '__main__':
    unittest.main()
