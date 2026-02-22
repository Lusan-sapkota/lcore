"""Tests for Lcore observability middleware."""

import unittest
import logging
import json
import uuid
import re

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import create_environ, run_request
from lcore import Lcore, RequestIDMiddleware, RequestLoggerMiddleware, ctx


class ListHandler(logging.Handler):
    """A logging handler that collects records into a list for assertions."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def get_header(headers, name):
    """Case-insensitive header lookup from a response headers dict.

    WSGI servers may title-case header names (e.g. ``X-Request-Id`` instead of
    ``X-Request-ID``).  This helper normalises the comparison so tests are not
    sensitive to that behaviour.
    """
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return value
    return None


# ---------------------------------------------------------------------------
#  RequestIDMiddleware Tests
# ---------------------------------------------------------------------------

class TestRequestIDMiddlewareGeneratesID(unittest.TestCase):
    """Test that RequestIDMiddleware generates a UUID request ID when none is
    provided by the client."""

    def setUp(self):
        self.app = Lcore()
        self.app.use(RequestIDMiddleware())

        @self.app.route('/test')
        def handler():
            return 'ok'

    def test_generates_request_id(self):
        status, headers, body = run_request(self.app, 'GET', '/test')
        request_id = get_header(headers, 'X-Request-ID')
        self.assertIsNotNone(request_id,
                             "X-Request-ID header must be present in response")
        # Validate it is a well-formed UUID (version 4)
        parsed = uuid.UUID(request_id, version=4)
        self.assertEqual(str(parsed), request_id)

    def test_generates_unique_ids_per_request(self):
        _, headers1, _ = run_request(self.app, 'GET', '/test')
        _, headers2, _ = run_request(self.app, 'GET', '/test')
        id1 = get_header(headers1, 'X-Request-ID')
        id2 = get_header(headers2, 'X-Request-ID')
        self.assertNotEqual(id1, id2,
                            "Each request must receive a unique ID")


class TestRequestIDMiddlewarePropagatesExisting(unittest.TestCase):
    """Test that RequestIDMiddleware propagates an existing X-Request-ID header
    from the incoming request."""

    def setUp(self):
        self.app = Lcore()
        self.app.use(RequestIDMiddleware())

        @self.app.route('/test')
        def handler():
            return 'ok'

    def test_propagates_existing_request_id(self):
        custom_id = 'my-custom-id-12345'
        status, headers, body = run_request(
            self.app, 'GET', '/test',
            headers={'X-Request-ID': custom_id}
        )
        self.assertEqual(get_header(headers, 'X-Request-ID'), custom_id,
                         "The middleware must propagate the client-supplied "
                         "X-Request-ID value")

    def test_propagates_uuid_format_id(self):
        custom_uuid = str(uuid.uuid4())
        _, headers, _ = run_request(
            self.app, 'GET', '/test',
            headers={'X-Request-ID': custom_uuid}
        )
        self.assertEqual(get_header(headers, 'X-Request-ID'), custom_uuid)

    def test_propagates_arbitrary_string_id(self):
        arbitrary_id = 'trace-abc-def-ghi'
        _, headers, _ = run_request(
            self.app, 'GET', '/test',
            headers={'X-Request-ID': arbitrary_id}
        )
        self.assertEqual(get_header(headers, 'X-Request-ID'), arbitrary_id)


class TestRequestIDInResponseHeaders(unittest.TestCase):
    """Test that X-Request-ID always appears in the response headers."""

    def setUp(self):
        self.app = Lcore()
        self.app.use(RequestIDMiddleware())

        @self.app.route('/hello')
        def handler():
            return 'hello'

        @self.app.route('/json')
        def json_handler():
            return '{"key": "value"}'

    def test_response_header_present_on_simple_route(self):
        status, headers, body = run_request(self.app, 'GET', '/hello')
        self.assertIsNotNone(get_header(headers, 'X-Request-ID'),
                             "X-Request-ID header must be in the response")

    def test_response_header_present_on_different_route(self):
        status, headers, body = run_request(self.app, 'GET', '/json')
        self.assertIsNotNone(get_header(headers, 'X-Request-ID'),
                             "X-Request-ID header must be in the response")

    def test_response_header_present_with_post_method(self):
        @self.app.route('/submit', method='POST')
        def submit_handler():
            return 'submitted'

        status, headers, body = run_request(self.app, 'POST', '/submit')
        self.assertIsNotNone(get_header(headers, 'X-Request-ID'),
                             "X-Request-ID header must be in the response")


class TestCtxRequestIDSet(unittest.TestCase):
    """Test that ctx.request_id is set during request processing."""

    def setUp(self):
        self.app = Lcore()
        self.app.use(RequestIDMiddleware())

    def test_ctx_request_id_set_with_generated_id(self):
        captured = {}

        @self.app.route('/capture')
        def handler():
            captured['request_id'] = ctx.request_id
            return 'ok'

        status, headers, body = run_request(self.app, 'GET', '/capture')
        self.assertIn('request_id', captured,
                      "ctx.request_id must be accessible inside the handler")
        self.assertIsNotNone(captured['request_id'])
        # The captured value must match the response header
        self.assertEqual(captured['request_id'],
                         get_header(headers, 'X-Request-ID'))

    def test_ctx_request_id_set_with_propagated_id(self):
        captured = {}
        custom_id = 'propagated-ctx-id'

        @self.app.route('/capture')
        def handler():
            captured['request_id'] = ctx.request_id
            return 'ok'

        run_request(self.app, 'GET', '/capture',
                    headers={'X-Request-ID': custom_id})
        self.assertEqual(captured['request_id'], custom_id,
                         "ctx.request_id must reflect the propagated value")

    def test_ctx_request_id_is_valid_uuid_when_generated(self):
        captured = {}

        @self.app.route('/capture')
        def handler():
            captured['request_id'] = ctx.request_id
            return 'ok'

        run_request(self.app, 'GET', '/capture')
        # Should be parseable as UUID
        parsed = uuid.UUID(captured['request_id'], version=4)
        self.assertEqual(str(parsed), captured['request_id'])


# ---------------------------------------------------------------------------
#  RequestLoggerMiddleware Tests
# ---------------------------------------------------------------------------

class TestRequestLoggerMiddlewareLogs(unittest.TestCase):
    """Test that RequestLoggerMiddleware logs structured request information."""

    def setUp(self):
        self.logger = logging.getLogger('test.access.' + self.id())
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.handler = ListHandler()
        self.logger.addHandler(self.handler)

        self.app = Lcore()
        self.app.use(RequestIDMiddleware())
        self.app.use(RequestLoggerMiddleware(logger=self.logger))

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def _get_logged_data(self, index=0):
        """Parse the JSON from the log record at the given index."""
        self.assertGreater(len(self.handler.records), index,
                           "Expected at least %d log record(s)" % (index + 1))
        return json.loads(self.handler.records[index].getMessage())

    def test_logs_request_method(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertEqual(data['method'], 'GET')

    def test_logs_request_path(self):
        @self.app.route('/some/path')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/some/path')
        data = self._get_logged_data()
        self.assertEqual(data['path'], '/some/path')

    def test_logs_status_code(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertEqual(data['status'], 200)

    def test_logs_request_id(self):
        custom_id = 'log-test-id-42'

        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test',
                    headers={'X-Request-ID': custom_id})
        data = self._get_logged_data()
        self.assertEqual(data['request_id'], custom_id)

    def test_logs_timestamp(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertIn('timestamp', data)
        # ISO 8601 format check (basic validation)
        self.assertRegex(data['timestamp'],
                         r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}')

    def test_logs_remote_addr(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        environ = create_environ('GET', '/test')
        environ['REMOTE_ADDR'] = '192.168.1.100'
        status_holder = {}
        def start_response(status, headers, exc_info=None):
            status_holder['status'] = status
        body = self.app(environ, start_response)
        if hasattr(body, 'close'): body.close()
        data = self._get_logged_data()
        self.assertEqual(data['remote_addr'], '192.168.1.100')

    def test_logs_post_request(self):
        @self.app.route('/submit', method='POST')
        def handler():
            return 'submitted'

        run_request(self.app, 'POST', '/submit', body=b'data=value',
                    content_type='application/x-www-form-urlencoded')
        data = self._get_logged_data()
        self.assertEqual(data['method'], 'POST')
        self.assertEqual(data['path'], '/submit')

    def test_log_record_is_valid_json(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        record = self.handler.records[0]
        # Should not raise
        parsed = json.loads(record.getMessage())
        self.assertIsInstance(parsed, dict)


class TestRequestLoggerMiddlewareTiming(unittest.TestCase):
    """Test that RequestLoggerMiddleware includes timing data."""

    def setUp(self):
        self.logger = logging.getLogger('test.timing.' + self.id())
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.handler = ListHandler()
        self.logger.addHandler(self.handler)

        self.app = Lcore()
        self.app.use(RequestIDMiddleware())
        self.app.use(RequestLoggerMiddleware(logger=self.logger))

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def _get_logged_data(self, index=0):
        """Parse the JSON from the log record at the given index."""
        self.assertGreater(len(self.handler.records), index,
                           "Expected at least %d log record(s)" % (index + 1))
        return json.loads(self.handler.records[index].getMessage())

    def test_includes_duration_ms(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertIn('duration_ms', data,
                      "Log entry must include duration_ms field")

    def test_duration_is_numeric(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertIsInstance(data['duration_ms'], (int, float),
                              "duration_ms must be a number")

    def test_duration_is_non_negative(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = self._get_logged_data()
        self.assertGreaterEqual(data['duration_ms'], 0,
                                "duration_ms must be non-negative")

    def test_duration_is_reasonable(self):
        """A simple handler should complete in well under 5 seconds."""
        @self.app.route('/fast')
        def handler():
            return 'fast'

        run_request(self.app, 'GET', '/fast')
        data = self._get_logged_data()
        self.assertLess(data['duration_ms'], 5000,
                        "A trivial handler should not take 5+ seconds")

    def test_duration_reflects_handler_work(self):
        """A handler with a deliberate delay should show measurable duration."""
        import time

        @self.app.route('/slow')
        def handler():
            time.sleep(0.05)  # 50ms
            return 'slow'

        run_request(self.app, 'GET', '/slow')
        data = self._get_logged_data()
        self.assertGreaterEqual(data['duration_ms'], 40,
                                "duration_ms should reflect the 50ms sleep "
                                "(allowing 10ms tolerance)")


# ---------------------------------------------------------------------------
#  Integration Tests
# ---------------------------------------------------------------------------

class TestObservabilityIntegration(unittest.TestCase):
    """Integration tests combining RequestIDMiddleware and
    RequestLoggerMiddleware together."""

    def setUp(self):
        self.logger = logging.getLogger('test.integration.' + self.id())
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.handler = ListHandler()
        self.logger.addHandler(self.handler)

        self.app = Lcore()
        self.app.use(RequestIDMiddleware())
        self.app.use(RequestLoggerMiddleware(logger=self.logger))

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def test_logged_request_id_matches_response_header(self):
        @self.app.route('/test')
        def handler():
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/test')
        data = json.loads(self.handler.records[0].getMessage())
        self.assertEqual(data['request_id'],
                         get_header(headers, 'X-Request-ID'),
                         "The request_id in the log must match the response "
                         "X-Request-ID header")

    def test_logged_request_id_matches_ctx_request_id(self):
        captured = {}

        @self.app.route('/test')
        def handler():
            captured['request_id'] = ctx.request_id
            return 'ok'

        run_request(self.app, 'GET', '/test')
        data = json.loads(self.handler.records[0].getMessage())
        self.assertEqual(data['request_id'], captured['request_id'])

    def test_full_log_entry_structure(self):
        @self.app.route('/health')
        def handler():
            return 'healthy'

        run_request(self.app, 'GET', '/health')
        data = json.loads(self.handler.records[0].getMessage())

        expected_keys = {'timestamp', 'request_id', 'method', 'path',
                         'status', 'duration_ms', 'remote_addr'}
        self.assertEqual(set(data.keys()), expected_keys,
                         "Log entry must contain exactly the expected keys")

    def test_multiple_requests_logged_independently(self):
        @self.app.route('/a')
        def handler_a():
            return 'a'

        @self.app.route('/b')
        def handler_b():
            return 'b'

        run_request(self.app, 'GET', '/a')
        run_request(self.app, 'GET', '/b')

        self.assertEqual(len(self.handler.records), 2)
        data_a = json.loads(self.handler.records[0].getMessage())
        data_b = json.loads(self.handler.records[1].getMessage())

        self.assertEqual(data_a['path'], '/a')
        self.assertEqual(data_b['path'], '/b')
        self.assertNotEqual(data_a['request_id'], data_b['request_id'])


class TestRequestLoggerMiddlewareDefaultLogger(unittest.TestCase):
    """Test that RequestLoggerMiddleware uses lcore.access logger by default."""

    def test_default_logger_name(self):
        middleware = RequestLoggerMiddleware()
        self.assertEqual(middleware.logger.name, 'lcore.access')

    def test_custom_logger_used(self):
        custom = logging.getLogger('my.custom.logger')
        middleware = RequestLoggerMiddleware(logger=custom)
        self.assertIs(middleware.logger, custom)


class TestMiddlewareOrder(unittest.TestCase):
    """Test that middleware order attributes are correct."""

    def test_request_id_middleware_order(self):
        m = RequestIDMiddleware()
        self.assertEqual(m.order, 1)

    def test_request_logger_middleware_order(self):
        m = RequestLoggerMiddleware()
        self.assertEqual(m.order, 2)

    def test_request_id_runs_before_logger(self):
        """RequestIDMiddleware (order=1) should run before
        RequestLoggerMiddleware (order=2), so the logger can read
        ctx.request_id set by the ID middleware."""
        self.assertLess(RequestIDMiddleware.order,
                        RequestLoggerMiddleware.order)


if __name__ == '__main__':
    unittest.main()
