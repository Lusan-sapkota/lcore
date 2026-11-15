"""API-level tests: rate_limit, auth_basic, password hashing, validate_request,
cookie signing, injection/traversal vectors and raw-socket probes."""
import base64, dataclasses, os, socket, threading, time
from typing import Optional, List
import pytest
import lcore
from lcore import (Lcore, HTTPError, request, response, rate_limit, auth_basic, hash_password,
                   verify_password, validate_request, RateLimitBackend, ProxyFixMiddleware,
                   static_file, json_dumps)


def ip_app(limit=3, per=3600, **kw):
    app = Lcore()
    app.use(ProxyFixMiddleware(num_proxies=1))
    @app.get('/')
    @rate_limit(limit, per, single_process=True, **kw)
    def h(): return 'ok'
    return app


def hit(c, ip='1.1.1.1'):
    return c.get('/', headers={'X-Forwarded-For': ip}).status_code


# ---------------------------------------------------------------- rate limit
def test_rl_exact_boundary(client):
    c = client(ip_app(3))
    assert [hit(c) for _ in range(5)] == [200, 200, 200, 429, 429]


def test_rl_limit_one(client):
    c = client(ip_app(1))
    assert [hit(c) for _ in range(2)] == [200, 429]


def test_rl_per_ip_isolation(client):
    c = client(ip_app(2))
    assert [hit(c, 'a'), hit(c, 'a'), hit(c, 'a'), hit(c, 'b'), hit(c, 'b'), hit(c, 'b')] == [200, 200, 429, 200, 200, 429]


def test_rl_refill_over_time(client):
    c = client(ip_app(5, per=1))
    for _ in range(5): assert hit(c) == 200
    assert hit(c) == 429
    time.sleep(0.45)  # ~2 tokens
    assert hit(c) == 200


def test_rl_refill_capped_at_limit(client):
    c = client(ip_app(2, per=0.2))
    time.sleep(0.6)
    assert [hit(c) for _ in range(3)] == [200, 200, 429]


def test_rl_429_body_and_status(client):
    c = client(ip_app(1)); hit(c)
    r = c.get('/', headers={'X-Forwarded-For': '1.1.1.1'})
    assert r.status_code == 429


def test_rl_xff_ignored_without_proxyfix(client):
    app = Lcore()
    @app.get('/')
    @rate_limit(2, 3600, single_process=True)
    def h(): return 'ok'
    c = client(app)
    codes = [c.get('/', headers={'X-Forwarded-For': str(i)}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]


def test_rl_xff_spoof_leftmost_does_not_reset(client):
    c = client(ip_app(2))
    codes = [c.get('/', headers={'X-Forwarded-For': '%d.9.9.9, 5.5.5.5' % i}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429]


def test_rl_separate_decorations_separate_buckets(client):
    app = Lcore()
    @app.get('/a')
    @rate_limit(1, 3600, single_process=True)
    def a(): return 'a'
    @app.get('/b')
    @rate_limit(1, 3600, single_process=True)
    def b(): return 'b'
    c = client(app)
    assert c.get('/a').status_code == 200 and c.get('/b').status_code == 200
    assert c.get('/a').status_code == 429


def test_rl_warns_without_backend_or_single_process():
    with pytest.warns(UserWarning):
        rate_limit(1)


def test_rl_single_process_silences_warning():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        rate_limit(1, single_process=True)


def test_rl_preserves_function_metadata():
    @rate_limit(1, single_process=True)
    def named(): "doc"
    assert named.__name__ == 'named' and named.__doc__ == 'doc'


def test_rl_error_inside_handler_still_consumes(client):
    app = Lcore()
    @app.get('/')
    @rate_limit(2, 3600, single_process=True)
    def h(): raise ValueError('x')
    c = client(app)
    assert [c.get('/').status_code for _ in range(3)] == [500, 500, 429]


def test_rl_concurrent_live_exact_count(live):
    app = ip_app(20)
    lv = live(app); codes = []; lock = threading.Lock()
    def w():
        s, _, _ = lv.request('GET', '/', headers={'X-Forwarded-For': '9.9.9.9'})
        with lock: codes.append(s)
    ts = [threading.Thread(target=w) for _ in range(60)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes.count(200) == 20 and codes.count(429) == 40


def test_rl_concurrent_many_ips_no_crash(live):
    app = ip_app(1)
    lv = live(app); codes = []
    def w(i):
        codes.append(lv.request('GET', '/', headers={'X-Forwarded-For': '10.0.%d.%d' % (i // 250, i % 250)})[0])
    ts = [threading.Thread(target=w, args=(i,)) for i in range(40)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert codes.count(200) == 40 and len(codes) == 40


def _buckets(deco_wrapper):
    for cell in deco_wrapper.__closure__ or ():
        v = cell.cell_contents
        if isinstance(v, dict):
            return v
    raise AssertionError('no bucket dict')


@pytest.mark.xfail(strict=True, reason="BUG: max_buckets only enforced during the once-per-window cleanup, so a long window lets buckets grow unbounded (lcore.py:3043-3053)")
def test_rl_max_buckets_bounded_within_window(client):
    app = Lcore(); app.use(ProxyFixMiddleware(num_proxies=1))
    @rate_limit(5, 3600, max_buckets=10, single_process=True)
    def h(): return 'ok'
    app.get('/')(h)
    c = client(app)
    for i in range(200):
        c.get('/', headers={'X-Forwarded-For': 'ip%d' % i})
    assert len(_buckets(h)) <= 10 * 2


def test_rl_stale_buckets_cleaned_after_window(client):
    app = Lcore(); app.use(ProxyFixMiddleware(num_proxies=1))
    @rate_limit(5, 0.2, max_buckets=1000, single_process=True)
    def h(): return 'ok'
    app.get('/')(h)
    c = client(app)
    for i in range(30):
        c.get('/', headers={'X-Forwarded-For': 'ip%d' % i})
    time.sleep(0.5)
    c.get('/', headers={'X-Forwarded-For': 'fresh'})
    assert len(_buckets(h)) <= 2


class CountBackend(RateLimitBackend):
    def __init__(self, allow): self.allow = allow; self.calls = []
    def consume(self, key, limit, per):
        self.calls.append((key, limit, per)); return self.allow(len(self.calls))


def test_rl_custom_backend_allow_deny(client):
    be = CountBackend(lambda n: n <= 2)
    app = Lcore()
    @app.get('/')
    @rate_limit(2, 10, backend=be)
    def h(): return 'ok'
    c = client(app)
    assert [c.get('/').status_code for _ in range(3)] == [200, 200, 429]
    assert be.calls[0][1:] == (2, 10)


def test_rl_custom_backend_key_is_client_addr(client):
    be = CountBackend(lambda n: True)
    app = Lcore(); app.use(ProxyFixMiddleware(num_proxies=1))
    @app.get('/')
    @rate_limit(2, 10, backend=be)
    def h(): return 'ok'
    client(app).get('/', headers={'X-Forwarded-For': '8.8.8.8'})
    assert be.calls[0][0] == '8.8.8.8'


def test_rl_custom_backend_no_warning():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        rate_limit(1, backend=CountBackend(lambda n: True))


def test_rl_backend_exception_is_500(client):
    def boom(n): raise RuntimeError('db down')
    app = Lcore()
    @app.get('/')
    @rate_limit(1, 10, backend=CountBackend(boom))
    def h(): return 'ok'
    assert client(app).get('/').status_code == 500


def test_rl_abstract_backend_cannot_instantiate():
    with pytest.raises(TypeError):
        RateLimitBackend()


@pytest.mark.xfail(strict=True, reason="BUG: backend= object that is not a RateLimitBackend subclass is silently ignored (falls back to in-process buckets, no warning) (lcore.py:3014)")
def test_rl_duck_typed_backend_is_honoured(client):
    class Duck:
        def __init__(self): self.n = 0
        def consume(self, key, limit, per): self.n += 1; return False
    d = Duck()
    app = Lcore()
    @app.get('/')
    @rate_limit(100, 10, backend=d)
    def h(): return 'ok'
    client(app).get('/')
    assert d.n == 1


# ---------------------------------------------------------------- auth_basic
def basic(u, p): return 'Basic ' + base64.b64encode(('%s:%s' % (u, p)).encode()).decode()


def auth_app(check=lambda u, p: (u, p) == ('bob', 'pw'), **kw):
    app = Lcore()
    @app.get('/')
    @auth_basic(check, **kw)
    def h(): return 'secret'
    return app


def test_basic_no_header_401_with_challenge(client):
    r = client(auth_app()).get('/')
    assert r.status_code == 401 and r.headers['Www-Authenticate'] == 'Basic realm="private"'


def test_basic_good_credentials(client):
    assert client(auth_app()).get('/', headers={'Authorization': basic('bob', 'pw')}).text == 'secret'


def test_basic_wrong_password(client):
    assert client(auth_app()).get('/', headers={'Authorization': basic('bob', 'nope')}).status_code == 401


def test_basic_colon_in_password(client):
    app = auth_app(lambda u, p: p == 'a:b:c')
    assert client(app).get('/', headers={'Authorization': basic('u', 'a:b:c')}).status_code == 200


def test_basic_empty_password_and_user(client):
    app = auth_app(lambda u, p: (u, p) == ('', ''))
    assert client(app).get('/', headers={'Authorization': basic('', '')}).status_code == 200


def test_basic_unicode_credentials(client):
    app = auth_app(lambda u, p: (u, p) == ('josé', 'pässwörd✓'))
    assert client(app).get('/', headers={'Authorization': basic('josé', 'pässwörd✓')}).status_code == 200


@pytest.mark.parametrize('hdr', ['Basic', 'Basic !!!notbase64', 'Basic ' + base64.b64encode(b'nocolon').decode(),
                                 'Basic ' + base64.b64encode(b'\xff\xfe:\xff').decode(), 'Bearer abc', 'basic', '', 'Basic  ',
                                 'Basic ' + 'A' * 100000, 'Digest username="x"', 'Basic =', 'Basic \x00'])
def test_basic_malformed_headers_401_not_500(client, hdr):
    r = client(auth_app()).get('/', headers={'Authorization': hdr})
    assert r.status_code == 401


def test_basic_scheme_case_insensitive(client):
    h = basic('bob', 'pw').replace('Basic', 'bAsIc')
    assert client(auth_app()).get('/', headers={'Authorization': h}).status_code == 200


def test_basic_custom_realm_and_text(client):
    r = client(auth_app(realm='area51', text='go away')).get('/')
    assert 'area51' in r.headers['Www-Authenticate'] and 'go away' in r.text


def test_basic_checker_exception_is_500(client):
    def bad(u, p): raise RuntimeError('x')
    assert client(auth_app(bad)).get('/', headers={'Authorization': basic('a', 'b')}).status_code == 500


@pytest.mark.xfail(strict=True, reason="BUG: auth_basic realm is interpolated unescaped into WWW-Authenticate (quote/CRLF injection) (lcore.py:5167)")
def test_basic_realm_quote_escaped(client):
    r = client(auth_app(realm='a", evil="1')).get('/')
    assert 'evil="1"' not in r.headers['Www-Authenticate']


def test_basic_handler_not_called_on_failure(client):
    hits = []
    app = Lcore()
    @app.get('/')
    @auth_basic(lambda u, p: False)
    def h(): hits.append(1); return 'x'
    client(app).get('/', headers={'Authorization': basic('a', 'b')})
    assert not hits


def test_basic_remote_user_fallback_has_no_password(client):
    seen = []
    app = Lcore()
    @app.get('/')
    @auth_basic(lambda u, p: seen.append((u, p)) or False)
    def h(): return 'x'
    from wsgiref.util import setup_testing_defaults
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'REMOTE_USER': 'ghost'}
    setup_testing_defaults(env)
    b''.join(app(env, lambda *a: None))
    assert seen == [('ghost', None)]


def test_basic_remote_user_cannot_bypass_with_none_password_check(client):
    # a naive check(u, p) comparing p to a stored password must not accept None
    app = auth_app(lambda u, p: p == 'pw')
    from wsgiref.util import setup_testing_defaults
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'REMOTE_USER': 'ghost'}
    setup_testing_defaults(env); out = {}
    b''.join(app(env, lambda s, h, e=None: out.setdefault('s', s)))
    assert out['s'].startswith('401')


# ---------------------------------------------------------------- password hashing
def test_hash_format():
    h = hash_password('pw', iterations=1000)
    method, rest = h.split(':', 1)
    algo, rest = rest.split(':', 1)
    it, salt, dk = rest.split('$')
    assert (method, algo, it) == ('pbkdf2', 'sha256', '1000') and len(salt) == 64 and len(dk) == 64


def test_hash_default_iterations_600k():
    assert hash_password('x').split('$')[0].endswith(':600000')


def test_hash_unique_salts():
    assert hash_password('pw', 1000) != hash_password('pw', 1000)


def test_verify_roundtrip():
    h = hash_password('hunter2', 1000)
    assert verify_password('hunter2', h) and not verify_password('hunter3', h)


def test_verify_empty_password():
    h = hash_password('', 1000)
    assert verify_password('', h) and not verify_password('x', h)


def test_verify_unicode_password():
    pw = 'pässwörd✓世界🙂'
    h = hash_password(pw, 1000)
    assert verify_password(pw, h) and not verify_password(pw + 'x', h)


def test_verify_bytes_password():
    h = hash_password(b'bytes', 1000)
    assert verify_password(b'bytes', h) and verify_password('bytes', h)


def test_verify_long_password():
    pw = 'p' * 100000
    h = hash_password(pw, 1000)
    assert verify_password(pw, h)


def test_verify_case_of_hex_irrelevant():
    h = hash_password('a', 1000)
    method, algo_rest = h.split('$', 1)[0], h.split('$', 1)[1]
    assert verify_password('a', h.upper().replace('PBKDF2:SHA256', 'pbkdf2:sha256')) in (True, False)


@pytest.mark.parametrize('bad', [None, 5, b'pbkdf2:sha256:1$aa$bb', [], '', 'garbage', 'a:b', 'a:b:c', 'pbkdf2:sha256:abc$aa$bb',
                                 'pbkdf2:sha256:10$zz$bb', 'pbkdf2:sha256:10$aa$zz', 'pbkdf2:sha256:10$aa', 'pbkdf2:nope:10$aa$bb',
                                 'pbkdf2:sha256:0$aa$bb', 'pbkdf2:sha256:-5$aa$bb', 'pbkdf2:sha256:10$$', 'pbkdf2:sha256:1e3$aa$bb'])
def test_verify_malformed_hash_false_not_exception(bad):
    assert verify_password('pw', bad) is False


def test_verify_tampered_hash_flip_each_part():
    h = hash_password('pw', 1000)
    head, salt, dk = h.split('$')
    flip = lambda s: ('0' if s[0] != '0' else '1') + s[1:]
    assert not verify_password('pw', '$'.join([head, flip(salt), dk]))
    assert not verify_password('pw', '$'.join([head, salt, flip(dk)]))
    assert not verify_password('pw', head.replace('1000', '1001') + '$' + salt + '$' + dk)


def test_verify_truncated_digest_false():
    h = hash_password('pw', 1000)
    assert not verify_password('pw', h[:-2])


def test_verify_lone_surrogate_password_false_not_crash():
    h = hash_password('pw', 1000)
    assert verify_password('\ud800', h) is False


def test_hash_lone_surrogate_password_clear_error():
    with pytest.raises((ValueError, TypeError)):
        hash_password('\ud800', 1000)


@pytest.mark.parametrize('it', [0, -1])
def test_hash_invalid_iterations_raises(it):
    with pytest.raises(ValueError):
        hash_password('x', it)


@pytest.mark.xfail(strict=True, reason="BUG: verify_password trusts the iteration count inside the stored hash: a crafted hash with huge iterations burns CPU for minutes (DoS) (lcore.py:5190)")
def test_verify_huge_iterations_dos_bounded():
    t = time.time()
    res = [None]
    def run(): res[0] = verify_password('x', 'pbkdf2:sha256:200000000$aa$bb')
    th = threading.Thread(target=run, daemon=True); th.start(); th.join(2.0)
    assert not th.is_alive(), 'still hashing after 2s: unbounded iterations accepted'


@pytest.mark.xfail(strict=True, reason="BUG: verify_password honours any hashlib algo named in the hash string, incl. non-sha256 / weak ones (md5, sha1) (lcore.py:5190)")
def test_verify_rejects_weak_algo():
    import hashlib
    salt = b'0' * 16
    dk = hashlib.pbkdf2_hmac('md5', b'pw', salt, 1)
    assert not verify_password('pw', 'pbkdf2:md5:1$%s$%s' % (salt.hex(), dk.hex()))


def test_verify_timing_roughly_constant_wrong_vs_right():
    h = hash_password('pw', 20000)
    def t(p):
        s = time.perf_counter()
        for _ in range(5): verify_password(p, h)
        return time.perf_counter() - s
    a, b = t('pw'), t('xx')
    assert abs(a - b) / max(a, b) < 0.5


# ---------------------------------------------------------------- validate_request
@dataclasses.dataclass
class User:
    name: str
    age: int
    nick: Optional[str] = None
    tags: list = dataclasses.field(default_factory=list)


def vapp():
    app = Lcore()
    @app.post('/d')
    @validate_request(body={'name': str, 'age': int, 'score': Optional[float], 'ok': bool})
    def d(): return json_dumps(request.json)
    @app.post('/dc')
    @validate_request(body=User)
    def dc(): return json_dumps(request.json)
    @app.get('/q')
    @validate_request(query={'page': int, 'q': Optional[str]})
    def q(): return json_dumps(dict(request.query))
    @app.get('/qd')
    @validate_request(query=User)
    def qd(): return 'ok'
    return app


GOOD = {'name': 'a', 'age': 3, 'ok': True}


def test_v_valid(client):
    r = client(vapp()).post('/d', json=GOOD)
    assert r.status_code == 200 and r.json['age'] == 3


def test_v_missing_fields_422_shape(client):
    r = client(vapp()).post('/d', json={})
    assert r.status_code == 422
    assert r.headers['Content-Type'].startswith('application/json')
    assert set(r.json['fields']) == {'name', 'age', 'ok'} and r.json['error'] == 'Validation failed'


def test_v_optional_absent_and_null(client):
    c = client(vapp())
    assert c.post('/d', json=GOOD).json.get('score') is None
    assert c.post('/d', json={**GOOD, 'score': None}).json['score'] is None


def test_v_optional_coerced(client):
    assert client(vapp()).post('/d', json={**GOOD, 'score': '1.5'}).json['score'] == 1.5


def test_v_required_null_rejected(client):
    assert client(vapp()).post('/d', json={**GOOD, 'name': None}).status_code == 422


@pytest.mark.parametrize('field,val', [('age', 'abc'), ('age', 1.5), ('age', True), ('age', []), ('age', {}), ('age', ''),
                                       ('ok', 'maybe'), ('ok', 5), ('name', []), ('name', {}), ('score', 'nan'), ('score', 'inf'),
                                       ('score', '1e999'), ('score', [1]), ('age', '9' * 5000)])
def test_v_bad_types_422(client, field, val):
    r = client(vapp()).post('/d', json={**GOOD, field: val})
    assert r.status_code == 422 and field in r.json['fields']


@pytest.mark.parametrize('field,val,exp', [('age', '42', 42), ('age', 42.0, 42), ('age', ' 7 ', 7), ('ok', 'yes', True), ('ok', 'off', False),
                                           ('ok', 0, False), ('ok', 'TRUE', True), ('name', 12, '12'), ('name', '  pad ', 'pad')])
def test_v_coercion(client, field, val, exp):
    r = client(vapp()).post('/d', json={**GOOD, field: val})
    assert r.status_code == 200 and r.json[field] == exp


def test_v_extra_fields_passthrough(client):
    r = client(vapp()).post('/d', json={**GOOD, 'extra': {'x': 1}})
    assert r.status_code == 200 and r.json['extra'] == {'x': 1}


@pytest.mark.parametrize('body', [b'[1,2]', b'"str"', b'5', b'null_', b'{bad json', b'\xff\xfe', b'{"a":'])
def test_v_non_object_or_bad_json_4xx(client, body):
    r = client(vapp()).post('/d', body=body, content_type='application/json')
    assert r.status_code in (400, 422)


def test_v_empty_body_422_required(client):
    r = client(vapp()).post('/d', body=b'', content_type='application/json')
    assert r.status_code == 422


def test_v_wrong_content_type_form(client):
    r = client(vapp()).post('/d', body=b'name=a&age=3&ok=1', content_type='application/x-www-form-urlencoded')
    assert r.status_code in (400, 422)


def test_v_huge_payload(client):
    r = client(vapp()).post('/d', json={**GOOD, 'name': 'x' * 2_000_000})
    assert r.status_code == 200 and len(r.json['name']) == 2_000_000


def test_v_deeply_nested_extra_no_crash(client):
    nested = '[' * 5000 + ']' * 5000
    r = client(vapp()).post('/d', body=('{"name":"a","age":1,"ok":true,"x":%s}' % nested).encode(), content_type='application/json')
    assert r.status_code in (200, 400, 413, 422)


def test_v_unicode_values(client):
    r = client(vapp()).post('/d', json={**GOOD, 'name': '世界🙂'})
    assert r.json['name'] == '世界🙂'


def test_v_dataclass_valid_defaults(client):
    r = client(vapp()).post('/dc', json={'name': 'n', 'age': '5'})
    assert r.status_code == 200 and r.json['age'] == 5


def test_v_dataclass_required_missing(client):
    r = client(vapp()).post('/dc', json={'name': 'n'})
    assert r.status_code == 422 and list(r.json['fields']) == ['age']


def test_v_dataclass_optional_none(client):
    assert client(vapp()).post('/dc', json={'name': 'n', 'age': 1, 'nick': None}).status_code == 200


def test_v_dataclass_default_factory_field_not_required(client):
    assert client(vapp()).post('/dc', json={'name': 'n', 'age': 1}).status_code == 200


def test_v_dataclass_list_field_coercion(client):
    # `list` is callable -> list('abc') silently becomes ['a','b','c']
    r = client(vapp()).post('/dc', json={'name': 'n', 'age': 1, 'tags': 'abc'})
    assert r.status_code == 422 or r.json['tags'] == 'abc' or r.json['tags'] == ['a', 'b', 'c']


@pytest.mark.xfail(strict=True, reason="BUG: callable-type coercion turns a JSON string into list(chars) / accepts anything the type ctor swallows (lcore.py:3925)")
def test_v_list_type_rejects_string(client):
    app = Lcore()
    @app.post('/')
    @validate_request(body={'tags': list})
    def h(): return json_dumps(request.json)
    r = client(app).post('/', json={'tags': 'abc'})
    assert r.status_code == 422


def test_v_query_valid(client):
    assert client(vapp()).get('/q', query_string='page=2').status_code == 200


def test_v_query_missing_400(client):
    r = client(vapp()).get('/q')
    assert r.status_code == 400 and r.json['fields']['page'].startswith('page')


@pytest.mark.parametrize('qs', ['page=x', 'page=', 'page=1.5', 'page=%00', 'page=' + '9' * 5000])
def test_v_query_bad_400(client, qs):
    assert client(vapp()).get('/q', query_string=qs).status_code == 400


def test_v_query_repeated_param_uses_last_or_first(client):
    assert client(vapp()).get('/q', query_string='page=1&page=zzz').status_code in (200, 400)


@pytest.mark.xfail(strict=True, reason="BUG: validate_request(query=...) validates but does not coerce: handler still sees raw strings, unlike body= (lcore.py:4057)")
def test_v_query_coerced_value_visible_to_handler(client):
    app = Lcore()
    @app.get('/')
    @validate_request(query={'n': int})
    def h(): return type(request.query.get('n')).__name__
    assert client(app).get('/', query_string='n=5').text == 'int'


def test_v_query_dataclass(client):
    assert client(vapp()).get('/qd').status_code == 400
    assert client(vapp()).get('/qd', query_string='name=a&age=3').status_code == 200


def test_v_error_response_has_no_input_reflection(client):
    r = client(vapp()).post('/d', json={**GOOD, 'age': '<script>x</script>'})
    assert '<script>' not in r.text


def test_v_body_and_query_together(client):
    app = Lcore()
    @app.post('/')
    @validate_request(body={'a': int}, query={'b': int})
    def h(): return 'ok'
    c = client(app)
    assert c.post('/', json={'a': 1}, query_string='b=2').status_code == 200
    assert c.post('/', json={'a': 1}).status_code == 400
    assert c.post('/', json={}, query_string='b=2').status_code == 422


# ---------------------------------------------------------------- cookie signing
def cookie_app(secret='s3'):
    app = Lcore()
    @app.get('/set')
    def s():
        response.set_cookie('u', request.query.get('v'), secret=secret); return 'ok'
    @app.get('/get')
    def g(): return request.get_cookie('u', default='NONE', secret=secret)
    @app.get('/getb')
    def g2(): return request.get_cookie('b', default='NONE', secret=secret)
    return app


def _cookie_val(r, name):
    for c in r.get_all('Set-Cookie'):
        if c.startswith(name + '='): return c.split(';', 1)[0].split('=', 1)[1]


def test_cookie_sign_roundtrip(client):
    c = client(cookie_app()); c.get('/set', query_string='v=hello')
    assert c.get('/get').text == 'hello'


@pytest.mark.parametrize('v', ['héllo✓', 'a b;c,d', 'x' * 2000, '', '"quoted"', 'a=b'])
def test_cookie_sign_roundtrip_values(client, v):
    c = client(cookie_app()); r = c.get('/set', query_string='v=' + __import__('urllib.parse').parse.quote(v))
    assert r.status_code == 200
    assert c.get('/get').text == v


def test_cookie_tampered_payload_rejected(client):
    c = client(cookie_app()); r = c.get('/set', query_string='v=hello')
    val = _cookie_val(r, 'u')
    sig, msg = val[1:].split('?', 1)
    forged = '!' + sig + '?' + base64.b64encode(b'["u", "admin"]').decode()
    c.cookies['u'] = forged
    assert c.get('/get').text == 'NONE'


def test_cookie_wrong_secret_rejected(client):
    r = client(cookie_app('A')).get('/set', query_string='v=x')
    c = client(cookie_app('B')); c.cookies['u'] = _cookie_val(r, 'u')
    assert c.get('/get').text == 'NONE'


def test_cookie_value_replay_across_names_rejected(client):
    c = client(cookie_app()); r = c.get('/set', query_string='v=admin')
    c.cookies['b'] = _cookie_val(r, 'u')
    assert c.get('/getb').text == 'NONE'


@pytest.mark.parametrize('junk', ['', '!', '!?', '!abc?def', '!' + 'A' * 50 + '?', 'plain', '!sig?' + base64.b64encode(b'5').decode(),
                                  '!sig?' + base64.b64encode(b'null').decode(), '!sig?!!!'])
def test_cookie_garbage_never_500(client, junk):
    c = client(cookie_app()); c.cookies['u'] = junk
    assert c.get('/get').status_code == 200


def test_cookie_unsigned_plain_cookie_not_accepted_when_secret_used(client):
    c = client(cookie_app()); c.cookies['u'] = 'admin'
    assert c.get('/get').text == 'NONE'


def test_cookie_too_big_raises(client):
    c = client(cookie_app())
    assert c.get('/set', query_string='v=' + 'x' * 4000).status_code == 500


def test_cookie_non_string_value_needs_secret():
    r = lcore.BaseResponse()
    with pytest.raises(TypeError):
        r.set_cookie('a', 5)


def test_cookie_flags_default(client):
    r = client(cookie_app()).get('/set', query_string='v=1')
    ck = r.get_all('Set-Cookie')[0]
    assert 'HttpOnly' in ck and 'samesite=lax' in ck.lower()


def test_cookie_samesite_invalid():
    r = lcore.BaseResponse()
    with pytest.raises(Exception):
        r.set_cookie('a', 'b', samesite='bogus')


# ---------------------------------------------------------------- injection / traversal
@pytest.mark.parametrize('val', ['a\r\nSet-Cookie: x=1', 'a\nX: y', 'a\rX: y', 'a\x00b'])
def test_response_header_crlf_rejected(val):
    r = lcore.BaseResponse()
    with pytest.raises(ValueError):
        r.set_header('X-Test', val)


@pytest.mark.parametrize('name', ['X\r\nY', pytest.param('X Y', marks=pytest.mark.xfail(strict=True, reason='BUG: set_header accepts header names with spaces (lcore.py:1954 _hkey)')), pytest.param('X:Y', marks=pytest.mark.xfail(strict=True, reason='BUG: set_header accepts header names containing colon (lcore.py:1954 _hkey)')), pytest.param('', marks=pytest.mark.xfail(strict=True, reason='BUG: set_header accepts empty header name (lcore.py:1954 _hkey)'))])
def test_response_header_name_validation(name):
    r = lcore.BaseResponse()
    try:
        r.set_header(name, 'v')
    except (ValueError, KeyError):
        return
    pytest.fail('bad header name accepted: %r' % name)


def test_redirect_crlf_location_rejected(client):
    app = Lcore()
    @app.get('/')
    def h(): lcore.redirect(request.query.get('u'))
    r = client(app).get('/', query_string='u=/x%0d%0aSet-Cookie:%20pwn=1')
    assert not any('pwn' in v for k, v in r.raw_headers if k.lower() == 'set-cookie')
    assert r.status_code in (302, 303, 400, 500)


def test_cookie_name_value_injection_blocked(client):
    app = Lcore()
    @app.get('/')
    def h():
        response.set_cookie('a', 'v\r\nX-Evil: 1'); return 'x'
    r = client(app).get('/')
    assert 'X-Evil' not in r.headers


@pytest.fixture
def static_root(tmp_path):
    root = tmp_path / 'pub'; root.mkdir()
    (root / 'a.txt').write_text('public')
    (tmp_path / 'secret.txt').write_text('SECRET')
    (tmp_path / 'pub2').mkdir(); (tmp_path / 'pub2' / 'x.txt').write_text('SIBLING')
    os.symlink(str(tmp_path / 'secret.txt'), str(root / 'link.txt'))
    return str(root)


def static_app(root):
    app = Lcore()
    @app.get('/s/<path:path>')
    def s(path): return static_file(path, root=root)
    return app


@pytest.mark.parametrize('p', ['a.txt', '/a.txt', '%2fa.txt'])
def test_static_serves_inside_root(client, static_root, p):
    r = client(static_app(static_root)).get('/s/' + p.lstrip('/'))
    assert r.status_code in (200, 404)


@pytest.mark.parametrize('p', ['../secret.txt', '..%2fsecret.txt', '%2e%2e/secret.txt', '%2e%2e%2fsecret.txt', '....//secret.txt',
                               '..\\secret.txt', '../pub2/x.txt', 'a.txt/../../secret.txt', '..%5csecret.txt', '%252e%252e/secret.txt',
                               '/etc/passwd', '..%00/secret.txt', 'a.txt%00../../secret.txt', '../../../../../../etc/passwd'])
def test_static_traversal_blocked(client, static_root, p):
    r = client(static_app(static_root)).get('/s/' + p)
    assert b'SECRET' not in r.body and b'SIBLING' not in r.body and b'root:' not in r.body
    assert r.status_code in (400, 403, 404)


def test_static_traversal_blocked_live_raw(live, static_root):
    lv = live(static_app(static_root))
    for p in ('/s/../secret.txt', '/s/%2e%2e/secret.txt', '/s/..%2fsecret.txt'):
        out = lv.raw(('GET %s HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n' % p).encode())
        assert b'SECRET' not in out


def test_static_symlink_escape_blocked(client, static_root):
    r = client(static_app(static_root)).get('/s/link.txt')
    assert b'SECRET' not in r.body


def test_static_sibling_prefix_dir_not_matched(client, static_root):
    # root 'pub' must not match sibling 'pub2' via naive startswith
    r = client(static_app(static_root)).get('/s/../pub2/x.txt')
    assert b'SIBLING' not in r.body


def test_static_dir_request(client, static_root):
    assert client(static_app(static_root)).get('/s/').status_code in (403, 404)


def test_route_null_byte_in_path(client):
    app = Lcore(); app.get('/<x>')(lambda x: 'ok')
    assert client(app).get('/a%00b').status_code in (200, 400, 404)


def test_query_param_huge_count_no_crash(client):
    app = Lcore(); app.get('/')(lambda: str(len(request.query)))
    r = client(app).get('/', query_string='&'.join('k%d=v' % i for i in range(20000)))
    assert r.status_code in (200, 400, 413)


# ---------------------------------------------------------------- raw socket probes
def sapp():
    app = Lcore()
    seen = []
    app.seen = seen
    @app.route('/echo', method=['GET', 'POST'])
    def echo():
        seen.append(request.path)
        return 'len=%d' % len(request.body.read())
    @app.get('/admin')
    def admin(): seen.append('ADMIN'); return 'admin'
    return app


def status_of(out):
    try: return int(out.split(b' ', 2)[1])
    except Exception: return None


def alive(lv):
    s, _, b = lv.request('POST', '/echo', body=b'x')
    return s == 200


def test_smuggle_cl_te_conflict_does_not_reach_admin(live):
    app = sapp(); lv = live(app)
    req = (b'POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n'
           b'0\r\n\r\nGET /admin HTTP/1.1\r\nHost: x\r\n\r\n')
    lv.raw(req)
    time.sleep(0.2)
    assert 'ADMIN' not in app.seen or app.seen.count('ADMIN') == 0
    assert alive(lv)


def test_smuggle_duplicate_content_length(live):
    app = sapp(); lv = live(app)
    out = lv.raw(b'POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 3\r\nContent-Length: 40\r\nConnection: close\r\n\r\nabc')
    assert alive(lv)
    assert 'ADMIN' not in app.seen


def test_smuggle_pipelined_second_request_handled_separately(live):
    app = sapp(); lv = live(app)
    s = socket.create_connection(('127.0.0.1', lv.port), timeout=3)
    s.sendall(b'POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n\r\nhelloGET /admin HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
    data = b''
    try:
        while True:
            d = s.recv(4096)
            if not d: break
            data += d
    except socket.timeout: pass
    s.close()
    assert data.count(b'HTTP/1.') >= 1 and b'len=5' in data


@pytest.mark.parametrize('cl', [b'-1', b'abc', b'1e3', b'99999999999999999999', b' 5', b'0x10', b'+5'])
def test_bad_content_length_values_survive(live, cl):
    lv = live(sapp())
    out = lv.raw(b'POST /echo HTTP/1.1\r\nHost: x\r\nContent-Length: ' + cl + b'\r\nConnection: close\r\n\r\nabcde')
    assert alive(lv)


def test_huge_header_value_survives(live):
    lv = live(sapp())
    out = lv.raw(b'GET /echo HTTP/1.1\r\nHost: x\r\nX-Big: ' + b'A' * 200000 + b'\r\nConnection: close\r\n\r\n')
    assert status_of(out) in (None, 400, 413, 414, 431, 200) and alive(lv)


def test_huge_request_line_survives(live):
    lv = live(sapp())
    out = lv.raw(b'GET /' + b'a' * 100000 + b' HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n')
    assert status_of(out) in (None, 400, 404, 414) and alive(lv)


def test_many_headers_survives(live):
    lv = live(sapp())
    hdrs = b''.join(b'X-%d: v\r\n' % i for i in range(5000))
    out = lv.raw(b'GET /echo HTTP/1.1\r\nHost: x\r\n' + hdrs + b'Connection: close\r\n\r\n')
    assert alive(lv)


@pytest.mark.parametrize('payload', [b'GET /echo\x00 HTTP/1.1\r\nHost: x\r\n\r\n', b'GET /echo HTTP/1.1\r\nHost: x\x00y\r\nConnection: close\r\n\r\n',
                                     b'\x00\x01\x02garbage\r\n\r\n', b'GET\r\n\r\n', b'GET /echo HTTP/9.9\r\nHost: x\r\n\r\n',
                                     b'GET /echo HTTP/1.1\r\nBad Header Line\r\n\r\n', b'GET /echo HTTP/1.1\nHost: x\nConnection: close\n\n',
                                     b'GET /echo HTTP/1.1\r\nHost: x\r\n X-Folded: y\r\nConnection: close\r\n\r\n'])
def test_malformed_requests_dont_kill_server(live, payload):
    lv = live(sapp())
    lv.raw(payload)
    assert alive(lv)


def test_slowloris_does_not_block_other_clients(live):
    lv = live(sapp())
    slow = socket.create_connection(('127.0.0.1', lv.port), timeout=3)
    slow.sendall(b'GET /echo HTTP/1.1\r\nHost: x\r\nX-Slow: ')
    time.sleep(0.2)
    # wsgiref is single-threaded: this documents behaviour; the server must at least recover once the slow client leaves
    slow.close()
    assert alive(lv)


def test_chunked_malformed_in_process(client):
    from io import BytesIO
    app = sapp()
    for bad in (b'zz\r\nabc\r\n0\r\n\r\n', b'5\r\nab', b'-5\r\nabcde\r\n0\r\n\r\n', b'ffffffffffffffff\r\nx', b''):
        env = {'REQUEST_METHOD': 'POST', 'PATH_INFO': '/echo', 'wsgi.input': BytesIO(bad), 'HTTP_TRANSFER_ENCODING': 'chunked',
               'SERVER_NAME': 'x', 'SERVER_PORT': '80', 'wsgi.url_scheme': 'http', 'wsgi.errors': BytesIO()}
        out = {}
        b''.join(app(env, lambda s, h, e=None: out.setdefault('s', s)))
        assert out['s'][:3] in ('200', '400', '413'), (bad, out)
