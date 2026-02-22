import sys, os, unittest, json, threading, time, hashlib, hmac, base64, tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from io import BytesIO, StringIO
from datetime import timedelta
from lcore import (
    Lcore, request, response, ctx, tob, touni, json_dumps, json_loads,
    HTTPError, HTTPResponse, _lscmp, load,
    rate_limit, static_file, html_escape,
    CORSMiddleware, CompressionMiddleware, BodyLimitMiddleware,
    MiddlewareHook, DependencyContainer, Middleware,
    RequestIDMiddleware, SecurityHeadersMiddleware,
    on_shutdown, _shutdown_hooks,
    cached_property as CachedProperty,
    hash_password, verify_password,
    TestClient, TestResponse,
    BackgroundTaskPool,
)
from tests.helpers import create_environ, run_request


class TestTimingSafeCompare(unittest.TestCase):

    def test_equal_strings(self):
        self.assertTrue(_lscmp('abc', 'abc'))

    def test_unequal_strings(self):
        self.assertFalse(_lscmp('abc', 'abd'))

    def test_different_lengths(self):
        self.assertFalse(_lscmp('ab', 'abc'))

    def test_empty_strings(self):
        self.assertTrue(_lscmp('', ''))

    def test_bytes_input(self):
        self.assertTrue(_lscmp(b'hello', b'hello'))

    def test_mixed_types(self):
        self.assertTrue(_lscmp('hello', b'hello'))

    def test_none_handling(self):
        self.assertFalse(_lscmp(None, 'abc'))
        self.assertFalse(_lscmp('abc', None))

    def test_unicode(self):
        self.assertTrue(_lscmp('caf\u00e9', 'caf\u00e9'))


class TestLoadSecurity(unittest.TestCase):

    def test_load_module(self):
        result = load('os')
        self.assertIs(result, os)

    def test_load_attribute(self):
        result = load('os:path')
        self.assertIs(result, os.path)

    def test_load_dotted_attribute(self):
        result = load('os:path.join')
        self.assertIs(result, os.path.join)

    def test_load_rejects_non_identifier(self):
        with self.assertRaises(AttributeError):
            load('os:system("whoami")')

    def test_load_rejects_dunder_exploit(self):
        with self.assertRaises(AttributeError):
            load('os:__import__("subprocess")')

    def test_load_rejects_semicolons(self):
        with self.assertRaises(AttributeError):
            load('os:path; import sys')

    def test_load_rejects_parens(self):
        with self.assertRaises(AttributeError):
            load('os:system("ls")')


class TestCookieSecurityJSON(unittest.TestCase):

    def setUp(self):
        self.app = Lcore()

        @self.app.route('/set')
        def set_cookie():
            response.set_cookie('test', 'myvalue', secret='s3cret')
            return 'ok'

        @self.app.route('/get')
        def get_cookie():
            val = request.get_cookie('test', secret='s3cret')
            return val or 'none'

    def test_signed_cookie_roundtrip(self):
        status, headers, body = run_request(self.app, 'GET', '/set')
        self.assertIn('Set-Cookie', headers)
        cookie_val = headers['Set-Cookie'].split('=', 1)[1].split(';')[0]
        stripped = cookie_val.strip('"')
        self.assertTrue(stripped.startswith('!'))

        status2, _, body2 = run_request(
            self.app, 'GET', '/get',
            headers={'Cookie': 'test=%s' % cookie_val}
        )
        self.assertEqual(body2, b'myvalue')

    def test_tampered_cookie_rejected(self):
        status, _, body = run_request(
            self.app, 'GET', '/get',
            headers={'Cookie': 'test=!tampered?dGFtcGVyZWQ='}
        )
        self.assertEqual(body, b'none')

    def test_wrong_secret_rejected(self):
        app2 = Lcore()

        @app2.route('/get')
        def get_cookie():
            val = request.get_cookie('test', secret='wrong')
            return val or 'none'

        status, headers, _ = run_request(self.app, 'GET', '/set')
        cookie_val = headers['Set-Cookie'].split('=', 1)[1].split(';')[0]
        _, _, body = run_request(
            app2, 'GET', '/get',
            headers={'Cookie': 'test=%s' % cookie_val}
        )
        self.assertEqual(body, b'none')


class TestStaticFileSecurity(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(self.tmpdir, 'test.txt'), 'w') as f:
            f.write('hello')
        self.app = Lcore()

        root = self.tmpdir
        @self.app.route('/static/<filepath:path>')
        def serve(filepath):
            return static_file(filepath, root=root)

    def test_normal_file(self):
        status, _, body = run_request(self.app, 'GET', '/static/test.txt')
        self.assertEqual(body, b'hello')

    def test_path_traversal_blocked(self):
        status, _, _ = run_request(self.app, 'GET', '/static/../../../etc/passwd')
        self.assertIn('403', status)

    def test_etag_uses_sha256(self):
        _, headers, _ = run_request(self.app, 'GET', '/static/test.txt')
        etag = (headers.get('ETag') or headers.get('Etag', '')).strip('"')
        self.assertEqual(len(etag), 64)

    def test_download_filename_sanitized(self):
        app = Lcore()
        root = self.tmpdir

        @app.route('/dl/<f:path>')
        def dl(f):
            return static_file(f, root=root, download='../../evil.txt')

        _, headers, _ = run_request(app, 'GET', '/dl/test.txt')
        disp = headers.get('Content-Disposition', '')
        self.assertNotIn('..', disp)
        self.assertIn('evil.txt', disp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestDotenvSecurity(unittest.TestCase):

    def test_rejects_invalid_key_names(self):
        from lcore import ConfigDict
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('VALID_KEY=good\n')
            f.write('123INVALID=bad\n')
            f.write('ALSO-INVALID=bad\n')
            f.write('GOOD_ONE=nice\n')
            f.name
        try:
            cfg = ConfigDict()
            old_env = os.environ.copy()
            cfg.load_dotenv(f.name)
            self.assertIn('VALID_KEY', os.environ)
            self.assertNotIn('123INVALID', os.environ)
            self.assertNotIn('ALSO-INVALID', os.environ)
            self.assertIn('GOOD_ONE', os.environ)
        finally:
            for k in ('VALID_KEY', '123INVALID', 'ALSO-INVALID', 'GOOD_ONE'):
                os.environ.pop(k, None)
            os.unlink(f.name)


class TestTimedeltaBug(unittest.TestCase):

    def test_timedelta_total_seconds(self):
        app = Lcore()

        @app.route('/cookie')
        def set_it():
            response.set_cookie('sess', 'val', max_age=timedelta(days=7))
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/cookie')
        cookie = headers.get('Set-Cookie', '')
        self.assertIn('Max-Age=604800', cookie)

    def test_timedelta_with_hours(self):
        app = Lcore()

        @app.route('/cookie')
        def set_it():
            response.set_cookie('s', 'v', max_age=timedelta(hours=2, minutes=30))
            return 'ok'

        _, headers, _ = run_request(app, 'GET', '/cookie')
        cookie = headers.get('Set-Cookie', '')
        self.assertIn('Max-Age=9000', cookie)


class TestContentLengthSafety(unittest.TestCase):

    def test_non_numeric_content_length(self):
        app = Lcore()

        @app.route('/test')
        def handler():
            return str(request.content_length)

        _, _, body = run_request(
            app, 'GET', '/test',
            headers={'Content-Length': 'not-a-number'}
        )
        self.assertEqual(body, b'-1')

    def test_empty_content_length(self):
        app = Lcore()

        @app.route('/test')
        def handler():
            return str(request.content_length)

        _, _, body = run_request(app, 'GET', '/test')
        self.assertEqual(body, b'0')


class TestRateLimitImprovements(unittest.TestCase):

    def test_none_remote_addr_handled(self):
        app = Lcore()

        @app.route('/limited')
        @rate_limit(100, per=60)
        def limited():
            return 'ok'

        environ = create_environ('GET', '/limited')
        environ.pop('REMOTE_ADDR', None)
        status, _, body = run_request(app, 'GET', '/limited')
        self.assertIn('200', status)

    def test_rate_limit_works(self):
        app = Lcore()

        @app.route('/rl')
        @rate_limit(2, per=60)
        def rl():
            return 'ok'

        run_request(app, 'GET', '/rl')
        run_request(app, 'GET', '/rl')
        status, _, _ = run_request(app, 'GET', '/rl')
        self.assertIn('429', status)


class TestCORSMiddleware(unittest.TestCase):

    def setUp(self):
        self.app = Lcore()
        self.app.use(CORSMiddleware(allow_origins='*'))

        @self.app.route('/api/data', method=['GET', 'OPTIONS'])
        def data():
            return {'key': 'value'}

    def test_cors_headers_on_normal_request(self):
        _, headers, _ = run_request(
            self.app, 'GET', '/api/data',
            headers={'Origin': 'http://example.com'}
        )
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), '*')

    def test_preflight_options_request(self):
        status, headers, body = run_request(
            self.app, 'OPTIONS', '/api/data',
            headers={'Origin': 'http://example.com'}
        )
        self.assertIn('204', status)
        self.assertIn('Access-Control-Allow-Methods', headers)
        self.assertIn('Access-Control-Allow-Headers', headers)
        self.assertIn('Access-Control-Max-Age', headers)

    def test_no_cors_without_origin(self):
        _, headers, _ = run_request(self.app, 'GET', '/api/data')
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_specific_origin(self):
        app = Lcore()
        app.use(CORSMiddleware(allow_origins=['http://good.com']))

        @app.route('/x')
        def x():
            return 'ok'

        _, headers, _ = run_request(
            app, 'GET', '/x',
            headers={'Origin': 'http://good.com'}
        )
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), 'http://good.com')

    def test_disallowed_origin(self):
        app = Lcore()
        app.use(CORSMiddleware(allow_origins=['http://good.com']))

        @app.route('/x')
        def x():
            return 'ok'

        _, headers, _ = run_request(
            app, 'GET', '/x',
            headers={'Origin': 'http://evil.com'}
        )
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_credentials_mode(self):
        app = Lcore()
        app.use(CORSMiddleware(
            allow_origins='http://app.com',
            allow_credentials=True
        ))

        @app.route('/x')
        def x():
            return 'ok'

        _, headers, _ = run_request(
            app, 'GET', '/x',
            headers={'Origin': 'http://app.com'}
        )
        self.assertEqual(headers.get('Access-Control-Allow-Credentials'), 'true')
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), 'http://app.com')
        self.assertIn('Vary', headers)


class TestBodyLimitMiddleware(unittest.TestCase):

    def test_allows_small_bodies(self):
        app = Lcore()
        app.use(BodyLimitMiddleware(max_size=1024))

        @app.route('/upload', method='POST')
        def upload():
            return 'ok'

        status, _, _ = run_request(
            app, 'POST', '/upload',
            body=b'x' * 100,
            content_type='application/octet-stream'
        )
        self.assertIn('200', status)

    def test_rejects_large_bodies(self):
        app = Lcore()
        app.use(BodyLimitMiddleware(max_size=100))

        @app.route('/upload', method='POST')
        def upload():
            return 'ok'

        status, _, _ = run_request(
            app, 'POST', '/upload',
            body=b'x' * 200,
            content_type='application/octet-stream'
        )
        self.assertIn('413', status)


class TestCompressionMiddleware(unittest.TestCase):

    def test_no_compression_without_accept(self):
        app = Lcore()
        app.use(CompressionMiddleware())

        @app.route('/data')
        def data():
            return 'hello world'

        _, headers, body = run_request(app, 'GET', '/data')
        self.assertNotIn('Content-Encoding', headers)

    def test_returns_body_with_accept_gzip(self):
        app = Lcore()
        app.use(CompressionMiddleware())

        @app.route('/data')
        def data():
            return 'hello world'

        _, _, body = run_request(
            app, 'GET', '/data',
            headers={'Accept-Encoding': 'gzip'}
        )
        self.assertIsNotNone(body)


class TestMiddlewareHook(unittest.TestCase):

    def test_pre_post_execution(self):
        app = Lcore()
        calls = []

        class TrackHook(MiddlewareHook):
            def pre(self, ctx):
                calls.append('pre')

            def post(self, ctx, result):
                calls.append('post')
                return result

        app.use(TrackHook())

        @app.route('/test')
        def handler():
            calls.append('handler')
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertEqual(calls, ['pre', 'handler', 'post'])

    def test_pre_short_circuit(self):
        app = Lcore()

        class BlockHook(MiddlewareHook):
            def pre(self, ctx):
                return HTTPResponse('blocked', status=403)

        app.use(BlockHook())

        @app.route('/test')
        def handler():
            return 'should not reach'

        status, _, body = run_request(app, 'GET', '/test')
        self.assertIn('403', status)

    def test_post_modifies_result(self):
        app = Lcore()

        class UpperHook(MiddlewareHook):
            def post(self, ctx, result):
                return 'MODIFIED'

        app.use(UpperHook())

        @app.route('/test')
        def handler():
            return 'original'

        _, _, body = run_request(app, 'GET', '/test')
        self.assertEqual(body, b'MODIFIED')


class TestDependencyInjection(unittest.TestCase):

    def test_singleton_shared_across_requests(self):
        app = Lcore()
        created = []

        class Cache:
            def __init__(self):
                self.id = len(created)
                created.append(self.id)

        app.inject('cache', Cache, lifetime='singleton')

        @app.route('/test')
        def handler():
            return str(ctx.cache.id)

        _, _, body1 = run_request(app, 'GET', '/test')
        _, _, body2 = run_request(app, 'GET', '/test')
        self.assertEqual(body1, body2)
        self.assertEqual(len(created), 1)

    def test_scoped_per_request(self):
        app = Lcore()
        created = []

        class Session:
            def __init__(self):
                self.id = len(created)
                created.append(self.id)
            def close(self):
                pass

        app.inject('session', Session, lifetime='scoped')

        @app.route('/test')
        def handler():
            return str(ctx.session.id)

        _, _, body1 = run_request(app, 'GET', '/test')
        _, _, body2 = run_request(app, 'GET', '/test')
        self.assertNotEqual(body1, body2)
        self.assertEqual(len(created), 2)

    def test_scoped_closed_after_request(self):
        app = Lcore()
        closed = []

        class DB:
            def close(self):
                closed.append(True)

        app.inject('db', DB, lifetime='scoped')

        @app.route('/test')
        def handler():
            _ = ctx.db
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertEqual(len(closed), 1)

    def test_transient_new_each_access(self):
        app = Lcore()
        count = [0]

        def make_logger():
            count[0] += 1
            return 'logger-%d' % count[0]

        app.inject('logger', make_logger, lifetime='transient')

        @app.route('/test')
        def handler():
            a = ctx.logger
            return a

        run_request(app, 'GET', '/test')
        run_request(app, 'GET', '/test')
        self.assertEqual(count[0], 2)

    def test_invalid_lifetime_raises(self):
        container = DependencyContainer()
        with self.assertRaises(ValueError):
            container.register('x', lambda: None, lifetime='invalid')

    def test_resolve_unknown_raises(self):
        container = DependencyContainer()
        with self.assertRaises(KeyError):
            container.resolve('nonexistent')

    def test_contains_and_len(self):
        container = DependencyContainer()
        container.register('a', lambda: 1)
        container.register('b', lambda: 2)
        self.assertIn('a', container)
        self.assertNotIn('c', container)
        self.assertEqual(len(container), 2)


class TestLifecycleHooks(unittest.TestCase):

    def test_all_hooks_fire_in_order(self):
        app = Lcore()
        events = []

        for name in ('on_request_start', 'on_auth_resolved',
                     'on_handler_enter', 'on_handler_exit',
                     'on_response_build', 'on_response_send'):
            hook_name = name
            app.add_hook(hook_name, lambda n=hook_name: events.append(n))

        @app.route('/test')
        def handler():
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertEqual(events, [
            'on_request_start', 'on_auth_resolved', 'on_handler_enter',
            'on_handler_exit', 'on_response_build', 'on_response_send'
        ])

    def test_hooks_fire_even_on_error(self):
        app = Lcore()
        events = []

        app.add_hook('on_request_start', lambda: events.append('start'))
        app.add_hook('on_response_build', lambda: events.append('build'))
        app.add_hook('on_response_send', lambda: events.append('send'))

        @app.route('/test')
        def handler():
            raise HTTPError(500, 'boom')

        run_request(app, 'GET', '/test')
        self.assertIn('start', events)
        self.assertIn('build', events)
        self.assertIn('send', events)


class TestModuleLifecycle(unittest.TestCase):

    def test_module_mount_hook(self):
        app = Lcore()
        mounted = []

        app.add_hook('on_module_mount', lambda prefix, child: mounted.append(prefix))

        child = Lcore()
        @child.route('/info')
        def info():
            return 'child'

        app.mount('/api/', child)
        self.assertEqual(mounted, ['/api/'])

    def test_module_scoped_before_request(self):
        app = Lcore()
        child = Lcore()
        events = []

        @child.hook('before_request')
        def child_before():
            events.append('child_before')

        @child.route('/data')
        def data():
            return 'data'

        @app.route('/main')
        def main():
            return 'main'

        app.mount('/api/', child)

        run_request(app, 'GET', '/main')
        self.assertEqual(events, [])

        run_request(app, 'GET', '/api/data')
        self.assertIn('child_before', events)

    def test_module_hook_decorator(self):
        app = Lcore()
        child = Lcore()
        events = []

        @child.route('/x')
        def x():
            return 'x'

        app.mount('/mod/', child)

        @app.module_hook('/mod/', 'after_request')
        def mod_after():
            events.append('mod_after')

        run_request(app, 'GET', '/mod/x')
        self.assertIn('mod_after', events)


class TestCachedPropertyThreadSafe(unittest.TestCase):

    def test_computed_once(self):
        count = [0]

        class Obj:
            @CachedProperty
            def value(self):
                count[0] += 1
                return 42

        obj = Obj()
        self.assertEqual(obj.value, 42)
        self.assertEqual(obj.value, 42)
        self.assertEqual(count[0], 1)

    def test_thread_safety(self):
        count = [0]
        lock = threading.Lock()

        class Obj:
            @CachedProperty
            def value(self):
                with lock:
                    count[0] += 1
                time.sleep(0.01)
                return 42

        obj = Obj()
        results = []
        errors = []

        def access():
            try:
                results.append(obj.value)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=access) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        self.assertTrue(all(r == 42 for r in results))
        self.assertEqual(count[0], 1)


class TestShowRoutes(unittest.TestCase):

    def test_show_routes_returns_list(self):
        app = Lcore()

        @app.route('/a', method='GET', name='route_a')
        def a():
            return 'a'

        @app.route('/b', method='POST')
        def b():
            return 'b'

        routes = app.show_routes()
        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[0]['method'], 'GET')
        self.assertEqual(routes[0]['rule'], '/a')
        self.assertEqual(routes[0]['name'], 'route_a')
        self.assertEqual(routes[1]['method'], 'POST')
        self.assertEqual(routes[1]['rule'], '/b')


class TestShowMiddleware(unittest.TestCase):

    def test_show_middleware_sorted(self):
        app = Lcore()
        app.use(SecurityHeadersMiddleware())
        app.use(RequestIDMiddleware())

        mw = app.show_middleware()
        self.assertEqual(len(mw), 2)
        self.assertEqual(mw[0]['name'], 'request_id')
        self.assertEqual(mw[1]['name'], 'security_headers')
        self.assertTrue(mw[0]['order'] < mw[1]['order'])


class TestAPIDocs(unittest.TestCase):

    def test_api_docs_structure(self):
        app = Lcore()

        @app.route('/users/<id:int>', method='GET', name='get_user')
        def get_user(id):
            """Fetch a user by ID."""
            return {'id': id}

        docs = app.api_docs()
        self.assertIn('routes', docs)
        self.assertIn('version', docs)
        self.assertEqual(len(docs['routes']), 1)

        route_doc = docs['routes'][0]
        self.assertEqual(route_doc['method'], 'GET')
        self.assertEqual(route_doc['rule'], '/users/<id:int>')
        self.assertEqual(route_doc['name'], 'get_user')
        self.assertEqual(route_doc['docstring'], 'Fetch a user by ID.')
        self.assertTrue(len(route_doc['parameters']) >= 1)

    def test_api_docs_json(self):
        app = Lcore()

        @app.route('/ping')
        def ping():
            return 'pong'

        result = app.api_docs_json()
        parsed = json.loads(result)
        self.assertIn('routes', parsed)


class TestGracefulShutdown(unittest.TestCase):

    def setUp(self):
        self._orig_hooks = _shutdown_hooks[:]

    def tearDown(self):
        _shutdown_hooks[:] = self._orig_hooks

    def test_on_shutdown_registers(self):
        calls = []

        @on_shutdown
        def cleanup():
            calls.append('cleaned')

        from lcore import _run_shutdown_hooks
        _run_shutdown_hooks()
        self.assertEqual(calls, ['cleaned'])

    def test_shutdown_hooks_run_in_reverse(self):
        order = []

        @on_shutdown
        def first():
            order.append('first')

        @on_shutdown
        def second():
            order.append('second')

        from lcore import _run_shutdown_hooks
        _run_shutdown_hooks()
        self.assertEqual(order, ['second', 'first'])

    def test_shutdown_hook_error_doesnt_crash(self):
        @on_shutdown
        def bad():
            raise RuntimeError('oops')

        @on_shutdown
        def good():
            pass

        from lcore import _run_shutdown_hooks
        _run_shutdown_hooks()


class TestMiddlewarePipelineCache(unittest.TestCase):

    def test_global_chain_cached(self):
        app = Lcore()
        app.use(RequestIDMiddleware())

        @app.route('/a')
        def a():
            return 'a'

        @app.route('/b')
        def b():
            return 'b'

        run_request(app, 'GET', '/a')
        chain1 = app.middleware._global_chain
        run_request(app, 'GET', '/b')
        chain2 = app.middleware._global_chain
        self.assertIs(chain1, chain2)

    def test_cache_invalidated_on_add(self):
        app = Lcore()
        app.use(RequestIDMiddleware())

        @app.route('/a')
        def a():
            return 'a'

        run_request(app, 'GET', '/a')
        old_chain = app.middleware._global_chain

        app.use(SecurityHeadersMiddleware())
        self.assertIsNone(app.middleware._global_chain)


class TestEdgeCases(unittest.TestCase):

    def test_empty_route_handler(self):
        app = Lcore()

        @app.route('/empty')
        def empty():
            return ''

        status, _, body = run_request(app, 'GET', '/empty')
        self.assertIn('200', status)

    def test_none_return(self):
        app = Lcore()

        @app.route('/none')
        def none_handler():
            return None

        status, _, _ = run_request(app, 'GET', '/none')
        self.assertIn('200', status)

    def test_bytes_return(self):
        app = Lcore()

        @app.route('/bytes')
        def bytes_handler():
            return b'raw bytes'

        _, _, body = run_request(app, 'GET', '/bytes')
        self.assertEqual(body, b'raw bytes')

    def test_multiple_methods_same_path(self):
        app = Lcore()

        @app.route('/resource', method='GET')
        def get_res():
            return 'GET'

        @app.route('/resource', method='POST')
        def post_res():
            return 'POST'

        _, _, body1 = run_request(app, 'GET', '/resource')
        _, _, body2 = run_request(app, 'POST', '/resource')
        self.assertEqual(body1, b'GET')
        self.assertEqual(body2, b'POST')

    def test_unicode_response(self):
        app = Lcore()

        @app.route('/uni')
        def uni():
            return 'caf\u00e9 \u2603'

        _, _, body = run_request(app, 'GET', '/uni')
        self.assertIn('caf\u00e9'.encode('utf-8'), body)

    def test_large_json_response(self):
        app = Lcore()

        @app.route('/big')
        def big():
            return {'items': list(range(1000))}

        _, headers, body = run_request(app, 'GET', '/big')
        self.assertIn('application/json', headers.get('Content-Type', ''))
        parsed = json.loads(body)
        self.assertEqual(len(parsed['items']), 1000)

    def test_404_for_unknown_route(self):
        app = Lcore()

        @app.route('/exists')
        def exists():
            return 'here'

        status, _, _ = run_request(app, 'GET', '/not-here')
        self.assertIn('404', status)

    def test_405_method_not_allowed(self):
        app = Lcore()

        @app.route('/only-get', method='GET')
        def only_get():
            return 'ok'

        status, _, _ = run_request(app, 'POST', '/only-get')
        self.assertIn('405', status)

    def test_error_handler_custom(self):
        app = Lcore()

        @app.error(404)
        def custom_404(err):
            return 'custom not found'

        status, _, body = run_request(app, 'GET', '/nope')
        self.assertIn('404', status)
        self.assertIn(b'custom not found', body)

    def test_head_request(self):
        app = Lcore()

        @app.route('/data')
        def data():
            return 'some body content'

        status, headers, body = run_request(app, 'HEAD', '/data')
        self.assertIn('200', status)
        self.assertEqual(body, b'')

    def test_query_params(self):
        app = Lcore()

        @app.route('/search')
        def search():
            return request.query.get('q', 'none')

        _, _, body = run_request(app, 'GET', '/search', query_string='q=hello')
        self.assertEqual(body, b'hello')


class TestConcurrentRequests(unittest.TestCase):

    def test_thread_isolated_state(self):
        app = Lcore()
        results = {}
        barrier = threading.Barrier(4)

        @app.route('/slow/<id>')
        def slow(id):
            barrier.wait(timeout=5)
            time.sleep(0.01)
            return id

        def make_request(tid):
            try:
                _, _, body = run_request(app, 'GET', '/slow/%d' % tid)
                results[tid] = body
            except Exception as e:
                results[tid] = str(e).encode()

        threads = [threading.Thread(target=make_request, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        for tid in range(4):
            self.assertEqual(results.get(tid), str(tid).encode())


class TestHookTriggerOptimization(unittest.TestCase):

    def test_empty_hooks_fast_path(self):
        app = Lcore()

        @app.route('/test')
        def handler():
            return 'ok'

        result = app.trigger_hook('on_request_start')
        self.assertEqual(result, [])

    def test_hook_with_callbacks(self):
        app = Lcore()
        app.add_hook('on_request_start', lambda: 'fired')
        result = app.trigger_hook('on_request_start')
        self.assertEqual(result, ['fired'])


class TestCompressionMiddlewareFix(unittest.TestCase):

    def setUp(self):
        self.app = Lcore()
        self.app.use(CompressionMiddleware(min_size=10))

    def test_gzip_compresses_response(self):
        @self.app.route('/big')
        def big():
            return 'A' * 500

        status, headers, body = run_request(
            self.app, 'GET', '/big',
            headers={'Accept-Encoding': 'gzip'}
        )
        self.assertEqual(status, '200 OK')
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertIn('Vary', headers)
        import gzip as _gzip
        decompressed = _gzip.decompress(body)
        self.assertEqual(decompressed, b'A' * 500)

    def test_no_gzip_without_accept_encoding(self):
        @self.app.route('/plain')
        def plain():
            return 'Hello World'

        status, headers, body = run_request(self.app, 'GET', '/plain')
        self.assertNotIn('Content-Encoding', headers)
        self.assertEqual(body, b'Hello World')

    def test_skip_small_responses(self):
        app = Lcore()
        app.use(CompressionMiddleware(min_size=1000))

        @app.route('/small')
        def small():
            return 'tiny'

        status, headers, body = run_request(
            app, 'GET', '/small',
            headers={'Accept-Encoding': 'gzip'}
        )
        self.assertNotIn('Content-Encoding', headers)
        self.assertEqual(body, b'tiny')

    def test_skip_non_compressible_content_type(self):
        @self.app.route('/img')
        def img():
            response.content_type = 'image/png'
            return b'\x89PNG'

        status, headers, body = run_request(
            self.app, 'GET', '/img',
            headers={'Accept-Encoding': 'gzip'}
        )
        self.assertNotIn('Content-Encoding', headers)


class TestPasswordHashing(unittest.TestCase):

    def test_hash_and_verify(self):
        hashed = hash_password('mysecret')
        self.assertTrue(verify_password('mysecret', hashed))

    def test_wrong_password_fails(self):
        hashed = hash_password('correct')
        self.assertFalse(verify_password('wrong', hashed))

    def test_unique_salts(self):
        h1 = hash_password('same')
        h2 = hash_password('same')
        self.assertNotEqual(h1, h2)
        self.assertTrue(verify_password('same', h1))
        self.assertTrue(verify_password('same', h2))

    def test_hash_format(self):
        hashed = hash_password('test', iterations=100000)
        self.assertTrue(hashed.startswith('pbkdf2:sha256:100000$'))
        parts = hashed.split('$')
        self.assertEqual(len(parts), 3)

    def test_empty_password(self):
        hashed = hash_password('')
        self.assertTrue(verify_password('', hashed))
        self.assertFalse(verify_password('notempty', hashed))

    def test_unicode_password(self):
        hashed = hash_password('café☕')
        self.assertTrue(verify_password('café☕', hashed))
        self.assertFalse(verify_password('cafe', hashed))

    def test_invalid_hash_string(self):
        self.assertFalse(verify_password('test', 'garbage'))
        self.assertFalse(verify_password('test', ''))
        self.assertFalse(verify_password('test', None))


class TestTestClient(unittest.TestCase):

    def setUp(self):
        self.app = Lcore()

        @self.app.route('/hello')
        def hello():
            return 'Hello World'

        @self.app.route('/json')
        def json_route():
            return {'message': 'ok'}

        @self.app.route('/echo', method='POST')
        def echo():
            return request.json

        @self.app.route('/status')
        def not_found():
            response.status = 404
            return 'Not Found'

        @self.app.route('/headers')
        def check_headers():
            return {'x_custom': request.get_header('X-Custom')}

        self.client = TestClient(self.app)

    def test_get_text(self):
        r = self.client.get('/hello')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, 'Hello World')

    def test_get_json(self):
        r = self.client.get('/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['message'], 'ok')

    def test_post_json(self):
        r = self.client.post('/echo', json={'key': 'value'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json['key'], 'value')

    def test_status_code(self):
        r = self.client.get('/status')
        self.assertEqual(r.status_code, 404)
        self.assertIn('404', r.status)

    def test_custom_headers(self):
        r = self.client.get('/headers', headers={'X-Custom': 'test123'})
        self.assertEqual(r.json['x_custom'], 'test123')

    def test_404_missing_route(self):
        r = self.client.get('/nonexistent')
        self.assertEqual(r.status_code, 404)

    def test_query_string(self):
        @self.app.route('/search')
        def search():
            return {'q': request.query.get('q')}

        r = self.client.get('/search', query_string='q=hello')
        self.assertEqual(r.json['q'], 'hello')

    def test_put_patch_delete(self):
        @self.app.route('/resource', method='PUT')
        def put_r():
            return 'updated'

        @self.app.route('/resource', method='DELETE')
        def del_r():
            return 'deleted'

        self.assertEqual(self.client.put('/resource').text, 'updated')
        self.assertEqual(self.client.delete('/resource').text, 'deleted')

    def test_response_body_bytes(self):
        r = self.client.get('/hello')
        self.assertIsInstance(r.body, bytes)


class TestBackgroundTaskPool(unittest.TestCase):

    def test_submit_and_result(self):
        pool = BackgroundTaskPool(max_workers=2)
        future = pool.submit(lambda x: x * 2, 21)
        self.assertEqual(future.result(timeout=5), 42)
        pool.shutdown()

    def test_pending_count(self):
        import time as _time
        pool = BackgroundTaskPool(max_workers=1)
        pool.submit(_time.sleep, 0.3)
        pool.submit(_time.sleep, 0.3)
        self.assertGreaterEqual(pool.pending, 1)
        _time.sleep(1)
        self.assertEqual(pool.pending, 0)
        pool.shutdown()

    def test_shutdown(self):
        pool = BackgroundTaskPool(max_workers=2)
        results = []
        pool.submit(lambda: results.append(1))
        pool.shutdown(wait=True)
        self.assertEqual(results, [1])

    def test_exception_in_task(self):
        pool = BackgroundTaskPool(max_workers=1)
        future = pool.submit(lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            future.result(timeout=5)
        pool.shutdown()


if __name__ == '__main__':
    unittest.main()
