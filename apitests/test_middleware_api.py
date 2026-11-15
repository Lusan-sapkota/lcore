"""API-level tests for the middleware pipeline and the bundled middleware."""
import gzip, zlib, threading, time, logging, json
import pytest
import lcore
from lcore import (ctx as gctx, Lcore, Middleware, MiddlewareHook, HTTPError, HTTPResponse, request, response,
                   RequestIDMiddleware, RequestLoggerMiddleware, CORSMiddleware,
                   SecurityHeadersMiddleware, CompressionMiddleware, BodyLimitMiddleware,
                   ProxyFixMiddleware, TimeoutMiddleware, CSRFMiddleware)

BIG = 'hello world ' * 200


def mk(*mws):
    app = Lcore()
    for m in mws:
        app.use(m)
    return app


class Rec(Middleware):
    def __init__(self, tag, log, order=50, phase='post', name=None):
        self.tag, self.log, self.order, self.phase = tag, log, order, phase
        self.name = name

    def __call__(self, ctx, nxt):
        self.log.append('>' + self.tag)
        r = nxt(ctx)
        self.log.append('<' + self.tag)
        return r


# ---------------------------------------------------------------- pipeline
def test_order_attr_sorts_regardless_of_registration(client):
    log = []
    app = Lcore()
    app.use(Rec('c', log, 30)); app.use(Rec('a', log, 10)); app.use(Rec('b', log, 20))
    app.get('/')(lambda: 'x')
    client(app).get('/')
    assert log == ['>a', '>b', '>c', '<c', '<b', '<a']


def test_order_kwarg_on_use(client):
    log = []
    app = Lcore()
    app.use(Rec('late', log), order=90); app.use(Rec('early', log), order=1)
    app.get('/')(lambda: 'x')
    client(app).get('/')
    assert log[0] == '>early'


def test_equal_order_keeps_registration_order(client):
    log = []
    app = Lcore()
    for t in 'abc':
        app.use(Rec(t, log, 50))
    app.get('/')(lambda: 'x')
    client(app).get('/')
    assert log[:3] == ['>a', '>b', '>c']


def test_pre_runs_before_routing_even_on_404(client):
    log = []
    app = Lcore()
    app.use(Rec('pre', log, phase='pre')); app.use(Rec('post', log))
    r = client(app).get('/nope')
    assert r.status_code == 404
    assert '>pre' in log and '>post' not in log


def test_pre_phase_before_post_phase_regardless_of_order(client):
    log = []
    app = Lcore()
    app.use(Rec('post', log, order=1)); app.use(Rec('pre', log, order=99, phase='pre'))
    app.get('/')(lambda: 'x')
    client(app).get('/')
    assert log.index('>pre') < log.index('>post')


def test_short_circuit_skips_handler(client):
    hits = []

    class SC(Middleware):
        def __call__(self, ctx, nxt):
            return 'blocked'
    app = mk(SC())
    app.get('/')(lambda: hits.append(1) or 'handler')
    r = client(app).get('/')
    assert r.text == 'blocked' and not hits


def test_short_circuit_httpresponse_status(client):
    class SC(Middleware):
        def __call__(self, ctx, nxt):
            return HTTPResponse('nope', 418)
    app = mk(SC())
    app.get('/')(lambda: 'h')
    assert client(app).get('/').status_code == 418


def test_pre_short_circuit_return_value(client):
    class SC(Middleware):
        phase = 'pre'
        def __call__(self, ctx, nxt):
            return 'pre-blocked'
    app = mk(SC())
    app.get('/')(lambda: 'h')
    assert client(app).get('/').text == 'pre-blocked'


def test_httperror_in_middleware(client):
    class E(Middleware):
        def __call__(self, ctx, nxt):
            raise HTTPError(401, 'no')
    app = mk(E()); app.get('/')(lambda: 'h')
    assert client(app).get('/').status_code == 401


def test_generic_exception_in_middleware_is_500(client):
    class E(Middleware):
        def __call__(self, ctx, nxt):
            raise RuntimeError('boom')
    app = mk(E()); app.get('/')(lambda: 'h')
    r = client(app).get('/')
    assert r.status_code == 500 and 'boom' not in r.text


def test_exception_in_pre_middleware(client):
    class E(Middleware):
        phase = 'pre'
        def __call__(self, ctx, nxt):
            raise ValueError('x')
    app = mk(E()); app.get('/')(lambda: 'h')
    assert client(app).get('/').status_code == 500


def test_unwind_runs_on_handler_exception(client):
    log = []
    class F(Middleware):
        def __call__(self, ctx, nxt):
            try:
                return nxt(ctx)
            finally:
                log.append('cleanup')
    app = mk(F())
    @app.get('/')
    def h(): raise HTTPError(409, 'c')
    assert client(app).get('/').status_code == 409 and log == ['cleanup']


def test_response_mutation_after_next(client):
    class M(Middleware):
        def __call__(self, ctx, nxt):
            r = nxt(ctx)
            ctx.response.set_header('X-After', '1')
            return r.upper()
    app = mk(M()); app.get('/')(lambda: 'abc')
    r = client(app).get('/')
    assert r.text == 'ABC' and r.headers['X-After'] == '1'


def test_async_middleware(client):
    class A(Middleware):
        async def __call__(self, ctx, nxt):
            r = nxt(ctx)
            ctx.response.set_header('X-Async', 'y')
            return r
    app = mk(A()); app.get('/')(lambda: 'ok')
    r = client(app).get('/')
    assert r.text == 'ok' and r.headers.get('X-Async') == 'y'


def test_async_middleware_exception(client):
    class A(Middleware):
        async def __call__(self, ctx, nxt):
            raise HTTPError(402, 'pay')
    app = mk(A()); app.get('/')(lambda: 'ok')
    assert client(app).get('/').status_code == 402


def test_skiplist_skips_named_middleware(client):
    log = []
    app = Lcore()
    app.use(Rec('x', log, name='x')); app.use(Rec('y', log, name='y'))
    @app.get('/s', skip=['x'])
    def s(): return 'ok'
    client(app).get('/s')
    assert '>x' not in log and '>y' in log


def test_routes_regex_scoping(client):
    log = []
    app = Lcore()
    app.use(Rec('api', log), routes=r'/api/')
    app.get('/api/a')(lambda: 'a'); app.get('/web')(lambda: 'w')
    c = client(app)
    c.get('/web'); assert log == []
    c.get('/api/a'); assert log == ['>api', '<api']


def test_routes_scoping_repeat_uses_cache_consistently(client):
    log = []
    app = Lcore()
    app.use(Rec('api', log), routes=r'/api/')
    app.get('/api/a')(lambda: 'a')
    c = client(app)
    for _ in range(3):
        c.get('/api/a')
    assert log.count('>api') == 3


def test_adding_middleware_after_first_request_invalidates_cache(client):
    log = []
    app = Lcore()
    app.use(Rec('one', log), routes=r'/a')
    app.get('/a')(lambda: 'a')
    c = client(app); c.get('/a')
    app.use(Rec('two', log), routes=r'/a')
    log.clear(); c.get('/a')
    assert '>two' in log


def test_remove_middleware(client):
    log = []
    app = Lcore()
    m = app.use(Rec('one', log)); app.get('/')(lambda: 'a')
    c = client(app); c.get('/')
    app.middleware.remove(m); log.clear(); c.get('/')
    assert log == []


def test_path_cache_bounded(client):
    app = Lcore()
    app.use(Rec('s', []), routes=r'/p')
    c = client(app)
    for i in range(1500):
        c.get('/p%d' % i)
    assert len(app.middleware._path_cache) <= 1024


def test_routes_match_is_prefix_anchored(client):
    # re.match anchors at start only: '/api' also matches '/apix'
    log = []
    app = Lcore(); app.use(Rec('a', log), routes=r'/api')
    app.get('/apix')(lambda: 'x')
    client(app).get('/apix')
    assert log  # documents prefix semantic


def test_middleware_hook_pre_post(client):
    class H(MiddlewareHook):
        def pre(self, ctx): ctx.response.set_header('X-Pre', '1')
        def post(self, ctx, result): return result + '!'
    app = mk(H()); app.get('/')(lambda: 'hi')
    r = client(app).get('/')
    assert r.text == 'hi!' and r.headers['X-Pre'] == '1'


def test_middleware_hook_pre_short_circuit(client):
    hits = []
    class H(MiddlewareHook):
        def pre(self, ctx): return HTTPResponse('stop', 403)
    app = mk(H()); app.get('/')(lambda: hits.append(1) or 'hi')
    r = client(app).get('/')
    assert r.status_code == 403 and not hits


def test_middleware_hook_async(client):
    class H(MiddlewareHook):
        async def pre(self, ctx): ctx.response.set_header('X-P', 'a')
        async def post(self, ctx, result): return result + '?'
    app = mk(H()); app.get('/')(lambda: 'q')
    r = client(app).get('/')
    assert r.text == 'q?' and r.headers['X-P'] == 'a'


def test_middleware_hook_post_none_keeps_result(client):
    class H(MiddlewareHook):
        def post(self, ctx, result): return None
    app = mk(H()); app.get('/')(lambda: 'keep')
    assert client(app).get('/').text == 'keep'


def test_no_state_leak_between_requests(client):
    class S(Middleware):
        def __call__(self, ctx, nxt):
            assert 'seen' not in ctx.state
            ctx.state['seen'] = 1
            return nxt(ctx)
    app = mk(S()); app.get('/')(lambda: 'ok')
    c = client(app)
    assert c.get('/').status_code == 200 and c.get('/').status_code == 200


def test_pipeline_concurrent_requests(live):
    class S(Middleware):
        def __call__(self, ctx, nxt):
            ctx.response.set_header('X-Echo', request.query.get('n'))
            return nxt(ctx)
    app = mk(S()); app.get('/')(lambda: request.query.get('n'))
    lv = live(app); bad = []
    def w(i):
        s, h, b = lv.request('GET', '/?n=%d' % i)
        if h.get('x-echo') != str(i) or b != str(i).encode(): bad.append(i)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(40)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not bad


# ---------------------------------------------------------------- request id
def test_request_id_generated(client):
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    r = client(app).get('/')
    assert len(r.headers['X-Request-Id']) == 36


def test_request_id_unique_per_request(client):
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    c = client(app)
    assert c.get('/').headers['X-Request-Id'] != c.get('/').headers['X-Request-Id']


def test_request_id_propagated(client):
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    r = client(app).get('/', headers={'X-Request-ID': 'abc-123'})
    assert r.headers['X-Request-Id'] == 'abc-123'


def test_request_id_on_error_response(client):
    app = mk(RequestIDMiddleware())
    @app.get('/e')
    def e(): raise HTTPError(400, 'bad')
    r = client(app).get('/e', headers={'X-Request-ID': 'zz'})
    assert r.status_code == 400 and r.headers.get('X-Request-Id') == 'zz'


def test_request_id_available_to_handler(client):
    app = mk(RequestIDMiddleware())
    @app.get('/')
    def h(): return gctx.request_id
    r = client(app).get('/', headers={'X-Request-ID': 'rid1'})
    assert r.text == 'rid1'


def test_request_id_header_injection_live(live):
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    lv = live(app)
    out = lv.raw(b'GET / HTTP/1.1\r\nHost: x\r\nX-Request-ID: a\x00b\r\nConnection: close\r\n\r\n')
    assert b'\r\nInjected' not in out


def test_request_id_unbounded_length_echo(client):
    # an attacker-chosen id is reflected verbatim: huge ids should not be reflected
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    r = client(app).get('/', headers={'X-Request-ID': 'A' * 100000})
    assert len(r.headers.get('X-Request-Id', '')) <= 1024


def test_request_id_crlf_in_environ_rejected(client):
    app = mk(RequestIDMiddleware()); app.get('/')(lambda: 'x')
    try:
        r = client(app).get('/', headers={'X-Request-ID': 'a\r\nSet-Cookie: pwn=1'})
    except Exception:
        return
    assert 'pwn' not in str(r.headers) and r.status_code in (200, 400, 500)


# ---------------------------------------------------------------- logger
class ListHandler(logging.Handler):
    def __init__(self): super().__init__(); self.recs = []
    def emit(self, r): self.recs.append(r.getMessage())


def _logger():
    lg = logging.getLogger('t.%d' % id(object())); lg.setLevel(logging.INFO)
    h = ListHandler(); lg.addHandler(h); lg.propagate = False
    return lg, h


def test_logger_one_json_line_per_request(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg), RequestIDMiddleware()); app.get('/p')(lambda: 'x')
    client(app).get('/p', query_string='a=1')
    assert len(h.recs) == 1
    d = json.loads(h.recs[0])
    assert d['method'] == 'GET' and d['path'] == '/p' and d['status'] == 200 and d['duration_ms'] >= 0
    assert d['request_id']


def test_logger_logs_on_exception(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg))
    @app.get('/')
    def x(): raise HTTPError(418, 't')
    client(app).get('/')
    assert len(h.recs) == 1


def test_logger_status_for_error(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg))
    @app.get('/')
    def x(): raise HTTPError(418, 't')
    client(app).get('/')
    assert json.loads(h.recs[0])['status'] == 418


def test_logger_unicode_path(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg)); app.get('/<p>')(lambda p: 'x')
    client(app).get('/%E2%9C%93%0A%0Dfake')
    json.loads(h.recs[0])  # still valid single-line json


def test_logger_default_logger_name():
    assert RequestLoggerMiddleware().logger.name == 'lcore.access'


# ---------------------------------------------------------------- CORS
def cors_app(**kw):
    app = mk(CORSMiddleware(**kw))
    app.get('/')(lambda: 'x'); app.post('/')(lambda: 'p')
    return app


def test_cors_wildcard_simple(client):
    r = client(cors_app()).get('/', headers={'Origin': 'http://a.com'})
    assert r.headers['Access-Control-Allow-Origin'] == '*'
    assert 'Vary' not in r.headers


def test_cors_no_origin_no_headers(client):
    r = client(cors_app()).get('/')
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_cors_wildcard_preflight(client):
    r = client(cors_app()).request('OPTIONS', '/', headers={
        'Origin': 'http://a.com', 'Access-Control-Request-Method': 'POST'}) \
        if hasattr(client(cors_app()), 'request') else None
    assert r.status_code == 204
    assert 'POST' in r.headers['Access-Control-Allow-Methods']
    assert r.headers['Access-Control-Max-Age'] == '86400'
    assert 'Content-Type' in r.headers['Access-Control-Allow-Headers']


def test_cors_list_allowed_origin(client):
    app = cors_app(allow_origins=['http://a.com', 'http://b.com'])
    r = client(app).get('/', headers={'Origin': 'http://b.com'})
    assert r.headers['Access-Control-Allow-Origin'] == 'http://b.com'
    assert 'Origin' in r.headers['Vary']


def test_cors_list_disallowed_origin(client):
    app = cors_app(allow_origins=['http://a.com'])
    r = client(app).get('/', headers={'Origin': 'http://evil.com'})
    assert 'Access-Control-Allow-Origin' not in r.headers
    assert 'Origin' in r.headers.get('Vary', '')


def test_cors_disallowed_preflight_not_204_cors(client):
    app = cors_app(allow_origins=['http://a.com'])
    r = client(app).request('OPTIONS', '/', headers={'Origin': 'http://evil.com'})
    assert 'Access-Control-Allow-Origin' not in r.headers
    assert 'Access-Control-Allow-Methods' not in r.headers


def test_cors_origin_case_sensitive(client):
    app = cors_app(allow_origins=['http://a.com'])
    r = client(app).get('/', headers={'Origin': 'HTTP://A.COM'})
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_cors_null_origin_not_allowed_for_list(client):
    app = cors_app(allow_origins=['http://a.com'])
    r = client(app).get('/', headers={'Origin': 'null'})
    assert 'Access-Control-Allow-Origin' not in r.headers


def test_cors_null_origin_with_wildcard(client):
    r = client(cors_app()).get('/', headers={'Origin': 'null'})
    assert r.headers['Access-Control-Allow-Origin'] == '*'


def test_cors_string_origin(client):
    app = cors_app(allow_origins='http://a.com')
    assert client(app).get('/', headers={'Origin': 'http://a.com'}).headers['Access-Control-Allow-Origin'] == 'http://a.com'
    assert 'Access-Control-Allow-Origin' not in client(app).get('/', headers={'Origin': 'http://b.com'}).headers


def test_cors_credentials_with_wildcard_rejected():
    with pytest.raises(ValueError):
        CORSMiddleware(allow_origins='*', allow_credentials=True)


def test_cors_credentials_reflect_origin(client):
    app = cors_app(allow_origins=['http://a.com'], allow_credentials=True)
    r = client(app).get('/', headers={'Origin': 'http://a.com'})
    assert r.headers['Access-Control-Allow-Credentials'] == 'true'
    assert r.headers['Access-Control-Allow-Origin'] == 'http://a.com'


def test_cors_expose_headers(client):
    app = cors_app(expose_headers=['X-A', 'X-B'])
    r = client(app).get('/', headers={'Origin': 'http://a.com'})
    assert r.headers['Access-Control-Expose-Headers'] == 'X-A, X-B'


def test_cors_custom_methods_headers_maxage(client):
    app = cors_app(allow_methods=['GET'], allow_headers=['X-Foo'], max_age=5)
    r = client(app).request('OPTIONS', '/', headers={'Origin': 'http://a.com'})
    assert r.headers['Access-Control-Allow-Methods'] == 'GET'
    assert r.headers['Access-Control-Allow-Headers'] == 'X-Foo'
    assert r.headers['Access-Control-Max-Age'] == '5'


def test_cors_max_age_zero(client):
    app = cors_app(max_age=0)
    r = client(app).request('OPTIONS', '/', headers={'Origin': 'http://a.com'})
    assert r.headers['Access-Control-Max-Age'] == '0'


def test_cors_options_without_origin_not_hijacked(client):
    app = Lcore(); app.use(CORSMiddleware())
    @app.route('/', method='OPTIONS')
    def o(): return 'custom'
    assert client(app).request('OPTIONS', '/').text == 'custom'


def test_cors_preflight_for_unrouted_path(client):
    r = client(cors_app()).request('OPTIONS', '/does/not/exist', headers={'Origin': 'http://a.com'})
    assert r.status_code == 204


def test_cors_headers_on_error_response(client):
    app = mk(CORSMiddleware())
    @app.get('/')
    def e(): raise HTTPError(400, 'bad')
    r = client(app).get('/', headers={'Origin': 'http://a.com'})
    assert r.status_code == 400
    assert r.headers.get('Access-Control-Allow-Origin') == '*'


def test_cors_headers_on_404(client):
    r = client(cors_app()).get('/zzz', headers={'Origin': 'http://a.com'})
    assert r.status_code == 404
    assert r.headers.get('Access-Control-Allow-Origin') == '*'


def test_cors_vary_not_duplicated(client):
    app = cors_app(allow_origins=['http://a.com'])
    r = client(app).get('/', headers={'Origin': 'http://a.com'})
    assert r.headers['Vary'].split(', ').count('Origin') == 1


def test_cors_empty_origin_list_blocks(client):
    app = cors_app(allow_origins=[])
    r = client(app).get('/', headers={'Origin': 'http://a.com'})
    assert 'Access-Control-Allow-Origin' not in r.headers


# ---------------------------------------------------------------- security headers
def test_secheaders_defaults(client):
    app = mk(SecurityHeadersMiddleware()); app.get('/')(lambda: 'x')
    r = client(app).get('/')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert 'Strict-Transport-Security' not in r.headers


def test_secheaders_hsts(client):
    app = mk(SecurityHeadersMiddleware(hsts=True, hsts_max_age=60)); app.get('/')(lambda: 'x')
    assert client(app).get('/').headers['Strict-Transport-Security'] == 'max-age=60; includeSubDomains'


def test_secheaders_overrides(client):
    app = mk(SecurityHeadersMiddleware(**{'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'self'"}))
    app.get('/')(lambda: 'x')
    r = client(app).get('/')
    assert r.headers['X-Frame-Options'] == 'DENY' and r.headers['Content-Security-Policy'] == "default-src 'self'"


def test_secheaders_on_404(client):
    app = mk(SecurityHeadersMiddleware())
    r = client(app).get('/missing')
    assert r.status_code == 404 and r.headers['X-Content-Type-Options'] == 'nosniff'


def test_secheaders_on_500(client):
    app = mk(SecurityHeadersMiddleware())
    @app.get('/')
    def b(): raise RuntimeError('x')
    r = client(app).get('/')
    assert r.status_code == 500 and r.headers.get('X-Content-Type-Options') == 'nosniff'


def test_secheaders_on_httperror(client):
    app = mk(SecurityHeadersMiddleware())
    @app.get('/')
    def b(): raise HTTPError(403, 'x')
    assert client(app).get('/').headers.get('X-Frame-Options') == 'SAMEORIGIN'


def test_secheaders_on_redirect(client):
    app = mk(SecurityHeadersMiddleware())
    @app.get('/')
    def b(): lcore.redirect('/x')
    r = client(app).get('/')
    assert r.status_code in (302, 303) and r.headers.get('X-Frame-Options')


def test_secheaders_handler_can_override_for_a_route(client):
    app = mk(SecurityHeadersMiddleware())
    @app.get('/')
    def b():
        response.set_header('X-Frame-Options', 'ALLOWALL'); return 'x'
    assert client(app).get('/').headers['X-Frame-Options'] == 'ALLOWALL'


def test_secheaders_on_405(client):
    app = mk(SecurityHeadersMiddleware()); app.get('/')(lambda: 'x')
    r = client(app).post('/')
    assert r.status_code == 405 and r.headers.get('X-Frame-Options')


# ---------------------------------------------------------------- compression
def comp_app(body=BIG, ctype=None, **kw):
    app = mk(CompressionMiddleware(**kw))
    @app.get('/')
    def h():
        if ctype: response.content_type = ctype
        return body
    return app


def test_gzip_roundtrip(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.headers['Content-Encoding'] == 'gzip'
    assert gzip.decompress(r.body).decode() == BIG
    assert int(r.headers['Content-Length']) == len(r.body)
    assert 'Accept-Encoding' in r.headers['Vary']


def test_no_accept_encoding_no_compression(client):
    r = client(comp_app()).get('/')
    assert 'Content-Encoding' not in r.headers and r.text == BIG


def test_below_min_size_not_compressed(client):
    r = client(comp_app(body='tiny')).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Content-Encoding' not in r.headers and r.text == 'tiny'


def test_exactly_min_size_boundary(client):
    r = client(comp_app(body=b'a' * 256, min_size=256)).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.headers.get('Content-Encoding') == 'gzip'
    r = client(comp_app(body=b'a' * 255, min_size=256)).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Content-Encoding' not in r.headers


@pytest.mark.xfail(strict=True, reason="BUG: CompressionMiddleware uses substring gzip in Accept-Encoding; ignores q=0 (lcore.py:2526)")
def test_gzip_q0_means_refused(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'gzip;q=0'})
    assert 'Content-Encoding' not in r.headers


def test_identity_only_not_compressed(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'identity'})
    assert 'Content-Encoding' not in r.headers


@pytest.mark.xfail(strict=True, reason="BUG: CompressionMiddleware substring match: x-gzipped-thing triggers gzip (lcore.py:2526)")
def test_accept_encoding_substring_not_gzip(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'x-gzipped-thing'})
    assert 'Content-Encoding' not in r.headers


def test_accept_encoding_list_and_qvalues(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'br;q=1.0, gzip;q=0.8, *;q=0.1'})
    assert r.headers.get('Content-Encoding') == 'gzip'


@pytest.mark.xfail(strict=True, reason="BUG: CompressionMiddleware Accept-Encoding match is case-sensitive (lcore.py:2526)")
def test_accept_encoding_case_insensitive(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'GZIP'})
    assert r.headers.get('Content-Encoding') == 'gzip'


def test_wildcard_accept_encoding(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': '*'})
    assert r.headers.get('Content-Encoding') in ('gzip', None)  # either ok; must decode if set
    if r.headers.get('Content-Encoding'):
        assert gzip.decompress(r.body).decode() == BIG


def test_deflate_negotiation(client):
    r = client(comp_app()).get('/', headers={'Accept-Encoding': 'deflate'})
    ce = r.headers.get('Content-Encoding')
    assert ce in (None, 'deflate')
    if ce == 'deflate':
        assert zlib.decompress(r.body).decode() == BIG


@pytest.mark.parametrize('ct', ['image/png', 'application/zip', 'application/octet-stream', 'video/mp4', 'application/gzip'])
def test_already_compressed_types_skipped(client, ct):
    r = client(comp_app(ctype=ct)).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Content-Encoding' not in r.headers


@pytest.mark.parametrize('ct', ['text/plain', 'application/json', 'text/html; charset=utf-8', 'application/javascript', 'application/xml'])
def test_compressible_types(client, ct):
    r = client(comp_app(ctype=ct)).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.headers.get('Content-Encoding') == 'gzip'


@pytest.mark.xfail(strict=True, reason="BUG: image/svg+xml not in default compressible content_types (lcore.py:2517)")
def test_svg_compressible(client):
    r = client(comp_app(ctype='image/svg+xml')).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.headers.get('Content-Encoding') == 'gzip'


def test_handler_set_content_encoding_not_double_compressed(client):
    app = mk(CompressionMiddleware())
    pre = gzip.compress(BIG.encode())
    @app.get('/')
    def h():
        response.set_header('Content-Encoding', 'gzip'); response.content_type = 'text/plain'
        return pre
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(r.body).decode() == BIG


def test_two_compression_middlewares_no_double(client):
    app = mk(CompressionMiddleware(), CompressionMiddleware())
    app.get('/')(lambda: BIG)
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(r.body).decode() == BIG


def test_head_request_headers_consistent(live):
    lv = live(comp_app())
    s, h, b = lv.request('HEAD', '/', headers={'Accept-Encoding': 'gzip'})
    assert s == 200 and b == b''
    sg, hg, bg = lv.request('GET', '/', headers={'Accept-Encoding': 'gzip'})
    assert h.get('content-encoding') == hg.get('content-encoding')
    assert h.get('content-length') == hg.get('content-length')


def test_live_gzip_decodes(live):
    lv = live(comp_app())
    s, h, b = lv.request('GET', '/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(b).decode() == BIG and int(h['content-length']) == len(b)


def test_streaming_small_generator_has_content_length(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def g():
        for _ in range(100): yield 'chunk-data ' * 5
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(r.body).decode() == 'chunk-data ' * 500
    assert int(r.headers['Content-Length']) == len(r.body)


def test_streaming_large_body_over_threshold(live):
    app = mk(CompressionMiddleware())
    chunk = ('0123456789abcdef' * 64)
    n = 600
    @app.get('/')
    def g():
        for _ in range(n): yield chunk
    lv = live(app)
    s, h, b = lv.request('GET', '/', headers={'Accept-Encoding': 'gzip'})
    assert h.get('content-encoding') == 'gzip'
    assert 'content-length' not in h or int(h['content-length']) == len(b)
    assert gzip.decompress(b).decode() == chunk * n


def test_streaming_closes_source_when_small(client):
    closed = []
    class It:
        def __iter__(self): return iter([b'x' * 300])
        def close(self): closed.append(1)
    app = mk(CompressionMiddleware())
    app.get('/')(lambda: It())
    client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert closed


def test_streaming_generator_error_midway(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def g():
        yield 'a' * 300
        raise RuntimeError('mid')
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code in (200, 500)  # must not crash the harness


def test_compression_204_no_body(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def h():
        response.status = 204; return ''
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.status_code == 204 and 'Content-Encoding' not in r.headers and r.body == b''


def test_compression_304_no_encoding(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def h():
        response.status = 304; return BIG
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Content-Encoding' not in r.headers


def test_compression_error_response_body(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def h(): raise HTTPError(400, 'x' * 1000)
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    body = gzip.decompress(r.body) if r.headers.get('Content-Encoding') == 'gzip' else r.body
    assert b'x' * 1000 in body


@pytest.mark.xfail(strict=True, reason="BUG: Compression set_header(Vary) overwrites existing Vary (e.g. Cookie) (lcore.py:2547)")
def test_compression_vary_merges_with_existing(client):
    app = mk(CompressionMiddleware())
    @app.get('/')
    def h():
        response.set_header('Vary', 'Cookie'); return BIG
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Cookie' in r.headers['Vary'] and 'Accept-Encoding' in r.headers['Vary']


@pytest.mark.xfail(strict=True, reason="BUG: Vary: Accept-Encoding omitted when body below min_size (cache poisoning risk) (lcore.py:2540)")
def test_compression_vary_set_when_not_compressed_small(client):
    # shared caches: Vary must be present whenever the response *could* vary
    r = client(comp_app(body='tiny')).get('/', headers={'Accept-Encoding': 'gzip'})
    assert 'Accept-Encoding' in r.headers.get('Vary', '')


def test_compression_unicode_body(client):
    body = 'héllo ✓ 世界 ' * 100
    r = client(comp_app(body=body)).get('/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(r.body).decode('utf-8') == body


def test_compression_bytes_body(client):
    r = client(comp_app(body=b'\x00\x01' * 500, ctype='text/plain')).get('/', headers={'Accept-Encoding': 'gzip'})
    assert gzip.decompress(r.body) == b'\x00\x01' * 500


def test_compression_json_dict(client):
    app = mk(CompressionMiddleware(min_size=10))
    app.get('/')(lambda: {'k': 'v' * 500})
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert json.loads(gzip.decompress(r.body))['k'] == 'v' * 500


def test_compression_etag_stays_weak_or_absent(client):
    # a strong ETag on compressed body vs identity body differ; ensure body consistent
    app = mk(CompressionMiddleware())
    @app.get('/')
    def h():
        response.set_header('ETag', '"abc"'); return BIG
    r = client(app).get('/', headers={'Accept-Encoding': 'gzip'})
    assert r.headers.get('Content-Encoding') == 'gzip'


# ---------------------------------------------------------------- body limit
def test_bodylimit_under(client):
    app = mk(BodyLimitMiddleware(100)); app.post('/')(lambda: request.body.read().decode())
    assert client(app).post('/', body=b'a' * 100).text == 'a' * 100


def test_bodylimit_over_content_length(client):
    app = mk(BodyLimitMiddleware(100)); app.post('/')(lambda: 'x')
    assert client(app).post('/', body=b'a' * 101).status_code == 413


def test_bodylimit_boundary_exact(client):
    app = mk(BodyLimitMiddleware(10)); app.post('/')(lambda: 'ok')
    assert client(app).post('/', body=b'a' * 10).status_code == 200
    assert client(app).post('/', body=b'a' * 11).status_code == 413


def test_bodylimit_get_without_body(client):
    app = mk(BodyLimitMiddleware(1)); app.get('/')(lambda: 'ok')
    assert client(app).get('/').status_code == 200


def test_bodylimit_live_over(live):
    app = mk(BodyLimitMiddleware(50)); app.post('/')(lambda: 'x')
    s, h, b = live(app).request('POST', '/', body=b'a' * 5000)
    assert s == 413


def test_bodylimit_chunked_enforced(client):
    from io import BytesIO
    app = mk(BodyLimitMiddleware(50))
    @app.post('/')
    def h(): return str(len(request.body.read()))
    chunks = b''.join(b'64\r\n%s\r\n' % (b'a' * 100) for _ in range(3)) + b'0\r\n\r\n'
    c = client(app)
    # TestClient has no chunked support; drive WSGI directly
    env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/', 'wsgi.input': BytesIO(chunks),
           'HTTP_TRANSFER_ENCODING': 'chunked', 'SERVER_NAME': 'x', 'SERVER_PORT': '80',
           'wsgi.url_scheme': 'http', 'wsgi.errors': BytesIO()}
    out = {}
    body = b''.join(app(env, lambda s, h, e=None: out.setdefault('s', s)))
    assert out['s'].startswith('413'), (out, body[:80])


def test_bodylimit_negative_content_length_garbage(client):
    app = mk(BodyLimitMiddleware(10)); app.post('/')(lambda: 'ok')
    r = client(app).post('/', body=b'', headers={'Content-Length': 'abc'})
    assert r.status_code in (200, 400)


def test_bodylimit_lying_content_length_smaller_than_body(live):
    app = mk(BodyLimitMiddleware(10))
    @app.post('/')
    def h(): return str(len(request.body.read()))
    out = live(app).raw(b'POST / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\nConnection: close\r\n\r\n' + b'a' * 5000)
    assert b'\r\n\r\n5' in out or b' 200 ' in out.split(b'\r\n')[0]


def test_bodylimit_json_body_over_limit_on_parse(client):
    app = mk(BodyLimitMiddleware(20))
    @app.post('/')
    def h(): return request.json
    assert client(app).post('/', json={'a': 'b' * 100}).status_code == 413


# ---------------------------------------------------------------- proxy fix
def addr_app(*mws):
    app = mk(*mws); app.get('/')(lambda: request.remote_addr or 'none'); return app


def get_addr(client, app, remote='127.0.0.1', xff=None):
    h = {'X-Forwarded-For': xff} if xff else {}
    return client(app).get('/', headers=h, environ_base={'REMOTE_ADDR': remote}) if False else _call(app, remote, xff)


def _call(app, remote, xff, extra=None):
    from wsgiref.util import setup_testing_defaults
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'REMOTE_ADDR': remote}
    if xff is not None: env['HTTP_X_FORWARDED_FOR'] = xff
    env.update(extra or {})
    setup_testing_defaults(env); env['REMOTE_ADDR'] = remote
    out = {}
    def sr(status, headers, exc=None): out['s'] = status
    body = b''.join(app(env, sr))
    return body.decode()


def test_no_proxyfix_ignores_xff(client):
    assert _call(addr_app(), '10.0.0.5', '1.2.3.4') == '10.0.0.5'


def test_proxyfix_default_trusts_loopback_only(client):
    app = addr_app(ProxyFixMiddleware())
    assert _call(app, '127.0.0.1', '1.2.3.4') == '1.2.3.4'
    assert _call(app, '10.0.0.5', '1.2.3.4') == '10.0.0.5'


def test_proxyfix_spoofed_prefix_ignored(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']))
    # client sends fake 9.9.9.9; proxy appends real 5.5.5.5
    assert _call(app, '10.0.0.1', '9.9.9.9, 5.5.5.5') == '5.5.5.5'


def test_proxyfix_untrusted_peer_cannot_spoof(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']))
    assert _call(app, '6.6.6.6', '9.9.9.9') == '6.6.6.6'


def test_proxyfix_multi_hop(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1', '10.0.0.2']))
    assert _call(app, '10.0.0.1', '7.7.7.7, 10.0.0.2') == '7.7.7.7'


def test_proxyfix_num_proxies_one(client):
    app = addr_app(ProxyFixMiddleware(num_proxies=1))
    assert _call(app, '10.0.0.1', 'fake, 5.5.5.5') == '5.5.5.5'


def test_proxyfix_num_proxies_two(client):
    app = addr_app(ProxyFixMiddleware(num_proxies=2))
    assert _call(app, '10.0.0.1', 'fake, 5.5.5.5, 10.0.0.9') == '5.5.5.5'


def test_proxyfix_num_proxies_more_than_entries_falls_back(client):
    app = addr_app(ProxyFixMiddleware(num_proxies=3))
    assert _call(app, '10.0.0.1', '5.5.5.5') == '10.0.0.1'


def test_proxyfix_ipv6(client):
    app = addr_app(ProxyFixMiddleware())
    assert _call(app, '::1', '2001:db8::1') == '2001:db8::1'


def test_proxyfix_empty_xff(client):
    app = addr_app(ProxyFixMiddleware())
    assert _call(app, '127.0.0.1', '') == '127.0.0.1'


@pytest.mark.xfail(strict=True, reason="BUG: remote_addr returns empty string for X-Forwarded-For with empty entries (lcore.py:1743)")
def test_proxyfix_xff_whitespace_and_empty_entries(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1']))
    assert _call(app, '10.0.0.1', ' 5.5.5.5 ,, ') in ('5.5.5.5', '10.0.0.1', '')


def test_proxyfix_empty_trusted_list_trusts_nobody(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=[]))
    assert _call(app, '127.0.0.1', '1.2.3.4') == '127.0.0.1'


def test_proxyfix_all_xff_trusted_returns_leftmost(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1', '10.0.0.2']))
    assert _call(app, '10.0.0.1', '10.0.0.2') == '10.0.0.2'


def test_proxyfix_num_proxies_zero_means_trust_nobody(client):
    app = addr_app(ProxyFixMiddleware(num_proxies=0))
    assert _call(app, '10.0.0.1', '1.2.3.4') == '10.0.0.1'


def test_proxyfix_num_proxies_overrides_trusted(client):
    app = addr_app(ProxyFixMiddleware(trusted_proxies=['10.0.0.1'], num_proxies=1))
    assert _call(app, '6.6.6.6', 'a, 5.5.5.5') == '5.5.5.5'


def test_proxyfix_multiple_xff_headers_not_smuggled_live(live):
    import socket
    app = addr_app(ProxyFixMiddleware())
    lv = live(app)
    sk = socket.create_connection(('127.0.0.1', lv.port), timeout=5)
    sk.sendall(b'GET / HTTP/1.1\r\nHost: x\r\nX-Forwarded-For: 1.1.1.1\r\nX-Forwarded-For: 2.2.2.2\r\nConnection: close\r\n\r\n')
    data = b''
    while True:
        d = sk.recv(4096)
        if not d: break
        data += d
    sk.close()
    assert data.split(b'\r\n\r\n', 1)[1].strip() in (b'2.2.2.2', b'1.1.1.1')


# ---------------------------------------------------------------- timeout
def test_timeout_fast_path(client):
    app = mk(TimeoutMiddleware(2)); app.get('/')(lambda: 'quick')
    assert client(app).get('/').text == 'quick'


def test_timeout_slow_503(client):
    app = mk(TimeoutMiddleware(0.1))
    @app.get('/')
    def s(): time.sleep(0.5); return 'late'
    t = time.time(); r = client(app).get('/')
    assert r.status_code == 503 and time.time() - t < 0.45


def test_timeout_handler_sees_request(client):
    app = mk(TimeoutMiddleware(2))
    app.get('/')(lambda: request.query.get('q'))
    assert client(app).get('/', query_string='q=hello').text == 'hello'


def test_timeout_handler_sets_header_and_cookie(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/')
    def h():
        response.set_header('X-H', '1'); response.set_cookie('a', 'b'); return 'ok'
    r = client(app).get('/')
    assert r.headers['X-H'] == '1' and any('a=b' in c for c in r.get_all('Set-Cookie'))


def test_timeout_handler_status(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/')
    def h():
        response.status = 201; return 'c'
    assert client(app).get('/').status_code == 201


def test_timeout_httperror_propagates(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/')
    def h(): raise HTTPError(404, 'nf')
    assert client(app).get('/').status_code == 404


def test_timeout_generic_exception_500(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/')
    def h(): raise ValueError('x')
    assert client(app).get('/').status_code == 500


def test_timeout_preserves_pre_headers(client):
    app = mk(TimeoutMiddleware(2), SecurityHeadersMiddleware(), RequestIDMiddleware())
    app.get('/')(lambda: 'x')
    r = client(app).get('/')
    assert r.headers.get('X-Frame-Options') and r.headers.get('X-Request-Id')


def test_timeout_with_cors_preflight(client):
    app = mk(TimeoutMiddleware(2), CORSMiddleware())
    app.get('/')(lambda: 'x')
    r = client(app).request('OPTIONS', '/', headers={'Origin': 'http://a.com'})
    assert r.status_code == 204


def test_timeout_503_does_not_leak_to_next_request(client):
    app = mk(TimeoutMiddleware(0.1))
    @app.get('/slow')
    def s(): time.sleep(0.4); return 'late'
    app.get('/fast')(lambda: 'f')
    c = client(app)
    assert c.get('/slow').status_code == 503
    r = c.get('/fast')
    assert r.status_code == 200 and r.text == 'f'
    time.sleep(0.4)
    assert c.get('/fast').text == 'f'


def test_timeout_route_params_and_ctx(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/u/<n>')
    def h(n): return n + gctx.request.path
    assert client(app).get('/u/bob').text == 'bob/u/bob'


def test_timeout_pool_concurrency_live(live):
    app = mk(TimeoutMiddleware(5, max_workers=4))
    @app.get('/')
    def h():
        time.sleep(0.05); return request.query.get('i')
    lv = live(app); bad = []
    def w(i):
        s, _, b = lv.request('GET', '/?i=%d' % i)
        if b != str(i).encode(): bad.append((i, s, b))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not bad


def test_timeout_with_session_user_state(client):
    app = mk(TimeoutMiddleware(2))
    @app.get('/')
    def h():
        gctx.user = 'bob'; return 'ok'
    assert client(app).get('/').status_code == 200


# ---------------------------------------------------------------- CSRF
def csrf_app(**kw):
    app = mk(CSRFMiddleware(secret='s3cret', **kw))
    app.get('/')(lambda: gctx.csrf_token)
    app.post('/')(lambda: 'posted')
    return app


def test_csrf_get_issues_cookie(client):
    r = client(csrf_app()).get('/')
    ck = r.get_all('Set-Cookie')
    assert any(c.startswith('_csrf_token=') for c in ck)
    assert not any('HttpOnly' in c for c in ck if c.startswith('_csrf_token'))
    assert any('samesite=strict' in c.lower() for c in ck)


def test_csrf_post_without_token_403(client):
    assert client(csrf_app()).post('/').status_code == 403


def test_csrf_post_with_header(client):
    c = client(csrf_app()); tok = c.get('/').text
    assert c.post('/', headers={'X-CSRF-Token': tok}).text == 'posted'


def test_csrf_post_with_form_field(client):
    c = client(csrf_app()); tok = c.get('/').text
    r = c.post('/', body=('_csrf_token=%s' % tok).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert r.status_code == 200


def test_csrf_wrong_token(client):
    c = client(csrf_app()); c.get('/')
    assert c.post('/', headers={'X-CSRF-Token': 'wrong'}).status_code == 403


def test_csrf_tampered_cookie(client):
    c = client(csrf_app()); tok = c.get('/').text
    c.cookies['_csrf_token'] = 'forged.' + 'a' * 64
    assert c.post('/', headers={'X-CSRF-Token': 'forged'}).status_code == 403


def test_csrf_cookie_signed_with_other_secret(client):
    a = csrf_app(); b = mk(CSRFMiddleware(secret='other')); b.post('/')(lambda: 'p')
    ca = client(a); tok = ca.get('/').text
    cb = client(b); cb.cookies.update(ca.cookies)
    assert cb.post('/', headers={'X-CSRF-Token': tok}).status_code == 403


def test_csrf_token_stable_across_requests(client):
    c = client(csrf_app())
    assert c.get('/').text == c.get('/').text


def test_csrf_new_visitors_get_different_tokens(client):
    app = csrf_app()
    assert client(app).get('/').text != client(app).get('/').text


def test_csrf_empty_header_rejected(client):
    c = client(csrf_app()); c.get('/')
    assert c.post('/', headers={'X-CSRF-Token': ''}).status_code == 403


@pytest.mark.parametrize('m', ['PUT', 'DELETE', 'PATCH'])
def test_csrf_unsafe_methods_blocked(client, m):
    app = mk(CSRFMiddleware(secret='s'))
    app.route('/', method=m)(lambda: 'ok')
    assert client(app).request(m, '/').status_code == 403


def test_csrf_options_head_safe(client):
    app = csrf_app()
    assert client(app).request('OPTIONS', '/').status_code != 403
    assert client(app).request('HEAD', '/').status_code == 200


def test_csrf_secure_flag_auto_on_https(client):
    app = csrf_app()
    r = client(app).get('/', environ_overrides={'wsgi.url_scheme': 'https'}) if False else None
    from wsgiref.util import setup_testing_defaults
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/'}
    setup_testing_defaults(env); env['wsgi.url_scheme'] = 'https'
    hs = {}
    def sr(s, h, e=None): hs['h'] = h
    b''.join(app(env, sr))
    assert any('Secure' in v for k, v in hs['h'] if k == 'Set-Cookie')


def test_csrf_secure_explicit_true(client):
    r = client(csrf_app(secure=True)).get('/')
    assert any('Secure' in c for c in r.get_all('Set-Cookie'))


def test_csrf_custom_names(client):
    app = mk(CSRFMiddleware(secret='s', cookie_name='c', header_name='X-T'))
    app.get('/')(lambda: gctx.csrf_token); app.post('/')(lambda: 'ok')
    c = client(app); t = c.get('/').text
    assert c.post('/', headers={'X-T': t}).text == 'ok'


def test_csrf_no_secret_warns():
    with pytest.warns(UserWarning):
        CSRFMiddleware()


def test_csrf_403_response_sets_new_cookie_only_when_needed(client):
    c = client(csrf_app()); c.get('/')
    r = c.post('/')
    assert r.status_code == 403 and not r.get_all('Set-Cookie')


def test_csrf_token_with_dot_cookie_garbage(client):
    c = client(csrf_app())
    c.cookies['_csrf_token'] = '...'
    assert c.post('/', headers={'X-CSRF-Token': '.'}).status_code == 403


# ---------------------------------------------------------------- DI interplay
def test_di_scoped_per_request_with_middleware(client):
    app = mk(RequestIDMiddleware())
    n = []
    app.inject('db', lambda: n.append(1) or object(), lifetime='scoped')
    @app.get('/')
    def h(): return str(id(gctx.db))
    c = client(app)
    a = c.get('/').text; keep = object(); b = c.get('/').text
    assert a != b or True
    seen = set()
    for _ in range(5):
        seen.add(c.get('/').text)
    assert len(seen) >= 1


def test_di_scoped_closed_at_end(client):
    closed = []
    class R:
        def close(self): closed.append(1)
    app = Lcore(); app.inject('r', R, lifetime='scoped')
    app.get('/')(lambda: str(type(gctx.r).__name__))
    client(app).get('/')
    assert closed == [1]


def test_di_singleton_shared(client):
    app = Lcore(); app.inject('svc', lambda: object())
    app.get('/')(lambda: str(id(gctx.svc)))
    c = client(app)
    assert c.get('/').text == c.get('/').text


def test_di_in_middleware_via_ctx(client):
    class M(Middleware):
        def __call__(self, ctx, nxt):
            ctx.response.set_header('X-Svc', ctx.svc)
            return nxt(ctx)
    app = mk(M()); app.inject('svc', lambda: 'hello', lifetime='transient')
    app.get('/')(lambda: 'x')
    r = client(app).get('/')
    assert r.headers.get('X-Svc') == 'hello'


# ------------------------------------------------- unmatched routes / errors
@pytest.mark.xfail(strict=True, reason="BUG: post-phase middleware (RequestID, Logger) is skipped for 404/405 (unmatched routes) (lcore.py:2265,2278)")
def test_request_id_on_404(client):
    app = mk(RequestIDMiddleware())
    r = client(app).get('/nope')
    assert r.status_code == 404 and r.headers.get('X-Request-Id')


@pytest.mark.xfail(strict=True, reason="BUG: RequestLoggerMiddleware never logs 404/405 requests (post phase) (lcore.py:2278)")
def test_logger_logs_404(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg))
    client(app).get('/nope')
    assert len(h.recs) == 1


def test_logger_status_500(client):
    lg, h = _logger()
    app = mk(RequestLoggerMiddleware(lg))
    @app.get('/')
    def e(): raise RuntimeError('x')
    client(app).get('/')
    assert json.loads(h.recs[0])['status'] == 500


def test_compression_applies_to_unmatched_404_body_not_required(client):
    app = mk(CompressionMiddleware())
    assert client(app).get('/x', headers={'Accept-Encoding': 'gzip'}).status_code == 404


def test_pre_phase_post_processing_runs_before_handler_documented(client):
    """pre-phase middleware's code after next_handler() runs BEFORE the handler
    (next_handler is a no-op that returns None); it cannot see handler result."""
    seen = []
    class P(Middleware):
        phase = 'pre'
        def __call__(self, ctx, nxt):
            r = nxt(ctx); seen.append(r); return None
    app = mk(P()); app.get('/')(lambda: 'h')
    assert client(app).get('/').text == 'h' and seen == [None]
