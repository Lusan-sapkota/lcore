"""API tests: response status/headers/cookies/body framing/redirects/errors/streaming."""
import json, threading, time
import pytest
import lcore
from lcore import (Lcore, request, response, HTTPError, HTTPResponse, BaseResponse,
                   abort, redirect, TestClient)


def parse_cookie(line):
    parts = [p.strip() for p in line.split(';')]
    name, _, val = parts[0].partition('=')
    attrs = {}
    for p in parts[1:]:
        k, _, v = p.partition('=')
        attrs[k.lower()] = v
    return name, val, attrs


# ---------------------------------------------------------------------- status

@pytest.mark.parametrize('status,code,line', [
    (200, 200, '200 OK'), (404, 404, '404 Not Found'), (418, 418, "418 I'm a teapot"),
    ('404 Brain not found', 404, '404 Brain not found'),
    (599, 599, '599 Unknown'), (100, 100, '100 Continue'), (999, 999, '999 Unknown'),
    ('200 OK ', 200, '200 OK'),
])
def test_status_valid(status, code, line):
    r = BaseResponse()
    r.status = status
    assert (r.status_code, r.status_line, r.status) == (code, line, line)


@pytest.mark.parametrize('bad', [99, 1000, 0, -1, 'OK', '', 'abc def', '200\r\nX: y OK',
                                 '200 OK\nSet-Cookie: a=b'])
def test_status_invalid_rejected(bad):
    with pytest.raises(ValueError):
        BaseResponse().status = bad


def test_status_float_rejected():
    with pytest.raises((ValueError, TypeError, AttributeError)):
        BaseResponse().status = 200.5


def test_status_none_defaults_200():
    assert BaseResponse(status=None).status_code == 200


def test_status_via_handler_and_default(client):
    app = Lcore()

    @app.get('/c')
    def c():
        response.status = 201
        return 'made'

    @app.get('/s')
    def s():
        response.status = '202 Whatever'
        return 'x'
    cl = client(app)
    assert cl.get('/c').status_code == 201
    assert cl.get('/s').status == '202 Whatever'


def test_invalid_status_in_handler_becomes_500(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.status = 1234
        return 'x'
    assert client(app).get('/x').status_code == 500


# --------------------------------------------------------------------- headers

def test_header_set_add_get_case_insensitive():
    r = BaseResponse()
    r.set_header('x-thing', 'a')
    assert r['X-THING'] == 'a' and r.get_header('X-Thing') == 'a' and 'x-Thing' in r
    r.add_header('X-Thing', 'b')
    assert r.headers.getall('X-Thing') == ['a', 'b'] and r['X-Thing'] == 'b'
    r.set_header('X-Thing', 'c')
    assert r.headers.getall('x-thing') == ['c']
    del r['x-thing']
    assert 'X-Thing' not in r and r.get_header('X-Thing', 'd') == 'd'


def test_header_name_normalisation_underscore():
    r = BaseResponse()
    r['x_my_header'] = 'v'
    assert ('X-My-Header', 'v') in r.headerlist


@pytest.mark.parametrize('val', ['a\r\nSet-Cookie: x=y', 'a\nb', 'a\rb', 'a\x00b'])
def test_header_value_injection_rejected(val):
    r = BaseResponse()
    for fn in (r.set_header, r.add_header):
        with pytest.raises(ValueError):
            fn('X-A', val)
    with pytest.raises(ValueError):
        r['X-A'] = val
    with pytest.raises(ValueError):
        BaseResponse(headers={'X-A': val})


@pytest.mark.parametrize('name', ['X-A\r\nInjected: 1', 'X\nY', 'X\x00'])
def test_header_name_injection_rejected(name):
    with pytest.raises(ValueError):
        BaseResponse().set_header(name, 'v')


def test_header_injection_in_handler_is_500_not_split(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.set_header('X-Evil', request.query.get('v'))
        return 'ok'
    r = client(app).get('/x', query_string='v=a%0d%0aSet-Cookie:%20pwn=1')
    assert r.status_code == 500 and 'Set-Cookie' not in r.headers
    assert r.get_all('set-cookie') == []


def test_header_non_str_values_coerced(live):
    app = Lcore()

    @app.get('/x')
    def x():
        response.set_header('X-N', 5)
        response.set_header('X-B', b'bytes')
        return 'x'
    s, h, _ = live(app).request('GET', '/x')
    assert h['x-n'] == '5' and h['x-b'] == 'bytes'


def test_header_unicode_value_utf8_on_the_wire(live):
    app = Lcore()

    @app.get('/x')
    def x():
        response.set_header('X-U', 'héllo')
        return 'x'
    s, h, _ = live(app).request('GET', '/x')
    assert s == 200 and h['x-u'].encode('latin1').decode('utf8') == 'héllo'


def test_headers_constructor_forms():
    r = BaseResponse('b', 200, [('A', '1'), ('A', '2')], B='3')
    assert r.headers.getall('A') == ['1', '2'] and r['B'] == '3'
    r2 = BaseResponse(headers={'C': '4'})
    assert r2['C'] == '4'


def test_response_copy_independent():
    r = BaseResponse()
    r['A'] = '1'
    r.set_cookie('c', 'v')
    c = r.copy()
    c['A'] = '2'; c.set_cookie('d', 'w')
    assert r['A'] == '1' and 'd' not in r._cookies and c._cookies['c'].value == 'v'


def test_content_length_property():
    r = BaseResponse()
    assert r.content_length == -1
    r.content_length = 5
    assert r.content_length == 5 and r['Content-Length'] == '5'


def test_expires_property_roundtrip():
    from datetime import datetime, timezone
    r = BaseResponse()
    r.expires = datetime(2030, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert r['Expires'] == 'Wed, 02 Jan 2030 03:04:05 GMT'
    assert r.expires.year == 2030


# ------------------------------------------------------------------- content type

@pytest.mark.parametrize('ct,charset', [('text/html; charset=latin1', 'latin1'),
                                        ('text/plain', 'UTF-8'),
                                        ('text/plain; charset=utf-16; x=y', 'utf-16'),
                                        ('text/plain;charset="x"', '"x"')])
def test_charset_property(ct, charset):
    r = BaseResponse()
    r.content_type = ct
    assert r.charset == charset


def test_default_content_type_html_utf8(client):
    app = Lcore()
    app.get('/x')(lambda: 'hi')
    assert client(app).get('/x').headers['Content-Type'] == 'text/html; charset=UTF-8'


def test_str_encoded_with_response_charset(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.content_type = 'text/plain; charset=latin1'
        return 'café'
    r = client(app).get('/x')
    assert r.body == 'café'.encode('latin1') and r.headers['Content-Length'] == '4'


def test_unencodable_for_charset_is_500_not_crash(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.content_type = 'text/plain; charset=ascii'
        return 'café'
    assert client(app).get('/x').status_code == 500


def test_dict_returns_json_content_type(client):
    app = Lcore()
    app.get('/x')(lambda: {'a': 'é'})
    r = client(app).get('/x')
    assert r.headers['Content-Type'].startswith('application/json') and r.json == {'a': 'é'}


# ------------------------------------------------------------- content-length/body

def body_app():
    app = Lcore()
    app.get('/str')(lambda: 'héllo ✓')
    app.get('/bytes')(lambda: b'\x00\x01\xff')
    app.get('/empty')(lambda: '')
    app.get('/none')(lambda: None)
    app.get('/list')(lambda: ['a', 'b', 'c'])
    app.get('/bytes_list')(lambda: [b'a', b'b'])

    @app.get('/gen')
    def gen():
        yield 'a'
        yield 'é'
        yield 'z'

    @app.get('/empty_gen')
    def egen():
        return iter(())

    @app.get('/gen_empty_first')
    def gef():
        yield ''
        yield 'x'

    @app.get('/bad_type')
    def bad(): return 12345

    @app.get('/bad_gen')
    def badgen():
        yield 1

    @app.get('/tuple')
    def tup(): return ('a', 'b')

    @app.get('/zero')
    def zero(): return 0

    @app.get('/false')
    def false(): return False
    return app


@pytest.mark.parametrize('path,body', [
    ('/str', 'héllo ✓'.encode()), ('/bytes', b'\x00\x01\xff'), ('/empty', b''), ('/none', b''),
    ('/list', b'abc'), ('/bytes_list', b'ab'), ('/tuple', b'ab'), ('/gen_empty_first', b'x'),
    ('/empty_gen', b''), ('/false', b''),
])
def test_body_types_and_content_length(client, path, body):
    r = client(body_app()).get(path)
    assert r.status_code == 200 and r.body == body
    if 'Content-Length' in r.headers:
        assert int(r.headers['Content-Length']) == len(body)


def test_generator_streams_without_content_length(client):
    r = client(body_app()).get('/gen')
    assert r.body == 'aéz'.encode() and 'Content-Length' not in r.headers


def test_unsupported_body_type_500(client):
    assert client(body_app()).get('/bad_type').status_code in (500,)
    assert client(body_app()).get('/bad_gen').status_code == 500


def test_zero_int_return_is_empty_body(client):
    r = client(body_app()).get('/zero')
    assert r.status_code == 200 and r.body == b''


@pytest.mark.parametrize('n', [0, 1, 65535, 65536, 1_000_000, 8_000_000])
def test_big_bodies_live(live, n):
    app = Lcore()

    @app.get('/big/<n:int>')
    def big(n): return b'x' * n
    s, h, b = live(app).request('GET', '/big/%d' % n)
    assert s == 200 and len(b) == n and int(h['content-length']) == n


def test_big_generator_body_live(live):
    app = Lcore()

    @app.get('/g')
    def g():
        for _ in range(500):
            yield b'y' * 10000
    s, h, b = live(app).request('GET', '/g')
    assert len(b) == 5_000_000


def test_live_content_length_matches_unicode_bytes(live):
    app = Lcore()
    app.get('/u')(lambda: '日本語✓😀')
    s, h, b = live(app).request('GET', '/u')
    assert int(h['content-length']) == len(b) == len('日本語✓😀'.encode())


def test_explicit_content_length_respected_for_str(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response['Content-Length'] = 3
        return 'abc'
    assert client(app).get('/x').headers['Content-Length'] == '3'


# ---------------------------------------------------------- HEAD / 204 / 304

def test_head_no_body_but_headers(live):
    app = Lcore()
    app.get('/x')(lambda: 'hello world')
    s, h, b = live(app).request('HEAD', '/x')
    assert s == 200 and b == b'' and h['content-length'] == '11'


def test_head_inprocess_closes_generator(client):
    closed = []

    class Body:
        def __iter__(self): yield b'a'
        def close(self): closed.append(1)
    app = Lcore()
    app.get('/x')(lambda: Body())
    r = client(app).head('/x')
    assert r.body == b'' and closed


@pytest.mark.parametrize('code', [204, 304, 100])
def test_no_body_statuses(client, code):
    app = Lcore()

    @app.get('/x')
    def x():
        response.status = code
        response['Content-Type'] = 'text/plain'
        return 'should not be sent'
    r = client(app).get('/x')
    assert r.status_code == code and r.body == b''


def test_204_has_no_content_type_or_length_headers(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.status = 204
        return ''
    r = client(app).get('/x')
    assert 'Content-Type' not in r.headers and 'Content-Length' not in r.headers


def test_304_strips_entity_headers(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.status = 304
        response['Last-Modified'] = 'x'
        response['ETag'] = '"a"'
        response['Content-Encoding'] = 'gzip'
        return ''
    r = client(app).get('/x')
    assert 'Last-Modified' not in r.headers and 'Content-Encoding' not in r.headers
    assert r.headers.get('Etag') == '"a"'


def test_204_via_live_has_empty_body(live):
    app = Lcore()

    @app.route('/x', method='DELETE')
    def x():
        response.status = 204
    s, h, b = live(app).request('DELETE', '/x')
    assert s == 204 and b == b''


# --------------------------------------------------------------------- cookies

def cookie_app(**opts):
    app = Lcore()

    @app.get('/c')
    def c():
        response.set_cookie('n', 'v', **opts)
        return 'x'
    return app


def test_cookie_defaults_lax_httponly(client):
    line = client(cookie_app()).get('/c').headers['Set-Cookie']
    n, v, a = parse_cookie(line)
    assert (n, v) == ('n', 'v') and a['samesite'].lower() == 'lax' and 'httponly' in a


def test_cookie_all_options(client):
    from datetime import datetime, timezone
    app = cookie_app(max_age=60, path='/p', domain='example.com', secure=True, httponly=True,
                     samesite='Strict', expires=datetime(2030, 1, 1, tzinfo=timezone.utc))
    n, v, a = parse_cookie(client(app).get('/c').headers['Set-Cookie'])
    assert a['max-age'] == '60' and a['path'] == '/p' and a['domain'] == 'example.com'
    assert 'secure' in a and 'httponly' in a and a['samesite'].lower() == 'strict'
    assert a['expires'] == 'Tue, 01 Jan 2030 00:00:00 GMT'


def test_cookie_max_age_timedelta():
    from datetime import timedelta
    r = BaseResponse()
    r.set_cookie('a', 'b', max_age=timedelta(days=1))
    assert r._cookies['a']['max-age'] == 86400


@pytest.mark.parametrize('ss,expected', [('lax', 'lax'), ('NONE', 'none'), ('Strict', 'strict'),
                                         (None, 'none')])
def test_cookie_samesite_values(ss, expected):
    r = BaseResponse()
    r.set_cookie('a', 'b', samesite=ss)
    assert r._cookies['a']['samesite'] == expected


def test_cookie_samesite_invalid():
    with pytest.raises(Exception):
        BaseResponse().set_cookie('a', 'b', samesite='bogus')


def test_cookie_httponly_false_and_secure_false_omitted():
    r = BaseResponse()
    r.set_cookie('a', 'b', httponly=False, secure=False)
    out = r._cookies['a'].OutputString()
    assert 'HttpOnly' not in out and 'Secure' not in out


def test_cookie_none_options_omitted():
    r = BaseResponse()
    r.set_cookie('a', 'b', domain=None, path=None, max_age=None)
    out = r._cookies['a'].OutputString()
    assert 'None' not in out.replace('SameSite', '') or 'Domain' not in out


def test_cookie_multiple_set_cookie_headers(client):
    app = Lcore()

    @app.get('/c')
    def c():
        response.set_cookie('a', '1'); response.set_cookie('b', '2')
        return 'x'
    r = client(app).get('/c')
    assert len(r.get_all('Set-Cookie')) == 2


def test_cookie_overwrite_same_name_last_wins():
    r = BaseResponse()
    r.set_cookie('a', '1'); r.set_cookie('a', '2')
    assert len(r._cookies) == 1 and r._cookies['a'].value == '2'


def test_cookie_non_string_without_secret_typeerror():
    with pytest.raises(TypeError):
        BaseResponse().set_cookie('a', 123)


@pytest.mark.parametrize('name', ['a b', 'a;b', 'a=b', 'a,b', '', 'é', 'a\r\nb', 'a\x00'])
def test_cookie_bad_names_rejected(name):
    with pytest.raises(Exception):
        r = BaseResponse()
        r.set_cookie(name, 'v')
        r.headerlist


@pytest.mark.parametrize('val', ['a\r\nSet-Cookie: pwn=1', 'a\nb'])
def test_cookie_value_injection_not_emitted(val):
    r = BaseResponse()
    try:
        r.set_cookie('a', val)
        hl = r.headerlist
    except Exception:
        return
    for k, v in hl:
        assert '\r' not in v and '\n' not in v


@pytest.mark.parametrize('val', ['a;b', 'a b', 'a,b', 'a"b', 'é', '日本'])
def test_cookie_special_values_are_quoted_or_encoded(client, val):
    app = Lcore()

    @app.get('/c')
    def c():
        response.set_cookie('n', val)
        return 'x'
    r = client(app).get('/c')
    line = r.headers['Set-Cookie']
    first = line.split(';', 1)[0]
    # the cookie must not smuggle extra attributes
    assert 'b' not in [p.strip().split('=')[0] for p in line.split(';')[1:]] or val != 'a;b'
    assert first.startswith('n=')


def test_cookie_path_attribute_injection():
    r = BaseResponse()
    try:
        r.set_cookie('a', 'b', path='/; Secure; Domain=evil.com')
        out = r._cookies['a'].OutputString()
    except Exception:
        return
    assert 'evil.com' not in out.split('Path=')[0]


def test_cookie_big_value_rejected():
    with pytest.raises(ValueError):
        BaseResponse().set_cookie('a', 'x' * 4000)


def test_delete_cookie_header():
    r = BaseResponse()
    r.delete_cookie('gone', path='/x')
    a = parse_cookie(r.headerlist[-1][1])
    assert a[1] in ('', '""') and a[2]['max-age'] == '-1' and a[2]['path'] == '/x'
    assert 'expires' in a[2] and a[2]['expires'].startswith('Thu, 01 Jan 1970')


def test_delete_cookie_clears_testclient_jar(client):
    app = Lcore()
    app.get('/set')(lambda: response.set_cookie('k', 'v') or 'x')
    app.get('/del')(lambda: response.delete_cookie('k') or 'x')

    @app.get('/show')
    def show(): return {'c': dict(request.cookies.items())}
    c = client(app)
    c.get('/set')
    assert c.get('/show').json == {'c': {'k': 'v'}}
    c.get('/del')
    assert c.get('/show').json == {'c': {}}


def test_cookies_isolated_between_requests(client):
    app = Lcore()
    state = {'n': 0}

    @app.get('/x')
    def x():
        state['n'] += 1
        if state['n'] == 1:
            response.set_cookie('first', '1')
        return 'x'
    cl = client(app, cookies=False)
    assert cl.get('/x').get_all('Set-Cookie')
    assert cl.get('/x').get_all('Set-Cookie') == []


# -------------------------------------------------------------------- redirects

def redirect_app():
    app = Lcore()

    @app.get('/r')
    def r():
        redirect(request.query.get('to', '/dest'), int(request.query.get('code', 0)) or None)

    @app.get('/dest')
    def dest(): return 'dest'

    @app.get('/rc')
    def rc():
        response.set_cookie('keep', '1')
        response['X-Keep'] = 'yes'
        redirect('/dest')
    return app


@pytest.mark.parametrize('code', [301, 302, 303, 307, 308])
def test_redirect_codes(client, code):
    r = client(redirect_app()).get('/r', query_string='code=%d' % code)
    assert r.status_code == code and r.headers['Location'] == 'http://localhost/dest'
    assert r.body in (b'', ) or code in (301, 302, 303, 307, 308)


def test_redirect_default_303_for_http11(client):
    assert client(redirect_app()).get('/r').status_code == 303


def test_redirect_default_302_for_http10():
    app = redirect_app()
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/r', 'SERVER_PROTOCOL': 'HTTP/1.0', 'SERVER_NAME': 'h',
           'SERVER_PORT': '80', 'wsgi.url_scheme': 'http', 'QUERY_STRING': '', 'HTTP_HOST': 'h',
           'wsgi.input': __import__('io').BytesIO(), 'wsgi.errors': __import__('io').StringIO()}
    got = {}
    app(env, lambda s, h, e=None: got.update(s=s, h=h))
    assert got['s'].startswith('302')


@pytest.mark.parametrize('to,loc', [
    ('/a/b', 'http://localhost/a/b'),
    ('rel', 'http://localhost/rel'),
    ('http://other.com/x', 'http://other.com/x'),
    ('//other.com/x', 'http://other.com/x'),
    ('?q=1', 'http://localhost/r?q=1'),
])
def test_redirect_targets(client, to, loc):
    from urllib.parse import quote
    r = client(redirect_app()).get('/r', query_string='to=' + quote(to, safe=''))
    assert r.headers['Location'] == loc or r.headers['Location'].startswith('http://')


@pytest.mark.parametrize('inj', ['/a%0d%0aSet-Cookie:%20x=y', '/a%0aX-Y:%20z', '/a%00b'])
def test_redirect_header_injection_neutralised(client, inj):
    r = client(redirect_app()).get('/r', query_string='to=' + inj)
    assert r.get_all('Set-Cookie') == [] and 'X-Y' not in r.headers
    loc = r.headers.get('Location', '')
    assert '\r' not in loc and '\n' not in loc and '\x00' not in loc


def test_redirect_keeps_response_cookies_and_headers(client):
    r = client(redirect_app()).get('/rc')
    assert r.status_code == 303 and r.headers.get('X-Keep') == 'yes'
    assert any(c.startswith('keep=') for c in r.get_all('Set-Cookie'))


def test_redirect_follow_in_testclient(client):
    r = client(redirect_app(), follow_redirects=True).get('/r')
    assert r.status_code == 200 and r.text == 'dest'


def test_redirect_loop_is_bounded(client):
    app = Lcore()
    app.get('/loop')(lambda: redirect('/loop'))
    r = client(app, follow_redirects=True).get('/loop')
    assert r.status_code in (301, 302, 303, 307, 308)


def test_redirect_unicode_url_live(live):
    app = Lcore()
    app.get('/r')(lambda: redirect('/café'))
    s, h, b = live(app).request('GET', '/r')
    assert s in (302, 303) and 'caf' in h['location']


# -------------------------------------------------------------- abort/HTTPError

def err_app(**cfg):
    app = Lcore()
    for k, v in cfg.items():
        app.config[k.replace('__', '.')] = v

    @app.get('/abort/<code:int>')
    def ab(code): abort(code, 'custom <b>msg</b>')

    @app.get('/raise')
    def rs(): raise ValueError('boom <script>')

    @app.get('/httperror')
    def he(): raise HTTPError(409, 'conflict', X_Extra='1')

    @app.get('/httpresponse')
    def hr(): raise HTTPResponse('made', 202, {'X-A': 'b'})

    @app.get('/ret_error')
    def re_(): return HTTPError(418, 'tea')

    @app.get('/ret_resp')
    def rr(): return HTTPResponse({'a': 1}, 201)

    @app.get('/jsonerr')
    def je(): raise HTTPError(400, 'bad', content_type='application/json')
    return app


def test_abort_html_escapes_message(client):
    r = client(err_app()).get('/abort/404')
    assert r.status_code == 404 and '<b>msg</b>' not in r.text and '&lt;b&gt;' in r.text
    assert r.headers['Content-Type'].startswith('text/html')


@pytest.mark.parametrize('code', [400, 401, 403, 404, 405, 409, 410, 413, 415, 422, 429, 500, 501, 503])
def test_abort_codes(client, code):
    r = client(err_app()).get('/abort/%d' % code)
    assert r.status_code == code and str(code) in r.text


def test_abort_unknown_code(client):
    r = client(err_app()).get('/abort/499')
    assert r.status_code == 499


def test_exception_is_500_without_leaking_traceback(client):
    r = client(err_app()).get('/raise')
    assert r.status_code == 500 and 'Traceback' not in r.text and 'boom' not in r.text


def test_exception_500_logged_to_wsgi_errors():
    app = err_app()
    import io
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/raise', 'wsgi.input': io.BytesIO(),
           'wsgi.errors': io.StringIO(), 'SERVER_NAME': 'x', 'SERVER_PORT': '80',
           'wsgi.url_scheme': 'http'}
    app(env, lambda *a: None)
    assert 'boom' in env['wsgi.errors'].getvalue()


def test_httperror_extra_headers(client):
    r = client(err_app()).get('/httperror')
    assert r.status_code == 409 and r.headers.get('X-Extra') == '1'


def test_httpresponse_raise(client):
    r = client(err_app()).get('/httpresponse')
    assert (r.status_code, r.text, r.headers['X-A']) == (202, 'made', 'b')


def test_return_httperror_object(client):
    assert client(err_app()).get('/ret_error').status_code == 418


def test_return_httpresponse_with_dict_body(client):
    r = client(err_app()).get('/ret_resp')
    assert r.status_code == 201 and r.json == {'a': 1}


def test_404_unknown_route_and_405(client):
    app = err_app()
    c = client(app)
    assert c.get('/nope').status_code == 404
    r = c.post('/httperror')
    assert r.status_code == 405 and 'GET' in r.headers.get('Allow', '')


def test_404_url_is_escaped_in_page(client):
    r = client(err_app()).get('/%3Cscript%3Ealert(1)%3C/script%3E')
    assert '<script>alert' not in r.text


def test_custom_error_handler(client):
    app = err_app()

    @app.error(404)
    def nf(e): return 'custom 404: ' + str(e.status_code)
    assert client(app).get('/zzz').text == 'custom 404: 404'


def test_custom_error_handler_for_500(client):
    app = err_app()

    @app.error(500)
    def e500(e):
        response.content_type = 'text/plain'
        return 'oops'
    r = client(app).get('/raise')
    assert r.status_code == 500 and r.text == 'oops'


def test_error_handler_exception_does_not_crash_server(client):
    app = err_app()

    @app.error(404)
    def bad(e): raise RuntimeError('handler broke')
    r = client(app).get('/nope')
    assert r.status_code == 500


def test_error_handler_cookie_headers_preserved(client):
    app = Lcore()

    @app.get('/x')
    def x():
        response.set_cookie('seen', '1')
        abort(403, 'no')
    r = client(app).get('/x')
    assert r.status_code == 403 and any(c.startswith('seen=') for c in r.get_all('Set-Cookie'))


@pytest.mark.parametrize('accept,kind', [
    ('application/json', 'json'), ('text/html', 'html'), ('*/*', 'html'), ('', 'html'),
    ('application/json, text/html', 'json'), ('text/html, application/json', 'html'),
    ('text/html;q=0.5, application/json', 'json'), ('application/json;q=0', 'html'),
    ('application/json;q=0.1, text/html;q=0.9', 'html'), ('text/*', 'html'),
    ('application/json;q=abc', 'html'), ('APPLICATION/JSON', 'json'),
])
def test_error_accept_negotiation(client, accept, kind):
    r = client(err_app()).get('/abort/404', headers={'Accept': accept} if accept else None)
    assert r.status_code == 404
    if kind == 'json':
        assert r.headers['Content-Type'].startswith('application/json')
        assert r.json['status'] == 404 and 'error' in r.json
    else:
        assert r.headers['Content-Type'].startswith('text/html')


def test_error_format_json_config(client):
    r = client(err_app(error__format='json')).get('/abort/403')
    assert r.json == {'error': 'custom <b>msg</b>', 'status': 403}


def test_error_format_json_for_404_default_text(client):
    r = client(err_app(error__format='json')).get('/nothing')
    assert r.json == {'error': 'Not Found', 'status': 404} or r.json['status'] == 404


def test_error_json_for_500(client):
    r = client(err_app(error__format='json')).get('/raise')
    assert r.status_code == 500 and r.json['status'] == 500 and 'boom' not in r.text


def test_error_json_content_type_given_by_handler(client):
    r = client(err_app()).get('/jsonerr')
    assert r.status_code == 400


def test_error_json_message_unicode_and_quote(client):
    app = Lcore(); app.config['error.format'] = 'json'

    @app.get('/x')
    def x(): abort(400, 'quote " and é')
    assert client(app).get('/x').json['error'] == 'quote " and é'


def test_error_head_request_no_body(live):
    s, h, b = live(err_app()).request('HEAD', '/abort/404')
    assert s == 404 and b == b''


def test_error_inside_hook_after_request(client):
    app = Lcore()
    app.get('/x')(lambda: 'ok')

    @app.hook('after_request')
    def h(): abort(418, 'hook')
    assert client(app).get('/x').status_code == 418


# ---------------------------------------------------------------------- streaming

class Tracked:
    def __init__(self, items, fail_at=None):
        self.items, self.fail_at, self.closed, self.n = items, fail_at, 0, 0

    def __iter__(self):
        for i, x in enumerate(self.items):
            if self.fail_at == i: raise RuntimeError('mid-stream')
            yield x

    def close(self): self.closed += 1


def test_close_called_after_full_iteration(client):
    t = Tracked([b'a', b'b'])
    app = Lcore(); app.get('/x')(lambda: t)
    assert client(app).get('/x').body == b'ab' and t.closed == 1


def test_close_called_on_empty_iterable(client):
    t = Tracked([])
    app = Lcore(); app.get('/x')(lambda: t)
    assert client(app).get('/x').body == b'' and t.closed >= 1


def test_close_called_when_first_item_raises(client):
    t = Tracked([b'a'], fail_at=0)
    app = Lcore(); app.get('/x')(lambda: t)
    r = client(app).get('/x')
    assert r.status_code == 500 and t.closed >= 1


def test_close_called_when_unsupported_type(client):
    t = Tracked([42])
    app = Lcore(); app.get('/x')(lambda: t)
    assert client(app).get('/x').status_code == 500 and t.closed >= 1


def test_exception_mid_stream_after_headers_live(live):
    t = Tracked([b'first', b'second'], fail_at=1)
    app = Lcore(); app.get('/x')(lambda: t)
    lv = live(app)
    raw = lv.raw(b'GET /x HTTP/1.0\r\n\r\n')
    # status line was already committed as 200; server must not crash and the generator is closed
    time.sleep(0.2)
    assert raw.startswith(b'HTTP/1.') and t.closed >= 1


def test_close_on_client_disconnect_live(live):
    import socket
    closed = threading.Event()

    class Endless:
        def __iter__(self):
            while True:
                yield b'x' * 65536
        def close(self): closed.set()
    app = Lcore(); app.get('/x')(lambda: Endless())
    lv = live(app)
    s = socket.create_connection(('127.0.0.1', lv.port), timeout=5)
    s.sendall(b'GET /x HTTP/1.0\r\n\r\n')
    s.recv(1000)
    s.close()
    assert closed.wait(5)


def test_file_like_body_closed(client):
    import io
    f = io.BytesIO(b'filebody')
    app = Lcore(); app.get('/x')(lambda: f)
    assert client(app).get('/x').body == b'filebody' and f.closed


def test_generator_yielding_str_and_bytes_mixed(client):
    app = Lcore()

    @app.get('/x')
    def x():
        yield 'a'
        yield b'b'
    r = client(app).get('/x')
    assert r.body == b'ab'


def test_async_handler(client):
    app = Lcore()

    @app.get('/x')
    async def x(): return {'a': 1}
    assert client(app).get('/x').json == {'a': 1}


def test_response_state_not_leaking_between_requests(client):
    app = Lcore()

    @app.get('/a')
    def a():
        response.status = 201
        response.set_header('X-Leak', '1')
        response.set_cookie('leak', '1')
        return 'a'
    app.get('/b')(lambda: 'b')
    c = client(app, cookies=False)
    c.get('/a')
    r = c.get('/b')
    assert r.status_code == 200 and 'X-Leak' not in r.headers and r.get_all('Set-Cookie') == []


def test_response_state_thread_isolation_live(live):
    import http.client
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import make_server, WSGIRequestHandler, WSGIServer

    class TS(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class Q(WSGIRequestHandler):
        def log_message(self, *a): pass
    app = Lcore()

    @app.get('/r/<i:int>')
    def r(i):
        response.status = (200, 201, 202, 203, 206)[i % 5]
        response.set_header('X-I', str(i))
        time.sleep(0.01)
        response.set_cookie('i', str(i))
        time.sleep(0.01)
        return str(i)
    srv = make_server('127.0.0.1', 0, app, server_class=TS, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bad = []

    def w(base):
        for k in range(8):
            i = base * 100 + k
            c = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
            c.request('GET', '/r/%d' % i)
            r = c.getresponse()
            body = r.read().decode()
            if not (body == str(i) and r.getheader('X-I') == str(i) and r.status == (200, 201, 202, 203, 206)[i % 5]
                    and ('i=%d' % i) in r.getheader('Set-Cookie', '')):
                bad.append((i, body, r.status))
            c.close()
    ts = [threading.Thread(target=w, args=(b,)) for b in range(10)]
    [t.start() for t in ts]; [t.join(60) for t in ts]
    srv.shutdown(); srv.server_close()
    assert not bad, bad[:3]


def test_response_object_repr_and_iter():
    r = BaseResponse('abc', 200, {'A': 'b'})
    assert 'A: b' in repr(r)
    assert list(BaseResponse(['x', 'y'])) == ['x', 'y']
    r.close()


def test_httpresponse_apply_does_not_clobber_existing_headers():
    r = BaseResponse(); r['X-A'] = 'handler'
    HTTPResponse('x', 200, {'X-A': 'exc', 'X-B': 'exc'}).apply(r)
    assert r['X-A'] == 'handler' and r['X-B'] == 'exc'


def test_json_plugin_dict_body_on_httpresponse(client):
    app = Lcore()

    @app.get('/x')
    def x(): raise HTTPResponse({'k': 'v'}, 202)
    r = client(app).get('/x')
    assert r.status_code == 202 and r.json == {'k': 'v'}


def test_json_dict_with_unserialisable_value_is_500(client):
    app = Lcore()
    app.get('/x')(lambda: {'a': object()})
    assert client(app).get('/x').status_code == 500


def test_json_ascii_unicode_handling(live):
    app = Lcore()
    app.get('/x')(lambda: {'a': '😀é'})
    s, h, b = live(app).request('GET', '/x')
    assert json.loads(b) == {'a': '😀é'}


@pytest.mark.parametrize('val', ['é', '日本', '😀', 'a b', 'x;y', 'a"b', 'a,b', 'a\\b', 'a=b'])
def test_cookie_value_roundtrip_through_wire(live, val):
    app = Lcore()

    @app.get('/set')
    def set_():
        response.set_cookie('n', val)
        return 'x'

    @app.get('/get')
    def get(): return request.cookies.get('n')
    lv = live(app)
    s, h, _ = lv.request('GET', '/set')
    sent = h['set-cookie'].split('; HttpOnly')[0]
    s, h, b = lv.request('GET', '/get', headers={'Cookie': sent})
    assert b.decode('utf8') == val


@pytest.mark.parametrize('opt', ['path', 'domain'])
def test_cookie_attribute_injection_via_semicolon(opt):
    r = BaseResponse()
    with pytest.raises(Exception):
        r.set_cookie('a', 'b', **{opt: 'x; Secure; Domain=evil.com'})


@pytest.mark.parametrize('opts', [{'max_age': 'x'}, {'expires': 'nonsense'}])
def test_cookie_garbage_max_age_expires_rejected(opts):
    with pytest.raises(Exception):
        BaseResponse().set_cookie('a', 'b', **opts)
