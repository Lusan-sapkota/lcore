"""Tests for Lcore middleware engine."""

import unittest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import Lcore, Middleware, MiddlewarePipeline, ctx


# ---------------------------------------------------------------------------
# Reusable test middleware classes
# ---------------------------------------------------------------------------

class LogMiddleware(Middleware):
    """Tracks pre/post processing calls."""
    order = 10

    def __init__(self):
        self.calls = []

    def __call__(self, ctx, next_handler):
        self.calls.append('before')
        result = next_handler(ctx)
        self.calls.append('after')
        return result


class HeaderMiddleware(Middleware):
    """Adds a custom response header after the handler runs."""
    order = 20

    def __call__(self, ctx, next_handler):
        result = next_handler(ctx)
        ctx.response.set_header('X-Middleware', 'applied')
        return result


class ShortCircuitMiddleware(Middleware):
    """Returns a response without calling next_handler."""
    order = 5

    def __call__(self, ctx, next_handler):
        ctx.response.status = 403
        return 'Forbidden by middleware'


class OrderTracker(Middleware):
    """Records execution order into a shared list."""

    def __init__(self, label, tracker):
        self.label = label
        self.tracker = tracker

    def __call__(self, ctx, next_handler):
        self.tracker.append(f'{self.label}:before')
        result = next_handler(ctx)
        self.tracker.append(f'{self.label}:after')
        return result


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestBasicMiddlewareExecution(unittest.TestCase):
    """Middleware runs its pre- and post-processing around the handler."""

    def setUp(self):
        self.app = Lcore()

    def test_middleware_calls_before_and_after(self):
        mw = LogMiddleware()
        self.app.use(mw)

        @self.app.route('/test')
        def handler():
            return 'ok'

        status, _, body = run_request(self.app, 'GET', '/test')
        self.assertIn('200', status)
        self.assertEqual(mw.calls, ['before', 'after'])

    def test_middleware_receives_ctx(self):
        """The first argument passed to __call__ is a RequestContext."""
        received = {}

        class InspectMiddleware(Middleware):
            def __call__(self, ctx, next_handler):
                received['has_request'] = hasattr(ctx, 'request')
                received['has_response'] = hasattr(ctx, 'response')
                return next_handler(ctx)

        self.app.use(InspectMiddleware())

        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertTrue(received['has_request'])
        self.assertTrue(received['has_response'])


class TestMiddlewareOrdering(unittest.TestCase):
    """Lower order values execute first (outermost in the chain)."""

    def setUp(self):
        self.app = Lcore()
        self.tracker = []

    def test_lower_order_runs_first(self):
        mw_a = OrderTracker('A', self.tracker)
        mw_a.order = 10
        mw_b = OrderTracker('B', self.tracker)
        mw_b.order = 20

        self.app.use(mw_b)
        self.app.use(mw_a)

        @self.app.route('/test')
        def handler():
            self.tracker.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(self.tracker, [
            'A:before', 'B:before', 'handler', 'B:after', 'A:after'
        ])

    def test_same_order_preserves_insertion(self):
        """Middleware with the same order should run in their insertion order."""
        mw_x = OrderTracker('X', self.tracker)
        mw_x.order = 50
        mw_y = OrderTracker('Y', self.tracker)
        mw_y.order = 50

        self.app.use(mw_x)
        self.app.use(mw_y)

        @self.app.route('/test')
        def handler():
            self.tracker.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(self.tracker, [
            'X:before', 'Y:before', 'handler', 'Y:after', 'X:after'
        ])

    def test_order_override_via_use(self):
        """The order parameter in app.use() overrides the class-level order."""
        mw_first = OrderTracker('First', self.tracker)
        mw_first.order = 100  # High order by default
        mw_second = OrderTracker('Second', self.tracker)
        mw_second.order = 1  # Low order by default

        self.app.use(mw_first, order=1)   # Override to low
        self.app.use(mw_second, order=99)  # Override to high

        @self.app.route('/test')
        def handler():
            self.tracker.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(self.tracker, [
            'First:before', 'Second:before', 'handler',
            'Second:after', 'First:after'
        ])


class TestMiddlewareModifiesResponse(unittest.TestCase):
    """Middleware can modify the response (headers, status, body)."""

    def setUp(self):
        self.app = Lcore()

    def test_middleware_adds_response_header(self):
        self.app.use(HeaderMiddleware())

        @self.app.route('/test')
        def handler():
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/test')
        self.assertEqual(headers.get('X-Middleware'), 'applied')

    def test_middleware_modifies_body(self):
        class BodyWrapMiddleware(Middleware):
            def __call__(self, ctx, next_handler):
                result = next_handler(ctx)
                return '[wrapped]' + (result or '')

        self.app.use(BodyWrapMiddleware())

        @self.app.route('/test')
        def handler():
            return 'content'

        _, _, body = run_request(self.app, 'GET', '/test')
        self.assertIn(b'[wrapped]content', body)

    def test_middleware_sets_state_for_handler(self):
        """Middleware can attach data to ctx.state for downstream use."""

        class StateMiddleware(Middleware):
            order = 1

            def __call__(self, ctx, next_handler):
                ctx.state['role'] = 'admin'
                return next_handler(ctx)

        self.app.use(StateMiddleware())

        captured = {}

        @self.app.route('/test')
        def handler():
            captured['role'] = ctx.state.get('role')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(captured['role'], 'admin')


class TestMiddlewareShortCircuit(unittest.TestCase):
    """Middleware can short-circuit the pipeline by not calling next_handler."""

    def setUp(self):
        self.app = Lcore()

    def test_short_circuit_prevents_handler(self):
        handler_called = []

        self.app.use(ShortCircuitMiddleware())

        @self.app.route('/test')
        def handler():
            handler_called.append(True)
            return 'ok'

        _, _, body = run_request(self.app, 'GET', '/test')
        self.assertFalse(handler_called)
        self.assertIn(b'Forbidden by middleware', body)

    def test_short_circuit_prevents_later_middleware(self):
        tracker = []

        class EarlyExit(Middleware):
            order = 1
            def __call__(self, ctx, next_handler):
                tracker.append('early')
                return 'blocked'

        class NeverReached(Middleware):
            order = 10
            def __call__(self, ctx, next_handler):
                tracker.append('never')
                return next_handler(ctx)

        self.app.use(EarlyExit())
        self.app.use(NeverReached())

        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(tracker, ['early'])


class TestMultipleMiddlewareChain(unittest.TestCase):
    """Multiple middleware chain correctly in LIFO (onion) order."""

    def setUp(self):
        self.app = Lcore()
        self.tracker = []

    def test_three_middleware_chain(self):
        mw_a = OrderTracker('A', self.tracker)
        mw_a.order = 10
        mw_b = OrderTracker('B', self.tracker)
        mw_b.order = 20
        mw_c = OrderTracker('C', self.tracker)
        mw_c.order = 30

        self.app.use(mw_c)
        self.app.use(mw_a)
        self.app.use(mw_b)

        @self.app.route('/test')
        def handler():
            self.tracker.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(self.tracker, [
            'A:before', 'B:before', 'C:before',
            'handler',
            'C:after', 'B:after', 'A:after',
        ])

    def test_each_middleware_sees_result_of_inner(self):
        results = []

        class Wrap(Middleware):
            def __init__(self, tag, order_val, results_list):
                self.tag = tag
                self.order = order_val
                self.results_list = results_list

            def __call__(self, ctx, next_handler):
                result = next_handler(ctx)
                self.results_list.append((self.tag, result))
                return f'<{self.tag}>{result}</{self.tag}>'

        self.app.use(Wrap('outer', 10, results))
        self.app.use(Wrap('inner', 20, results))

        @self.app.route('/test')
        def handler():
            return 'core'

        _, _, body = run_request(self.app, 'GET', '/test')
        # inner wraps first, then outer wraps inner's result
        self.assertEqual(results[0], ('inner', 'core'))
        self.assertEqual(results[1][0], 'outer')
        self.assertIn(b'<outer><inner>core</inner></outer>', body)


class TestRouteSpecificMiddleware(unittest.TestCase):
    """Middleware can be restricted to matching routes via a regex pattern."""

    def setUp(self):
        self.app = Lcore()

    def test_middleware_applies_to_matching_route(self):
        tracker = []

        class ApiMiddleware(Middleware):
            def __call__(self, ctx, next_handler):
                tracker.append('api_mw')
                return next_handler(ctx)

        self.app.use(ApiMiddleware(), routes=r'^/api/')

        @self.app.route('/api/data')
        def api_handler():
            return 'api data'

        @self.app.route('/web/page')
        def web_handler():
            return 'web page'

        # Request to /api/data should trigger the middleware
        run_request(self.app, 'GET', '/api/data')
        self.assertEqual(tracker, ['api_mw'])

        # Request to /web/page should NOT trigger the middleware
        tracker.clear()
        run_request(self.app, 'GET', '/web/page')
        self.assertEqual(tracker, [])

    def test_global_and_route_middleware_combine(self):
        tracker = []

        class GlobalMW(Middleware):
            order = 1
            def __call__(self, ctx, next_handler):
                tracker.append('global')
                return next_handler(ctx)

        class AdminMW(Middleware):
            order = 10
            def __call__(self, ctx, next_handler):
                tracker.append('admin')
                return next_handler(ctx)

        self.app.use(GlobalMW())                       # All routes
        self.app.use(AdminMW(), routes=r'^/admin/')     # Only /admin/*

        @self.app.route('/admin/dashboard')
        def admin():
            return 'admin'

        @self.app.route('/public')
        def public():
            return 'public'

        run_request(self.app, 'GET', '/admin/dashboard')
        self.assertEqual(tracker, ['global', 'admin'])

        tracker.clear()
        run_request(self.app, 'GET', '/public')
        self.assertEqual(tracker, ['global'])


class TestMiddlewareRemoval(unittest.TestCase):
    """Middleware can be removed from the pipeline."""

    def setUp(self):
        self.app = Lcore()

    def test_remove_middleware_from_pipeline(self):
        tracker = []

        class TrackerMW(Middleware):
            def __call__(self, ctx, next_handler):
                tracker.append('mw')
                return next_handler(ctx)

        mw = TrackerMW()
        self.app.use(mw)

        @self.app.route('/test')
        def handler():
            return 'ok'

        # Middleware is active
        run_request(self.app, 'GET', '/test')
        self.assertEqual(tracker, ['mw'])

        # Remove middleware
        self.app.middleware.remove(mw)
        tracker.clear()

        run_request(self.app, 'GET', '/test')
        self.assertEqual(tracker, [])

    def test_remove_one_of_many(self):
        tracker = []

        class MwA(Middleware):
            order = 10
            def __call__(self, ctx, next_handler):
                tracker.append('A')
                return next_handler(ctx)

        class MwB(Middleware):
            order = 20
            def __call__(self, ctx, next_handler):
                tracker.append('B')
                return next_handler(ctx)

        mw_a = MwA()
        mw_b = MwB()
        self.app.use(mw_a)
        self.app.use(mw_b)

        @self.app.route('/test')
        def handler():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(tracker, ['A', 'B'])

        # Remove only A
        self.app.middleware.remove(mw_a)
        tracker.clear()

        run_request(self.app, 'GET', '/test')
        self.assertEqual(tracker, ['B'])


class TestAppUseRegistration(unittest.TestCase):
    """app.use() correctly registers middleware onto the pipeline."""

    def setUp(self):
        self.app = Lcore()

    def test_use_returns_middleware(self):
        mw = LogMiddleware()
        result = self.app.use(mw)
        self.assertIs(result, mw)

    def test_use_adds_to_pipeline(self):
        mw = LogMiddleware()
        self.app.use(mw)
        # The internal list should contain the registered middleware
        registered = [m for m, _ in self.app.middleware._middleware]
        self.assertIn(mw, registered)

    def test_use_with_order(self):
        mw = LogMiddleware()
        self.app.use(mw, order=5)
        self.assertEqual(mw.order, 5)

    def test_use_with_routes(self):
        mw = LogMiddleware()
        self.app.use(mw, routes=r'^/api/')
        # Pattern should be compiled and stored
        _, pattern = self.app.middleware._middleware[-1]
        self.assertIsNotNone(pattern)
        self.assertTrue(pattern.match('/api/test'))
        self.assertFalse(pattern.match('/web/page'))

    def test_use_multiple_middleware(self):
        mw1 = LogMiddleware()
        mw2 = HeaderMiddleware()
        self.app.use(mw1)
        self.app.use(mw2)
        registered = [m for m, _ in self.app.middleware._middleware]
        self.assertIn(mw1, registered)
        self.assertIn(mw2, registered)
        self.assertEqual(len(registered), 2)


class TestMiddlewarePipelineDirectly(unittest.TestCase):
    """Unit tests for MiddlewarePipeline independent of a full app."""

    def test_empty_pipeline_calls_handler(self):
        pipeline = MiddlewarePipeline()
        called = []

        from lcore import RequestContext, request as req, response as resp
        context = RequestContext()

        def handler():
            called.append(True)
            return 'done'

        # We need a request with a path for _get_chain
        from helpers import create_environ
        environ = create_environ('GET', '/test')
        req.bind(environ)
        resp.bind()
        context.request = req
        context.response = resp

        result = pipeline.execute(context, handler)
        self.assertEqual(called, [True])
        self.assertEqual(result, 'done')

    def test_pipeline_add_and_remove(self):
        pipeline = MiddlewarePipeline()
        mw = Middleware()
        pipeline.add(mw)
        self.assertEqual(len(pipeline._middleware), 1)
        pipeline.remove(mw)
        self.assertEqual(len(pipeline._middleware), 0)

    def test_pipeline_sorting(self):
        pipeline = MiddlewarePipeline()

        class Low(Middleware):
            order = 1

        class High(Middleware):
            order = 99

        high = High()
        low = Low()
        pipeline.add(high)
        pipeline.add(low)

        # Trigger sorting via _get_chain
        chain = pipeline._get_chain('/')
        self.assertIs(chain[0], low)
        self.assertIs(chain[1], high)


class TestBaseMiddlewareClass(unittest.TestCase):
    """The base Middleware class provides sensible defaults."""

    def test_default_name_is_none(self):
        mw = Middleware()
        self.assertIsNone(mw.name)

    def test_default_order_is_50(self):
        mw = Middleware()
        self.assertEqual(mw.order, 50)

    def test_default_call_passes_through(self):
        """Base __call__ simply invokes next_handler."""
        mw = Middleware()
        results = []

        def fake_next(c):
            results.append('called')
            return 'pass-through'

        result = mw(None, fake_next)
        self.assertEqual(result, 'pass-through')
        self.assertEqual(results, ['called'])


if __name__ == '__main__':
    unittest.main()
