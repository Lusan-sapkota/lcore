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
