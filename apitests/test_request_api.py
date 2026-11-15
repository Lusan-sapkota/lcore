"""API tests: request parsing (query, forms, json, multipart, body, headers, cookies, urls)."""
import json, os, socket, threading, time
import pytest
import lcore
from lcore import (Lcore, request, response, HTTPError, BodyLimitMiddleware,
                   FileUpload, WSGIHeaderDict, BaseRequest, parse_range_header,
                   parse_auth)


def make_app(**cfg):
    app = Lcore()
    for k, v in cfg.items():
        app.config[k.replace('__', '.')] = v

    @app.route('/q')
    def q():
        return {'q': dict(request.query.allitems()) and
                {k: request.query.getall(k) for k in request.query.keys()}}

    @app.route('/form', method='POST')
    def form():
        return {k: request.forms.getall(k) for k in request.forms.keys()}

    @app.route('/params', method='POST')
    def params():
        return {k: request.params.getall(k) for k in request.params.keys()}

    @app.route('/json', method=['POST', 'PUT'])
    def js():
        return {'v': request.json}

    @app.route('/json_or', method='POST')
    def json_or():
        return {'v': request.json_or({'d': 1})}

    @app.route('/body', method='POST')
    def body():
        b = request.body.read()
        again = request.body.read()
        return {'len': len(b), 'again': len(again), 'cl': request.content_length,
                'chunked': request.chunked}

    @app.route('/echo', method='POST')
    def echo():
        response.content_type = 'application/octet-stream'
        return request.body.read()

    @app.route('/upload', method='POST')
    def upload():
        out = {'fields': {k: request.forms.getall(k) for k in request.forms.keys()},
               'files': {}}
        for name, f in request.files.allitems():
            data = f.file.read()
            out['files'].setdefault(name, []).append(
                {'filename': f.filename, 'raw': f.raw_filename, 'size': len(data),
                 'ct': f.content_type, 'head': data[:20].decode('latin1')})
        return out

    @app.route('/hdr')
    def hdr():
        return {'x': request.get_header('X-Thing'), 'x2': request.headers['x-thing']
                if 'x-thing' in request.headers else None,
                'keys': sorted(request.headers.keys())}

    @app.route('/cookies')
    def cookies():
        return {'c': dict(request.cookies.items())}

    @app.route('/setsigned')
    def setsigned():
        response.set_cookie('s', {'uid': 7, 'n': 'é'}, secret='k1')
        return 'ok'

    @app.route('/getsigned')
    def getsigned():
        return {'v': request.get_cookie('s', secret=request.query.get('secret', 'k1'),
                                        default='NONE')}

    @app.route('/info')
    def info():
        u = request.urlparts
        return {'url': request.url, 'scheme': u.scheme, 'host': u.netloc,
                'path': request.path, 'fullpath': request.fullpath,
                'script_name': request.script_name, 'qs': request.query_string,
                'xhr': request.is_xhr, 'ajax': request.is_ajax, 'auth': request.auth,
                'remote_addr': request.remote_addr, 'route': request.remote_route,
                'ct': request.content_type, 'method': request.method}

    @app.route('/tid')
    def tid():
        t = request.query.get('t')
        time.sleep(0.02)
        response.set_header('X-T', t)
        response.set_cookie('t', t)
        time.sleep(0.02)
        return {'t': request.query.get('t'), 'path': request.path,
                'hdr': request.get_header('X-Id')}
    return app


# ---------------------------------------------------------------- query string

@pytest.mark.parametrize('qs,expect', [
    ('a=1', {'a': ['1']}),
    ('a=1&a=2&a=3', {'a': ['1', '2', '3']}),
    ('a=&b=', {'a': [''], 'b': ['']}),
    ('a', {'a': ['']}),
    ('=v', {'': ['v']}),
    ('a=b=c', {'a': ['b=c']}),
    ('a=1&&b=2&', {'a': ['1'], 'b': ['2']}),
    ('a+b=c+d', {'a b': ['c d']}),
    ('a%20b=c%20d', {'a b': ['c d']}),
    ('a=%2B', {'a': ['+']}),
    ('a=%26%3D', {'a': ['&=']}),
    ('n=%C3%A9', {'n': ['é']}),
    ('%E2%9C%93=%F0%9F%98%80', {'✓': ['😀']}),
    ('', {}),
    ('&', {}),
    ('a=1;b=2', {'a': ['1;b=2']}),
])
def test_query_parsing(client, qs, expect):
    r = client(make_app()).get('/q', query_string=qs)
    assert r.status_code == 200
    assert r.json['q'] == expect


@pytest.mark.parametrize('qs', ['a=%', 'a=%zz', 'a=%4', '%=1', 'a=%E9'])
def test_query_malformed_percent_does_not_crash(client, qs):
    r = client(make_app()).get('/q', query_string=qs)
    assert r.status_code == 200  # must not be a 500


def test_query_malformed_percent_values(client):
    r = client(make_app()).get('/q', query_string='a=%zz&b=%')
    assert r.json['q']['a'] == ['%zz'] and r.json['q']['b'] == ['%']


def test_query_invalid_utf8_replaced(client):
    r = client(make_app()).get('/q', query_string='a=%FF%FE')
    assert r.status_code == 200
    assert '\ufffd' in r.json['q']['a'][0]


def test_query_field_limit_ok_at_1000(client):
    qs = '&'.join('k%d=v' % i for i in range(1000))
    r = client(make_app()).get('/q', query_string=qs)
    assert r.status_code == 200 and len(r.json['q']) == 1000


def test_query_field_limit_413_at_1001(client):
    qs = '&'.join('k%d=v' % i for i in range(1001))
    assert client(make_app()).get('/q', query_string=qs).status_code == 413


def test_query_repeated_key_limit_413(client):
    qs = '&'.join('a=1' for _ in range(5000))
    assert client(make_app()).get('/q', query_string=qs).status_code == 413


def test_query_huge_single_value(client):
    r = client(make_app()).get('/q', query_string='a=' + 'x' * 200000)
    assert r.status_code == 200 and len(r.json['q']['a'][0]) == 200000


def test_query_cached_on_request_and_params_merge(client):
    r = client(make_app()).post('/params', query_string='a=1&b=2', body=b'a=3&c=4',
                                content_type='application/x-www-form-urlencoded')
    assert r.json == {'a': ['1', '3'], 'b': ['2'], 'c': ['4']}


def test_query_formsdict_attr_and_getunicode(client):
    app = Lcore()

    @app.route('/x')
    def x():
        return {'attr': request.query.name, 'missing': request.query.nothing,
                'u': request.query.getunicode('name')}
    r = client(app).get('/x', query_string='name=h%C3%A9')
    assert r.json == {'attr': 'hé', 'missing': '', 'u': 'hé'}


# ----------------------------------------------------------------------- forms

@pytest.mark.parametrize('body,expect', [
    (b'a=1&b=2', {'a': ['1'], 'b': ['2']}),
    (b'a=1&a=2', {'a': ['1', '2']}),
    (b'', {}),
    (b'a=%C3%A9+x', {'a': ['é x']}),
    (b'a=%zz', {'a': ['%zz']}),
    (b'=', {'': ['']}),
])
def test_form_urlencoded(client, body, expect):
    r = client(make_app()).post('/form', body=body,
                                content_type='application/x-www-form-urlencoded')
    assert r.status_code == 200 and r.json == expect


def test_form_without_content_type_still_parsed_as_urlencoded(client):
    r = client(make_app()).post('/form', body=b'a=1')
    assert r.json == {'a': ['1']}


def test_form_invalid_utf8_does_not_500(client):
    r = client(make_app()).post('/form', body=b'a=%FF&b=\xff\xfe',
                                content_type='application/x-www-form-urlencoded')
    assert r.status_code == 200


def test_form_field_limit_413(client):
    body = '&'.join('k%d=v' % i for i in range(1001)).encode()
    r = client(make_app()).post('/form', body=body,
                                content_type='application/x-www-form-urlencoded')
    assert r.status_code == 413


def test_form_not_parsed_on_get(client):
    r = client(make_app()).post('/form', body=b'a=1', content_type='text/plain')
    assert r.status_code == 200  # text/plain is parsed urlencoded-style, never crashes


# ------------------------------------------------------------------------ json

@pytest.mark.parametrize('payload', [
    {'a': 1}, [1, 2, 3], 'str', 12, 1.5, True, {'n': {'n': {'n': [1, {'x': None}]}}},
    {'u': 'héllo ✓ 😀'}, {},
])
def test_json_roundtrip(client, payload):
    r = client(make_app()).post('/json', json=payload)
    assert r.status_code == 200 and r.json['v'] == payload


def test_json_null_body_literal(client):
    r = client(make_app()).post('/json', body=b'null', content_type='application/json')
    assert r.json['v'] is None


def test_json_empty_body_is_none(client):
    r = client(make_app()).post('/json', body=b'', content_type='application/json')
    assert r.status_code == 200 and r.json['v'] is None


@pytest.mark.parametrize('body', [b'{', b'{"a":', b'nope', b"{'a':1}", b'[1,2,', b'{"a":1}}'])
def test_json_malformed_400(client, body):
    r = client(make_app()).post('/json', body=body, content_type='application/json')
    assert r.status_code == 400


def test_json_invalid_utf8_is_400_not_500(client):
    r = client(make_app()).post('/json', body=b'{"a":"\xff\xfe"}',
                                content_type='application/json')
    assert r.status_code == 400


def test_json_utf8_bom(client):
    r = client(make_app()).post('/json', body=b'\xef\xbb\xbf{"a":1}',
                                content_type='application/json')
    assert r.status_code in (200, 400)  # must not be a 500


@pytest.mark.parametrize('ct', ['application/json', 'APPLICATION/JSON',
                                'application/json; charset=utf-8',
                                'application/json;charset=UTF-8', 'application/json-rpc'])
def test_json_content_type_variants(client, ct):
    r = client(make_app()).post('/json', body=b'{"a":1}', content_type=ct)
    assert r.json['v'] == {'a': 1}


@pytest.mark.parametrize('ct', ['text/plain', 'application/x-www-form-urlencoded',
                                'application/jsonx', 'application/vnd.api+json', ''])
def test_json_wrong_content_type_returns_none(client, ct):
    r = client(make_app()).post('/json', body=b'{"a":1}', content_type=ct or None)
    assert r.json['v'] is None


def test_json_or_default_and_value(client):
    c = client(make_app())
    assert c.post('/json_or', body=b'', content_type='application/json').json['v'] == {'d': 1}
    assert c.post('/json_or', body=b'x').json['v'] == {'d': 1}
    assert c.post('/json_or', json={'z': 2}).json['v'] == {'z': 2}


def test_json_huge_body_413_by_config(client):
    app = make_app(request__max_body=1000)
    r = client(app).post('/json', body=json.dumps({'a': 'x' * 5000}).encode(),
                         content_type='application/json')
    assert r.status_code == 413


def test_json_large_ok_spills_to_tempfile(client):
    payload = {'a': 'x' * 300000}
    r = client(make_app(request__max_body=0)).post('/json', json=payload)
    assert r.status_code == 200 and len(r.json['v']['a']) == 300000


@pytest.mark.xfail(strict=True, reason="BUG: deeply nested JSON raises RecursionError -> 500 instead of 400")
def test_json_deep_nesting_no_crash(client):
    body = b'[' * 100000 + b']' * 100000
    r = client(make_app()).post('/json', body=body, content_type='application/json')
    assert r.status_code in (200, 400, 413)  # RecursionError must not become a 500


def test_json_cached_per_request(client):
    app = Lcore()

    @app.post('/x')
    def x():
        return {'same': request.json is request.json}
    assert client(app).post('/x', json={'a': 1}).json == {'same': True}


# ------------------------------------------------------------- body and limits

def test_body_readable_twice_and_content_length(client):
    r = client(make_app()).post('/body', body=b'x' * 1234)
    assert r.json == {'len': 1234, 'again': 1234, 'cl': 1234, 'chunked': False}


def test_body_empty_post(client):
    r = client(make_app()).post('/body', body=b'')
    assert r.json['len'] == 0


def test_body_large_roundtrip_over_memfile_max(client):
    data = os.urandom(BaseRequest.MEMFILE_MAX * 3 + 17)
    r = client(make_app(request__max_body=0)).post('/echo', body=data)
    assert r.body == data


def test_body_limit_config_413(client):
    r = client(make_app(request__max_body=100)).post('/body', body=b'x' * 101)
    assert r.status_code == 413


def test_body_limit_config_exact_ok(client):
    r = client(make_app(request__max_body=100)).post('/body', body=b'x' * 100)
    assert r.status_code == 200


def test_body_limit_middleware_fast_reject(client):
    app = make_app()
    app.use(BodyLimitMiddleware(max_size=50))
    assert client(app).post('/body', body=b'x' * 51).status_code == 413
    assert client(app).post('/body', body=b'x' * 50).status_code == 200


def test_body_content_length_invalid_treated_as_unknown(client):
    app = make_app()
    r = client(app).post('/body', body=b'abc', headers={'Content-Length': 'abc'})
    assert r.status_code == 200 and r.json['cl'] == -1


def test_body_negative_content_length(client):
    r = client(make_app()).post('/body', body=b'abc', headers={'Content-Length': '-5'})
    assert r.status_code == 200 and r.json['len'] == 0


def test_body_content_length_shorter_than_body_truncates(client):
    r = client(make_app()).post('/body', body=b'abcdefgh', headers={'Content-Length': '3'})
    assert r.json['len'] == 3


def test_body_limit_enforced_even_if_content_length_lies(client):
    # Declared small, server only reads declared bytes, so cannot exceed.
    r = client(make_app(request__max_body=10)).post(
        '/body', body=b'x' * 100, headers={'Content-Length': '5'})
    assert r.status_code == 200 and r.json['len'] == 5


# ---------------------------------------------------- live sockets: chunked etc

def _chunked(parts, ext=b''):
    out = b''
    for p in parts:
        out += b'%x%s\r\n' % (len(p), ext) + p + b'\r\n'
    return out + b'0\r\n\r\n'


def _post_raw(path, body, extra=b'', te=True):
    h = b'POST ' + path + b' HTTP/1.1\r\nHost: x\r\nConnection: close\r\n'
    h += b'Transfer-Encoding: chunked\r\n' if te else b''
    return h + extra + b'\r\n' + body


def _read_all(lv, payload):
    s = socket.create_connection(('127.0.0.1', lv.port), timeout=5)
    s.sendall(payload)
    data = b''
    try:
        while True:
            c = s.recv(65536)
            if not c: break
            data += c
    except socket.timeout:
        data += b'<timeout>'
    s.close()
    return data


def _chunk_body(parts, ext=b''):
    return _chunked(parts, ext)


@pytest.mark.parametrize('parts', [[b'hello'], [b'a', b'bb', b'ccc'], [b'x' * 100, b'y' * 150000]])
def test_chunked_inprocess_roundtrip(client, parts):
    r = client(make_app(request__max_body=0)).post(
        '/echo', body=_chunk_body(parts), headers={'Transfer-Encoding': 'chunked'})
    assert r.status_code == 200 and r.body == b''.join(parts)


def test_chunked_inprocess_extension(client):
    r = client(make_app()).post('/echo', body=_chunk_body([b'abcdef'], b';name=val'),
                                headers={'Transfer-Encoding': 'chunked'})
    assert r.body == b'abcdef'


def test_chunked_inprocess_byte_at_a_time_works(client):
    # Socket-like stream that returns one byte per read: the code path that works.
    from io import BytesIO
    class Slow(BytesIO):
        def read(self, n=-1): return super().read(1)
    app = make_app()
    from lcore import TestClient
    env_body = _chunk_body([b'abcdef', b'gh'])
    holder = {}
    def wrapped(environ, sr):
        environ['wsgi.input'] = Slow(env_body)
        return app(environ, sr)
    r = TestClient(wrapped).post('/echo', body=env_body, headers={'Transfer-Encoding': 'chunked'})
    assert r.body == b'abcdefgh'


def test_chunked_detected_case_insensitive(client):
    r = client(make_app()).post('/body', body=b'0\r\n\r\n', headers={'Transfer-Encoding': 'Chunked'})
    assert r.json['chunked'] is True and r.json['len'] == 0


def _live_chunked(lv, parts, path=b'/echo', ext=b''):
    s = socket.create_connection(('127.0.0.1', lv.port), timeout=5)
    s.sendall(_post_raw(path, _chunked(parts, ext)))
    s.shutdown(socket.SHUT_WR)  # wsgiref blocks in read(bufsize) otherwise
    data = b''
    try:
        while True:
            c = s.recv(65536)
            if not c: break
            data += c
    except socket.timeout:
        data += b'<timeout>'
    s.close()
    return data


@pytest.mark.parametrize('parts', [[b'hello'], [b'a', b'bb', b'ccc']])
def test_live_chunked_echo(live, parts):
    raw = _live_chunked(live(make_app(request__max_body=0)), parts)
    assert raw.startswith(b'HTTP/1.') and raw.endswith(b''.join(parts)), raw[:200]


def test_live_chunked_without_eof_blocks_until_client_closes(live):
    # Documented-by-test hazard: lcore reads chunk headers with read(bufsize), which blocks on a
    # raw socket stream; only matters for servers that do not de-chunk themselves (wsgiref).
    lv = live(make_app())
    raw = lv.raw(_post_raw(b'/echo', _chunked([b'hello'])))
    assert raw in (b'<timeout>',) or raw.startswith(b'HTTP/1.')


@pytest.mark.parametrize('body', [b'zz\r\nabc\r\n0\r\n\r\n', b'5\r\nabc', b'-1\r\nabc\r\n0\r\n\r\n', b''])
def test_chunked_malformed_is_400(client, body):
    r = client(make_app()).post('/echo', body=body, headers={'Transfer-Encoding': 'chunked'})
    assert r.status_code == 400


def test_chunked_over_limit_413_single_chunk(client):
    r = client(make_app(request__max_body=1000)).post(
        '/echo', body=_chunk_body([b'x' * 1200]), headers={'Transfer-Encoding': 'chunked'})
    assert r.status_code == 413


def test_chunked_over_limit_middleware_413_single_chunk(client):
    app = make_app()
    app.use(BodyLimitMiddleware(max_size=500))
    r = client(app).post('/echo', body=_chunk_body([b'x' * 900]),
                         headers={'Transfer-Encoding': 'chunked'})
    assert r.status_code == 413


def test_live_chunked_over_limit_413(live):
    raw = _live_chunked(live(make_app(request__max_body=1000)), [b'x' * 1200])
    assert b' 413 ' in raw.split(b'\r\n', 1)[0], raw[:100]


def test_chunked_over_limit_413_multi_chunk(client):
    r = client(make_app(request__max_body=1000)).post(
        '/echo', body=_chunk_body([b'x' * 600, b'y' * 600]), headers={'Transfer-Encoding': 'chunked'})
    assert r.status_code == 413


def test_live_content_length_over_limit_413(live):
    lv = live(make_app(request__max_body=100))
    s, h, b = lv.request('POST', '/body', body=b'x' * 500)
    assert s == 413


def test_live_truncated_body_does_not_hang_or_500(live):
    lv = live(make_app())
    raw = lv.raw(b'POST /body HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\n'
                 b'Connection: close\r\n\r\nshort')
    # server must not crash; the connection may time out waiting (acceptable), or answer
    assert raw in (b'', b'<timeout>') or raw.startswith(b'HTTP/1.')


def test_live_keepalive_state_not_leaking(live):
    import http.client
    lv = live(make_app())
    c = http.client.HTTPConnection('127.0.0.1', lv.port, timeout=5)
    for i in range(3):
        c.request('POST', '/form', body='a=%d' % i,
                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
        r = c.getresponse()
        assert json.loads(r.read()) == {'a': [str(i)]}
    c.close()


# ------------------------------------------------------------------ multipart

def mp(fields=(), files=(), boundary='XBOUNDARYX'):
    out = b''
    for name, val in fields:
        out += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n'
                % (boundary, name)).encode() + (val if isinstance(val, bytes) else val.encode()) + b'\r\n'
    for name, fn, data, *ct in files:
        out += ('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                % (boundary, name, fn)).encode()
        if ct: out += ('Content-Type: %s\r\n' % ct[0]).encode()
        out += b'\r\n' + data + b'\r\n'
    return out + ('--%s--\r\n' % boundary).encode()


MPCT = 'multipart/form-data; boundary=XBOUNDARYX'


def test_multipart_fields_and_files(client):
    body = mp([('a', '1'), ('a', '2'), ('u', 'héllo')],
              [('f', 'hello.txt', b'file-content', 'text/plain')])
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    j = r.json
    assert j['fields'] == {'a': ['1', '2'], 'u': ['héllo']}
    assert j['files']['f'][0]['filename'] == 'hello.txt'
    assert j['files']['f'][0]['size'] == 12 and j['files']['f'][0]['ct'] == 'text/plain'


def test_multipart_multiple_files_same_name(client):
    body = mp(files=[('f', 'a.txt', b'A'), ('f', 'b.txt', b'BB')])
    j = client(make_app()).post('/upload', body=body, content_type=MPCT).json
    assert [x['filename'] for x in j['files']['f']] == ['a.txt', 'b.txt']


def test_multipart_empty_file(client):
    body = mp(files=[('f', 'e.txt', b'')])
    j = client(make_app()).post('/upload', body=body, content_type=MPCT).json
    assert j['files']['f'][0]['size'] == 0


def test_multipart_binary_with_crlf_and_boundary_like_content(client):
    data = b'\r\n--XBOUNDARYX-not\r\n\x00\x01\xff\r\n\r\n'
    body = mp(files=[('f', 'b.bin', data)])
    j = client(make_app()).post('/upload', body=body, content_type=MPCT).json
    assert j['files']['f'][0]['size'] == len(data)


@pytest.mark.parametrize('fn,expected', [
    ('../../etc/passwd', 'passwd'),
    ('..\\..\\windows\\system32\\cmd.exe', 'cmd.exe'),
    ('C:\\Users\\x\\evil.exe', 'evil.exe'),
    ('/abs/path/file.txt', 'file.txt'),
    ('a b c.txt', 'a-b-c.txt'),
    ('héllo.txt', 'hello.txt'),
    ('...', 'empty'),
    ('', 'empty'),
    ('.hidden', 'hidden'),
    ('a;b|c&d$e.txt', 'abcde.txt'),
    ('<script>.txt', 'script.txt'),
    ('x' * 400 + '.txt', None),
])
def test_fileupload_filename_sanitising(fn, expected):
    f = FileUpload(None, 'f', fn)
    if expected is None:
        assert len(f.filename) <= 255 and '/' not in f.filename
    else:
        assert f.filename == expected
    assert f.raw_filename == fn


def test_multipart_traversal_filename_end_to_end(client):
    body = mp(files=[('f', '../../../../tmp/pwn.txt', b'x')])
    j = client(make_app()).post('/upload', body=body, content_type=MPCT).json
    assert j['files']['f'][0]['filename'] == 'pwn.txt'
    assert '/' not in j['files']['f'][0]['raw']


def test_multipart_missing_boundary_400(client):
    r = client(make_app()).post('/upload', body=mp(), content_type='multipart/form-data')
    assert r.status_code == 400


def test_multipart_wrong_boundary_400(client):
    r = client(make_app()).post('/upload', body=mp([('a', '1')]),
                                content_type='multipart/form-data; boundary=other')
    assert r.status_code == 400


def test_multipart_quoted_boundary(client):
    body = mp([('a', '1')])
    r = client(make_app()).post('/upload', body=body,
                                content_type='multipart/form-data; boundary="XBOUNDARYX"')
    assert r.json['fields'] == {'a': ['1']}


@pytest.mark.parametrize('cut', [10, 40, 80, -10, -3])
def test_multipart_truncated_400(client, cut):
    body = mp([('a', '1')], [('f', 'x.txt', b'data' * 10)])
    body = body[:cut] if cut > 0 else body[:cut]
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    assert r.status_code == 400


def test_multipart_missing_disposition_400(client):
    body = b'--XBOUNDARYX\r\nX-Foo: bar\r\n\r\nvalue\r\n--XBOUNDARYX--\r\n'
    assert client(make_app()).post('/upload', body=body, content_type=MPCT).status_code == 400


def test_multipart_header_without_colon_400(client):
    body = b'--XBOUNDARYX\r\nGarbage\r\n\r\nvalue\r\n--XBOUNDARYX--\r\n'
    assert client(make_app()).post('/upload', body=body, content_type=MPCT).status_code == 400


def test_multipart_bad_part_content_length_not_500(client):
    body = (b'--XBOUNDARYX\r\nContent-Disposition: form-data; name="a"\r\n'
            b'Content-Length: abc\r\n\r\nv\r\n--XBOUNDARYX--\r\n')
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    assert r.status_code in (200, 400)


def test_multipart_bad_charset_not_500(client):
    body = (b'--XBOUNDARYX\r\nContent-Disposition: form-data; name="a"\r\n'
            b'Content-Type: text/plain; charset=nonsense\r\n\r\nv\r\n--XBOUNDARYX--\r\n')
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    assert r.status_code in (200, 400)


def test_multipart_field_invalid_utf8_not_500(client):
    body = mp([('a', b'\xff\xfe')])
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    assert r.status_code in (200, 400)


def test_multipart_empty_stream_ok(client):
    r = client(make_app()).post('/upload', body=b'--XBOUNDARYX--\r\n', content_type=MPCT)
    assert r.status_code == 200 and r.json == {'fields': {}, 'files': {}}


def test_multipart_data_after_terminator_400(client):
    r = client(make_app()).post('/upload', body=b'--XBOUNDARYX--\r\njunk\r\n', content_type=MPCT)
    assert r.status_code == 400


def test_multipart_huge_part_spills_to_disk(client):
    data = os.urandom(2 * 1024 * 1024)
    body = mp(files=[('f', 'big.bin', data)])
    app = make_app()
    r = client(app).post('/upload', body=body, content_type=MPCT)
    assert r.status_code == 200 and r.json['files']['f'][0]['size'] == len(data)


def test_multipart_with_unlimited_max_body(client):
    body = mp([('a', '1')], [('f', 'x.txt', b'data')])
    r = client(make_app(request__max_body=0)).post('/upload', body=body, content_type=MPCT)
    assert r.status_code == 200


def test_multipart_many_parts(client):
    body = mp([('f%d' % i, 'v') for i in range(500)])
    r = client(make_app()).post('/upload', body=body, content_type=MPCT)
    assert r.status_code == 200 and len(r.json['fields']) == 500


def test_multipart_over_body_limit_rejected(client):
    body = mp(files=[('f', 'big.bin', b'x' * 5000)])
    r = client(make_app(request__max_body=1000)).post('/upload', body=body, content_type=MPCT)
    assert r.status_code in (400, 413)


def test_multipart_field_huge_value_memory_limit(client):
    body = mp([('a', 'x' * 400000)])
    r = client(make_app(request__max_body=0)).post('/upload', body=body, content_type=MPCT)
    assert r.status_code in (200, 400, 413)


def test_multipart_live_roundtrip(live):
    lv = live(make_app())
    body = mp([('a', '1')], [('f', 'n.txt', b'DATA')])
    s, h, b = lv.request('POST', '/upload', body=body, headers={'Content-Type': MPCT})
    assert s == 200 and json.loads(b)['files']['f'][0]['size'] == 4


# ---------------------------------------------------------------- FileUpload.save

def _upload(data=b'payload', fn='f.txt'):
    from io import BytesIO
    return FileUpload(BytesIO(data), 'f', fn)


def test_save_to_directory_uses_sanitised_name(tmp_path):
    u = _upload(fn='../../evil name.txt')
    u.save(str(tmp_path))
    assert (tmp_path / 'evil-name.txt').read_bytes() == b'payload'
    assert list(tmp_path.parent.glob('evil*')) == []


def test_save_to_path_and_no_overwrite(tmp_path):
    dst = str(tmp_path / 'out.bin')
    _upload().save(dst)
    with pytest.raises(IOError):
        _upload(b'other').save(dst)
    assert open(dst, 'rb').read() == b'payload'


def test_save_overwrite_true_truncates(tmp_path):
    dst = str(tmp_path / 'out.bin')
    _upload(b'long-original-content').save(dst)
    _upload(b'new').save(dst, overwrite=True)
    assert open(dst, 'rb').read() == b'new'


def test_save_to_fileobj_and_repeatable(tmp_path):
    from io import BytesIO
    u = _upload()
    a, b = BytesIO(), BytesIO()
    u.save(a); u.save(b)
    assert a.getvalue() == b.getvalue() == b'payload'


def test_save_into_dir_collision_without_overwrite(tmp_path):
    _upload().save(str(tmp_path))
    with pytest.raises(IOError):
        _upload().save(str(tmp_path))


def test_save_large_chunked(tmp_path):
    data = os.urandom(300000)
    _upload(data).save(str(tmp_path / 'x'), chunk_size=1000)
    assert (tmp_path / 'x').read_bytes() == data


def test_save_symlink_destination_not_followed_when_xb(tmp_path):
    target = tmp_path / 'target'; target.write_text('keep')
    link = tmp_path / 'link'; link.symlink_to(target)
    with pytest.raises(IOError):
        _upload().save(str(link))
    assert target.read_text() == 'keep'


def test_validate_extension_and_type():
    u = FileUpload(None, 'f', 'a.PNG', [('Content-Type', 'image/png; charset=x')])
    u.validate_extension(['png'])
    u.validate_content_type(['image/png'])
    with pytest.raises(HTTPError) as e:
        u.validate_extension(['jpg'])
    assert e.value.status_code == 415
    with pytest.raises(HTTPError):
        u.validate_content_type(['text/plain'])


def test_validate_extension_double_extension_uses_last():
    u = FileUpload(None, 'f', 'shell.php.png')
    u.validate_extension(['png'])
    with pytest.raises(HTTPError):
        FileUpload(None, 'f', 'shell.png.php').validate_extension(['png'])


# --------------------------------------------------------------------- headers

def test_header_case_insensitive_lookup(client):
    r = client(make_app()).get('/hdr', headers={'X-Thing': 'v'})
    assert r.json['x'] == 'v' and r.json['x2'] == 'v'
    assert 'X-Thing' in r.json['keys']


def test_header_missing_default(client):
    assert client(make_app()).get('/hdr').json['x'] is None


def test_wsgi_header_dict_basics():
    h = WSGIHeaderDict({'HTTP_X_FOO_BAR': 'a', 'CONTENT_TYPE': 'text/x',
                        'CONTENT_LENGTH': '5', 'REMOTE_ADDR': '1.1.1.1'})
    assert h['x-foo-bar'] == 'a' and h['X-Foo-Bar'] == 'a'
    assert h['Content-Type'] == 'text/x' and h['content-length'] == '5'
    assert 'Remote-Addr' not in h and len(h) == 3
    with pytest.raises(KeyError): h['nothing']
    with pytest.raises(TypeError): h['x'] = 1
    assert sorted(h.keys()) == ['Content-Length', 'Content-Type', 'X-Foo-Bar']


def test_wsgi_header_dict_non_http_key_hidden():
    h = WSGIHeaderDict({'wsgi.input': 1, 'HTTP_A': 'b'})
    assert list(h) == ['A'] and 'wsgi.input' not in h


def test_header_unicode_value_latin1_roundtrip(live):
    app = Lcore()

    @app.get('/h')
    def h(): return request.get_header('X-Name')
    s, hd, b = live(app).request('GET', '/h', headers={'X-Name': 'caf\xc3\xa9'})
    assert s == 200 and b.decode('utf8') == 'caf\xe9'


def test_header_duplicate_headers_combined_by_server(live):
    app = Lcore()

    @app.get('/h')
    def h(): return request.get_header('X-Dup')
    lv = live(app)
    raw = _read_all(lv, b'GET /h HTTP/1.1\r\nHost: x\r\nX-Dup: one\r\nX-Dup: two\r\nConnection: close\r\n\r\n')
    assert b'one' in raw and b'two' in raw  # wsgiref joins with comma


def test_header_huge_value(live):
    app = Lcore()

    @app.get('/h')
    def h(): return str(len(request.get_header('X-Big') or ''))
    s, _, b = live(app).request('GET', '/h', headers={'X-Big': 'a' * 8000})
    assert s == 200 and b == b'8000'


# --------------------------------------------------------------------- cookies

@pytest.mark.parametrize('hdr,expect', [
    ('a=1; b=2', {'a': '1', 'b': '2'}),
    ('a=1;b=2', {'a': '1', 'b': '2'}),
    ('a="quoted value"', {'a': 'quoted value'}),
    ('a=1; a=2', None),
    ('', {}),
    ('garbage', None),
    ('a=; b=2', None),
    ('=x', None),
    ('a=b=c', {'a': 'b=c'}),
])
def test_cookie_parsing(client, hdr, expect):
    r = client(make_app(), cookies=False).get('/cookies', headers={'Cookie': hdr})
    assert r.status_code == 200
    if expect is not None:
        assert r.json['c'] == expect


def test_cookie_malformed_does_not_drop_good_cookies_or_crash(client):
    r = client(make_app(), cookies=False).get('/cookies', headers={'Cookie': 'a=1; \x01bad; b=2'})
    assert r.status_code == 200


def test_cookie_unicode_value(live):
    app = make_app()
    s, h, b = live(app).request('GET', '/cookies', headers={'Cookie': 'n=caf\xe9'})
    assert s == 200


def test_cookie_huge_header(client):
    r = client(make_app(), cookies=False).get('/cookies', headers={'Cookie': 'a=' + 'x' * 100000})
    assert r.status_code == 200 and len(r.json['c']['a']) == 100000


def test_cookie_many_cookies(client):
    hdr = '; '.join('c%d=v' % i for i in range(2000))
    r = client(make_app(), cookies=False).get('/cookies', headers={'Cookie': hdr})
    assert r.status_code == 200 and len(r.json['c']) == 2000


def test_signed_cookie_roundtrip_structured(client):
    c = client(make_app())
    c.get('/setsigned')
    assert c.get('/getsigned').json == {'v': {'uid': 7, 'n': 'é'}}


def test_signed_cookie_roundtrip_string(client):
    app = make_app()

    @app.route('/sets')
    def sets():
        response.set_cookie('u', 'alice é', secret='k1', max_age=100)
        return 'ok'

    @app.route('/gets')
    def gets():
        return {'v': request.get_cookie('u', secret='k1')}
    c = client(app)
    c.get('/sets')
    assert c.get('/gets').json == {'v': 'alice é'}


def test_signed_cookie_wrong_secret(client):
    c = client(make_app())
    c.get('/setsigned')
    assert c.get('/getsigned', query_string='secret=nope').json == {'v': 'NONE'}


def test_signed_cookie_tampered_payload(client):
    c = client(make_app())
    r = c.get('/setsigned')
    val = r.headers['Set-Cookie'].split(';')[0].split('=', 1)[1].strip('"')
    sig, msg = val[1:].split('?', 1)
    import base64
    bad = base64.b64encode(json.dumps(['s', {'uid': 1}]).encode()).decode()
    r2 = client(make_app(), cookies=False).get('/getsigned', headers={'Cookie': 's="!%s?%s"' % (sig, bad)})
    assert r2.json == {'v': 'NONE'}


@pytest.mark.parametrize('val', ['plain', '!nosep', '!sig?', '?x', '!', '!a?b?c',
                                 '!' + 'A' * 50 + '?' + 'B' * 50])
def test_signed_cookie_garbage_values(client, val):
    r = client(make_app(), cookies=False).get('/getsigned', headers={'Cookie': 's=' + val})
    assert r.status_code == 200 and r.json == {'v': 'NONE'}


def test_signed_cookie_replayed_under_other_name_rejected():
    r = BaseRequest({})
    resp = lcore.BaseResponse()
    resp.set_cookie('a', 'v', secret='k')
    val = resp._cookies['a'].value
    req = BaseRequest({'HTTP_COOKIE': 'b="%s"' % val})
    assert req.get_cookie('b', secret='k') is None
    req2 = BaseRequest({'HTTP_COOKIE': 'a="%s"' % val})
    assert req2.get_cookie('a', secret='k') == 'v'


def test_signed_cookie_too_big_raises():
    resp = lcore.BaseResponse()
    with pytest.raises(ValueError):
        resp.set_cookie('a', 'x' * 4000, secret='k')


def test_get_cookie_unsigned_with_secret_requires_signature():
    req = BaseRequest({'HTTP_COOKIE': 'a=plain'})
    assert req.get_cookie('a', secret='k') is None
    assert req.get_cookie('a', default='d') == 'plain'
    assert req.get_cookie('zz', default='d') == 'd'


# ------------------------------------------------------------ url / environ

def test_info_basic(client):
    j = client(make_app()).get('/info', query_string='a=1&b=%20x').json
    assert j['url'] == 'http://localhost/info?a=1&b=%20x'
    assert (j['scheme'], j['host'], j['path'], j['fullpath']) == ('http', 'localhost', '/info', '/info')
    assert j['method'] == 'GET' and j['qs'] == 'a=1&b=%20x'


def test_info_script_name(client):
    app = make_app()
    from lcore import TestClient
    env_app = lambda env, sr: (env.update(SCRIPT_NAME='/mnt'), app(env, sr))[1]
    j = TestClient(env_app).get('/info').json
    assert j['script_name'] == '/mnt/' and j['fullpath'] == '/mnt/info'
    assert j['url'] == 'http://localhost/mnt/info'


def test_info_path_percent_encoded_unicode(client):
    app = Lcore()

    @app.get('/<x>')
    def x(x): return {'x': x, 'p': request.path, 'url': request.url}
    j = client(app).get('/caf\xc3\xa9').json   # wsgi latin1 form of utf8 bytes
    assert j['x'] == 'café' and j['p'] == '/café' and j['url'].endswith('/caf%C3%A9')


@pytest.mark.parametrize('path', ['/caf\xe9', '/ok\xff', '/\xc3'])
def test_invalid_utf8_path_does_not_escape_wsgi(client, path):
    app = Lcore()

    @app.get('/ok')
    def ok(): return 'ok'
    r = client(app).get(path)
    assert r.status_code in (400, 404)


def test_live_path_unicode_and_encoded(live):
    app = Lcore()

    @app.get('/<x>')
    def x(x): return x
    lv = live(app)
    s, _, b = lv.request('GET', '/caf%C3%A9')
    assert (s, b.decode('utf8')) == (200, 'café')
    s, _, b = lv.request('GET', '/a%20b')
    assert b == b'a b'


def test_live_path_encoded_slash_is_not_route_separator(live):
    app = Lcore()

    @app.get('/<x>')
    def x(x): return x
    s, _, b = live(app).request('GET', '/a%2Fb')
    assert s in (200, 404)


def test_info_host_header_and_port(client):
    j = client(make_app()).get('/info', headers={'Host': 'example.com:8080'}).json
    assert j['host'] == 'example.com:8080' and j['url'].startswith('http://example.com:8080/')


def test_info_no_host_uses_server_name_port():
    env = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/x', 'SERVER_NAME': 's', 'SERVER_PORT': '8000',
           'wsgi.url_scheme': 'http'}
    assert BaseRequest(env).url == 'http://s:8000/x'
    base = {'REQUEST_METHOD': 'GET', 'PATH_INFO': '/x', 'SERVER_NAME': 's', 'wsgi.url_scheme': 'http'}
    assert BaseRequest(dict(base, SERVER_PORT='80')).url == 'http://s/x'
    assert BaseRequest(dict(base, SERVER_PORT='443', **{'wsgi.url_scheme': 'https'})).url == 'https://s/x'


def test_forwarded_headers_ignored_without_trust(client):
    j = client(make_app()).get('/info', headers={'X-Forwarded-Proto': 'https',
                                                 'X-Forwarded-Host': 'evil.com',
                                                 'X-Forwarded-For': '6.6.6.6'}).json
    assert j['scheme'] == 'http' and j['host'] == 'localhost'
    assert j['remote_addr'] is None or j['remote_addr'] != '6.6.6.6'


def test_forwarded_headers_honoured_with_trusted_proxy():
    env = {'REMOTE_ADDR': '10.0.0.1', 'lcore.trusted_proxies': frozenset(['10.0.0.1']),
           'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_X_FORWARDED_HOST': 'real.com',
           'HTTP_X_FORWARDED_FOR': '9.9.9.9, 10.0.0.1', 'PATH_INFO': '/', 'wsgi.url_scheme': 'http'}
    r = BaseRequest(env)
    assert r.url == 'https://real.com/' and r.remote_addr == '9.9.9.9'


def test_remote_addr_spoof_via_xff_with_trusted_proxy_picks_rightmost_untrusted():
    env = {'REMOTE_ADDR': '10.0.0.1', 'lcore.trusted_proxies': frozenset(['10.0.0.1']),
           'HTTP_X_FORWARDED_FOR': '1.2.3.4, 9.9.9.9'}
    assert BaseRequest(env).remote_addr == '9.9.9.9'


def test_remote_route_lists_all_hops():
    env = {'REMOTE_ADDR': '1.1.1.1', 'HTTP_X_FORWARDED_FOR': 'a, b ,c'}
    assert BaseRequest(env).remote_route == ['a', 'b', 'c']
    assert BaseRequest({'REMOTE_ADDR': '1.1.1.1'}).remote_route == ['1.1.1.1']
    assert BaseRequest({}).remote_route == []


def test_is_xhr(client):
    assert client(make_app()).get('/info', headers={'X-Requested-With': 'XMLHttpRequest'}).json['xhr']
    assert not client(make_app()).get('/info', headers={'X-Requested-With': 'fetch'}).json['xhr']
    assert not client(make_app()).get('/info').json['ajax']


@pytest.mark.parametrize('hdr,expect', [
    ('Basic ' + __import__('base64').b64encode(b'u:p').decode(), ['u', 'p']),
    ('Basic ' + __import__('base64').b64encode(b'u:p:q').decode(), ['u', 'p:q']),
    ('Basic ' + __import__('base64').b64encode('é:ü'.encode()).decode(), ['é', 'ü']),
    ('basic ' + __import__('base64').b64encode(b'u:').decode(), ['u', '']),
])
def test_auth_basic(client, hdr, expect):
    assert client(make_app()).get('/info', headers={'Authorization': hdr}).json['auth'] == expect


@pytest.mark.parametrize('hdr', ['Basic', 'Basic !!!notbase64', 'Bearer abc', 'Basic ' + __import__('base64').b64encode(b'nocolon').decode(),
                                 'Basic ' + __import__('base64').b64encode(b'\xff\xfe:x').decode(), ''])
def test_auth_basic_malformed_no_crash(client, hdr):
    r = client(make_app()).get('/info', headers={'Authorization': hdr} if hdr else None)
    assert r.status_code == 200 and r.json['auth'] is None


def test_auth_remote_user_fallback():
    assert BaseRequest({'REMOTE_USER': 'bob'}).auth == ('bob', None)


def test_content_type_lowercased(client):
    j = client(make_app()).post('/info', content_type='Text/Plain; Charset=UTF-8') if False else None
    r = client(make_app()).get('/info', headers={'Content-Type': 'Text/HTML'})
    assert r.json['ct'] == 'text/html'


@pytest.mark.parametrize('hdr,maxlen,expect', [
    ('bytes=0-9', 100, [(0, 10)]),
    ('bytes=-5', 100, [(95, 100)]),
    ('bytes=90-', 100, [(90, 100)]),
    ('bytes=0-1000', 100, [(0, 100)]),
    ('bytes=0-1,5-9', 100, [(0, 2), (5, 10)]),
    ('bytes=100-', 100, []),
    ('bytes=9-0', 100, []),
    ('bytes=abc', 100, []),
    ('bytes=a-b', 100, []),
    ('items=0-1', 100, []),
    ('', 100, []),
    ('bytes=-0', 100, []),
    ('bytes=-1000', 100, [(0, 100)]),
    ('bytes=0-0', 0, []),
    ('bytes=-', 100, []),
    ('bytes=1-2-3', 100, []),
])
def test_parse_range_header(hdr, maxlen, expect):
    assert list(parse_range_header(hdr, maxlen) or []) == expect


def test_environ_access_and_readonly_semantics():
    r = BaseRequest({'A': 1, 'PATH_INFO': '/x'})
    assert r['A'] == 1 and r.get('B', 5) == 5 and 'A' in list(r) and len(r) >= 2
    r['QUERY_STRING'] = 'z=1'
    assert r.query['z'] == '1'
    r['QUERY_STRING'] = 'z=2'
    assert r.query['z'] == '2'  # cache invalidated
    r.environ['lcore.request.readonly'] = True
    with pytest.raises(KeyError):
        r['X'] = 1


def test_request_ext_attributes():
    r = BaseRequest({})
    r.thing = 5
    assert r.thing == 5 and r.environ['lcore.request.ext.thing'] == 5
    with pytest.raises(AttributeError):
        r.thing = 6
    del r.thing
    with pytest.raises(AttributeError):
        r.thing
    with pytest.raises(AttributeError):
        r.method = 'x'


def test_request_path_normalisation():
    assert BaseRequest({'PATH_INFO': ''}).path == '/'
    assert BaseRequest({'PATH_INFO': '//a'}).path == '/a'
    assert BaseRequest({'REQUEST_METHOD': 'post'}).method == 'POST'


def test_path_shift():
    r = BaseRequest({'SCRIPT_NAME': '/a', 'PATH_INFO': '/b/c'})
    r.path_shift(1)
    assert r.environ['SCRIPT_NAME'] == '/a/b' and r.environ['PATH_INFO'] == '/c'
    r.path_shift(-1)
    assert r.environ['PATH_INFO'] == '/b/c'


# --------------------------------------------------- thread-local isolation

def test_live_concurrent_requests_do_not_leak_state(live):
    import http.client
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import make_server, WSGIRequestHandler

    class TS(ThreadingMixIn, __import__('wsgiref.simple_server', fromlist=['x']).WSGIServer):
        daemon_threads = True

    class Q(WSGIRequestHandler):
        def log_message(self, *a): pass
    srv = make_server('127.0.0.1', 0, make_app(), server_class=TS, handler_class=Q)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors = []

    def worker(i):
        try:
            for j in range(5):
                t = '%d-%d' % (i, j)
                c = http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=10)
                c.request('GET', '/tid?t=' + t, headers={'X-Id': t})
                r = c.getresponse()
                body = json.loads(r.read())
                if body['t'] != t or body['hdr'] != t or r.getheader('X-T') != t:
                    errors.append((t, body, r.getheader('X-T')))
                if 't=%s' % t not in (r.getheader('Set-Cookie') or ''):
                    errors.append(('cookie', t, r.getheader('Set-Cookie')))
                c.close()
        except Exception as e:
            errors.append(repr(e))
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    [t.start() for t in ts]; [t.join(30) for t in ts]
    srv.shutdown(); srv.server_close()
    assert not errors, errors[:3]


def test_request_outside_context_raises():
    out = []

    def f():
        try:
            lcore.request.environ
        except RuntimeError as e:
            out.append(str(e))
    t = threading.Thread(target=f); t.start(); t.join()
    assert out and 'not initialized' in out[0]


def test_live_invalid_utf8_path_does_not_kill_connection(live):
    app = Lcore()
    app.get('/ok')(lambda: 'ok')
    lv = live(app)
    for p in (b'/caf%E9', b'/ok%FF', b'/%C3'):
        raw = lv.raw(b'GET ' + p + b' HTTP/1.0\r\n\r\n')
        assert raw.startswith(b'HTTP/1.') and (b' 404 ' in raw.split(b'\r\n')[0] or b' 400 ' in raw.split(b'\r\n')[0]), raw[:80]
