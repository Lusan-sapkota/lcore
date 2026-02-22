"""Tests for Lcore request context."""

import unittest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import Lcore, RequestContext, ctx


class TestRequestContextCreation(unittest.TestCase):
    """Test RequestContext initialization with various arguments."""

    def test_default_creation(self):
        rc = RequestContext()
        self.assertIsNone(rc.request)
        self.assertIsNone(rc.response)
        self.assertIsNone(rc.app)
        self.assertIsNone(rc.route)
        self.assertIsNone(rc.request_id)
        self.assertIsNone(rc.user)
        self.assertIsInstance(rc.state, dict)
        self.assertEqual(rc.state, {})
        self.assertIsInstance(rc._lazy, dict)
        self.assertEqual(rc._lazy, {})

    def test_creation_with_req(self):
        sentinel = object()
        rc = RequestContext(req=sentinel)
        self.assertIs(rc.request, sentinel)
        self.assertIsNone(rc.response)
        self.assertIsNone(rc.app)

    def test_creation_with_resp(self):
        sentinel = object()
        rc = RequestContext(resp=sentinel)
        self.assertIsNone(rc.request)
        self.assertIs(rc.response, sentinel)
        self.assertIsNone(rc.app)

    def test_creation_with_app(self):
        sentinel = object()
        rc = RequestContext(app=sentinel)
        self.assertIsNone(rc.request)
        self.assertIsNone(rc.response)
        self.assertIs(rc.app, sentinel)

    def test_creation_with_all_args(self):
        req = object()
        resp = object()
        app = object()
        rc = RequestContext(req=req, resp=resp, app=app)
        self.assertIs(rc.request, req)
        self.assertIs(rc.response, resp)
        self.assertIs(rc.app, app)

    def test_slots_defined(self):
        expected_slots = ('request', 'response', 'app', 'route',
                          'request_id', 'user', 'state', '_lazy')
        self.assertEqual(RequestContext.__slots__, expected_slots)

    def test_route_defaults_to_none(self):
        rc = RequestContext()
        self.assertIsNone(rc.route)

    def test_user_defaults_to_none(self):
        rc = RequestContext()
        self.assertIsNone(rc.user)

    def test_set_slot_attributes_directly(self):
        rc = RequestContext()
        rc.request_id = 'abc-123'
        self.assertEqual(rc.request_id, 'abc-123')
        rc.user = {'name': 'alice'}
        self.assertEqual(rc.user, {'name': 'alice'})
        route_obj = object()
        rc.route = route_obj
        self.assertIs(rc.route, route_obj)


class TestRequestContextState(unittest.TestCase):
    """Test that extra attributes are stored in the state dict."""

    def test_extra_attribute_stored_in_state(self):
        rc = RequestContext()
        rc.custom_value = 42
        self.assertEqual(rc.custom_value, 42)
        self.assertIn('custom_value', rc.state)
        self.assertEqual(rc.state['custom_value'], 42)

    def test_multiple_extra_attributes(self):
        rc = RequestContext()
        rc.foo = 'bar'
        rc.count = 10
        rc.items = [1, 2, 3]
        self.assertEqual(rc.foo, 'bar')
        self.assertEqual(rc.count, 10)
        self.assertEqual(rc.items, [1, 2, 3])
        self.assertEqual(rc.state, {'foo': 'bar', 'count': 10, 'items': [1, 2, 3]})

    def test_overwrite_extra_attribute(self):
        rc = RequestContext()
        rc.key = 'old'
        self.assertEqual(rc.key, 'old')
        rc.key = 'new'
        self.assertEqual(rc.key, 'new')
        self.assertEqual(rc.state['key'], 'new')

    def test_slot_attributes_not_in_state(self):
        rc = RequestContext()
        rc.request_id = 'xyz'
        self.assertNotIn('request_id', rc.state)
        self.assertEqual(rc.request_id, 'xyz')

    def test_state_dict_can_be_accessed_directly(self):
        rc = RequestContext()
        rc.state['manual'] = 'value'
        self.assertEqual(rc.manual, 'value')


class TestRequestContextLazy(unittest.TestCase):
    """Test lazy evaluation of resources."""

    def test_lazy_evaluation(self):
        rc = RequestContext()
        rc.lazy('db', lambda: {'connection': 'active'})
        result = rc.db
        self.assertEqual(result, {'connection': 'active'})

    def test_lazy_factory_called_on_access(self):
        call_count = [0]

        def factory():
            call_count[0] += 1
            return 'computed'

        rc = RequestContext()
        rc.lazy('resource', factory)
        self.assertEqual(call_count[0], 0)  # Not called yet
        _ = rc.resource
        self.assertEqual(call_count[0], 1)  # Called on first access

    def test_lazy_is_cached(self):
        call_count = [0]

        def factory():
            call_count[0] += 1
            return 'expensive_result'

        rc = RequestContext()
        rc.lazy('cached_val', factory)

        first = rc.cached_val
        second = rc.cached_val
        third = rc.cached_val

        self.assertEqual(first, 'expensive_result')
        self.assertEqual(second, 'expensive_result')
        self.assertEqual(third, 'expensive_result')
        self.assertEqual(call_count[0], 1)  # Factory called only once

    def test_lazy_result_stored_in_state(self):
        rc = RequestContext()
        rc.lazy('computed', lambda: 99)
        _ = rc.computed
        self.assertIn('computed', rc.state)
        self.assertEqual(rc.state['computed'], 99)

    def test_multiple_lazy_resources(self):
        rc = RequestContext()
        rc.lazy('a', lambda: 'alpha')
        rc.lazy('b', lambda: 'beta')
        self.assertEqual(rc.a, 'alpha')
        self.assertEqual(rc.b, 'beta')

    def test_lazy_overridden_by_direct_set(self):
        rc = RequestContext()
        rc.lazy('val', lambda: 'lazy_value')
        rc.val = 'direct_value'
        self.assertEqual(rc.val, 'direct_value')


class TestRequestContextMissingAttribute(unittest.TestCase):
    """Test that accessing undefined attributes raises AttributeError."""

    def test_missing_attribute_raises_error(self):
        rc = RequestContext()
        with self.assertRaises(AttributeError) as cm:
            _ = rc.nonexistent
        self.assertIn('nonexistent', str(cm.exception))

    def test_missing_attribute_error_message(self):
        rc = RequestContext()
        with self.assertRaises(AttributeError) as cm:
            _ = rc.does_not_exist
        self.assertIn("RequestContext has no attribute 'does_not_exist'",
                       str(cm.exception))

    def test_missing_attribute_after_other_attrs_set(self):
        rc = RequestContext()
        rc.existing = 'yes'
        with self.assertRaises(AttributeError):
            _ = rc.missing


class TestCtxDuringRequestProcessing(unittest.TestCase):
    """Test that the global ctx is properly bound during request processing."""

    def test_ctx_request_is_set(self):
        app = Lcore()
        results = {}

        @app.route('/test')
        def handler():
            results['request'] = ctx.request
            return 'ok'

        status, _, body = run_request(app, 'GET', '/test')
        self.assertEqual(status, '200 OK')
        self.assertIsNotNone(results['request'])

    def test_ctx_response_is_set(self):
        app = Lcore()
        results = {}

        @app.route('/test')
        def handler():
            results['response'] = ctx.response
            return 'ok'

        status, _, body = run_request(app, 'GET', '/test')
        self.assertEqual(status, '200 OK')
        self.assertIsNotNone(results['response'])

    def test_ctx_app_is_set(self):
        app = Lcore()
        results = {}

        @app.route('/test')
        def handler():
            results['app'] = ctx.app
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertIs(results['app'], app)

    def test_ctx_route_is_set(self):
        app = Lcore()
        results = {}

        @app.route('/test')
        def handler():
            results['route'] = ctx.route
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertIsNotNone(results['route'])
        self.assertEqual(results['route'].rule, '/test')

    def test_ctx_route_has_correct_method(self):
        app = Lcore()
        results = {}

        @app.route('/endpoint', method='POST')
        def handler():
            results['route'] = ctx.route
            return 'ok'

        run_request(app, 'POST', '/endpoint')
        self.assertEqual(results['route'].method, 'POST')

    def test_ctx_request_path(self):
        app = Lcore()
        results = {}

        @app.route('/hello')
        def handler():
            results['path'] = ctx.request.path
            return 'ok'

        run_request(app, 'GET', '/hello')
        self.assertEqual(results['path'], '/hello')

    def test_ctx_request_method(self):
        app = Lcore()
        results = {}

        @app.route('/data', method='PUT')
        def handler():
            results['method'] = ctx.request.method
            return 'ok'

        run_request(app, 'PUT', '/data')
        self.assertEqual(results['method'], 'PUT')

    def test_ctx_state_during_request(self):
        app = Lcore()
        results = {}

        @app.hook('before_request')
        def before():
            ctx.custom_data = 'from_hook'

        @app.route('/test')
        def handler():
            results['custom'] = ctx.custom_data
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertEqual(results['custom'], 'from_hook')

    def test_ctx_lazy_during_request(self):
        app = Lcore()
        results = {}

        @app.hook('before_request')
        def before():
            ctx.lazy('db', lambda: 'db_connection')

        @app.route('/test')
        def handler():
            results['db'] = ctx.db
            return 'ok'

        run_request(app, 'GET', '/test')
        self.assertEqual(results['db'], 'db_connection')

    def test_ctx_isolated_between_requests(self):
        app = Lcore()
        results_first = {}
        results_second = {}

        @app.route('/first')
        def first_handler():
            ctx.marker = 'first_request'
            results_first['marker'] = ctx.marker
            return 'ok'

        @app.route('/second')
        def second_handler():
            results_second['has_marker'] = 'marker' in ctx.state
            return 'ok'

        run_request(app, 'GET', '/first')
        run_request(app, 'GET', '/second')

        self.assertEqual(results_first['marker'], 'first_request')
        self.assertFalse(results_second['has_marker'])


if __name__ == '__main__':
    unittest.main()
