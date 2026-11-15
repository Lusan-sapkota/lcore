"""API-level tests for routing: matching, filters, methods, mounting, groups, reverse routing."""
import threading
import warnings
import pytest
import lcore
from lcore import Lcore, HTTPError, HTTPResponse, request, response, Router, RouteBuildError, RouteSyntaxError, path_shift


def mk():
    return Lcore()


def latin(s):
    """What a WSGI server hands the app for a (decoded) utf-8 path."""
    return s.encode('utf8').decode('latin1')


# ---------------------------------------------------------------- static / dynamic

@pytest.fixture
def app():
    a = mk()

    @a.route('/')
    def index(): return 'index'

    @a.route('/static/page')
    def page(): return 'page'

    @a.route('/user/<name>')
    def user(name): return 'user:' + name

    @a.route('/item/<id:int>')
    def item(id): return 'item:%r' % (id,)

    @a.route('/f/<x:float>')
    def fl(x): return 'f:%r' % (x,)

    @a.route('/files/<p:path>')
    def files(p): return 'path:' + p

    @a.route('/re/<code:re:[A-Z]{3}\\d>')
    def rx(code): return 're:' + code

    @a.route('/a/<x>/b/<y>')
    def two(x, y): return '%s,%s' % (x, y)

    return a


def test_root(client, app):
    r = client(app).get('/')
    assert (r.status_code, r.text) == (200, 'index')


def test_empty_path_info_is_root(app):
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': ''}
    target, args = app.router.match(env)
    assert target.rule == '/'


def test_static_route(client, app):
    assert client(app).get('/static/page').text == 'page'


def test_dynamic_basic(client, app):
    assert client(app).get('/user/bob').text == 'user:bob'


def test_two_params(client, app):
    assert client(app).get('/a/1/b/2').text == '1,2'


def test_default_wildcard_does_not_cross_slash(client, app):
    assert client(app).get('/user/a/b').status_code == 404


def test_default_wildcard_requires_nonempty(client, app):
    assert client(app).get('/user/').status_code == 404


@pytest.mark.parametrize('p,expect', [('/item/5', 'item:5'), ('/item/-5', 'item:-5'), ('/item/0', 'item:0'),
                                      ('/item/007', 'item:7'),
                                      ('/item/99999999999999999999999', 'item:99999999999999999999999')])
def test_int_filter_ok(client, app, p, expect):
    assert client(app).get(p).text == expect


@pytest.mark.parametrize('p', ['/item/x', '/item/1.5', '/item/', '/item/+5', '/item/5/', '/item/ 5', '/item/1e3'])
def test_int_filter_rejects(client, app, p):
    assert client(app).get(p).status_code == 404


@pytest.mark.parametrize('p,expect', [('/f/1.5', 'f:1.5'), ('/f/3', 'f:3.0'), ('/f/-2.25', 'f:-2.25'), ('/f/.5', 'f:0.5')])
def test_float_filter_ok(client, app, p, expect):
    assert client(app).get(p).text == expect


@pytest.mark.parametrize('p', ['/f/1.2.3', '/f/.', '/f/..', '/f/-.'])
def test_float_filter_pattern_matches_but_value_bad_gives_400(client, app, p):
    # pattern -?[\d.]+ matches, float() fails -> documented as 400 'wrong format'
    assert client(app).get(p).status_code == 400


def test_float_filter_letters_404(client, app):
    assert client(app).get('/f/abc').status_code == 404


def test_path_filter_spans_slashes(client, app):
    assert client(app).get('/files/a/b/c.txt').text == 'path:a/b/c.txt'


def test_path_filter_single(client, app):
    assert client(app).get('/files/x').text == 'path:x'


def test_path_filter_empty_404(client, app):
    assert client(app).get('/files/').status_code == 404


def test_regex_filter(client, app):
    assert client(app).get('/re/ABC1').text == 're:ABC1'
    assert client(app).get('/re/abc1').status_code == 404
    assert client(app).get('/re/ABCD').status_code == 404


def test_regex_with_inner_group_does_not_break_args():
    a = mk()

    @a.route('/v/<v:re:(a|b)+>/<w>')
    def f(v, w): return v + '|' + w

    c = lcore.TestClient(a)
    assert c.get('/v/abab/z').text == 'abab|z'


def test_regex_with_escaped_paren_and_angle():
    a = mk()

    @a.route('/e/<v:re:\\(x\\)>')
    def f(v): return v

    assert lcore.TestClient(a).get('/e/(x)').text == '(x)'


def test_anonymous_wildcards():
    a = mk()

    @a.route('/<:re:[a-z]+>/<:int>')
    def f(): return 'anon'

    assert lcore.TestClient(a).get('/abc/12').text == 'anon'


def test_regex_special_chars_in_static_part_escaped():
    a = mk()

    @a.route('/a.b/<x>')
    def f(x): return x

    c = lcore.TestClient(a)
    assert c.get('/a.b/1').status_code == 200
    assert c.get('/aXb/1').status_code == 404


def test_old_colon_syntax_still_works():
    a = mk()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')

        @a.route('/old/:name')
        def f(name): return name

    assert lcore.TestClient(a).get('/old/zed').text == 'zed'


def test_escaped_angle_is_literal():
    a = mk()

    @a.route('/lit/\\<x>')
    def f(): return 'lit'

    assert lcore.TestClient(a).get('/lit/<x>').text == 'lit'


def test_invalid_regex_raises_routesyntaxerror():
    a = mk()
    with pytest.raises(RouteSyntaxError):
        @a.route('/bad/<x:re:[a-z>')
        def f(x): pass


def test_unknown_filter_raises():
    a = mk()
    with pytest.raises(KeyError):
        @a.route('/bad/<x:nosuch>')
        def f(x): pass


# ---------------------------------------------------------------- custom filters

def test_custom_filter_add_filter():
    a = mk()

    def hexfilter(conf):
        return r'[0-9a-f]+', lambda s: int(s, 16), lambda i: '%x' % i

    a.router.add_filter('hex', hexfilter)

    @a.route('/h/<n:hex>', name='h')
    def f(n): return str(n)

    c = lcore.TestClient(a)
    assert c.get('/h/ff').text == '255'
    assert c.get('/h/zz').status_code == 404
    assert a.router.build('h', n=255) == '/h/ff'


def test_custom_filter_with_conf():
    a = mk()
    a.router.add_filter('len', lambda conf: (r'\w{%s}' % conf, None, None))

    @a.route('/l/<x:len:3>')
    def f(x): return x

    c = lcore.TestClient(a)
    assert c.get('/l/abc').status_code == 200
    assert c.get('/l/abcd').status_code == 404


def test_add_route_filter_helper():
    a = mk()
    a.add_route_filter('slug', r'[a-z0-9-]+', to_python=str.upper)

    @a.route('/s/<x:slug>')
    def f(x): return x

    assert lcore.TestClient(a).get('/s/ab-1').text == 'AB-1'


def test_filter_raising_valueerror_gives_400():
    a = mk()

    def bad(conf):
        def conv(s): raise ValueError('nope')
        return r'\d+', conv, None

    a.router.add_filter('bad', bad)

    @a.route('/b/<x:bad>')
    def f(x): return x

    assert lcore.TestClient(a).get('/b/1').status_code == 400


def test_filter_raising_other_exception_gives_500():
    a = mk()

    def bad(conf):
        def conv(s): raise KeyError('boom')
        return r'\d+', conv, None

    a.router.add_filter('bad', bad)

    @a.route('/b/<x:bad>')
    def f(x): return x

    assert lcore.TestClient(a).get('/b/1').status_code == 500


# ---------------------------------------------------------------- methods

@pytest.fixture
def mapp():
    a = mk()

    @a.get('/r')
    def g(): return 'GET'

    @a.post('/r')
    def p(): return 'POST'

    @a.put('/r')
    def pu(): return 'PUT'

    @a.patch('/r')
    def pa(): return 'PATCH'

    @a.delete('/r')
    def d(): return 'DELETE'

    @a.route('/any', method='ANY')
    def an(): return 'ANY:' + request.method

    @a.route('/multi', method=['GET', 'POST'])
    def mu(): return 'multi:' + request.method

    @a.route('/only-post', method='POST')
    def op(): return 'op'

    @a.route('/getonly')
    def go():
        return 'body-data'

    return a


@pytest.mark.parametrize('m', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
def test_each_method_dispatch(client, mapp, m):
    assert client(mapp).request(m, '/r').text == m


@pytest.mark.parametrize('m', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD', 'TRACE', 'FOO'])
def test_any_method(client, mapp, m):
    r = client(mapp).request(m, '/any')
    assert r.status_code == 200
    if m != 'HEAD':
        assert r.text == 'ANY:' + m


def test_lowercase_method_normalised(client, mapp):
    assert client(mapp).request('post', '/r').text == 'POST'


def test_method_list(client, mapp):
    c = client(mapp)
    assert c.get('/multi').text == 'multi:GET'
    assert c.post('/multi').text == 'multi:POST'
    assert c.put('/multi').status_code == 405


def test_405_with_allow(client, mapp):
    r = client(mapp).put('/only-post')
    assert r.status_code == 405
    assert r.headers['Allow'] == 'POST'


def test_405_allow_lists_all_sorted(client, mapp):
    r = client(mapp).request('OPTIONS', '/r')
    assert r.status_code == 405
    assert r.headers['Allow'] == 'DELETE,GET,PATCH,POST,PUT'


def test_405_allow_for_dynamic_routes(client):
    a = mk()

    @a.post('/d/<x>')
    def f(x): return x

    r = client(a).get('/d/1')
    assert r.status_code == 405 and r.headers['Allow'] == 'POST'


def test_405_allow_excludes_proxy_pseudo_method(client):
    a = mk()
    a.mount('/m', lambda e, s: (s('200 OK', []), [b'x'])[1])

    @a.post('/zz')
    def f(): return 'x'

    r = client(a).get('/zz')
    assert r.status_code == 405 and 'PROXY' not in r.headers['Allow']


def test_404_unknown(client, mapp):
    assert client(mapp).get('/nope').status_code == 404


def test_404_body_does_not_reflect_raw_html():
    a = mk()
    r = lcore.TestClient(a).get('/<script>alert(1)</script>')
    assert r.status_code == 404
    assert '<script>alert(1)</script>' not in r.text


def test_head_falls_back_to_get(client, mapp):
    r = client(mapp).head('/getonly')
    assert r.status_code == 200
    assert r.body == b''


def test_head_content_length_matches_get(client, mapp):
    c = client(mapp)
    g = c.get('/getonly')
    h = c.head('/getonly')
    assert h.headers.get('Content-Length') == g.headers.get('Content-Length') == str(len(b'body-data'))


def test_explicit_head_route_beats_get():
    a = mk()

    @a.route('/x', method='GET')
    def g(): return 'get'

    @a.route('/x', method='HEAD')
    def h():
        response.set_header('X-Which', 'head')
        return ''

    r = lcore.TestClient(a).head('/x')
    assert r.headers.get('X-Which') == 'head'


def test_head_on_post_only_is_405(client, mapp):
    assert client(mapp).head('/only-post').status_code == 405


def test_get_does_not_fall_to_post(client, mapp):
    assert client(mapp).get('/only-post').status_code == 405


def test_head_body_stripped_live(live, mapp):
    lv = live(mapp)
    st, h, body = lv.request('HEAD', '/getonly')
    assert st == 200 and body == b''
    assert h['content-length'] == '9'


def test_unknown_method_to_nonany_route_405(client, mapp):
    assert client(mapp).request('FOO', '/r').status_code == 405


def test_options_is_405_unless_registered():
    a = mk()

    @a.route('/o', method='OPTIONS')
    def o():
        response.set_header('Allow', 'OPTIONS')
        return ''

    assert lcore.TestClient(a).options('/o').status_code == 200


# ---------------------------------------------------------------- trailing slash

def test_trailing_slash_strict(client, app):
    c = client(app)
    assert c.get('/static/page/').status_code == 404
    a = mk()

    @a.route('/s/')
    def f(): return 's'

    assert lcore.TestClient(a).get('/s').status_code == 404
    assert lcore.TestClient(a).get('/s/').status_code == 200


def test_both_slash_forms_can_be_registered():
    a = mk()

    @a.route('/t')
    @a.route('/t/')
    def f(): return 'ok'

    c = lcore.TestClient(a)
    assert c.get('/t').text == 'ok' and c.get('/t/').text == 'ok'


def test_dynamic_trailing_slash_not_matched(client, app):
    assert client(app).get('/user/bob/').status_code == 404


# ---------------------------------------------------------------- paths / encodings

def test_unicode_path_static():
    a = mk()

    @a.route('/café')
    def f(): return 'ok'

    assert lcore.TestClient(a).get(latin('/café')).text == 'ok'


def test_unicode_path_dynamic():
    a = mk()

    @a.route('/u/<n>')
    def f(n): return n

    r = lcore.TestClient(a).get(latin('/u/日本語'))
    assert r.body.decode('utf8') == '日本語'


def test_percent_decoding_live(live):
    a = mk()

    @a.route('/u/<n>')
    def f(n): return n

    lv = live(a)
    st, h, b = lv.request('GET', '/u/caf%C3%A9')
    assert (st, b.decode('utf8')) == (200, 'café')
    st, h, b = lv.request('GET', '/u/a%20b')
    assert b == b'a b'


def test_encoded_slash_does_not_cross_segments_live(live):
    a = mk()

    @a.route('/u/<n>')
    def f(n): return 'n=' + n

    lv = live(a)
    st, h, b = lv.request('GET', '/u/a%2Fb')
    # wsgiref decodes %2F to '/', so a single-segment wildcard must not match
    assert st == 404


@pytest.mark.xfail(strict=True, reason="BUG: invalid UTF-8 percent bytes surrogate-escape into PATH_INFO; echoing it returns 500 instead of a clean 4xx/replacement")
def test_invalid_utf8_percent_live(live):
    a = mk()

    @a.route('/u/<n>')
    def f(n): return 'n=' + n

    st, h, b = live(a).request('GET', '/u/%ff')
    assert st in (200, 400, 404)


def test_invalid_utf8_percent_does_not_crash_server_live(live):
    a = mk()

    @a.route('/u/<n>')
    def f(n): return 'ok'

    lv = live(a)
    st, _, _ = lv.request('GET', '/u/%ff')
    assert st in (200, 400, 404)
    assert lv.request('GET', '/u/fine')[0] == 200


def test_dotdot_segments_not_normalised_by_router(client):
    a = mk()

    @a.route('/a/<x>')
    def f(x): return x

    @a.route('/secret')
    def s(): return 'secret'

    c = client(a)
    assert c.get('/a/../secret').status_code == 404  # no traversal
    assert c.get('/a/..').text == '..'


def test_double_slash_paths_not_collapsed(client, app):
    c = client(app)
    assert c.get('//').status_code == 404
    assert c.get('//static/page').status_code == 404
    assert c.get('/static//page').status_code == 404


def test_path_filter_with_dotdot_gets_raw_value(client, app):
    assert client(app).get('/files/../../etc/passwd').text == 'path:../../etc/passwd'


def test_very_long_static_path_404(client, app):
    r = client(app).get('/' + 'a' * 100000)
    assert r.status_code == 404


def test_very_long_dynamic_segment(client, app):
    r = client(app).get('/user/' + 'a' * 200000)
    assert r.status_code == 200 and len(r.text) == 200005


def test_nul_and_control_chars_in_path(client, app):
    assert client(app).get('/user/a\x00b').text == 'user:a\x00b'


def test_query_string_ignored_for_matching(client, app):
    assert client(app).get('/static/page', query_string='x=1&y=2').status_code == 200


def test_regex_catastrophic_backtracking_is_user_responsibility():
    # sanity: a normal pattern with long non-matching input returns quickly
    a = mk()

    @a.route('/x/<v:re:[a-z]+>')
    def f(v): return v

    r = lcore.TestClient(a).get('/x/' + 'a' * 50000 + '!')
    assert r.status_code == 404


# ---------------------------------------------------------------- priority / conflicts / ordering

def test_static_before_dynamic_regardless_of_order(client):
    a = mk()

    @a.route('/p/<x>')
    def dyn(x): return 'dyn'

    @a.route('/p/special')
    def st(): return 'static'

    c = client(a)
    assert c.get('/p/special').text == 'static'
    assert c.get('/p/other').text == 'dyn'


def test_dynamic_first_registered_wins():
    a = mk()

    @a.route('/p/<x>')
    def one(x): return 'one'

    @a.route('/p/<y:re:[a-z]+>')
    def two(y): return 'two'

    assert lcore.TestClient(a).get('/p/abc').text == 'one'


def test_duplicate_static_route_last_wins():
    a = mk()

    @a.route('/dup')
    def one(): return 'one'

    @a.route('/dup')
    def two(): return 'two'

    assert lcore.TestClient(a).get('/dup').text == 'two'


def test_duplicate_dynamic_route_last_wins_no_growth():
    a = mk()

    @a.route('/d/<x>')
    def one(x): return 'one'

    @a.route('/d/<x>')
    def two(x): return 'two'

    assert lcore.TestClient(a).get('/d/1').text == 'two'
    assert len(a.router.dyna_routes['GET']) == 1


def test_overwrite_warning_in_debug():
    a = mk()
    lcore.DEBUG = True
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter('always')

            @a.route('/d/<x>')
            def one(x): return 'one'

            @a.route('/d/<x>')
            def two(x): return 'two'
        assert any('overwrites' in str(i.message) for i in w)
    finally:
        lcore.DEBUG = False


def test_strict_order_router_respects_registration_order():
    a = mk()
    a.router = Router(strict=True)

    @a.route('/p/<x>')
    def dyn(x): return 'dyn'

    @a.route('/p/special')
    def st(): return 'static'

    assert lcore.TestClient(a).get('/p/special').text == 'dyn'


def test_same_rule_different_methods_independent(client):
    a = mk()

    @a.get('/m/<x>')
    def g(x): return 'g'

    @a.post('/m/<x>')
    def p(x): return 'p'

    c = client(a)
    assert c.get('/m/1').text == 'g' and c.post('/m/1').text == 'p'


def test_any_loses_to_specific_method():
    a = mk()

    @a.route('/z', method='ANY')
    def anyh(): return 'any'

    @a.get('/z')
    def g(): return 'get'

    c = lcore.TestClient(a)
    assert c.get('/z').text == 'get'
    assert c.post('/z').text == 'any'


def test_specific_dynamic_method_beats_any_static():
    a = mk()

    @a.route('/y/s', method='ANY')
    def anyh(): return 'any'

    @a.get('/y/<x>')
    def g(x): return 'dyn'

    # method order is GET, then ANY: GET dynamic wins over ANY static
    assert lcore.TestClient(a).get('/y/s').text == 'dyn'


def test_route_decorator_returns_original_function():
    a = mk()

    def f(): return 'x'

    assert a.route('/q')(f) is f


def test_route_with_callback_arg_and_list_of_paths():
    a = mk()
    a.route(['/a1', '/a2', '/a3/<n>'], callback=lambda n=None: 'ok')
    c = lcore.TestClient(a)
    assert c.get('/a1').status_code == 200 and c.get('/a2').status_code == 200


def test_yieldroutes_from_function_name_and_defaults():
    a = mk()

    @a.route
    def hello__world(name='x'): return 'hw:' + name

    c = lcore.TestClient(a)
    assert c.get('/hello/world').text == 'hw:x'
    assert c.get('/hello/world/bob').text == 'hw:bob'


def test_many_routes_1000_mixed():
    a = mk()
    for i in range(1000):
        a.route('/s%d' % i, callback=(lambda i=i: lambda: 'static%d' % i)())
        a.route('/d%d/<x>' % i, callback=(lambda i=i: lambda x: 'dyn%d:%s' % (i, x))())
    c = lcore.TestClient(a)
    for i in (0, 1, 98, 99, 100, 101, 197, 198, 199, 500, 998, 999):
        assert c.get('/s%d' % i).text == 'static%d' % i
        assert c.get('/d%d/v' % i).text == 'dyn%d:v' % i
    assert c.get('/d1000/v').status_code == 404
    assert c.get('/s1000').status_code == 404


@pytest.mark.parametrize('n', [98, 99, 100, 101, 198, 199, 200, 250])
def test_regex_group_boundaries_every_route_reachable(n):
    a = mk()
    for i in range(n):
        a.route('/g%d/<x>' % i, callback=(lambda i=i: lambda x: 'r%d' % i)())
    c = lcore.TestClient(a)
    for i in range(n):
        assert c.get('/g%d/z' % i).text == 'r%d' % i, i


def test_dynamic_routes_with_many_groups_each_reachable():
    # routes each carrying 5 groups: combined-pattern chunking by route count
    # must still keep the python regex group limit safe
    a = mk()
    for i in range(120):
        a.route('/m%d/<a>/<b>/<c>/<d>/<e>' % i, callback=(lambda i=i: lambda a, b, c, d, e: 'm%d' % i)())
    c = lcore.TestClient(a)
    for i in (0, 50, 99, 119):
        assert c.get('/m%d/1/2/3/4/5' % i).text == 'm%d' % i


def test_many_routes_overwrite_across_chunk_boundary():
    a = mk()
    for i in range(150):
        a.route('/h%d/<x>' % i, callback=(lambda i=i: lambda x: 'v1-%d' % i)())
    a.route('/h120/<x>', callback=lambda x: 'v2')
    c = lcore.TestClient(a)
    assert c.get('/h120/q').text == 'v2'
    assert c.get('/h121/q').text == 'v1-121'


# ---------------------------------------------------------------- 404 vs 405 / error pages

def test_405_vs_404_for_other_method_dynamic_mismatch(client):
    a = mk()

    @a.post('/i/<n:int>')
    def f(n): return 'x'

    c = client(a)
    assert c.get('/i/abc').status_code == 404
    assert c.get('/i/1').status_code == 405


def test_custom_404_handler(client):
    a = mk()

    @a.error(404)
    def e(err): return 'custom404'

    r = client(a).get('/nothing')
    assert r.status_code == 404 and r.text == 'custom404'


def test_custom_405_handler_sees_allow(client):
    a = mk()

    @a.post('/x')
    def f(): return ''

    @a.error(405)
    def e(err): return 'no:' + response.headers.get('Allow', '')

    r = client(a).get('/x')
    assert r.status_code == 405 and r.text == 'no:POST'


# ---------------------------------------------------------------- names / url building

def test_named_route_build():
    a = mk()

    @a.route('/user/<id:int>/<slug>', name='user')
    def f(id, slug): return ''

    assert a.router.build('user', id=3, slug='x') == '/user/3/x'


def test_build_by_rule_string():
    a = mk()

    @a.route('/plain')
    def f(): return ''

    assert a.router.build('/plain') == '/plain'


def test_build_missing_arg_raises():
    a = mk()

    @a.route('/u/<id>', name='u')
    def f(id): return ''

    with pytest.raises(RouteBuildError):
        a.router.build('u')


def test_build_unknown_name_raises():
    with pytest.raises(RouteBuildError):
        mk().router.build('ghost')


def test_build_extra_args_become_query_string():
    a = mk()

    @a.route('/u/<id>', name='u')
    def f(id): return ''

    assert a.router.build('u', id=1, q='a b', z=['1', '2']) in ('/u/1?q=a+b&z=1&z=2', '/u/1?z=1&z=2&q=a+b')


def test_build_positional_anon():
    a = mk()

    @a.route('/<:int>/<:re:[a-z]+>', name='anon')
    def f(): return ''

    assert a.router.build('anon', 5, 'abc') == '/5/abc'


def test_build_int_filter_normalises_value():
    a = mk()

    @a.route('/n/<i:int>', name='n')
    def f(i): return ''

    assert a.router.build('n', i='007') == '/n/7'


def test_build_int_filter_rejects_non_int():
    a = mk()

    @a.route('/n/<i:int>', name='n')
    def f(i): return ''

    with pytest.raises(ValueError):
        a.router.build('n', i='abc')


def test_get_url_inside_request_honours_script_name(client):
    a = mk()

    @a.route('/where', name='where')
    def f(): return a.get_url('where')

    r = client(a).get('/where', headers={})
    assert r.text == '/where'
    # SCRIPT_NAME
    from lcore import TestClient
    env_c = TestClient(a)
    orig = env_c.app

    def wrapper(environ, sr):
        environ['SCRIPT_NAME'] = '/prefix'
        return orig(environ, sr)

    env_c.app = wrapper
    assert env_c.get('/where').text == '/prefix/where'


@pytest.mark.xfail(strict=True, reason="BUG: Router.build/get_url do not percent-encode path values (space, '/', '?', '#' produce broken/ambiguous URLs)")
@pytest.mark.parametrize('val,enc', [('a b', 'a%20b'), ('a/b', 'a%2Fb'), ('a?b', 'a%3Fb'), ('a#b', 'a%23b')])
def test_build_quotes_path_values(val, enc):
    a = mk()

    @a.route('/u/<s>', name='u')
    def f(s): return ''

    assert a.router.build('u', s=val) == '/u/' + enc


def test_duplicate_route_names_last_wins():
    a = mk()

    @a.route('/one', name='n')
    def f(): return ''

    @a.route('/two', name='n')
    def g(): return ''

    assert a.router.build('n') == '/two'


def test_name_applies_to_each_method_route():
    a = mk()

    @a.route('/x', method=['GET', 'POST'], name='x')
    def f(): return ''

    assert a.router.build('x') == '/x'


# ---------------------------------------------------------------- route groups

def test_group_prefixes(client):
    a = mk()
    g = a.group('/api')

    @g.get('/users')
    def u(): return 'users'

    @g.post('/users')
    def cu(): return 'create'

    @g.get('/<id:int>')
    def one(id): return 'one%d' % id

    c = client(a)
    assert c.get('/api/users').text == 'users'
    assert c.post('/api/users').text == 'create'
    assert c.get('/api/5').text == 'one5'


def test_group_trailing_slash_prefix_normalised(client):
    a = mk()
    g = a.group('/api/')

    @g.get('x')
    def f(): return 'x'

    assert client(a).get('/api/x').text == 'x'


def test_group_default_path_is_prefix_slash(client):
    a = mk()
    g = a.group('/v1')

    @g.get()
    def f(): return 'root'

    assert client(a).get('/v1/').text == 'root'


def test_group_context_manager_and_put_patch_delete(client):
    a = mk()
    with a.group('/g') as g:
        g.put('/r')(lambda: 'put')
        g.patch('/r')(lambda: 'patch')
        g.delete('/r')(lambda: 'del')
    c = client(a)
    assert [c.request(m, '/g/r').text for m in ('PUT', 'PATCH', 'DELETE')] == ['put', 'patch', 'del']


def test_group_common_config_and_override():
    a = mk()
    g = a.group('/c', flag=1)

    @g.get('/a')
    def f(): return ''

    @g.get('/b', flag=2)
    def h(): return ''

    ra, rb = a.routes
    assert ra.config['flag'] == 1 and rb.config['flag'] == 2


def test_group_does_not_mutate_parent_prefix():
    a = mk()
    a.group('/one')
    g2 = a.group('/two')
    g2.get('/x')(lambda: 'x')
    assert [r.rule for r in a.routes] == ['/two/x']


def test_nested_group_by_prefix_concat(client):
    a = mk()
    g = a.group('/a' + '/b')
    g.get('/c')(lambda: 'abc')
    assert client(a).get('/a/b/c').text == 'abc'


def test_group_route_with_name_and_method_kw():
    a = mk()
    g = a.group('/n')
    g.route('/x', method=['GET', 'POST'], name='gx')(lambda: '')
    assert a.router.build('gx') == '/n/x'


# ---------------------------------------------------------------- route config, skip

def test_route_config_accessible_in_handler():
    a = mk()

    @a.route('/cfg', auth='admin', limit=5)
    def f(): return '%s/%s' % (request.route.config['auth'], request.route.config['limit'])

    assert lcore.TestClient(a).get('/cfg').text == 'admin/5'


def test_route_config_falls_back_to_app_config():
    a = mk()
    a.config['site.name'] = 'lc'

    @a.route('/cfg')
    def f(): return request.route.config['site.name']

    assert lcore.TestClient(a).get('/cfg').text == 'lc'


def test_route_config_dict_namespaces():
    a = mk()

    @a.route('/cfg', **{'x.y': 3})
    def f(): return str(request.route.config['x.y'])

    assert lcore.TestClient(a).get('/cfg').text == '3'


def test_skip_plugin_by_name():
    calls = []

    class P:
        name = 'p'
        api = 2

        def apply(self, cb, route):
            def w(*a, **k):
                calls.append(1)
                return cb(*a, **k)
            return w

    a = mk()
    a.install(P())
    a.route('/s1')(lambda: 'a')
    a.route('/s2', skip=['p'])(lambda: 'b')
    c = lcore.TestClient(a)
    c.get('/s1'); assert calls == [1]
    c.get('/s2'); assert calls == [1]


def test_skip_true_skips_all_plugins_including_json():
    a = mk()
    a.route('/s', skip=True)(lambda: {'a': 1})
    r = lcore.TestClient(a).get('/s')
    # dict return without JSONPlugin cannot be cast -> not JSON
    assert r.headers.get('Content-Type', '').startswith('application/json') is False


def test_skip_by_plugin_instance_and_type():
    class P:
        name = 'pp'
        api = 2
        hits = 0

        def apply(self, cb, route):
            def w(*a, **k):
                P.hits += 1
                return cb(*a, **k)
            return w

    a = mk()
    p = a.install(P())
    a.route('/i', skip=[p])(lambda: 'x')
    a.route('/t', skip=[P])(lambda: 'x')
    c = lcore.TestClient(a)
    c.get('/i'); c.get('/t')
    assert P.hits == 0


def test_route_level_apply_plugin():
    def deco(cb):
        def w(*a, **k): return 'wrapped:' + cb(*a, **k)
        return w

    a = mk()
    a.route('/ap', apply=[deco])(lambda: 'x')
    assert lcore.TestClient(a).get('/ap').text == 'wrapped:x'


def test_show_routes_lists_everything():
    a = mk()
    a.route('/a', name='an')(lambda: '')
    a.post('/b')(lambda: '')
    rows = a.show_routes()
    assert [(r['method'], r['rule'], r['name']) for r in rows] == [('GET', '/a', 'an'), ('POST', '/b', '')]
    assert 'json' in rows[0]['plugins']


# ---------------------------------------------------------------- mounting

def test_mount_lcore_subapp(client):
    sub = mk()

    @sub.route('/x')
    def x(): return 'x'

    @sub.route('/')
    def root(): return 'root'

    @sub.route('/<n:int>')
    def n(n): return 'n%d' % n

    m = mk()
    m.mount('/sub/', sub)
    c = client(m)
    assert c.get('/sub/x').text == 'x'
    assert c.get('/sub/').text == 'root'
    assert c.get('/sub/7').text == 'n7'
    assert c.get('/x').status_code == 404
    assert c.get('/sub').status_code == 404


def test_mount_prefix_must_start_with_slash():
    with pytest.raises(ValueError):
        mk().mount('sub/', mk())


def test_mount_wsgi_root_rejected():
    with pytest.raises(ValueError):
        mk().mount('/', lambda e, s: [])


def wsgi_echo(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [('%s|%s' % (environ['SCRIPT_NAME'], environ['PATH_INFO'])).encode()]


def test_mount_wsgi_app_path_shift(client):
    m = mk()
    m.mount('/w', wsgi_echo)
    c = client(m)
    assert c.get('/w/a/b').text == '/w|/a/b'
    assert c.get('/w').text == '/w|/'
    assert c.get('/wx/a').status_code == 404


def test_mount_wsgi_nested_prefix(client):
    m = mk()
    m.mount('/a/b', wsgi_echo)
    assert client(m).get('/a/b/c').text == '/a/b|/c'


def test_mount_wsgi_restores_request_script_name_after(client):
    m = mk()
    seen = []
    m.mount('/w', wsgi_echo)

    @m.hook('after_request')
    def h(): seen.append((request.script_name, request.path))

    client(m).get('/w/zz')
    assert seen == [('/', '/w/zz')]


def test_mount_wsgi_preserves_method_and_body(client):
    def echo(environ, sr):
        sr('201 Created', [('X-M', environ['REQUEST_METHOD'])])
        return [environ['wsgi.input'].read(int(environ['CONTENT_LENGTH']))]

    m = mk()
    m.mount('/e', echo)
    r = client(m).post('/e/', body=b'payload')
    assert (r.status_code, r.text, r.headers['X-M']) == (201, 'payload', 'POST')


def test_mount_wsgi_any_method(client):
    m = mk()
    m.mount('/w', wsgi_echo)
    for meth in ('GET', 'PUT', 'DELETE', 'PATCH', 'POST'):
        assert client(m).request(meth, '/w/q').status_code == 200


def test_mount_wsgi_raises_in_child_gives_500(client):
    def bad(environ, sr): raise RuntimeError('x')

    m = mk()
    m.mount('/b', bad)
    assert client(m).get('/b/z').status_code == 500


def test_mount_wsgi_state_restored_after_exception():
    def bad(environ, sr): raise RuntimeError('x')

    m = mk()
    m.mount('/b', bad)
    m.route('/ok')(lambda: request.script_name)
    c = lcore.TestClient(m)
    c.get('/b/z')
    assert c.get('/ok').text == '/'


def test_mount_lcore_without_trailing_slash_falls_back_to_wsgi(client):
    sub = mk()
    sub.route('/x')(lambda: 'subx')
    m = mk()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        m.mount('/sub', sub)
    assert client(m).get('/sub/x').text == 'subx'


def test_mount_same_app_twice_falls_back_to_wsgi(client):
    sub = mk()
    sub.route('/x')(lambda: 'subx')
    m = mk()
    m.mount('/one/', sub)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        m.mount('/two/', sub)
    c = client(m)
    assert c.get('/one/x').text == 'subx'
    assert c.get('/two/x').text == 'subx'


def test_mount_hooks_scoped_to_module():
    sub = mk()
    log = []
    sub.add_hook('before_request', lambda: log.append('sub-before'))
    sub.route('/x')(lambda: 'x')
    m = mk()
    m.route('/other')(lambda: 'o')
    m.mount('/sub/', sub)
    c = lcore.TestClient(m)
    c.get('/other')
    assert log == []
    c.get('/sub/x')
    assert log == ['sub-before']


def test_mount_on_module_mount_hook_fires():
    fired = []
    m = mk()
    m.add_hook('on_module_mount', lambda prefix, app: fired.append(prefix))
    m.mount('/s/', mk())
    assert fired == ['/s/']


def test_merge_routes():
    a, b = mk(), mk()
    b.route('/b')(lambda: 'b')
    a.merge(b)
    assert lcore.TestClient(a).get('/b').text == 'b'


def test_mount_subapp_errors_use_parent_handlers(client):
    sub = mk()
    sub.route('/boom')(lambda: 1 / 0)
    m = mk()
    m.error(500)(lambda e: 'parent500')
    m.mount('/s/', sub)
    assert client(m).get('/s/boom').text == 'parent500'


def test_mount_subapp_route_names_and_build():
    sub = mk()
    sub.route('/thing/<id:int>', name='thing')(lambda id: '')
    m = mk()
    m.mount('/s/', sub)
    assert m.router.build('thing', id=2) == '/s/thing/2'


# ---------------------------------------------------------------- path_shift / SCRIPT_NAME

@pytest.mark.parametrize('sn,pi,shift,exp', [
    ('/', '/a/b/c', 1, ('/a', '/b/c')),
    ('/', '/a/b/c', 2, ('/a/b', '/c')),
    ('/a/b', '/c', -1, ('/a', '/b/c')),
    ('/a', '/b/c/', 1, ('/a/b', '/c/')),
    ('/', '/a', 1, ('/a', '/')),
    ('/x', '/y', 0, ('/x', '/y')),
    ('/a/b', '/', -2, ('/', '/a/b/')),
])
def test_path_shift_function(sn, pi, shift, exp):
    assert path_shift(sn, pi, shift) == exp


@pytest.mark.parametrize('sn,pi,shift', [('/', '/', 1), ('/', '/a', 2), ('/', '/a', -1)])
def test_path_shift_errors(sn, pi, shift):
    with pytest.raises(AssertionError):
        path_shift(sn, pi, shift)


def test_request_path_shift_roundtrip(client):
    a = mk()

    @a.route('/p/q')
    def f():
        before = (request.script_name, request.path)
        request.path_shift(1)
        mid = (request.script_name, request.path)
        request.path_shift(-1)
        return repr((before, mid, (request.script_name, request.path)))

    assert client(a).get('/p/q').text == repr((('/', '/p/q'), ('/p/', '/q'), ('/', '/p/q')))


def test_script_name_prefix_in_fullpath(client):
    a = mk()
    a.route('/x')(lambda: request.fullpath + '|' + request.url)
    orig = a

    def wrapped(environ, sr):
        environ['SCRIPT_NAME'] = '/app'
        return orig(environ, sr)

    r = lcore.TestClient(wrapped).get('/x')
    assert r.text.startswith('/app/x|http://localhost/app/x')


# ---------------------------------------------------------------- reset / removal / state

def test_app_reset_triggers_hook_and_rebuilds_callbacks(client):
    a = mk()
    fired = []
    a.add_hook('app_reset', lambda: fired.append(1))
    a.route('/x')(lambda: 'x')
    c = client(a)
    c.get('/x')
    a.reset()
    assert fired and c.get('/x').text == 'x'


def test_reset_single_route_by_index_and_instance():
    a = mk()
    a.route('/x')(lambda: 'x')
    r = a.routes[0]
    r.call
    assert 'call' in r.__dict__
    a.reset(0)
    assert 'call' not in r.__dict__
    r.call
    a.reset(r)
    assert 'call' not in r.__dict__


def test_install_plugin_late_applies_to_existing_routes():
    a = mk()
    a.route('/x')(lambda: 'x')
    c = lcore.TestClient(a)
    assert c.get('/x').text == 'x'

    class P:
        api = 2
        def apply(self, cb, route):
            return lambda *a, **k: 'P' + cb(*a, **k)

    a.install(P())
    assert c.get('/x').text == 'Px'


def test_router_has_no_remove_but_new_app_clean():
    # routes of one app never leak into another
    a, b = mk(), mk()
    a.route('/only-a')(lambda: 'a')
    assert lcore.TestClient(b).get('/only-a').status_code == 404


def test_default_app_module_level_route():
    app = lcore.default_app.push()
    try:
        lcore.route('/mod-level')(lambda: 'ml')
        assert lcore.TestClient(app).get('/mod-level').text == 'ml'
    finally:
        lcore.default_app.pop()


# ---------------------------------------------------------------- concurrency / state

def test_concurrent_requests_do_not_leak_url_args(live):
    a = mk()

    @a.route('/echo/<n:int>')
    def f(n):
        import time; time.sleep(0.005)
        return str(n) + '|' + request.path

    lv = live(a)
    errs = []

    def worker(i):
        try:
            for j in range(10):
                n = i * 100 + j
                st, h, b = lv.request('GET', '/echo/%d' % n)
                if b.decode() != '%d|/echo/%d' % (n, n):
                    errs.append((n, b))
        except Exception as e:
            errs.append(e)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs


def test_repeated_requests_same_result(client, app):
    c = client(app)
    assert {c.get('/user/z').text for _ in range(200)} == {'user:z'}


def test_route_registration_while_serving_is_safe(client):
    a = mk()
    a.route('/base')(lambda: 'b')
    c = client(a)
    for i in range(50):
        a.route('/late%d/<x>' % i, callback=(lambda i=i: lambda x: 'L%d' % i)())
        assert c.get('/late%d/v' % i).text == 'L%d' % i
        assert c.get('/base').text == 'b'


def test_url_args_available_in_request(client):
    a = mk()

    @a.route('/u/<n:int>')
    def f(n): return repr(request.url_args)

    assert client(a).get('/u/4').text == "{'n': 4}"


def test_handler_signature_mismatch_is_500(client):
    a = mk()

    @a.route('/u/<n>')
    def f(): return 'x'

    assert client(a).get('/u/1').status_code == 500


@pytest.mark.xfail(strict=True, reason="BUG: invalid-UTF-8 %xx in path + any error page -> Request.url urlquote hits surrogate -> wsgi() fallback tob() raises -> exception escapes to the server")
@pytest.mark.parametrize('path', ['/%e9', '/%ff/x', '/ok%ff'])
def test_invalid_utf8_in_unknown_path_is_clean_404_live(live, path):
    a = mk()
    a.route('/ok')(lambda: 'ok')
    lv = live(a)
    st, h, b = lv.request('GET', path)
    assert st == 404
    assert lv.request('GET', '/ok')[0] == 200


@pytest.mark.xfail(strict=True, reason="BUG: wsgi() critical-error fallback does tob(err) on a path containing surrogates and raises from inside the except block")
def test_wsgi_critical_fallback_survives_surrogate_path():
    a = mk()
    a.route('/ok')(lambda: 'ok')
    c = lcore.TestClient(a)
    r = c.get('/é')  # 'é' as latin-1 byte 0xE9 == invalid utf-8 after recode
    assert r.status_code in (400, 404)


def test_empty_rule_with_def_function_name_fallback_is_documented_quirk():
    a = mk()

    def foo(): return 'foo'

    a.route('')(foo)  # falsy path -> yieldroutes (Bottle quirk): serves /foo, not /
    assert lcore.TestClient(a).get('/foo').text == 'foo'
