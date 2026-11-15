"""API tests: static_file and SimpleTemplate / view()."""
import email.utils, os, time, threading
import pytest
import lcore
from lcore import (Lcore, request, response, static_file, SimpleTemplate, template, view,
                   TemplateError, BaseTemplate, HTTPError, StplSyntaxError)

IMS_FMT = lambda t: email.utils.formatdate(t, usegmt=True)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / 'root'
    r.mkdir()
    (r / 'hello.txt').write_text('0123456789abcdefghij')   # 20 bytes
    (r / 'empty.txt').write_bytes(b'')
    (r / 'data.json').write_text('{"a":1}')
    (r / 'page.html').write_text('<b>x</b>')
    (r / 'app.js').write_text('var a=1;')
    (r / 'noext').write_bytes(b'raw')
    (r / 'weird.unknownext').write_bytes(b'zz')
    (r / 'arch.tar.gz').write_bytes(b'gz')
    (r / 'arch.tar.bz2').write_bytes(b'bz')
    (r / 'fén ü.txt').write_text('unicode name')
    (r / 'sub').mkdir()
    (r / 'sub' / 'inner.txt').write_text('inner')
    (tmp_path / 'secret.txt').write_text('TOPSECRET')
    (tmp_path / 'root-evil').mkdir()
    (tmp_path / 'root-evil' / 'x.txt').write_text('EVIL')
    return r


def sapp(root, **kw):
    app = Lcore()

    @app.route('/f/<path:path>', method=['GET', 'HEAD'])
    def f(path):
        opts = {}
        for k in ('download', 'mimetype', 'etag', 'charset'):
            v = request.query.get(k)
            if v is not None:
                opts[k] = {'true': True, 'false': False, 'none': None}.get(v, v)
        opts.update(kw)
        return static_file(path, root=str(root), **opts)

    @app.route('/raw')
    def raw():
        return static_file(request.query.get('p'), root=str(root))
    return app


# ----------------------------------------------------------------- basic serving

def test_serves_file_with_headers(client, root):
    r = client(sapp(root)).get('/f/hello.txt')
    h = r.headers
    assert r.status_code == 200 and r.text == '0123456789abcdefghij'
    assert h['Content-Length'] == '20' and h['Content-Type'] == 'text/plain; charset=UTF-8'
    assert h['Accept-Ranges'] == 'bytes' and h['Etag'].startswith('"') and 'Last-Modified' in h
    assert h['Last-Modified'].endswith('GMT') and 'Date' in h


@pytest.mark.parametrize('name,ctype', [
    ('data.json', 'application/json'), ('page.html', 'text/html; charset=UTF-8'),
    ('app.js', None), ('weird.unknownext', None), ('noext', None),
    ('arch.tar.gz', 'application/gzip'), ('arch.tar.bz2', 'application/x-bzip2'),
])
def test_mimetypes(client, root, name, ctype):
    r = client(sapp(root)).get('/f/' + name)
    assert r.status_code == 200
    got = r.headers.get('Content-Type')
    if ctype is None:
        assert got is None or got.startswith(('text/javascript', 'application/javascript',
                                             'application/octet-stream', 'text/'))
    else:
        assert got == ctype


def test_mimetype_override_and_disable(client, root):
    c = client(sapp(root))
    assert c.get('/f/hello.txt', query_string='mimetype=application/x-foo').headers['Content-Type'] == 'application/x-foo'
    assert c.get('/f/hello.txt', query_string='mimetype=text/csv').headers['Content-Type'] == 'text/csv; charset=UTF-8'
    r = c.get('/f/hello.txt', query_string='mimetype=false')
    assert r.status_code == 200


def test_charset_option(client, root):
    r = client(sapp(root)).get('/f/hello.txt', query_string='charset=latin1')
    assert r.headers['Content-Type'] == 'text/plain; charset=latin1'


def test_empty_file(client, root):
    r = client(sapp(root)).get('/f/empty.txt')
    assert r.status_code == 200 and r.body == b'' and r.headers['Content-Length'] == '0'


def test_empty_file_range_is_416(client, root):
    r = client(sapp(root)).get('/f/empty.txt', headers={'Range': 'bytes=0-0'})
    assert r.status_code == 416


def test_unicode_filename(client, root):
    r = client(sapp(root)).get('/f/f\xc3\xa9n \xc3\xbc.txt')
    assert r.status_code == 200 and r.text == 'unicode name'


def test_subdir_file(client, root):
    assert client(sapp(root)).get('/f/sub/inner.txt').text == 'inner'


def test_missing_file_404(client, root):
    assert client(sapp(root)).get('/f/nope.txt').status_code == 404


def test_directory_is_404_not_listing(client, root):
    r = client(sapp(root)).get('/raw', query_string='p=sub')
    assert r.status_code == 404
    assert client(sapp(root)).get('/raw', query_string='p=').status_code in (403, 404)
    assert client(sapp(root)).get('/raw', query_string='p=/').status_code in (403, 404)


def test_head_has_headers_no_body(client, root):
    r = client(sapp(root)).head('/f/hello.txt')
    assert r.status_code == 200 and r.body == b'' and r.headers['Content-Length'] == '20'


def test_head_live(live, root):
    s, h, b = live(sapp(root)).request('HEAD', '/f/hello.txt')
    assert s == 200 and b == b'' and h['content-length'] == '20'


def test_live_full_get_matches(live, root):
    s, h, b = live(sapp(root)).request('GET', '/f/hello.txt')
    assert s == 200 and b == b'0123456789abcdefghij' and h['content-length'] == '20'


def test_large_file_live(live, root):
    data = os.urandom(5 * 1024 * 1024 + 3)
    (root / 'big.bin').write_bytes(data)
    s, h, b = live(sapp(root)).request('GET', '/f/big.bin')
    assert s == 200 and b == data


def test_file_handle_closed_after_response(client, root):
    import gc
    before = len(os.listdir('/proc/self/fd'))
    c = client(sapp(root))
    for _ in range(30):
        c.get('/f/hello.txt')
        c.get('/f/hello.txt', headers={'Range': 'bytes=0-3'})
        c.get('/f/hello.txt', headers={'If-None-Match': c.get('/f/hello.txt').headers['Etag']})
        c.head('/f/hello.txt')
    gc.collect()
    assert len(os.listdir('/proc/self/fd')) <= before + 2


# ------------------------------------------------------------------- downloads

def test_download_true_uses_filename(client, root):
    r = client(sapp(root)).get('/f/hello.txt', query_string='download=true')
    assert r.headers['Content-Disposition'] == 'attachment; filename="hello.txt"'


def test_download_custom_name_sets_mimetype_from_name(client, root):
    r = client(sapp(root)).get('/f/hello.txt', query_string='download=report.json')
    assert r.headers['Content-Disposition'] == 'attachment; filename="report.json"'
    assert r.headers['Content-Type'] == 'application/json'


@pytest.mark.parametrize('name', ['a"b.txt', '../../etc/passwd', 'x\r\nSet-Cookie: a=b', 'a\\b.txt'])
def test_download_name_sanitised(client, root, name):
    from urllib.parse import quote
    r = client(sapp(root)).get('/f/hello.txt', query_string='download=' + quote(name))
    cd = r.headers['Content-Disposition']
    assert r.get_all('Set-Cookie') == [] and '\r' not in cd and '\n' not in cd
    assert '/' not in cd.split('filename=')[1]
    assert cd.count('"') == 2


def test_download_unicode_name_header_encodable(live, root):
    s, h, b = live(sapp(root)).request('GET', '/f/hello.txt?download=caf%C3%A9.txt')
    assert s == 200 and 'attachment' in h['content-disposition']


# ------------------------------------------------------------------------ ranges

@pytest.mark.parametrize('rng,status,body,crange', [
    ('bytes=0-4', 206, '01234', 'bytes 0-4/20'),
    ('bytes=5-', 206, '56789abcdefghij', 'bytes 5-19/20'),
    ('bytes=-5', 206, 'fghij', 'bytes 15-19/20'),
    ('bytes=0-0', 206, '0', 'bytes 0-0/20'),
    ('bytes=19-19', 206, 'j', 'bytes 19-19/20'),
    ('bytes=0-1000', 206, '0123456789abcdefghij', 'bytes 0-19/20'),
    ('bytes=-1000', 206, '0123456789abcdefghij', 'bytes 0-19/20'),
    ('bytes=0-', 206, '0123456789abcdefghij', 'bytes 0-19/20'),
])
def test_range_single(client, root, rng, status, body, crange):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': rng})
    assert r.status_code == status and r.text == body
    assert r.headers['Content-Range'] == crange and r.headers['Content-Length'] == str(len(body))


@pytest.mark.parametrize('rng', ['bytes=20-', 'bytes=25-30', 'bytes=9-3', 'bytes=-0', 'bytes=abc',
                                 'bytes=a-b', 'bytes=-', 'bytes=1-2-3'])
def test_range_unsatisfiable_416(client, root, rng):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': rng})
    assert r.status_code == 416 and r.headers['Content-Range'] == 'bytes */20'


@pytest.mark.parametrize('rng', ['items=0-1', 'garbage', 'bytes 0-1', 'BYTES=0-1'])
def test_range_wrong_unit_ignored_or_416(client, root, rng):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': rng})
    assert r.status_code in (200, 416)


@pytest.mark.xfail(strict=True, reason="BUG(minor): unrecognised Range unit (e.g. items=0-1) answers 416; RFC 7233 says ignore the header and send 200")
def test_range_unknown_unit_should_be_ignored(client, root):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': 'items=0-1'})
    assert r.status_code == 200 and r.text == '0123456789abcdefghij'


def test_range_multiple_returns_something_valid(client, root):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': 'bytes=0-1,5-6'})
    assert r.status_code in (200, 206)
    if r.status_code == 206:
        assert r.headers['Content-Type'].startswith(('text/plain', 'multipart/byteranges'))


def test_range_overlapping_does_not_amplify(client, root):
    rng = 'bytes=' + ','.join(['0-19'] * 500)
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': rng})
    assert r.status_code in (200, 206, 416) and len(r.body) <= 20


def test_range_huge_numbers(client, root):
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': 'bytes=0-%d' % (10 ** 30)})
    assert r.status_code == 206 and r.headers['Content-Range'] == 'bytes 0-19/20'
    r = client(sapp(root)).get('/f/hello.txt', headers={'Range': 'bytes=%d-' % (10 ** 30)})
    assert r.status_code == 416


def test_range_head_ignores_range(client, root):
    r = client(sapp(root)).head('/f/hello.txt', headers={'Range': 'bytes=0-3'})
    assert r.status_code == 200 and r.body == b''


def test_range_live_206(live, root):
    s, h, b = live(sapp(root)).request('GET', '/f/hello.txt', headers={'Range': 'bytes=2-5'})
    assert s == 206 and b == b'2345' and h['content-range'] == 'bytes 2-5/20'


def test_range_large_file_middle(live, root):
    data = os.urandom(3 * 1024 * 1024)
    (root / 'big.bin').write_bytes(data)
    s, h, b = live(sapp(root)).request('GET', '/f/big.bin', headers={'Range': 'bytes=1048570-2097160'})
    assert s == 206 and b == data[1048570:2097161]


def test_range_closes_file(client, root):
    before = len(os.listdir('/proc/self/fd'))
    c = client(sapp(root))
    for _ in range(40):
        c.get('/f/hello.txt', headers={'Range': 'bytes=0-3'})
        c.get('/f/hello.txt', headers={'Range': 'bytes=99-'})
    assert len(os.listdir('/proc/self/fd')) <= before + 2


# ------------------------------------------------------------------ conditionals

def test_if_none_match_304(client, root):
    c = client(sapp(root))
    etag = c.get('/f/hello.txt').headers['Etag']
    r = c.get('/f/hello.txt', headers={'If-None-Match': etag})
    assert r.status_code == 304 and r.body == b'' and r.headers['Etag'] == etag


@pytest.mark.parametrize('fmt', ['{}', 'W/{}', '"nomatch", {}', '{} , "other"', '*'])
def test_if_none_match_variants(client, root, fmt):
    c = client(sapp(root))
    etag = c.get('/f/hello.txt').headers['Etag']
    assert c.get('/f/hello.txt', headers={'If-None-Match': fmt.format(etag)}).status_code == 304


@pytest.mark.parametrize('val', ['"nomatch"', '', 'garbage', '"a", "b"'])
def test_if_none_match_mismatch_200(client, root, val):
    r = client(sapp(root)).get('/f/hello.txt', headers={'If-None-Match': val})
    assert r.status_code == 200 and r.text


def test_if_modified_since_304_and_200(client, root):
    c = client(sapp(root))
    lm = c.get('/f/hello.txt').headers['Last-Modified']
    assert c.get('/f/hello.txt', headers={'If-Modified-Since': lm}).status_code == 304
    old = IMS_FMT(time.time() - 10 ** 7)
    assert c.get('/f/hello.txt', headers={'If-Modified-Since': old}).status_code == 200
    future = IMS_FMT(time.time() + 10 ** 6)
    assert c.get('/f/hello.txt', headers={'If-Modified-Since': future}).status_code == 304


@pytest.mark.parametrize('val', ['garbage', '', 'Mon, 99 Foo 2020 99:99:99 GMT', '0', '-1', 'x' * 5000])
def test_if_modified_since_garbage_ignored(client, root, val):
    r = client(sapp(root)).get('/f/hello.txt', headers={'If-Modified-Since': val})
    assert r.status_code == 200


def test_if_modified_since_with_length_suffix(client, root):
    c = client(sapp(root))
    lm = c.get('/f/hello.txt').headers['Last-Modified']
    assert c.get('/f/hello.txt', headers={'If-Modified-Since': lm + '; length=20'}).status_code == 304


@pytest.mark.xfail(strict=True, reason="BUG(minor): If-Modified-Since is honoured even when If-None-Match is present and does not match (RFC 7232 3.3: ignore IMS)")
def test_if_none_match_mismatch_overrides_ims(client, root):
    c = client(sapp(root))
    lm = c.get('/f/hello.txt').headers['Last-Modified']
    r = c.get('/f/hello.txt', headers={'If-None-Match': '"different"', 'If-Modified-Since': lm})
    assert r.status_code == 200


def test_custom_etag_option(client, root):
    c = client(sapp(root))
    assert c.get('/f/hello.txt', query_string='etag=abc').headers['Etag'] == '"abc"'
    assert c.get('/f/hello.txt', query_string='etag=abc', headers={'If-None-Match': '"abc"'}).status_code == 304
    r = c.get('/f/hello.txt', query_string='etag=false')
    assert 'Etag' not in r.headers


def test_etag_changes_when_file_changes(client, root):
    c = client(sapp(root))
    e1 = c.get('/f/hello.txt').headers['Etag']
    p = root / 'hello.txt'
    p.write_text('changed content!!!!!!')
    os.utime(p, (time.time() + 100, time.time() + 100))
    assert c.get('/f/hello.txt').headers['Etag'] != e1


def test_304_live_has_no_body(live, root):
    lv = live(sapp(root))
    s, h, b = lv.request('GET', '/f/hello.txt')
    s2, h2, b2 = lv.request('GET', '/f/hello.txt', headers={'If-None-Match': h['etag']})
    assert s2 == 304 and b2 == b''


# --------------------------------------------------------------------- traversal

TRAV = ['../secret.txt', '..%2fsecret.txt', '%2e%2e/secret.txt', '%2e%2e%2fsecret.txt',
        '..\\secret.txt', '../root-evil/x.txt', 'sub/../../secret.txt', '....//secret.txt',
        '/../secret.txt', '//..//secret.txt', 'sub/%2e%2e/%2e%2e/secret.txt', '..;/secret.txt',
        '../../../../../../etc/passwd', '%252e%252e/secret.txt']


@pytest.mark.parametrize('p', TRAV)
def test_traversal_via_query_param_never_leaks(client, root, p):
    from urllib.parse import unquote
    # handler passes the (already decoded) value straight to static_file
    r = client(sapp(root)).get('/raw', query_string='p=' + p.replace('\\', '%5C'))
    assert r.status_code in (403, 404) and 'TOPSECRET' not in r.text and 'EVIL' not in r.text


@pytest.mark.parametrize('p', TRAV)
def test_traversal_via_live_path_never_leaks(live, root, p):
    s, h, b = live(sapp(root)).request('GET', '/f/' + p.replace('\\', '%5C'))
    assert b'TOPSECRET' not in b and b'EVIL' not in b and b'root:' not in b


def test_traversal_raw_literal_dotdot_via_socket(live, root):
    lv = live(sapp(root))
    raw = lv.raw(b'GET /f/../../secret.txt HTTP/1.0\r\n\r\n')
    assert b'TOPSECRET' not in raw
    raw = lv.raw(b'GET /f/%2e%2e/%2e%2e/secret.txt HTTP/1.0\r\n\r\n')
    assert b'TOPSECRET' not in raw


def test_sibling_prefix_dir_not_accessible(client, root):
    # /root-evil shares the string prefix of /root
    r = client(sapp(root)).get('/raw', query_string='p=../root-evil/x.txt')
    assert r.status_code in (403, 404)


@pytest.mark.xfail(strict=True, reason="BUG: NUL byte in filename -> ValueError from os.path.realpath/isfile propagates as 500 instead of 404/400")
@pytest.mark.parametrize('p', ['hello.txt%00', 'a%00.txt', '%00'])
def test_null_byte_in_filename(client, root, p):
    r = client(sapp(root)).get('/raw', query_string='p=' + p)
    assert r.status_code in (400, 403, 404)


@pytest.mark.parametrize('p', ['x' * 5000, 'a/' * 3000, '.' * 300, '...'])
def test_pathological_filenames_404(client, root, p):
    r = client(sapp(root)).get('/raw', query_string='p=' + p)
    assert r.status_code in (403, 404)


def test_symlink_escaping_root_blocked(client, root, tmp_path):
    (root / 'link.txt').symlink_to(tmp_path / 'secret.txt')
    r = client(sapp(root)).get('/f/link.txt')
    assert r.status_code == 403 and 'TOPSECRET' not in r.text


def test_symlinked_dir_escaping_root_blocked(client, root, tmp_path):
    (root / 'dlink').symlink_to(tmp_path)
    r = client(sapp(root)).get('/f/dlink/secret.txt')
    assert r.status_code == 403 and 'TOPSECRET' not in r.text


def test_symlink_inside_root_allowed(client, root):
    (root / 'ok-link.txt').symlink_to(root / 'hello.txt')
    assert client(sapp(root)).get('/f/ok-link.txt').text == '0123456789abcdefghij'


def test_symlink_escape_head_blocked(client, root, tmp_path):
    (root / 'link.txt').symlink_to(tmp_path / 'secret.txt')
    r = client(sapp(root)).head('/f/link.txt')
    assert r.status_code in (403, 404), 'HEAD must not confirm existence of files outside root'


def test_dangling_symlink_404(client, root):
    (root / 'dangling').symlink_to(root / 'nonexistent')
    assert client(sapp(root)).get('/f/dangling').status_code in (403, 404)


def test_unreadable_file_403(client, root):
    if os.geteuid() == 0:
        pytest.skip('root can read everything')
    p = root / 'locked.txt'
    p.write_text('x'); p.chmod(0)
    try:
        assert client(sapp(root)).get('/f/locked.txt').status_code == 403
    finally:
        p.chmod(0o644)


def test_fifo_is_not_served(client, root):
    os.mkfifo(root / 'fifo')
    assert client(sapp(root)).get('/f/fifo').status_code == 404


def test_root_with_trailing_slash_and_relative(client, root):
    app = Lcore()
    app.get('/x')(lambda: static_file('hello.txt', root=str(root) + '/'))
    assert client(app).get('/x').status_code == 200
    app2 = Lcore()
    app2.get('/x')(lambda: static_file('hello.txt', root=str(root) + '/sub/../'))
    assert client(app2).get('/x').status_code == 200


def test_missing_root_dir_404(client, tmp_path):
    app = Lcore()
    app.get('/x')(lambda: static_file('a.txt', root=str(tmp_path / 'nope')))
    assert client(app).get('/x').status_code == 404


def test_extra_headers_param(client, root):
    app = Lcore()
    app.get('/x')(lambda: static_file('hello.txt', root=str(root), headers={'X-Custom': '1', 'Cache-Control': 'max-age=60'}))
    r = client(app).get('/x')
    assert r.headers['X-Custom'] == '1' and r.headers['Cache-Control'] == 'max-age=60'


def test_headers_param_not_mutated(root):
    hd = {'X-A': '1'}
    app = Lcore()
    app.get('/x')(lambda: static_file('hello.txt', root=str(root), headers=hd))
    lcore.TestClient(app).get('/x')
    assert hd == {'X-A': '1'}


def test_concurrent_static_requests_live(live, root):
    lv = live(sapp(root))
    errs = []

    def w():
        for _ in range(10):
            s, h, b = lv.request('GET', '/f/hello.txt', headers={'Range': 'bytes=0-4'})
            if (s, b) != (206, b'01234'): errs.append((s, b))
    ts = [threading.Thread(target=w) for _ in range(4)]
    [t.start() for t in ts]; [t.join(30) for t in ts]
    assert not errs


# -------------------------------------------------------------- SimpleTemplate

def T(src, **kw):
    return SimpleTemplate(src).render(**kw)


@pytest.mark.parametrize('src,vars,out', [
    ('Hello {{name}}', {'name': 'W'}, 'Hello W'),
    ('{{x}}', {'x': '<b>&"\'</b>'}, '&lt;b&gt;&amp;&quot;&#039;&lt;/b&gt;'),
    ('{{!x}}', {'x': '<b>'}, '<b>'),
    ('{{ x }}', {'x': 1}, '1'),
    ('{{x + 1}}', {'x': 1}, '2'),
    ('{{x}}', {'x': None}, ''),
    ('{{x}}', {'x': 0}, '0'),
    ('{{x}}', {'x': 'é✓😀'}, 'é✓😀'),
    ('{{x}}', {'x': b'bytes \xc3\xa9'}, 'bytes é'),
    ('{{x}}', {'x': 1.5}, '1.5'),
    ('{{x}}', {'x': [1, '<']}, "[1, &#039;&lt;&#039;]"),
    ('{{"{{"}}', {}, '{{'),
    ('a\nb', {}, 'a\nb'),
    ('no tags', {}, 'no tags'),
    ('{{x}}{{y}}', {'x': 1, 'y': 2}, '12'),
    ('{{"a" if x else "b"}}', {'x': 0}, 'b'),
])
def test_template_expressions(src, vars, out):
    assert T(src, **vars) == out


def test_template_code_lines_and_loops():
    src = "%for i in items:\n<{{i}}>\n%end\n"
    assert T(src, items=[1, 2, 3]) == '<1>\n<2>\n<3>\n'


def test_template_if_elif_else():
    src = "%if x == 1:\none\n%elif x == 2:\ntwo\n%else:\nother\n%end\n"
    assert [T(src, x=i).strip() for i in (1, 2, 3)] == ['one', 'two', 'other']


def test_template_percent_escape_and_inline_code():
    assert T("\\% not code\n").strip() == '% not code'
    assert T("<% x = 5 %>\n{{x}}").strip() == '5'


def test_template_try_except_inside():
    src = "%try:\n{{1/0}}\n%except ZeroDivisionError:\nboom\n%end\n"
    assert T(src).strip() == 'boom'


def test_template_defined_get_setdefault():
    src = "{{defined('a')}} {{get('b', 'dflt')}}{{setdefault('c', 3)}} {{c}}"
    assert T(src, a=1) == 'True dflt3 3'


def test_template_missing_variable_raises_nameerror():
    with pytest.raises(NameError):
        T('{{nope}}')


def test_template_syntax_errors():
    with pytest.raises(SyntaxError):
        T('{{ 1 + }}')
    with pytest.raises(SyntaxError):
        T('%for x in y\n a\n%end', y=[1])
    with pytest.raises(SyntaxError):
        T('%else:\nx\n')


def test_template_lenient_unclosed_and_stray_end():
    assert T('%if x:\nno end\n', x=1) == 'no end\n'   # tolerated, as in Bottle
    assert T('%end\n') == ''


def test_template_exception_in_expression_propagates():
    with pytest.raises(ZeroDivisionError):
        T('{{1/0}}')


def test_template_defaults_and_override():
    t = SimpleTemplate('{{a}}{{b}}')
    t.defaults = {'a': 'D', 'b': 'D'}
    assert t.render(a='X') == 'XD'


def test_template_render_does_not_leak_between_calls():
    t = SimpleTemplate('{{get("x", "unset")}}%x = 1\n')
    assert t.render(x=5).startswith('5')
    assert t.render().startswith('unset')


def test_template_dict_args_and_kwargs_merge():
    assert SimpleTemplate('{{a}}{{b}}').render({'a': 1}, b=2) == '12'


def test_template_noescape_setting():
    assert SimpleTemplate('{{x}}', noescape=True).render(x='<b>') == '<b>'
    assert SimpleTemplate('{{!x}}', noescape=True).render(x='<b>') == '&lt;b&gt;'


def test_template_custom_escape_func():
    assert SimpleTemplate('{{x}}', escape_func=lambda s: s.upper()).render(x='ab') == 'AB'


def test_template_custom_syntax():
    t = SimpleTemplate('<% x = 2 %>\n[[x]]', syntax='<% %> % [[ ]]')
    assert t.render().strip() == '2'


def test_template_xss_in_all_default_vectors():
    payload = '"><script>alert(1)</script>'
    out = T('<a href="{{u}}">{{u}}</a>', u=payload)
    assert '<script>' not in out and '"&gt;' not in out.replace('&quot;&gt;', '')


def test_template_large_loop():
    out = T('%for i in range(20000):\n{{i}},\n%end\n')
    assert out.count(',') == 20000


def test_template_unicode_source_and_bytes_source():
    assert T('héllo {{x}}', x='✓') == 'héllo ✓'
    assert SimpleTemplate('h\xc3\xa9llo'.encode('latin1')).render() == 'héllo'


def test_template_invalid_utf8_source():
    with pytest.raises(Exception):
        SimpleTemplate(b'\xff\xfe{{x}}').render(x=1)


# ----------------------------------------------------- includes / rebase / lookup

@pytest.fixture
def tpls(tmp_path):
    d = tmp_path / 'views'
    d.mkdir()
    (d / 'base.tpl').write_text('<html>{{!base}}</html>')
    (d / 'child.tpl').write_text("%rebase('base.tpl')\n<p>{{msg}}</p>")
    (d / 'inc.tpl').write_text('[inc {{v}}]')
    (d / 'parent.tpl').write_text("a\n%include('inc.tpl', v=v)\nb\n%include('inc.tpl', v='x')\n")
    (d / 'hello.tpl').write_text('Hello {{name}}!')
    (d / 'page.html').write_text('HTML {{name}}')
    (d / 'sub').mkdir()
    (d / 'sub' / 'deep.tpl').write_text('deep')
    (tmp_path / 'outside.tpl').write_text('OUTSIDE')
    (d / 'self.tpl').write_text("%include('self.tpl')")
    return d


def tp(d, tname, **kw):
    return SimpleTemplate(name=tname, lookup=[str(d)]).render(**kw)


def test_template_by_name_with_ext_search(tpls):
    assert tp(tpls, 'hello', name='W') == 'Hello W!'
    assert tp(tpls, 'hello.tpl', name='W') == 'Hello W!'
    assert tp(tpls, 'page', name='W') == 'HTML W'
    assert tp(tpls, 'sub/deep') == 'deep'


def test_template_include_and_rebase(tpls):
    assert tp(tpls, 'parent', v=1) == 'a\n[inc 1]b\n[inc x]'
    assert tp(tpls, 'child', msg='<hi>').strip() == '<html><p>&lt;hi&gt;</p></html>'


def test_template_missing_raises(tpls):
    with pytest.raises(TemplateError):
        tp(tpls, 'missing')


def test_template_missing_include_raises(tpls):
    (tpls / 'bad.tpl').write_text("%include('nonexistent')")
    with pytest.raises(TemplateError):
        tp(tpls, 'bad')


@pytest.mark.parametrize('name', ['../outside.tpl', '../outside', 'sub/../../outside.tpl',
                                  '..\\outside.tpl', 'sub/../../../etc/passwd'])
def test_template_lookup_traversal_blocked(tpls, name):
    with pytest.raises(TemplateError):
        tp(tpls, name)


def test_template_traversal_never_renders_outside(tpls):
    for name in ('../outside.tpl', 'sub/../../outside.tpl'):
        try:
            out = tp(tpls, name)
        except Exception:
            continue
        assert 'OUTSIDE' not in out


def test_template_include_traversal_blocked(tpls):
    (tpls / 'evil.tpl').write_text("%include('../outside.tpl')")
    try:
        out = tp(tpls, 'evil')
    except Exception:
        return
    assert 'OUTSIDE' not in out


def test_template_recursive_include_bounded(tpls):
    with pytest.raises(RecursionError):
        tp(tpls, 'self')


def test_template_search_helper_returns_none_for_traversal(tpls):
    assert BaseTemplate.search('../outside.tpl', [str(tpls)]) is None
    assert BaseTemplate.search('hello', [str(tpls)]).endswith('hello.tpl')
    assert BaseTemplate.search('nope', [str(tpls)]) is None


def test_template_file_changed_not_reloaded_without_debug(tpls):
    # compiled template objects are cached by template(); document staleness semantics
    lookup = [str(tpls)]
    lcore.TEMPLATES.clear()
    assert template('hello', name='A', template_lookup=lookup) == 'Hello A!'
    (tpls / 'hello.tpl').write_text('Bye {{name}}')
    out = template('hello', name='A', template_lookup=lookup)
    assert out in ('Hello A!', 'Bye A')   # cached unless DEBUG
    lcore.TEMPLATES.clear()
    assert template('hello', name='A', template_lookup=lookup) == 'Bye A'


def test_template_function_inline_source_and_cache_key():
    lcore.TEMPLATES.clear()
    assert template('Hi {{n}}', n=1) == 'Hi 1'
    assert template('Hi {{n}}', n=2) == 'Hi 2'
    assert template('Hi {{n}}', {'n': 3}) == 'Hi 3'


def test_template_function_name_not_found():
    with pytest.raises(TemplateError):
        template('nonexistent_tpl_zzz', template_lookup=['/nonexistent-dir'])


def test_template_cache_eviction_bounded():
    lcore.TEMPLATES.clear()
    for i in range(lcore._TEMPLATES_MAX + 50):
        template('t%d {{x}}' % i, x=1)
    assert len(lcore.TEMPLATES) <= lcore._TEMPLATES_MAX + 1


def test_template_thread_safety_shared_template():
    t = SimpleTemplate('{{x}}-{{y}}')
    errs = []

    def w(i):
        for j in range(200):
            if t.render(x=i, y=j) != '%d-%d' % (i, j): errs.append((i, j))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    [x.start() for x in ts]; [x.join() for x in ts]
    assert not errs


def test_template_shared_include_cache_thread_safety(tpls):
    t = SimpleTemplate(name='parent', lookup=[str(tpls)])
    errs = []

    def w(i):
        for j in range(100):
            if t.render(v=i) != 'a\n[inc %d]b\n[inc x]' % i: errs.append(i)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    [x.start() for x in ts]; [x.join() for x in ts]
    assert not errs


# --------------------------------------------------------------------- view()

def test_view_decorator_dict_none_and_passthrough(client, tpls):
    app = Lcore()
    lookup = [str(tpls)]

    @app.get('/d')
    @view('hello', template_lookup=lookup)
    def d(): return {'name': 'Dict'}

    @app.get('/n')
    @view('hello', template_lookup=lookup, name='Default')
    def n(): return None

    @app.get('/p')
    @view('hello', template_lookup=lookup)
    def p(): return 'plain string'

    @app.get('/o')
    @view('hello', template_lookup=lookup, name='Def')
    def o(): return {'name': 'Override'}

    @app.get('/e')
    @view('hello', template_lookup=lookup)
    def e(): abort(404, 'gone')
    c = client(app)
    assert c.get('/d').text == 'Hello Dict!'
    assert c.get('/n').text == 'Hello Default!'
    assert c.get('/p').text == 'plain string'
    assert c.get('/o').text == 'Hello Override!'
    assert c.get('/e').status_code == 404


def abort(*a): raise HTTPError(*a)


def test_view_escapes_user_input_end_to_end(client, tpls):
    app = Lcore()

    @app.get('/x')
    @view('hello', template_lookup=[str(tpls)])
    def x(): return {'name': request.query.get('n')}
    r = client(app).get('/x', query_string='n=%3Cscript%3Ealert(1)%3C/script%3E')
    assert '<script>' not in r.text and '&lt;script&gt;' in r.text


def test_view_missing_template_is_500(client):
    app = Lcore()

    @app.get('/x')
    @view('does_not_exist_zz', template_lookup=['/nonexistent'])
    def x(): return {}
    assert client(app).get('/x').status_code == 500


def test_view_template_error_does_not_leak_source(client):
    app = Lcore()

    @app.get('/x')
    @view('{{ undefined_name }} SECRETSRC')
    def x(): return {}
    r = client(app).get('/x')
    assert r.status_code == 500 and 'SECRETSRC' not in r.text


def test_view_preserves_function_metadata():
    @view('x')
    def handler(): "doc"
    assert handler.__name__ == 'handler' and handler.__doc__ == 'doc'


def test_template_route_config_plugin(client, tpls):
    app = Lcore()
    lcore.TEMPLATE_PATH.insert(0, str(tpls))
    try:
        @app.get('/x', template='hello')
        def x(): return {'name': 'Plug'}
        assert client(app).get('/x').text == 'Hello Plug!'
    finally:
        lcore.TEMPLATE_PATH.remove(str(tpls))


def test_view_with_dictmixin_result(client, tpls):
    from lcore import FormsDict
    app = Lcore()

    @app.get('/x')
    @view('hello', template_lookup=[str(tpls)])
    def x(): return FormsDict(name='FD')
    assert client(app).get('/x').text == 'Hello FD!'


def test_view_unicode_template_roundtrip_live(live, tpls):
    (tpls / 'uni.tpl').write_text('日本語 {{x}} ✓', encoding='utf8')
    app = Lcore()

    @app.get('/x')
    @view('uni', template_lookup=[str(tpls)])
    def x(): return {'x': 'é😀'}
    s, h, b = live(app).request('GET', '/x')
    assert s == 200 and b.decode('utf8') == '日本語 é😀 ✓' and int(h['content-length']) == len(b)


# ------------------------------------------------------------- jinja2 adapter

def test_jinja2_adapter_escape_and_render(tpls):
    pytest.importorskip('jinja2')
    from lcore import Jinja2Template
    t = Jinja2Template('Hi {{ n }}', autoescape=True)
    assert t.render(n='<b>') == 'Hi &lt;b&gt;'
    (tpls / 'j.html').write_text('J {{ n }}')
    assert Jinja2Template(name='j.html', lookup=[str(tpls)]).render(n=1) == 'J 1'


def test_jinja2_lookup_traversal_blocked(tpls):
    pytest.importorskip('jinja2')
    from lcore import Jinja2Template
    (tpls / 'bad.html').write_text("{% include '../outside.tpl' %}")
    t = Jinja2Template(name='bad.html', lookup=[str(tpls)])
    try:
        out = t.render()
    except Exception:
        return
    assert 'OUTSIDE' not in out


def test_template_absolute_name_raises_templateerror(tpls):
    with pytest.raises(TemplateError):
        tp(tpls, '/etc/passwd')


def test_template_search_empty_lookup_raises_templateerror():
    with pytest.raises(TemplateError):
        BaseTemplate.search('x', [])
