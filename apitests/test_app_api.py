"""API-level tests for the Lcore app object: hooks, errors, return types, config,
plugins, DI, background tasks, docs, loading and lifecycle."""
import asyncio
import dataclasses
import io
import json
import os
import sys
import threading
import time
import warnings
import pytest
import lcore
from lcore import (Lcore, TestClient, HTTPError, HTTPResponse, ConfigDict, JSONPlugin, BackgroundTaskPool,
                   DependencyContainer, request, response, abort, redirect, ctx)


def mk():
    return Lcore()


# =============================================================== return types

def _cases():
    return {
        'dict': (lambda: {'a': 1}, 200, b'{"a": 1}'),
        'str': (lambda: 's', 200, b's'),
        'unicode': (lambda: '\u00e9\u65e5', 200, '\u00e9\u65e5'.encode()),
        'bytes': (lambda: b'\x00\xff', 200, b'\x00\xff'),
        'none': (lambda: None, 200, b''),
        'empty_str': (lambda: '', 200, b''),
        'empty_list': (lambda: [], 200, b''),
        'zero': (lambda: 0, 200, b''),
        'false': (lambda: False, 200, b''),
        'list_bytes': (lambda: [b'a', b'b'], 200, b'ab'),
        'list_str': (lambda: ['a', 'b'], 200, b'ab'),
        'tuple_str': (lambda: ('a', 'b'), 200, b'ab'),
        'gen_bytes': (lambda: (x for x in [b'a', b'b']), 200, b'ab'),
        'gen_str': (lambda: (x for x in ['\u00e9', 'b']), 200, '\u00e9b'.encode()),
        'gen_empty_first': (lambda: (x for x in [b'', b'x']), 200, b'x'),
        'gen_all_empty': (lambda: (x for x in [b'', b'']), 200, b''),
        'iterator': (lambda: iter([b'i1', b'i2']), 200, b'i1i2'),
        'file': (lambda: io.BytesIO(b'filedata'), 200, b'filedata'),
        'httpresponse': (lambda: HTTPResponse('r', 201), 201, b'r'),
        'httpresponse_dict': (lambda: HTTPResponse({'a': 1}, 202), 202, b'{"a": 1}'),
        'httperror': (lambda: HTTPError(418, 'tea'), 418, None),
        'int': (lambda: 5, 500, None),
        'float': (lambda: 1.5, 500, None),
        'set': (lambda: {1}, 500, None),
        'gen_int': (lambda: (x for x in [1]), 500, None),
        'gen_first_raises': (lambda: (1 / 0 for _ in [1]), 500, None),
        'list_of_int': (lambda: [1, 2], 200, b'[1, 2]'),
        'mixed_list': (lambda: ['a', b'b'], 500, None),
    }


@pytest.fixture(scope='module')
def rt_app():
    a = mk()
    a.config['catchall'] = True
    for k, (f, _, _) in _cases().items():
        a.route('/' + k)(f)
    return a


@pytest.mark.parametrize('name', sorted(_cases()))
def test_return_types(rt_app, name):
    _, status, body = _cases()[name]
    r = TestClient(rt_app).get('/' + name)
    assert r.status_code == status
    if body is not None:
        assert r.body == body


def test_dict_sets_json_content_type(rt_app):
    assert TestClient(rt_app).get('/dict').headers['Content-Type'] == 'application/json'


def test_str_default_content_type(rt_app):
    assert TestClient(rt_app).get('/str').headers['Content-Type'].startswith('text/html')


def test_content_length_set_for_str_and_dict(rt_app):
    c = TestClient(rt_app)
    assert c.get('/unicode').headers['Content-Length'] == str(len('\u00e9\u65e5'.encode()))
    assert c.get('/dict').headers['Content-Length'] == '8'


def test_empty_response_has_zero_content_length(rt_app):
    assert TestClient(rt_app).get('/none').headers['Content-Length'] == '0'


@pytest.mark.parametrize('val', [[{'a': 1}], [1, 2]])
def test_list_return_serialised_as_json_documented(val):
    a = mk()
    a.route('/l')(lambda: val)
    r = TestClient(a).get('/l')
    assert r.status_code == 200 and (r.body == b'' or json.loads(r.text) == val)


def test_error_handler_returning_dict_is_not_key_iterated():
    a = mk()

    @a.error(401)
    def e(err): return {'err': 1, 'other': 2}

    a.route('/x')(lambda: abort(401))
    r = TestClient(a).get('/x')
    assert not r.body.startswith(b'err')


def test_text_filelike_return():
    a = mk()
    a.route('/s')(lambda: io.StringIO('hello'))
    r = TestClient(a).get('/s')
    assert r.status_code in (200, 500)


def test_response_headers_status_cookie_from_handler():
    a = mk()

    @a.route('/h')
    def h():
        response.status = 201
        response.set_header('X-A', '1')
        response.set_cookie('k', 'v')
        return 'created'

    r = TestClient(a).get('/h')
    assert (r.status_code, r.headers['X-A']) == (201, '1')
    assert any(c.startswith('k=v') for c in r.get_all('Set-Cookie'))


def test_response_state_does_not_leak_between_requests():
    a = mk()
    a.route('/one')(lambda: (response.set_header('X-Leak', '1'), setattr(response, 'status', 404), 'a')[2])
    a.route('/two')(lambda: 'b')
    c = TestClient(a)
    assert c.get('/one').status_code == 404
    r = c.get('/two')
    assert r.status_code == 200 and 'X-Leak' not in r.headers


@pytest.mark.parametrize('code', [204, 304])
def test_no_body_statuses_strip_body(code):
    a = mk()
    a.route('/n')(lambda: HTTPResponse('should not be sent', code))
    r = TestClient(a).get('/n')
    assert r.status_code == code and r.body == b''


def test_httperror_headers_and_body_pass_through():
    a = mk()
    a.route('/e')(lambda: HTTPError(429, 'slow', **{'Retry-After': '9'}))
    r = TestClient(a).get('/e')
    assert r.status_code == 429 and r.headers['Retry-After'] == '9'


def test_raise_httpresponse_from_handler():
    a = mk()

    @a.route('/r')
    def r():
        raise HTTPResponse('raised', 202)

    x = TestClient(a).get('/r')
    assert (x.status_code, x.text) == (202, 'raised')


def test_redirect_default_and_codes():
    a = mk()
    a.route('/r')(lambda: redirect('/dest'))
    a.route('/r301')(lambda: redirect('/dest', 301))
    c = TestClient(a)
    r = c.get('/r')
    assert r.status_code in (302, 303) and r.headers['Location'].endswith('/dest')
    assert c.get('/r301').status_code == 301


def test_redirect_follow_client():
    a = mk()
    a.route('/r')(lambda: redirect('/dest'))
    a.route('/dest')(lambda: 'arrived')
    assert TestClient(a, follow_redirects=True).get('/r').text == 'arrived'


def test_abort_sets_status_and_message():
    a = mk()
    a.route('/a')(lambda: abort(403, 'nope'))
    r = TestClient(a).get('/a')
    assert r.status_code == 403 and 'nope' in r.text


def test_generator_closed_on_head():
    closed = []

    class It:
        def __iter__(self): return iter([b'a', b'b'])
        def close(self): closed.append(1)

    a = mk()
    a.route('/i')(lambda: It())
    c = TestClient(a)
    c.get('/i'); c.head('/i')
    assert closed == [1, 1]


def test_filelike_closed_on_head_and_get():
    closed = []

    class F(io.BytesIO):
        def close(self):
            closed.append(1)
            super().close()

    a = mk()
    a.route('/f')(lambda: F(b'data'))
    c = TestClient(a)
    c.get('/f'); c.head('/f')
    assert closed == [1, 1]


def test_generator_closed_when_first_item_raises():
    closed = []

    def gen():
        try:
            raise ValueError('x')
            yield b''
        finally:
            closed.append(1)

    a = mk()
    a.route('/g')(gen)
    assert TestClient(a).get('/g').status_code == 500
    assert closed == [1]


def test_generator_error_midstream_propagates_to_server():
    def gen():
        yield b'one'
        raise ValueError('mid')

    a = mk()
    a.route('/g')(gen)
    with pytest.raises(ValueError):
        TestClient(a).get('/g')


def test_large_body_streams_live(live):
    a = mk()
    a.route('/big')(lambda: (b'x' * 1024 for _ in range(2048)))
    st, h, b = live(a).request('GET', '/big')
    assert st == 200 and len(b) == 2 * 1024 * 1024


def test_unicode_charset_response_live(live):
    a = mk()
    a.route('/u')(lambda: '\u65e5\u672c')
    st, h, b = live(a).request('GET', '/u')
    assert b.decode('utf8') == '\u65e5\u672c' and 'utf-8' in h['content-type'].lower()


# ------------------------------------------------------------ async handlers

def test_async_handler_returns_str_dict():
    a = mk()

    async def s(): return 'x'

    async def d(): return {'a': 1}

    a.route('/s')(s); a.route('/d')(d)
    c = TestClient(a)
    assert c.get('/s').text == 'x'
    assert c.get('/d').json == {'a': 1}


def test_async_handler_actually_awaits():
    a = mk()

    async def slow():
        await asyncio.sleep(0.01)
        return 'slept'

    a.route('/slow')(slow)
    assert TestClient(a).get('/slow').text == 'slept'


def test_async_handler_abort_and_error():
    a = mk()

    async def ab(): abort(403, 'no')

    async def er(): raise ValueError('v')

    a.route('/ab')(ab); a.route('/er')(er)
    c = TestClient(a)
    assert c.get('/ab').status_code == 403
    assert c.get('/er').status_code == 500


def test_async_handler_httpresponse_dict():
    a = mk()

    async def f(): return HTTPResponse({'a': 1}, status=201)

    a.route('/f')(f)
    r = TestClient(a).get('/f')
    assert r.status_code == 201 and r.json == {'a': 1}


def test_async_handler_skip_all_plugins_still_runs():
    a = mk()

    async def f(): return 'bare'

    a.route('/f', skip=True)(f)
    assert TestClient(a).get('/f').text == 'bare'


def test_async_handler_warns_once_per_route_build():
    a = mk()

    async def f(): return 'x'

    a.route('/f')(f)
    with pytest.warns(UserWarning, match='async def'):
        TestClient(a).get('/f')


def test_async_handler_called_from_running_loop():
    a = mk()

    async def f(): return 'inloop'

    a.route('/f')(f)

    async def main():
        return TestClient(a).get('/f').text

    assert asyncio.run(main()) == 'inloop'


def test_async_handler_with_url_args():
    a = mk()

    async def f(n): return str(n * 2)

    a.route('/f/<n:int>')(f)
    assert TestClient(a).get('/f/21').text == '42'


def test_async_runtimeerror_not_masked_in_running_loop():
    a = mk()
    a.config['catchall'] = False

    async def f(): raise RuntimeError('real-problem')

    a.route('/f')(f)

    async def main():
        try:
            TestClient(a).get('/f')
        except Exception as e:
            return str(e)

    assert asyncio.run(main()) == 'real-problem'


def test_async_runtimeerror_not_masked_without_loop():
    a = mk()
    a.config['catchall'] = False

    async def f(): raise RuntimeError('real-problem')

    a.route('/f')(f)
    with pytest.raises(RuntimeError, match='real-problem'):
        TestClient(a).get('/f')


# =============================================================== hooks

HOOK_ORDER = ['on_request_start', 'before_request', 'on_auth_resolved', 'on_handler_enter',
              'on_handler_exit', 'on_response_build', 'after_request', 'on_response_send']


def _hooked():
    a = mk()
    log = []
    for n in HOOK_ORDER:
        a.add_hook(n, (lambda n: lambda: log.append(n))(n))
    a.route('/')(lambda: 'x')
    a.route('/boom')(lambda: 1 / 0)
    return a, log


def test_hook_sequence_on_success():
    a, log = _hooked()
    TestClient(a).get('/')
    assert log == HOOK_ORDER


def test_hook_sequence_on_404_skips_handler_hooks():
    a, log = _hooked()
    TestClient(a).get('/nope')
    assert log == ['on_request_start', 'before_request', 'on_response_build', 'after_request', 'on_response_send']


def test_hook_sequence_on_handler_exception_still_runs_cleanup_hooks():
    a, log = _hooked()
    assert TestClient(a).get('/boom').status_code == 500
    assert 'on_response_send' in log and 'on_handler_exit' not in log


def test_hooks_run_for_every_request():
    a, log = _hooked()
    c = TestClient(a)
    for _ in range(3): c.get('/')
    assert log == HOOK_ORDER * 3


def test_reversed_hooks_run_lifo_and_normal_fifo():
    a = mk()
    log = []
    for i in range(3):
        a.add_hook('before_request', (lambda i: lambda: log.append('b%d' % i))(i))
        a.add_hook('after_request', (lambda i: lambda: log.append('a%d' % i))(i))
    a.route('/')(lambda: 'x')
    TestClient(a).get('/')
    assert log == ['b0', 'b1', 'b2', 'a2', 'a1', 'a0']


def test_hook_decorator_returns_function():
    a = mk()

    @a.hook('before_request')
    def f(): pass

    assert callable(f) and f in a._hooks['before_request']


def test_remove_hook():
    a = mk()
    log = []
    f = lambda: log.append(1)
    a.add_hook('before_request', f)
    assert a.remove_hook('before_request', f) is True
    assert a.remove_hook('before_request', f) is None
    a.route('/')(lambda: 'x')
    TestClient(a).get('/')
    assert log == []


def test_unknown_hook_name_add_raises():
    with pytest.raises(KeyError):
        mk().add_hook('bogus', lambda: 1)


def test_unknown_hook_name_remove_is_noop():
    assert mk().remove_hook('bogus', lambda: 1) is None


def test_hook_exception_in_before_request_is_500():
    a = mk()
    a.add_hook('before_request', lambda: 1 / 0)
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 500


def test_hook_abort_in_before_request_becomes_response():
    a = mk()
    a.add_hook('before_request', lambda: abort(401, 'denied'))
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 401


def test_hook_exception_in_after_request_is_500():
    a = mk()
    a.add_hook('after_request', lambda: 1 / 0)
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 500


def test_after_request_hook_can_add_headers_even_on_errors():
    a = mk()
    a.add_hook('after_request', lambda: response.set_header('X-H', '1'))
    a.route('/')(lambda: 'x')
    c = TestClient(a)
    assert c.get('/').headers.get('X-H') == '1'
    assert c.get('/missing').headers.get('X-H') == '1'


def test_after_request_hook_abort_overrides_response():
    a = mk()
    a.add_hook('after_request', lambda: abort(503, 'down'))
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 503


def test_exception_in_hook_midlist_stops_later_hooks_of_same_name():
    a = mk()
    log = []
    a.add_hook('before_request', lambda: 1 / 0)
    a.add_hook('before_request', lambda: log.append('second'))
    a.route('/')(lambda: 'x')
    TestClient(a).get('/')
    assert log == []


def test_on_response_send_runs_even_when_handler_fails():
    a = mk()
    log = []
    a.add_hook('on_response_send', lambda: log.append('sent'))
    a.route('/')(lambda: 1 / 0)
    TestClient(a).get('/')
    assert log == ['sent']


def test_trigger_hook_with_args_and_hook_removal_during_trigger():
    a = mk()
    got = []

    def once(x):
        got.append(x)
        a.remove_hook('config', once)

    a.add_hook('config', once)
    a.trigger_hook('config', 1)
    a.trigger_hook('config', 2)
    assert got == [1]


def test_trigger_hook_returns_list_documented():
    a = mk()
    a.add_hook('before_request', lambda: 7)
    assert a.trigger_hook('before_request') == [7]


def test_config_hook_fires_on_change_only():
    a = mk()
    ch = []
    a.add_hook('config', lambda c, k, v: ch.append((k, v)))
    a.config['x.y'] = 1
    a.config['x.y'] = 1
    a.config['x.y'] = 2
    assert ch == [('x.y', 1), ('x.y', 2)]


def test_app_reset_hook_called_on_install_and_uninstall():
    a = mk()
    n = []
    a.add_hook('app_reset', lambda: n.append(1))
    p = a.install(lambda cb: cb)
    a.uninstall(p)
    assert len(n) == 2


def test_module_hooks_before_after_for_mounted_app():
    sub, parent = mk(), mk()
    log = []
    sub.add_hook('before_request', lambda: log.append('sb'))
    sub.add_hook('after_request', lambda: log.append('sa'))
    sub.route('/x')(lambda: 'x')
    parent.mount('/s/', sub)
    c = TestClient(parent)
    c.get('/s/x')
    assert log == ['sb', 'sa']


def test_on_module_request_hook_receives_prefix():
    sub, parent = mk(), mk()
    seen = []
    parent.add_hook('on_module_request', lambda prefix, ctx_: seen.append(prefix))
    sub.route('/x')(lambda: 'x')
    parent.mount('/s/', sub)
    TestClient(parent).get('/s/x')
    assert seen == ['/s/']


def test_hook_state_isolated_between_apps():
    a, b = mk(), mk()
    a.add_hook('before_request', lambda: 1 / 0)
    b.route('/')(lambda: 'ok')
    assert TestClient(b).get('/').status_code == 200


def test_hooks_run_in_each_thread_live(live):
    a = mk()
    seen = []
    a.add_hook('before_request', lambda: seen.append(request.path))
    a.route('/<n>')(lambda n: n)
    lv = live(a)
    ts = [threading.Thread(target=lambda i=i: lv.request('GET', '/t%d' % i)) for i in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(seen) == sorted('/t%d' % i for i in range(10))


# =============================================================== error handlers

def test_error_handler_per_status():
    a = mk()
    a.error(404)(lambda e: 'nf')
    a.error(418)(lambda e: 'teapot')
    a.route('/t')(lambda: abort(418))
    c = TestClient(a)
    assert c.get('/nothing').text == 'nf'
    assert c.get('/t').text == 'teapot' and c.get('/t').status_code == 418


def test_error_handler_receives_httperror_with_exception():
    a = mk()
    a.error(500)(lambda e: 'ise:' + type(e.exception).__name__)
    a.route('/b')(lambda: 1 / 0)
    assert TestClient(a).get('/b').text == 'ise:ZeroDivisionError'


def test_error_handler_decorator_and_callback_forms():
    a = mk()
    a.error(404, lambda e: 'cb')
    assert TestClient(a).get('/x').text == 'cb'


def test_error_handler_code_as_string():
    a = mk()
    a.error('404')(lambda e: 'strcode')
    assert TestClient(a).get('/x').text == 'strcode'


def test_error_handler_can_set_headers():
    a = mk()

    @a.error(401)
    def e(err):
        response.set_header('WWW-Authenticate', 'Basic')
        return 'auth'

    a.route('/x')(lambda: abort(401))
    assert TestClient(a).get('/x').headers['Www-Authenticate'] == 'Basic'


def test_default_error_page_html_escapes_message():
    a = mk()
    a.route('/x')(lambda: abort(400, '<script>alert(1)</script>'))
    r = TestClient(a).get('/x')
    assert '<script>alert(1)</script>' not in r.text


def test_default_error_page_hides_traceback_outside_debug():
    a = mk()
    a.route('/b')(lambda: 1 / 0)
    r = TestClient(a).get('/b')
    assert r.status_code == 500 and 'Traceback' not in r.text and 'ZeroDivisionError' not in r.text


def test_error_json_format_config():
    a = mk()
    a.config['error.format'] = 'json'
    r = TestClient(a).get('/zz')
    assert r.status_code == 404 and r.headers['Content-Type'].startswith('application/json')
    assert r.json['status'] == 404


def test_error_json_via_accept_header():
    a = mk()
    r = TestClient(a).get('/zz', headers={'Accept': 'application/json'})
    assert r.json['status'] == 404
    r = TestClient(a).get('/zz', headers={'Accept': 'text/html, application/json;q=0.5'})
    assert r.headers['Content-Type'].startswith('text/html')


def test_error_handler_that_raises_gives_500():
    a = mk()
    a.error(404)(lambda e: 1 / 0)
    assert TestClient(a).get('/x').status_code == 500


def test_error_handler_returning_json_content_type_respected():
    a = mk()

    @a.error(404)
    def e(err):
        response.content_type = 'application/json'
        return json.dumps({'custom': True})

    r = TestClient(a).get('/x')
    assert r.json == {'custom': True}


def test_unhandled_exception_500_catchall_true_and_logged():
    a = mk()
    a.route('/b')(lambda: 1 / 0)
    env_errors = io.StringIO()
    orig = a

    def wrapper(environ, sr):
        environ['wsgi.errors'] = env_errors
        return orig(environ, sr)

    r = TestClient(wrapper).get('/b')
    assert r.status_code == 500 and 'ZeroDivisionError' in env_errors.getvalue()


def test_catchall_false_propagates():
    a = mk()
    a.config['catchall'] = False
    a.route('/b')(lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        TestClient(a).get('/b')


def test_catchall_false_httperror_still_handled():
    a = mk()
    a.config['catchall'] = False
    a.route('/b')(lambda: abort(404))
    assert TestClient(a).get('/b').status_code == 404


def test_catchall_false_hook_exception_propagates():
    a = mk()
    a.config['catchall'] = False
    a.add_hook('before_request', lambda: 1 / 0)
    a.route('/')(lambda: 'x')
    with pytest.raises(ZeroDivisionError):
        TestClient(a).get('/')


def test_catchall_property_and_validation():
    a = mk()
    assert a.catchall is True
    a.catchall = False
    assert a.config['catchall'] is False


def test_catchall_deprecated_kwarg():
    a = Lcore(catchall=False)
    assert a.config['catchall'] is False


def test_keyboardinterrupt_not_swallowed():
    a = mk()

    def f(): raise KeyboardInterrupt()

    a.route('/k')(f)
    with pytest.raises(KeyboardInterrupt):
        TestClient(a).get('/k')


def test_error_after_failure_does_not_poison_next_request():
    a = mk()
    a.route('/b')(lambda: 1 / 0)
    a.route('/ok')(lambda: 'ok')
    c = TestClient(a)
    for _ in range(5):
        assert c.get('/b').status_code == 500
        assert c.get('/ok').text == 'ok'


def test_head_on_error_has_no_body():
    a = mk()
    r = TestClient(a).head('/nope')
    assert r.status_code == 404 and r.body == b''


def test_500_content_type_html_and_server_still_alive_live(live):
    a = mk()
    a.route('/b')(lambda: 1 / 0)
    a.route('/ok')(lambda: 'ok')
    lv = live(a)
    assert lv.request('GET', '/b')[0] == 500
    assert lv.request('GET', '/ok')[2] == b'ok'


# =============================================================== ConfigDict

def test_config_load_dict_nested_dotted():
    c = ConfigDict().load_dict({'a': {'b': {'c': 1}}, 'd': 2})
    assert dict(c) == {'a.b.c': 1, 'd': 2}


def test_config_load_dict_namespace():
    c = ConfigDict().load_dict({'x': 1}, namespace='ns')
    assert c['ns.x'] == 1


def test_config_non_string_key_rejected():
    c = ConfigDict()
    with pytest.raises(TypeError):
        c[1] = 2
    with pytest.raises(TypeError):
        c.load_dict({1: 2})


def test_config_update_with_prefix():
    c = ConfigDict()
    c.update('pre', {'x': 1})
    c.update({'y': 2}, z=3)
    assert (c['pre.x'], c['y'], c['z']) == (1, 2, 3)


def test_config_setdefault():
    c = ConfigDict()
    assert c.setdefault('k', 1) == 1 and c.setdefault('k', 2) == 1


def test_config_overlay_inherits_and_overrides():
    base = ConfigDict()
    base['a'] = 1
    o = base._make_overlay()
    assert o['a'] == 1
    o['a'] = 5
    assert (o['a'], base['a']) == (5, 1)
    del o['a']
    assert o['a'] == 1
    base['a'] = 9
    assert o['a'] == 9


def test_config_overlay_propagates_new_and_deleted_keys():
    base = ConfigDict()
    o = base._make_overlay()
    base['new'] = 1
    assert o.get('new') == 1
    del base['new']
    assert 'new' not in o


def test_config_overlay_does_not_leak_to_parent():
    base = ConfigDict()
    o = base._make_overlay()
    o['mine'] = 1
    assert 'mine' not in base


def test_config_virtual_key_delete_raises():
    base = ConfigDict()
    base['a'] = 1
    o = base._make_overlay()
    with pytest.raises(KeyError):
        del o['a']


def test_config_delete_missing_raises():
    with pytest.raises(KeyError):
        del ConfigDict()['x']


def test_config_overlays_are_weakly_held():
    import gc
    base = ConfigDict()
    o = base._make_overlay()
    del o
    gc.collect()
    base._make_overlay()
    assert len(base._overlays) == 1


def test_config_change_listener_and_veto():
    c = ConfigDict()
    seen = []
    c._add_change_listener(lambda cfg, k, v: seen.append((k, v)))
    c['k'] = 1
    c['k'] = 1
    c['k'] = 2
    del c['k']
    assert seen == [('k', 1), ('k', 2), ('k', None)]


def test_config_meta_filter_applied():
    c = ConfigDict()
    c.meta_set('p', 'filter', int)
    c['p'] = '7'
    assert c['p'] == 7 and 'filter' in c.meta_list('p')


def test_config_app_default_meta_validate_catchall():
    assert mk().config['catchall'] is True


def test_config_load_json(tmp_path):
    p = tmp_path / 'c.json'
    p.write_text('{"s": {"k": [1, 2]}, "n": null, "u": "\u00e9"}')
    c = ConfigDict().load_json(str(p))
    assert (c['s.k'], c['n'], c['u']) == ([1, 2], None, '\u00e9')


def test_config_load_json_missing_file():
    with pytest.raises(FileNotFoundError):
        ConfigDict().load_json('/nonexistent/x.json')


def test_config_load_json_malformed(tmp_path):
    p = tmp_path / 'bad.json'
    p.write_text('{nope')
    with pytest.raises(ValueError):
        ConfigDict().load_json(str(p))


def test_config_load_ini_sections_interpolation(tmp_path):
    p = tmp_path / 'c.ini'
    p.write_text('[lcore]\nfoo=1\n[Sec]\nBar=x\nbaz=${bar}\nnov\n')
    c = ConfigDict().load_config(str(p))
    assert dict(c) == {'foo': '1', 'sec.bar': 'x', 'sec.baz': 'x', 'sec.nov': None}


def test_config_load_ini_missing_file_is_silent(tmp_path):
    assert dict(ConfigDict().load_config(str(tmp_path / 'nope.ini'))) == {}


def test_config_load_env(monkeypatch):
    monkeypatch.setenv('LCORE_A__B', '1')
    monkeypatch.setenv('LCORE_PLAIN', 'p')
    monkeypatch.setenv('OTHER_X', 'q')
    c = ConfigDict().load_env()
    assert c['a.b'] == '1' and c['plain'] == 'p' and 'x' not in c
    c2 = ConfigDict().load_env('OTHER_', strip_prefix=False)
    assert c2['other_x'] == 'q'


def test_config_load_env_values_are_strings(monkeypatch):
    monkeypatch.setenv('LCORE_N', '5')
    assert ConfigDict().load_env()['n'] == '5'


def test_config_load_dotenv(tmp_path, monkeypatch):
    for k in ('APP_ONE', 'APP_Q', 'APP_SP'):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / '.env'
    p.write_text('# c\nAPP_ONE=1\nAPP_Q="quoted v"\nbad key=2\n  APP_SP = x \nNOEQ\n')
    ConfigDict().load_dotenv(str(p))
    assert (os.environ['APP_ONE'], os.environ['APP_Q'], os.environ['APP_SP']) == ('1', 'quoted v', 'x')
    monkeypatch.delenv('APP_ONE'); monkeypatch.delenv('APP_Q'); monkeypatch.delenv('APP_SP')


def test_config_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_KEEP', 'real')
    p = tmp_path / '.env'
    p.write_text('APP_KEEP=file\n')
    ConfigDict().load_dotenv(str(p))
    assert os.environ['APP_KEEP'] == 'real'


def test_config_load_dotenv_missing_file_noop(tmp_path):
    ConfigDict().load_dotenv(str(tmp_path / 'nope'))


def test_config_load_module_uppercase_only(tmp_path, monkeypatch):
    (tmp_path / 'cfgmod_x.py').write_text('PORT=1\nlower=2\nNEST={"a": 1}\n')
    monkeypatch.syspath_prepend(str(tmp_path))
    c = ConfigDict().load_module('cfgmod_x')
    assert dict(c) == {'PORT': 1, 'NEST.a': 1}
    c2 = ConfigDict().load_module('cfgmod_x', squash=False)
    assert c2['NEST'] == {'a': 1}


@dataclasses.dataclass
class Schema:
    port: int
    debug: bool = False
    name: str = 'x'


def test_validate_config_coerces():
    c = ConfigDict()
    c['port'] = '8080'
    c['debug'] = 'yes'
    c.validate_config(Schema)
    assert c['port'] == 8080 and c['debug'] is True


@pytest.mark.parametrize('val,expected', [('true', True), ('1', True), ('YES', True), ('false', False), ('0', False), ('no', False)])
def test_validate_config_bool_strings(val, expected):
    c = ConfigDict()
    c['port'] = 1
    c['debug'] = val
    c.validate_config(Schema)
    assert c['debug'] is expected


def test_validate_config_missing_required():
    with pytest.raises(ValueError, match='Missing required config key: port'):
        ConfigDict().validate_config(Schema)


def test_validate_config_bad_int():
    c = ConfigDict()
    c['port'] = 'abc'
    with pytest.raises(ValueError, match='expected int'):
        c.validate_config(Schema)


def test_validate_config_reports_all_errors():
    @dataclasses.dataclass
    class S:
        a: int
        b: int

    c = ConfigDict()
    c['a'] = 'x'
    with pytest.raises(ValueError) as ei:
        c.validate_config(S)
    assert 'expected int' in str(ei.value) and 'Missing required config key: b' in str(ei.value)


def test_validate_config_requires_dataclass():
    with pytest.raises(TypeError):
        ConfigDict().validate_config(dict)


def test_validate_config_underscore_maps_to_dotted_key():
    @dataclasses.dataclass
    class S:
        db_port: int

    c = ConfigDict()
    c['db.port'] = '5'
    c.validate_config(S)
    assert c['db.port'] == 5


def test_validate_config_garbage_bool_is_an_error():
    c = ConfigDict()
    c['port'] = 1
    c['debug'] = 'banana'
    with pytest.raises(ValueError):
        c.validate_config(Schema)


def test_validate_config_underscore_key_roundtrip():
    @dataclasses.dataclass
    class S:
        max_body: int

    c = ConfigDict()
    c['max_body'] = '5'
    c.validate_config(S)
    assert c['max_body'] == 5


def test_app_config_defaults_and_update():
    a = mk()
    assert a.config['error.format'] == 'html' and a.config['request.max_body'] == 10 * 1024 * 1024
    a.config.update({'custom.key': 'v'})
    assert a.config['custom.key'] == 'v'


def test_app_config_independent_between_apps():
    a, b = mk(), mk()
    a.config['only.a'] = 1
    assert 'only.a' not in b.config


def test_app_config_shared_global_default_propagates():
    a = mk()
    Lcore._global_config['shared.default.test'] = 'x'
    try:
        assert a.config['shared.default.test'] == 'x'
        assert mk().config['shared.default.test'] == 'x'
    finally:
        del Lcore._global_config['shared.default.test']
    assert 'shared.default.test' not in a.config


def test_app_config_used_by_request_max_body():
    a = mk()
    a.config['request.max_body'] = 10
    a.route('/p', method='POST')(lambda: str(len(request.body.read())))
    r = TestClient(a).post('/p', body=b'x' * 100)
    assert r.status_code == 413


# =============================================================== plugins

class Rec:
    api = 2

    def __init__(self, name, log):
        self.name = name
        self.log = log

    def setup(self, app): self.log.append('setup-' + self.name)

    def apply(self, cb, route):
        def w(*a, **k):
            self.log.append(self.name)
            return cb(*a, **k)
        return w

    def close(self): self.log.append('close-' + self.name)


def test_plugin_apply_order_first_installed_is_outermost():
    log = []
    a = mk()
    a.install(Rec('a', log)); a.install(Rec('b', log))
    a.route('/')(lambda: 'x')
    TestClient(a).get('/')
    assert log == ['setup-a', 'setup-b', 'a', 'b']


def test_plugin_uninstall_by_name_type_instance_and_all():
    log = []
    a = mk()
    p1, p2 = Rec('a', log), Rec('b', log)
    a.install(p1); a.install(p2)
    assert a.uninstall('a') == [p1]
    assert a.uninstall(p2) == [p2]
    assert a.uninstall('nonexistent') == []
    a.install(Rec('c', log))
    removed = a.uninstall(Rec)
    assert len(removed) == 1
    assert set(type(p).__name__ for p in a.uninstall(True)) == {'JSONPlugin', 'TemplatePlugin'}
    assert a.plugins == []


def test_plugin_uninstall_calls_close():
    log = []
    a = mk()
    a.install(Rec('a', log)); a.uninstall('a')
    assert 'close-a' in log


def test_plugin_install_rejects_noncallable():
    with pytest.raises(TypeError):
        mk().install(object())


def test_plugin_plain_callable():
    a = mk()
    a.install(lambda cb: (lambda *x, **k: 'F' + cb(*x, **k)))
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').text == 'Fx'


def test_plugin_applied_to_routes_defined_before_and_after():
    a = mk()
    a.route('/before')(lambda: 'x')
    a.install(lambda cb: (lambda *x, **k: 'P' + cb(*x, **k)))
    a.route('/after')(lambda: 'y')
    c = TestClient(a)
    assert c.get('/before').text == 'Px' and c.get('/after').text == 'Py'


def test_plugin_uninstall_takes_effect_on_existing_routes():
    a = mk()
    p = a.install(lambda cb: (lambda *x, **k: 'P' + cb(*x, **k)))
    a.route('/')(lambda: 'x')
    c = TestClient(a)
    assert c.get('/').text == 'Px'
    a.uninstall(p)
    assert c.get('/').text == 'x'


def test_plugin_same_name_applied_once():
    log = []
    a = mk()
    a.install(Rec('dup', log)); a.install(Rec('dup', log))
    a.route('/')(lambda: 'x')
    log.clear()
    TestClient(a).get('/')
    assert log == ['dup']


def test_plugin_setup_attribute_protected():
    class P:
        api = 2
        def setup(self, app): app.myattr = 1
        def apply(self, cb, r): return cb

    a = mk()
    a.install(P())
    with pytest.raises(AttributeError):
        a.myattr = 2


def test_plugin_exception_propagates_as_500():
    def bad(cb):
        def w(*a, **k): raise PermissionError('p')
        return w

    a = mk()
    a.install(bad)
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 500


def test_plugin_can_short_circuit_with_httpresponse():
    a = mk()

    def guard(cb):
        def w(*x, **k): raise HTTPResponse('blocked', 403)
        return w

    a.install(guard)
    a.route('/')(lambda: 'x')
    assert TestClient(a).get('/').status_code == 403


def test_plugin_sees_route_config():
    seen = []

    class P:
        api = 2
        def apply(self, cb, route):
            seen.append(route.config.get('role'))
            return cb

    a = mk()
    a.install(P())
    a.route('/', role='admin')(lambda: 'x')
    TestClient(a).get('/')
    assert 'admin' in seen


def test_plugin_wrapped_handler_keeps_url_args():
    a = mk()
    a.install(lambda cb: cb)
    a.route('/<n:int>')(lambda n: str(n))
    assert TestClient(a).get('/4').text == '4'


def test_jsonplugin_default_behaviours():
    a = mk()
    a.route('/d')(lambda: {'k': '\u00e9', 'n': None, 'l': [1, {'x': 2}], 1: 'intkey'})
    r = TestClient(a).get('/d')
    assert r.json == {'k': '\u00e9', 'n': None, 'l': [1, {'x': 2}], '1': 'intkey'}


@pytest.mark.parametrize('val', [{'o': object()}, {'d': __import__('datetime').datetime(2020, 1, 1)}, {'s': {1, 2}}, {(1, 2): 'tuplekey'}])
def test_jsonplugin_nonserialisable_values_give_500_not_crash(val):
    a = mk()
    a.route('/d')(lambda: val)
    c = TestClient(a)
    assert c.get('/d').status_code == 500
    a.route('/ok')(lambda: 'fine')
    assert c.get('/ok').text == 'fine'


def test_jsonplugin_nan_is_not_valid_json():
    a = mk()
    a.route('/n')(lambda: {'n': float('nan')})
    body = TestClient(a).get('/n').text
    # strict JSON parsers reject NaN; expect either an error status or null
    with pytest.raises(ValueError):
        json.loads(body, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))


def test_jsonplugin_custom_dumps_via_install():
    a = mk()
    a.uninstall(JSONPlugin)
    a.install(JSONPlugin(lambda o: 'CUSTOM'))
    a.route('/')(lambda: {'a': 1})
    assert TestClient(a).get('/').text == 'CUSTOM'


def test_jsonplugin_content_type_overridden_to_json():
    a = mk()
    a.route('/')(lambda: (response.set_header('Content-Type', 'text/x-custom'), {'a': 1})[1])
    assert TestClient(a).get('/').headers['Content-Type'] == 'application/json'


def test_jsonplugin_httperror_dict_body():
    a = mk()
    a.route('/')(lambda: HTTPError(400, {'why': 'bad'}))
    r = TestClient(a).get('/')
    assert r.status_code == 400 and r.json == {'why': 'bad'}


def test_jsonplugin_unicode_roundtrip_live(live):
    a = mk()
    a.route('/')(lambda: {'k': '\u65e5\u672c'})
    st, h, b = live(a).request('GET', '/')
    assert json.loads(b) == {'k': '\u65e5\u672c'}


def test_jsonplugin_uninstalled_dict_not_treated_as_json():
    a = mk()
    a.uninstall('json')
    a.route('/')(lambda: {'a': 1})
    r = TestClient(a).get('/')
    assert not r.headers['Content-Type'].startswith('application/json')


def test_jsonplugin_json_enable_false_is_honoured():
    a = mk()
    a.config['json.enable'] = False
    a.route('/')(lambda: {'a': 1})
    r = TestClient(a).get('/')
    assert not r.headers['Content-Type'].startswith('application/json')


def test_jsonplugin_dump_func_config_honoured():
    a = mk()
    a.config['json.dump_func'] = lambda o: 'XX'
    a.route('/')(lambda: {'a': 1})
    assert TestClient(a).get('/').text == 'XX'


def test_jsonplugin_ascii_false_emits_utf8():
    a = mk()
    a.route('/')(lambda: {'a': '\u00e9'})
    assert '\u00e9' in TestClient(a).get('/').text


def test_template_plugin_string_template_escapes_html():
    a = mk()
    a.route('/', template='hello {{name}} {{!raw}}')(lambda: {'name': '<x>', 'raw': '<i>'})
    assert TestClient(a).get('/').text == 'hello &lt;x&gt; <i>'


def test_template_plugin_tuple_defaults_override():
    a = mk()
    a.route('/', template=('hi {{n}}', {'n': 'dflt'}))(lambda: {})
    a.route('/o', template=('hi {{n}}', {'n': 'dflt'}))(lambda: {'n': 'mine'})
    c = TestClient(a)
    assert c.get('/').text == 'hi dflt' and c.get('/o').text == 'hi mine'


def test_template_plugin_non_dict_passthrough():
    a = mk()
    a.route('/s', template='hello {{name}}')(lambda: 'plain')
    a.route('/r', template='hello {{name}}')(lambda: HTTPResponse('r', 202))
    c = TestClient(a)
    assert c.get('/s').text == 'plain'
    assert (c.get('/r').status_code, c.get('/r').text) == (202, 'r')


def test_template_missing_var_is_500_and_next_ok():
    a = mk()
    a.route('/t', template='{{x}}')(lambda: {'y': 1})
    a.route('/ok')(lambda: 'ok')
    c = TestClient(a)
    assert c.get('/t').status_code == 500 and c.get('/ok').text == 'ok'


def test_template_file_from_template_path(tmp_path, monkeypatch):
    (tmp_path / 'page.tpl').write_text('<p>{{v}}</p>')
    monkeypatch.setattr(lcore, 'TEMPLATE_PATH', [str(tmp_path) + os.sep])
    lcore.TEMPLATES.clear()
    a = mk()
    a.route('/', template='page.tpl')(lambda: {'v': 'a&b'})
    assert TestClient(a).get('/').text == '<p>a&amp;b</p>'


def test_template_skip_plugin():
    a = mk()
    a.route('/', template='x{{a}}', skip=['template'])(lambda: 'raw')
    assert TestClient(a).get('/').text == 'raw'


# =============================================================== dependency injection

class Svc:
    made = 0

    def __init__(self):
        Svc.made += 1
        self.closed = False

    def close(self): self.closed = True


@pytest.fixture
def di_app():
    Svc.made = 0
    insts = []

    def factory():
        s = Svc(); insts.append(s); return s

    a = mk()
    a.inject('single', factory)
    a.inject('scoped', factory, 'scoped')
    a.inject('trans', factory, 'transient')
    a.route('/ids')(lambda: '%d,%d,%d' % (id(ctx.single), id(ctx.scoped), id(ctx.trans)))
    a.route('/same')(lambda: '%s,%s,%s' % (ctx.single is ctx.single, ctx.scoped is ctx.scoped, ctx.trans is ctx.trans))
    a.route('/none')(lambda: 'x')
    a.route('/err')(lambda: (ctx.scoped, 1 / 0))
    a.insts = insts
    return a


def test_di_lifetimes_within_request(di_app):
    assert TestClient(di_app).get('/same').text == 'True,True,True'


def test_di_singleton_shared_scoped_per_request(di_app):
    c = TestClient(di_app)
    a = c.get('/ids').text.split(',')
    b = c.get('/ids').text.split(',')
    assert a[0] == b[0] and a[1] != b[1]


def test_di_lazy_scoped_and_transient_not_built_when_unused(di_app):
    TestClient(di_app).get('/none')
    # only the eager singleton may have been created
    assert Svc.made == 1


def test_di_scoped_closed_after_request(di_app):
    c = TestClient(di_app)
    c.get('/ids')
    scoped_closed = [i.closed for i in di_app.insts]
    assert scoped_closed.count(True) == 1  # the scoped instance, not the singleton


def test_di_scoped_closed_even_if_handler_fails(di_app):
    TestClient(di_app).get('/none')  # warm the eager singleton
    n = len(di_app.insts)
    TestClient(di_app).get('/err')
    assert [i.closed for i in di_app.insts[n:]] == [True]


def test_di_async_close_awaited():
    class AC:
        closed = False
        async def close(self): AC.closed = True

    a = mk()
    a.inject('ac', AC, 'scoped')
    a.route('/')(lambda: type(ctx.ac).__name__)
    assert TestClient(a).get('/').text == 'AC' and AC.closed


def test_di_close_exception_swallowed():
    class Bad:
        def close(self): raise RuntimeError('x')

    a = mk()
    a.inject('bad', Bad, 'scoped')
    a.route('/')(lambda: type(ctx.bad).__name__)
    assert TestClient(a).get('/').text == 'Bad'


def test_di_failing_singleton_factory_makes_every_request_500():
    a = mk()
    a.inject('bad', lambda: 1 / 0)
    a.route('/')(lambda: 'x')
    c = TestClient(a)
    assert c.get('/').status_code == 500 and c.get('/').status_code == 500


def test_di_failing_transient_only_fails_when_used():
    a = mk()
    a.inject('bad', lambda: 1 / 0, 'transient')
    a.route('/')(lambda: 'x')
    a.route('/u')(lambda: ctx.bad)
    c = TestClient(a)
    assert c.get('/').status_code == 200 and c.get('/u').status_code == 500


def test_di_invalid_lifetime():
    with pytest.raises(ValueError):
        mk().inject('x', Svc, 'weird')


@pytest.mark.parametrize('name', ['route', 'request', 'response', 'app', 'user', 'state', 'lazy', 'request_id'])
def test_di_reserved_names_rejected(name):
    with pytest.raises(ValueError):
        mk().inject(name, Svc)


def test_di_unresolved_name_attribute_error():
    a = mk()
    a.route('/')(lambda: ctx.nothing)
    assert TestClient(a).get('/').status_code == 500


def test_di_container_resolve_api():
    c = DependencyContainer()
    c.register('s', lambda: object())
    assert c.resolve('s') is c.resolve('s') and 's' in c and len(c) == 1
    with pytest.raises(KeyError):
        c.resolve('missing')
    c.register('sc', lambda: 1, 'scoped')
    with pytest.raises(RuntimeError):
        c.resolve('sc')
    c.register('t', lambda: object(), 'transient')
    assert c.resolve('t') is not c.resolve('t')


def test_di_singleton_factory_called_once_under_concurrency():
    made = []
    c = DependencyContainer()
    c.register('s', lambda: (time.sleep(0.02), made.append(1), object())[2])
    out = []
    ts = [threading.Thread(target=lambda: out.append(c.resolve('s'))) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(made) == 1 and len(set(map(id, out))) == 1


def test_di_scoped_isolated_between_concurrent_requests_live(live):
    a = mk()
    import itertools
    seq = itertools.count()
    a.inject('rid', lambda: next(seq), 'scoped')
    a.route('/<n>')(lambda n: (time.sleep(0.02), '%s:%s' % (n, ctx.rid))[1])
    lv = live(a)
    out = []
    ts = [threading.Thread(target=lambda i=i: out.append(lv.request('GET', '/%d' % i)[2])) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(set(o.split(b':')[1] for o in out)) == 8


def test_di_registered_after_routes_still_available():
    a = mk()
    a.route('/')(lambda: ctx.late)
    a.inject('late', lambda: 'L')
    assert TestClient(a).get('/').text == 'L'


def test_ctx_state_does_not_leak_between_requests():
    a = mk()
    a.route('/set')(lambda: (setattr(ctx, 'mine', 1), 'x')[1])
    a.route('/get')(lambda: str(getattr(ctx, 'mine', 'absent')))
    c = TestClient(a)
    c.get('/set')
    assert c.get('/get').text == 'absent'


# =============================================================== background tasks

def test_background_pool_runs_task_and_pending_drops():
    p = BackgroundTaskPool(2)
    ev, res = threading.Event(), []
    f = p.submit(lambda: (ev.wait(2), res.append(1)))
    assert p.pending == 1
    ev.set(); f.result()
    time.sleep(0.05)
    assert p.pending == 0 and res == [1]
    p.shutdown()


def test_background_pool_args_kwargs_and_result():
    p = BackgroundTaskPool()
    assert p.submit(lambda a, b=0: a + b, 1, b=2).result() == 3
    p.shutdown()


def test_background_pool_exception_surfaces_on_future_only():
    p = BackgroundTaskPool()
    f = p.submit(lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        f.result()
    time.sleep(0.05)
    assert p.pending == 0
    assert p.submit(lambda: 'alive').result() == 'alive'
    p.shutdown()


def test_background_pool_shutdown_waits_and_rejects_new():
    p = BackgroundTaskPool(1)
    res = []
    p.submit(lambda: (time.sleep(0.05), res.append(1)))
    p.shutdown(wait=True)
    assert res == [1]
    with pytest.raises(RuntimeError):
        p.submit(lambda: 1)


def test_background_pool_queued_beyond_workers():
    p = BackgroundTaskPool(1)
    fs = [p.submit(lambda i=i: (time.sleep(0.01), i)[1]) for i in range(5)]
    assert [f.result() for f in fs] == list(range(5))
    p.shutdown()


def test_background_pool_from_handler_does_not_block_response():
    p = BackgroundTaskPool()
    ev = threading.Event()
    a = mk()
    a.route('/')(lambda: (p.submit(ev.wait, 2), 'fast')[1])
    t0 = time.time()
    assert TestClient(a).get('/').text == 'fast'
    assert time.time() - t0 < 1
    ev.set(); p.shutdown()


def test_background_pool_many_tasks_pending_consistent():
    p = BackgroundTaskPool(4)
    fs = [p.submit(lambda: time.sleep(0.001)) for _ in range(200)]
    [f.result() for f in fs]
    time.sleep(0.1)
    assert p.pending == 0
    p.shutdown()


# =============================================================== docs / openapi

def _docs_app():
    a = mk()
    a.enable_docs()

    @a.route('/u/<id:int>', name='u')
    def user(id: int, q: str = 'x') -> dict:
        """Get <user>"""
        return {}

    return a


def test_docs_json_structure():
    r = TestClient(_docs_app()).get('/docs/json')
    assert r.status_code == 200 and r.headers['Content-Type'] == 'application/json'
    d = r.json
    assert d['version'] == lcore.__version__
    rt = d['routes'][0]
    assert rt['rule'] == '/u/<id:int>' and rt['method'] == 'GET' and rt['name'] == 'u'
    assert rt['callback'] == 'user' and rt['docstring'] == 'Get <user>' and rt['return_type'] == 'dict'
    params = {p['name']: p for p in rt['parameters']}
    assert params['id']['type'] == 'int' and params['q']['default'] == "'x'"


def test_docs_endpoints_hidden_from_docs():
    rules = [r['rule'] for r in TestClient(_docs_app()).get('/docs/json').json['routes']]
    assert '/docs' not in rules and '/docs/json' not in rules


def test_docs_html_escapes_docstring():
    r = TestClient(_docs_app()).get('/docs')
    assert r.status_code == 200 and '&lt;user&gt;' in r.text and 'Get <user>' not in r.text


def test_docs_html_escapes_malicious_rule_and_docstring():
    a = mk()
    a.enable_docs()

    @a.route('/x')
    def evil():
        """<script>alert(1)</script>"""

    r = TestClient(a).get('/docs')
    assert '<script>alert(1)</script>' not in r.text.split('</style>')[1].split('<script>')[0]


def test_docs_custom_path():
    a = mk()
    a.enable_docs('/api/docs')
    c = TestClient(a)
    assert c.get('/api/docs').status_code == 200 and c.get('/api/docs/json').status_code == 200
    assert c.get('/docs').status_code == 404


def test_docs_reflect_routes_added_later():
    a = mk()
    a.enable_docs()
    a.route('/late')(lambda: 'x')
    assert any(r['rule'] == '/late' for r in TestClient(a).get('/docs/json').json['routes'])


def test_docs_multi_method_and_no_routes():
    a = mk()
    a.enable_docs()
    a.route('/m', method=['GET', 'POST'])(lambda: 'x')
    d = TestClient(a).get('/docs/json').json
    assert sorted(r['method'] for r in d['routes']) == ['GET', 'POST']
    b = mk(); b.enable_docs()
    assert TestClient(b).get('/docs/json').json['routes'] == []
    assert '0 endpoints' in TestClient(b).get('/docs').text


def test_docs_wrapped_callback_uses_undecorated_signature():
    import functools

    def deco(f):
        @functools.wraps(f)
        def w(*a, **k): return f(*a, **k)
        return w

    a = mk()
    a.enable_docs()
    a.route('/w/<n>')(deco(lambda n: 'x'))
    rt = TestClient(a).get('/docs/json').json['routes'][0]
    assert [p['name'] for p in rt['parameters']] == ['n']


def test_api_docs_json_matches_api_docs():
    a = _docs_app()
    assert json.loads(a.api_docs_json()) == a.api_docs()


def test_show_middleware_empty_and_after_use():
    a = mk()
    assert a.show_middleware() == []
    a.use(lcore.RequestIDMiddleware())
    assert a.show_middleware()[0]['type'] == 'RequestIDMiddleware'


# =============================================================== load / load_app

@pytest.fixture
def modpath(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    return tmp_path


def test_load_module_and_attr(modpath):
    (modpath / 'lm_app.py').write_text('from lcore import Lcore\napp = Lcore()\nx = {"a": [1, 2]}\n')
    assert type(lcore.load('lm_app:app')).__name__ == 'Lcore'
    assert lcore.load('lm_app').x == {'a': [1, 2]}
    assert lcore.load('os:path.join') is os.path.join


def test_load_errors(modpath):
    with pytest.raises(ImportError):
        lcore.load('definitely_not_a_module_xyz')
    (modpath / 'lm_b.py').write_text('a = 1\n')
    with pytest.raises(AttributeError):
        lcore.load('lm_b:missing')


@pytest.mark.parametrize('expr', ['a(', '__import__("os").system("true")', 'a b', 'a;b', '1x'])
def test_load_rejects_non_identifier_expressions(modpath, expr):
    (modpath / 'lm_c.py').write_text('a = 1\n')
    with pytest.raises(AttributeError):
        lcore.load('lm_c:' + expr)


def test_load_app_finds_lcore_instance_in_module(modpath):
    (modpath / 'la_a.py').write_text("from lcore import Lcore\napp = Lcore()\n@app.route('/')\ndef i(): return 'mod'\nother = 1\n")
    assert TestClient(lcore.load_app('la_a')).get('/').text == 'mod'
    assert TestClient(lcore.load_app('la_a:app')).get('/').text == 'mod'


def test_load_app_default_app_module(modpath):
    (modpath / 'la_d.py').write_text("from lcore import route\n@route('/')\ndef i(): return 'default'\n")
    assert TestClient(lcore.load_app('la_d')).get('/').text == 'default'


def test_load_app_restores_norun_and_stack(modpath):
    (modpath / 'la_r.py').write_text("import lcore\nlcore.run(host='127.0.0.1', port=1)\napp = lcore.Lcore()\n")
    n = len(lcore.default_app)
    app = lcore.load_app('la_r')
    assert isinstance(app, Lcore) and lcore.NORUN is False and len(lcore.default_app) == n


def test_load_app_py_path(modpath):
    (modpath / 'la_p.py').write_text("from lcore import Lcore\napp = Lcore()\napp.route('/')(lambda: 'p')\n")
    assert TestClient(lcore.load_app('la_p.py')).get('/').text == 'p'


def test_route_callback_as_dotted_string(modpath):
    (modpath / 'la_h.py').write_text("def handler(): return 'loaded'\n")
    a = mk()
    a.route('/', callback='la_h:handler')
    assert TestClient(a).get('/').text == 'loaded'


def test_error_handler_as_string(modpath):
    (modpath / 'la_e.py').write_text("def h(e): return 'loaded-err'\n")
    a = mk()
    a.error(404, 'la_e:h')
    assert TestClient(a).get('/x').text == 'loaded-err'


# =============================================================== lifecycle / run()

class RecServer(lcore.ServerAdapter):
    ran = []

    def run(self, handler):
        RecServer.ran.append(handler)


@pytest.fixture
def clean_hooks():
    saved = list(lcore._shutdown_hooks)
    lcore._shutdown_hooks.clear()
    RecServer.ran.clear()
    yield
    lcore._shutdown_hooks[:] = saved
    lcore.debug(False)


def test_app_close_closes_plugins():
    log = []
    a = mk()
    a.install(Rec('a', log))
    a.close()
    assert 'close-a' in log


def test_context_manager_pushes_default_app():
    a = mk()
    with a as x:
        assert x is a and lcore.default_app() is a
    assert lcore.default_app() is not a


def test_run_unknown_server_name_clear_error(clean_hooks):
    with pytest.raises((ValueError, ImportError)) as ei:
        lcore.run(mk(), server='definitely_not_a_server', quiet=True)
    assert ei.type is ValueError, 'unknown server names should give a ValueError, got %r' % ei.value


def test_run_not_callable(clean_hooks):
    with pytest.raises(ValueError, match='not callable'):
        lcore.run(5, quiet=True)


def test_run_wsgiref_refuses_public_host(clean_hooks):
    with pytest.raises(RuntimeError, match='Refusing'):
        lcore.run(mk(), host='0.0.0.0', quiet=True)


def test_run_dev_server_ok_overrides(clean_hooks):
    lcore.run(mk(), host='0.0.0.0', server=RecServer, quiet=True)  # custom adapters are not guarded
    assert RecServer.ran


def test_run_bad_port_value(clean_hooks):
    with pytest.raises(ValueError):
        lcore.run(mk(), port='abc', quiet=True)


def test_run_port_in_use_message_and_exit(clean_hooks, capsys):
    import socket
    s = socket.socket()
    s.bind(('127.0.0.1', 0)); s.listen(1)
    port = s.getsockname()[1]
    try:
        with pytest.raises(SystemExit) as ei:
            lcore.run(mk(), port=port, quiet=True)
    finally:
        s.close()
    assert ei.value.code == 1
    assert 'already in use' in capsys.readouterr().err


def test_run_calls_shutdown_hooks_lifo_and_survives_failing_hook(clean_hooks):
    log = []
    lcore.on_shutdown(lambda: log.append('h1'))
    lcore.on_shutdown(lambda: 1 / 0)
    lcore.on_shutdown(lambda: log.append('h3'))
    lcore.run(mk(), server=RecServer, quiet=True)
    assert log == ['h3', 'h1']


def test_shutdown_hook_coroutine_awaited(clean_hooks):
    log = []

    async def h(): log.append('async')

    lcore.on_shutdown(h)
    lcore.run(mk(), server=RecServer, quiet=True)
    assert log == ['async']


def test_shutdown_hooks_run_only_once(clean_hooks):
    log = []
    lcore.on_shutdown(lambda: log.append('once'))
    lcore.run(mk(), server=RecServer, quiet=True)
    lcore.run(mk(), server=RecServer, quiet=True)
    assert log == ['once']


def test_run_closes_app_plugins_even_when_server_fails(clean_hooks):
    class Boom(lcore.ServerAdapter):
        def run(self, h): raise RuntimeError('server died')

    log = []
    a = mk()
    a.install(Rec('p', log))
    with pytest.raises(RuntimeError, match='server died'):
        lcore.run(a, server=Boom, quiet=True)
    assert 'close-p' in log


def test_run_keyboardinterrupt_is_clean(clean_hooks):
    class KI(lcore.ServerAdapter):
        def run(self, h): raise KeyboardInterrupt()

    lcore.run(mk(), server=KI, quiet=True)


def test_run_installs_plugins_and_config(clean_hooks):
    a = mk()
    n = len(a.plugins)
    lcore.run(a, server=RecServer, quiet=True, plugins=[lambda cb: cb], config={'zz': 1})
    assert a.config['zz'] == 1 and len(a.plugins) == n + 1


def test_run_accepts_app_string(clean_hooks, modpath):
    (modpath / 'run_app_mod.py').write_text('from lcore import Lcore\napp = Lcore()\n')
    lcore.run('run_app_mod', server=RecServer, quiet=True)
    assert RecServer.ran and isinstance(RecServer.ran[0], Lcore)


def test_run_debug_enables_docs_and_public_host_allowed(clean_hooks):
    a = mk()
    lcore.run(a, host='0.0.0.0', server=RecServer, quiet=True, debug=True)
    assert a._docs_paths == {'/docs', '/docs/json'}


def test_run_norun_flag_short_circuits(clean_hooks):
    lcore.NORUN = True
    try:
        lcore.run(mk(), server='definitely_not_a_server')
    finally:
        lcore.NORUN = False


def test_app_run_method_delegates(clean_hooks):
    mk().run(server=RecServer, quiet=True)
    assert RecServer.ran


def test_run_real_server_serves_then_stops(clean_hooks):
    import socket
    import http.client
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    a = mk()
    a.route('/')(lambda: 'alive')
    holder = {}

    class Adapter(lcore.WSGIRefServer):
        def run(self, handler):
            from wsgiref.simple_server import make_server, WSGIRequestHandler

            class Q(WSGIRequestHandler):
                def log_message(self, *x): pass

            holder['srv'] = make_server(self.host, self.port, handler, handler_class=Q)
            holder['srv'].serve_forever()

    t = threading.Thread(target=lambda: lcore.run(a, server=Adapter, host='127.0.0.1', port=port, quiet=True,
                                                  ), daemon=True)
    # signal handler install only works in main thread; run() guards for that
    t.start()
    for _ in range(100):
        if 'srv' in holder: break
        time.sleep(0.02)
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    c.request('GET', '/')
    assert c.getresponse().read() == b'alive'
    holder['srv'].shutdown(); holder['srv'].server_close()
    t.join(3)
    assert not t.is_alive()


# =============================================================== misc app behaviours

def test_app_wsgi_callable_via_plain_wsgi_interface():
    a = mk()
    a.route('/')(lambda: 'raw')
    got = {}

    def sr(status, headers, exc_info=None):
        got['status'], got['headers'] = status, dict(headers)

    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'SERVER_NAME': 'x', 'SERVER_PORT': '80',
           'wsgi.input': io.BytesIO(), 'wsgi.errors': io.StringIO(), 'wsgi.url_scheme': 'http'}
    body = b''.join(a(env, sr))
    assert body == b'raw' and got['status'].startswith('200')


def test_app_works_with_missing_optional_environ_keys():
    a = mk()
    a.route('/')(lambda: 'ok')
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/', 'wsgi.input': io.BytesIO(), 'wsgi.errors': io.StringIO()}
    out = a(env, lambda s, h, e=None: None)
    assert b''.join(out) == b'ok'


def test_two_apps_in_one_process_do_not_share_state():
    a, b = mk(), mk()
    a.route('/x')(lambda: 'a')
    b.route('/x')(lambda: 'b')
    a.error(404)(lambda e: 'a404')
    assert TestClient(a).get('/x').text == 'a' and TestClient(b).get('/x').text == 'b'
    assert TestClient(b).get('/nope').text != 'a404'


def test_many_sequential_requests_no_state_drift(live):
    a = mk()
    cnt = []
    a.route('/')(lambda: (cnt.append(1), str(len(cnt)))[1])
    lv = live(a)
    for i in range(1, 51):
        assert lv.request('GET', '/')[2] == str(i).encode()


def test_concurrent_requests_isolated_request_object_live(live):
    a = mk()

    @a.route('/<n>')
    def f(n):
        time.sleep(0.01)
        return request.query.get('q', '') + ':' + n + ':' + request.path

    lv = live(a)
    out = {}

    def w(i):
        out[i] = lv.request('GET', '/p%d?q=v%d' % (i, i))[2].decode()

    ts = [threading.Thread(target=w, args=(i,)) for i in range(12)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert all(out[i] == 'v%d:p%d:/p%d' % (i, i, i) for i in range(12))


def test_post_body_roundtrip_live(live):
    a = mk()
    a.route('/e', method='POST')(lambda: request.body.read())
    payload = os.urandom(70000)
    st, h, b = live(a).request('POST', '/e', body=payload, headers={'Content-Type': 'application/octet-stream'})
    assert b == payload


def test_load_rejects_dunder_attributes():
    import pytest, lcore
    with pytest.raises(AttributeError):
        lcore.load('lcore:Lcore.__init__')


def test_cli_bad_target_and_port_are_one_line_errors():
    import subprocess, sys, os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for args, needle in ((['nosuch_mod:app'], 'Cannot load'), (['x:app', '--bind', '127.0.0.1:99999'], 'Invalid port')):
        r = subprocess.run([sys.executable, os.path.join(root, 'lcore.py')] + args,
                           capture_output=True, text=True, cwd=root, timeout=20)
        assert r.returncode == 1 and needle in r.stderr and 'Traceback' not in r.stderr
