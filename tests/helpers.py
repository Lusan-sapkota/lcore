"""Shared test utilities for Lcore framework tests."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from io import BytesIO, StringIO
from lcore import Lcore, request, response, tob


def create_environ(method='GET', path='/', body=b'', headers=None,
                   query_string='', content_type=None):
    """Create a minimal WSGI environ dict for testing."""
    environ = {
        'REQUEST_METHOD': method.upper(),
        'PATH_INFO': path,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8080',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.input': BytesIO(body),
        'wsgi.errors': StringIO(),
        'wsgi.url_scheme': 'http',
        'QUERY_STRING': query_string,
        'CONTENT_LENGTH': str(len(body)),
        'HTTP_HOST': 'localhost:8080',
    }
    if content_type:
        environ['CONTENT_TYPE'] = content_type
    if headers:
        for key, value in headers.items():
            key = key.upper().replace('-', '_')
            if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                key = 'HTTP_' + key
            environ[key] = value
    return environ


def run_request(app, method='GET', path='/', body=b'', headers=None,
                query_string='', content_type=None):
    """Execute a WSGI request against an Lcore app, return (status, headers, body)."""
    environ = create_environ(method, path, body, headers, query_string, content_type)
    status_holder = {}
    headers_holder = {}

    def start_response(status, response_headers, exc_info=None):
        status_holder['status'] = status
        headers_holder['headers'] = dict(response_headers)

    body_chunks = app(environ, start_response)
    response_body = b''.join(body_chunks)

    if hasattr(body_chunks, 'close'):
        body_chunks.close()

    return status_holder['status'], headers_holder['headers'], response_body
