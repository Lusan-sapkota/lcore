"""Tests for Lcore async support."""

import unittest
import json
import asyncio

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import Lcore, HTTPError, response


class TestAsyncRouteHandler(unittest.TestCase):
    """Test that async route handlers return correct responses."""

    def setUp(self):
        self.app = Lcore()

    def test_async_route_returns_string(self):
        @self.app.route('/async')
        async def async_handler():
            return 'hello async'

        status, _, body = run_request(self.app, 'GET', '/async')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'hello async')

    def test_async_route_returns_bytes(self):
        @self.app.route('/bytes')
        async def async_bytes():
            return b'raw bytes'

        status, _, body = run_request(self.app, 'GET', '/bytes')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'raw bytes')

    def test_async_route_returns_empty_string(self):
        @self.app.route('/empty')
        async def async_empty():
            return ''

        status, headers, body = run_request(self.app, 'GET', '/empty')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'')

    def test_async_route_get_method(self):
        @self.app.route('/data', method='GET')
        async def get_data():
            return 'got data'

        status, _, body = run_request(self.app, 'GET', '/data')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'got data')

    def test_async_route_post_method(self):
        @self.app.route('/submit', method='POST')
        async def post_data():
            return 'submitted'

        status, _, body = run_request(self.app, 'POST', '/submit')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'submitted')


class TestMixedSyncAndAsyncRoutes(unittest.TestCase):
    """Test that sync and async routes coexist and work together."""

    def setUp(self):
        self.app = Lcore()

    def test_sync_and_async_side_by_side(self):
        @self.app.route('/sync')
        def sync_handler():
            return 'sync response'

        @self.app.route('/async')
        async def async_handler():
            return 'async response'

        _, _, sync_body = run_request(self.app, 'GET', '/sync')
        _, _, async_body = run_request(self.app, 'GET', '/async')

        self.assertEqual(sync_body, b'sync response')
        self.assertEqual(async_body, b'async response')

    def test_multiple_async_routes(self):
        @self.app.route('/one')
        async def one():
            return 'first'

        @self.app.route('/two')
        async def two():
            return 'second'

        @self.app.route('/three')
        def three():
            return 'third'

        _, _, body1 = run_request(self.app, 'GET', '/one')
        _, _, body2 = run_request(self.app, 'GET', '/two')
        _, _, body3 = run_request(self.app, 'GET', '/three')

        self.assertEqual(body1, b'first')
        self.assertEqual(body2, b'second')
        self.assertEqual(body3, b'third')

    def test_async_and_sync_same_http_method(self):
        @self.app.route('/api/sync', method='POST')
        def sync_post():
            return 'sync post'

        @self.app.route('/api/async', method='POST')
        async def async_post():
            return 'async post'

        _, _, sync_body = run_request(self.app, 'POST', '/api/sync')
        _, _, async_body = run_request(self.app, 'POST', '/api/async')

        self.assertEqual(sync_body, b'sync post')
        self.assertEqual(async_body, b'async post')

    def test_interleaved_sync_async_requests(self):
        @self.app.route('/sync')
        def sync_handler():
            return 'sync'

        @self.app.route('/async')
        async def async_handler():
            return 'async'

        # Call them in alternating order to ensure no state leakage
        _, _, b1 = run_request(self.app, 'GET', '/async')
        _, _, b2 = run_request(self.app, 'GET', '/sync')
        _, _, b3 = run_request(self.app, 'GET', '/async')
        _, _, b4 = run_request(self.app, 'GET', '/sync')

        self.assertEqual(b1, b'async')
        self.assertEqual(b2, b'sync')
        self.assertEqual(b3, b'async')
        self.assertEqual(b4, b'sync')


class TestAsyncRouteWithParameters(unittest.TestCase):
    """Test async routes with URL parameters."""

    def setUp(self):
        self.app = Lcore()

    def test_async_route_string_param(self):
        @self.app.route('/user/<name>')
        async def user(name):
            return f'Hello {name}'

        _, _, body = run_request(self.app, 'GET', '/user/lusan')
        self.assertEqual(body, b'Hello lusan')

    def test_async_route_int_param(self):
        @self.app.route('/item/<id:int>')
        async def item(id):
            return f'Item {id} type {type(id).__name__}'

        _, _, body = run_request(self.app, 'GET', '/item/42')
        self.assertEqual(body, b'Item 42 type int')

    def test_async_route_multiple_params(self):
        @self.app.route('/api/<version>/<resource>/<id:int>')
        async def api(version, resource, id):
            return f'{version}/{resource}/{id}'

        _, _, body = run_request(self.app, 'GET', '/api/v2/items/99')
        self.assertEqual(body, b'v2/items/99')

    def test_async_route_param_used_in_logic(self):
        @self.app.route('/greet/<name>')
        async def greet(name):
            if name == 'admin':
                return 'Welcome back, admin!'
            return f'Hello, {name}!'

        _, _, body_admin = run_request(self.app, 'GET', '/greet/admin')
        _, _, body_user = run_request(self.app, 'GET', '/greet/visitor')

        self.assertEqual(body_admin, b'Welcome back, admin!')
        self.assertEqual(body_user, b'Hello, visitor!')


class TestAsyncRouteHTTPError(unittest.TestCase):
    """Test async routes that raise HTTPError.

    When using skip=['json'] the async wrapper is applied directly by
    _make_callback, so HTTPError raised inside async handlers is properly
    caught by the framework's HTTPResponse handler in _handle.
    """

    def setUp(self):
        self.app = Lcore()

    def test_async_route_raises_404(self):
        @self.app.route('/find/<name>', skip=['json'])
        async def find(name):
            if name == 'missing':
                raise HTTPError(404, 'Not found')
            return f'Found {name}'

        status, _, _ = run_request(self.app, 'GET', '/find/missing')
        self.assertIn('404', status)

        status, _, body = run_request(self.app, 'GET', '/find/something')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'Found something')

    def test_async_route_raises_403(self):
        @self.app.route('/secret', skip=['json'])
        async def secret():
            raise HTTPError(403, 'Forbidden')

        status, _, _ = run_request(self.app, 'GET', '/secret')
        self.assertIn('403', status)

    def test_async_route_raises_500(self):
        @self.app.route('/crash', skip=['json'])
        async def crash():
            raise HTTPError(500, 'Internal Server Error')

        status, _, _ = run_request(self.app, 'GET', '/crash')
        self.assertIn('500', status)

    def test_async_route_unhandled_exception_becomes_500(self):
        @self.app.route('/bug')
        async def bug():
            raise ValueError('unexpected error')

        status, _, _ = run_request(self.app, 'GET', '/bug')
        self.assertIn('500', status)

    def test_async_route_conditional_error(self):
        @self.app.route('/check/<value>', skip=['json'])
        async def check(value):
            if value == 'bad':
                raise HTTPError(400, 'Bad request')
            return f'ok: {value}'

        status_bad, _, _ = run_request(self.app, 'GET', '/check/bad')
        self.assertIn('400', status_bad)

        status_ok, _, body_ok = run_request(self.app, 'GET', '/check/good')
        self.assertEqual(status_ok, '200 OK')
        self.assertEqual(body_ok, b'ok: good')


class TestAsyncRouteReturnsDict(unittest.TestCase):
    """Test async routes returning JSON responses.

    Async handlers produce JSON by serializing the dict manually and
    setting the content type, which is the recommended pattern for async
    routes in Lcore.
    """

    def setUp(self):
        self.app = Lcore()

    def test_async_route_returns_simple_json(self):
        @self.app.route('/api/status')
        async def api_status():
            response.content_type = 'application/json'
            return json.dumps({'status': 'ok', 'count': 42})

        _, headers, body = run_request(self.app, 'GET', '/api/status')
        data = json.loads(body)
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['count'], 42)
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_async_route_returns_nested_json(self):
        @self.app.route('/api/user')
        async def api_user():
            response.content_type = 'application/json'
            return json.dumps({
                'user': {'name': 'lusan', 'role': 'admin'},
                'active': True
            })

        _, headers, body = run_request(self.app, 'GET', '/api/user')
        data = json.loads(body)
        self.assertEqual(data['user']['name'], 'lusan')
        self.assertEqual(data['user']['role'], 'admin')
        self.assertTrue(data['active'])
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_async_route_returns_json_with_list(self):
        @self.app.route('/api/items')
        async def api_items():
            response.content_type = 'application/json'
            return json.dumps({'items': ['a', 'b', 'c'], 'total': 3})

        _, headers, body = run_request(self.app, 'GET', '/api/items')
        data = json.loads(body)
        self.assertEqual(data['items'], ['a', 'b', 'c'])
        self.assertEqual(data['total'], 3)
        self.assertIn('application/json', headers.get('Content-Type', ''))

    def test_sync_dict_auto_json_vs_async_manual_json(self):
        @self.app.route('/sync/data')
        def sync_data():
            return {'source': 'sync'}

        @self.app.route('/async/data')
        async def async_data():
            response.content_type = 'application/json'
            return json.dumps({'source': 'async'})

        _, sync_headers, sync_body = run_request(self.app, 'GET', '/sync/data')
        _, async_headers, async_body = run_request(self.app, 'GET', '/async/data')

        sync_parsed = json.loads(sync_body)
        async_parsed = json.loads(async_body)

        self.assertEqual(sync_parsed['source'], 'sync')
        self.assertEqual(async_parsed['source'], 'async')
        self.assertIn('application/json', sync_headers.get('Content-Type', ''))
        self.assertIn('application/json', async_headers.get('Content-Type', ''))


class TestAsyncRouteWithBeforeRequestHook(unittest.TestCase):
    """Test async routes with before_request and after_request hooks."""

    def setUp(self):
        self.app = Lcore()

    def test_before_request_runs_before_async_handler(self):
        order = []

        @self.app.hook('before_request')
        def before():
            order.append('before')

        @self.app.route('/test')
        async def handler():
            order.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertIn('before', order)
        self.assertIn('handler', order)
        self.assertTrue(order.index('before') < order.index('handler'))

    def test_before_request_sets_header_for_async_handler(self):
        @self.app.hook('before_request')
        def before():
            response.set_header('X-Before', 'yes')

        @self.app.route('/test')
        async def handler():
            return 'ok'

        _, headers, body = run_request(self.app, 'GET', '/test')
        self.assertEqual(headers.get('X-Before'), 'yes')
        self.assertEqual(body, b'ok')

    def test_multiple_before_hooks_with_async_handler(self):
        order = []

        @self.app.hook('before_request')
        def first():
            order.append('first')

        @self.app.hook('before_request')
        def second():
            order.append('second')

        @self.app.route('/test')
        async def handler():
            order.append('handler')
            return 'done'

        run_request(self.app, 'GET', '/test')
        self.assertIn('first', order)
        self.assertIn('second', order)
        self.assertIn('handler', order)
        # before_request hooks always run before the handler
        self.assertTrue(order.index('first') < order.index('handler'))
        self.assertTrue(order.index('second') < order.index('handler'))
        # before_request hooks run in registration order
        self.assertTrue(order.index('first') < order.index('second'))

    def test_hook_ordering_with_skip(self):
        """With skip=['json'], the async wrapper is applied directly so the
        handler runs synchronously within _handle and hook ordering is
        guaranteed: before_request -> handler -> after_request."""
        order = []

        @self.app.hook('before_request')
        def first():
            order.append('first')

        @self.app.hook('before_request')
        def second():
            order.append('second')

        @self.app.hook('after_request')
        def after():
            order.append('after')

        @self.app.route('/test', skip=['json'])
        async def handler():
            order.append('handler')
            return 'done'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(order, ['first', 'second', 'handler', 'after'])

    def test_before_request_hook_with_async_param_route(self):
        called_with = {}

        @self.app.hook('before_request')
        def before():
            called_with['hook'] = True

        @self.app.route('/user/<name>')
        async def user(name):
            return f'Hello {name}'

        _, _, body = run_request(self.app, 'GET', '/user/lusan')
        self.assertTrue(called_with.get('hook'))
        self.assertEqual(body, b'Hello lusan')

    def test_after_request_adds_header_to_async_response(self):
        @self.app.hook('after_request')
        def after():
            response.set_header('X-After', 'done')

        @self.app.route('/test')
        async def handler():
            return 'async result'

        _, headers, body = run_request(self.app, 'GET', '/test')
        self.assertEqual(headers.get('X-After'), 'done')
        self.assertEqual(body, b'async result')


class TestAsyncRouteWithAwait(unittest.TestCase):
    """Test that async handlers can use await internally."""

    def setUp(self):
        self.app = Lcore()

    def test_async_handler_with_await(self):
        async def fetch_data():
            await asyncio.sleep(0)
            return 'fetched'

        @self.app.route('/data')
        async def handler():
            result = await fetch_data()
            return result

        status, _, body = run_request(self.app, 'GET', '/data')
        self.assertEqual(status, '200 OK')
        self.assertEqual(body, b'fetched')

    def test_async_handler_with_multiple_awaits(self):
        async def step_one():
            await asyncio.sleep(0)
            return 'one'

        async def step_two():
            await asyncio.sleep(0)
            return 'two'

        @self.app.route('/multi')
        async def handler():
            a = await step_one()
            b = await step_two()
            return f'{a}-{b}'

        _, _, body = run_request(self.app, 'GET', '/multi')
        self.assertEqual(body, b'one-two')

    def test_async_handler_awaits_computation(self):
        async def compute(x, y):
            await asyncio.sleep(0)
            return x + y

        @self.app.route('/compute/<a:int>/<b:int>')
        async def handler(a, b):
            result = await compute(a, b)
            return f'result={result}'

        _, _, body = run_request(self.app, 'GET', '/compute/10/25')
        self.assertEqual(body, b'result=35')

    def test_async_handler_with_gather(self):
        async def task_a():
            await asyncio.sleep(0)
            return 'A'

        async def task_b():
            await asyncio.sleep(0)
            return 'B'

        @self.app.route('/gather')
        async def handler():
            results = await asyncio.gather(task_a(), task_b())
            return ','.join(results)

        _, _, body = run_request(self.app, 'GET', '/gather')
        self.assertEqual(body, b'A,B')


if __name__ == '__main__':
    unittest.main()
