"""Regression tests for the v0.0.6 audit fixes."""
import sys, os, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Optional
from lcore import *


def _post(schema, payload):
    app = Lcore()

    @app.post('/u')
    @validate_request(body=schema)
    def u(): return request.json

    return TestClient(app).post('/u', json=payload)


def test_validate_rejects_junk_and_accepts_optional_null():
    assert _post({'n': str}, {'n': None}).status_code == 422
    assert _post({'n': str}, {'n': {'a': 1}}).status_code == 422
    assert _post({'n': float}, {'n': 'nan'}).status_code == 422
    assert _post({'n': int}, {'n': 3.9}).status_code == 422
    assert _post({'n': bool}, {'n': []}).status_code == 422
    assert _post({'n': int}, {'n': True}).status_code == 422
    assert _post({'n': bool}, {'n': 'false'}).json == {'n': False}
    assert _post({'n': int}, {'n': 3.0}).json == {'n': 3}
    assert _post({'n': Optional[int]}, {'n': None}).json == {'n': None}


def test_malformed_content_type_is_not_a_500():
    app = Lcore()

    @app.post('/p')
    def p(): return dict(request.forms)

    c = TestClient(app)
    assert c.post('/p', body=b'a=1', content_type='application/x-www-form-urlencoded;charset').json == {'a': '1'}
    assert c.post('/p', body=b'a=1', content_type='multipart/form-data;boundary').status_code == 400


def test_rate_limit_cleanup_survives_concurrent_inserts():
    import threading
    from lcore import rate_limit
    errs = []

    @rate_limit(10 ** 9, per=0.0001, single_process=True)
    def f(): return 1

    def w(t):
        for i in range(15000):
            request.bind({'REMOTE_ADDR': '10.%d.%d.%d' % (t, i >> 8 & 255, i & 255)})
            try: f()
            except RuntimeError as e: errs.append(e); return

    ts = [threading.Thread(target=w, args=(t,)) for t in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs


def test_default_body_limit_and_override():
    app = Lcore()

    @app.post('/j')
    def j(): return {'n': len(request.json['x'])}

    c = TestClient(app)
    big = b'{"x": "' + b'a' * (11 * 1024 * 1024) + b'"}'
    assert c.post('/j', body=big, content_type='application/json').status_code == 413
    app.config['request.max_body'] = 0
    assert c.post('/j', body=big, content_type='application/json').status_code == 200


def test_redirect_with_line_break_is_400():
    app = Lcore()

    @app.get('/r')
    def r(): redirect(request.query.u)

    c = TestClient(app)
    assert c.get('/r', query_string='u=%0d%0aSet-Cookie:x=1').status_code == 400
    assert c.get('/r', query_string='u=/ok').headers['Location'] == 'http://localhost/ok'
