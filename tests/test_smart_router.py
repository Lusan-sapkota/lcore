"""Tests for Lcore smart router enhancements."""

import unittest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import Lcore


class TestRouteGroup(unittest.TestCase):
    """Tests for app.group() context manager that groups routes under a prefix."""

    def setUp(self):
        self.app = Lcore()

    def test_group_basic_prefix(self):
        """Routes defined inside a group should be accessible under the prefix."""
        with self.app.group('/api/v1') as api:
            @api.route('/users')
            def list_users():
                return 'users list'

            @api.route('/items')
            def list_items():
                return 'items list'

        status, headers, body = run_request(self.app, 'GET', '/api/v1/users')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'users list', body)

        status, headers, body = run_request(self.app, 'GET', '/api/v1/items')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'items list', body)

    def test_group_prefix_not_accessible_without_prefix(self):
        """Routes defined inside a group should NOT be accessible without the prefix."""
        with self.app.group('/api/v1') as api:
            @api.route('/users')
            def list_users():
                return 'users list'

        status, headers, body = run_request(self.app, 'GET', '/users')
        self.assertIn('404', status)

    def test_group_with_nested_paths(self):
        """Routes inside a group can have deeper nested paths."""
        with self.app.group('/api/v1') as api:
            @api.route('/users/active')
            def active_users():
                return 'active users'

            @api.route('/users/inactive')
            def inactive_users():
                return 'inactive users'

        status, headers, body = run_request(self.app, 'GET', '/api/v1/users/active')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'active users', body)

        status, headers, body = run_request(self.app, 'GET', '/api/v1/users/inactive')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'inactive users', body)

    def test_group_with_url_parameters(self):
        """Routes inside a group can use URL parameters."""
        with self.app.group('/api/v1') as api:
            @api.route('/users/<user_id:int>')
            def get_user(user_id):
                return 'user %d' % user_id

        status, headers, body = run_request(self.app, 'GET', '/api/v1/users/42')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'user 42', body)

    def test_group_route_restored_after_context(self):
        """After the group context exits, app.route should work without prefix."""
        with self.app.group('/api') as api:
            @api.route('/inside')
            def inside():
                return 'inside group'

        @self.app.route('/outside')
        def outside():
            return 'outside group'

        status, headers, body = run_request(self.app, 'GET', '/api/inside')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'inside group', body)

        status, headers, body = run_request(self.app, 'GET', '/outside')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'outside group', body)

        # /api/outside should NOT exist
        status, headers, body = run_request(self.app, 'GET', '/api/outside')
        self.assertIn('404', status)


class TestMultipleRouteGroups(unittest.TestCase):
    """Tests for using multiple route groups on the same app."""

    def setUp(self):
        self.app = Lcore()

    def test_multiple_groups_separate(self):
        """Multiple groups should each register routes under their own prefix."""
        with self.app.group('/api/v1') as v1:
            @v1.route('/data')
            def v1_data():
                return 'v1 data'

        with self.app.group('/api/v2') as v2:
            @v2.route('/data')
            def v2_data():
                return 'v2 data'

        status, headers, body = run_request(self.app, 'GET', '/api/v1/data')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'v1 data', body)

        status, headers, body = run_request(self.app, 'GET', '/api/v2/data')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'v2 data', body)

    def test_multiple_groups_no_cross_contamination(self):
        """A route in one group should not be accessible under another group prefix."""
        with self.app.group('/admin') as admin:
            @admin.route('/settings')
            def admin_settings():
                return 'admin settings'

        with self.app.group('/user') as user:
            @user.route('/profile')
            def user_profile():
                return 'user profile'

        # Cross-contamination checks
        status, _, _ = run_request(self.app, 'GET', '/admin/profile')
        self.assertIn('404', status)

        status, _, _ = run_request(self.app, 'GET', '/user/settings')
        self.assertIn('404', status)

    def test_groups_with_regular_routes(self):
        """Groups and regular routes should coexist without interference."""
        @self.app.route('/home')
        def home():
            return 'home page'

        with self.app.group('/api') as api:
            @api.route('/status')
            def api_status():
                return 'api ok'

        @self.app.route('/about')
        def about():
            return 'about page'

        status, _, body = run_request(self.app, 'GET', '/home')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'home page', body)

        status, _, body = run_request(self.app, 'GET', '/api/status')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'api ok', body)

        status, _, body = run_request(self.app, 'GET', '/about')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'about page', body)

    def test_group_trailing_slash_normalization(self):
        """Group prefix with trailing slash should not produce double slashes."""
        with self.app.group('/api/') as api:
            @api.route('/endpoint')
            def endpoint():
                return 'endpoint reached'

        # The group method strips trailing slash from prefix and leading slash
        # from path, so /api/ + /endpoint becomes /api/endpoint
        status, _, body = run_request(self.app, 'GET', '/api/endpoint')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'endpoint reached', body)


class TestCustomRouteFilter(unittest.TestCase):
    """Tests for app.add_route_filter() custom URL parameter filters."""

    def setUp(self):
        self.app = Lcore()

    def test_hex_filter(self):
        """Custom hex filter should convert matched hex string to integer."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        @self.app.route('/color/<code:hex>')
        def color(code):
            return str(code)

        status, headers, body = run_request(self.app, 'GET', '/color/ff')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'255', body)

    def test_hex_filter_uppercase(self):
        """Hex filter should handle uppercase hex values."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        @self.app.route('/color/<code:hex>')
        def color(code):
            return str(code)

        status, headers, body = run_request(self.app, 'GET', '/color/FF')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'255', body)

    def test_hex_filter_rejects_non_hex(self):
        """Hex filter should not match non-hex characters."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        @self.app.route('/color/<code:hex>')
        def color(code):
            return str(code)

        status, _, _ = run_request(self.app, 'GET', '/color/xyz')
        self.assertIn('404', status)

    def test_uuid_filter(self):
        """Custom uuid filter should match UUID strings."""
        self.app.add_route_filter(
            'uuid',
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            None,
            None
        )

        @self.app.route('/resource/<rid:uuid>')
        def get_resource(rid):
            return 'resource %s' % rid

        test_uuid = '550e8400-e29b-41d4-a716-446655440000'
        status, headers, body = run_request(self.app, 'GET', '/resource/' + test_uuid)
        self.assertEqual(status, '200 OK')
        self.assertIn(test_uuid.encode(), body)

    def test_uuid_filter_rejects_invalid(self):
        """UUID filter should not match invalid UUID strings."""
        self.app.add_route_filter(
            'uuid',
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            None,
            None
        )

        @self.app.route('/resource/<rid:uuid>')
        def get_resource(rid):
            return 'resource %s' % rid

        status, _, _ = run_request(self.app, 'GET', '/resource/not-a-uuid')
        self.assertIn('404', status)

    def test_filter_with_to_python_converter(self):
        """Custom filter with to_python should convert the matched string."""
        self.app.add_route_filter(
            'bool',
            r'true|false|1|0',
            lambda x: x in ('true', '1'),
            lambda x: 'true' if x else 'false'
        )

        @self.app.route('/feature/<enabled:bool>')
        def feature(enabled):
            return 'on' if enabled else 'off'

        status, _, body = run_request(self.app, 'GET', '/feature/true')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'on', body)

        status, _, body = run_request(self.app, 'GET', '/feature/false')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'off', body)

        status, _, body = run_request(self.app, 'GET', '/feature/1')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'on', body)

        status, _, body = run_request(self.app, 'GET', '/feature/0')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'off', body)

    def test_filter_with_to_python_type_conversion(self):
        """The to_python converter should produce the correct Python type."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        received_types = []

        @self.app.route('/check/<val:hex>')
        def check(val):
            received_types.append(type(val))
            return str(val)

        run_request(self.app, 'GET', '/check/1a')
        self.assertEqual(len(received_types), 1)
        self.assertIs(received_types[0], int)

    def test_multiple_custom_filters(self):
        """Multiple custom filters can be registered and used in different routes."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )
        self.app.add_route_filter(
            'slug',
            r'[a-z0-9]+(?:-[a-z0-9]+)*',
            None,
            None
        )

        @self.app.route('/color/<code:hex>')
        def color(code):
            return str(code)

        @self.app.route('/article/<title:slug>')
        def article(title):
            return 'article: %s' % title

        status, _, body = run_request(self.app, 'GET', '/color/ab')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'171', body)

        status, _, body = run_request(self.app, 'GET', '/article/my-cool-post')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'article: my-cool-post', body)

    def test_custom_filter_with_multiple_params(self):
        """A route can use multiple custom filter parameters."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        @self.app.route('/rgb/<r:hex>/<g:hex>/<b:hex>')
        def rgb(r, g, b):
            return '%d,%d,%d' % (r, g, b)

        status, _, body = run_request(self.app, 'GET', '/rgb/ff/80/00')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'255,128,0', body)

    def test_custom_filter_mixed_with_builtin(self):
        """Custom filters can be combined with built-in filters in the same route."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        @self.app.route('/item/<item_id:int>/color/<code:hex>')
        def item_color(item_id, code):
            return 'item %d color %d' % (item_id, code)

        status, _, body = run_request(self.app, 'GET', '/item/7/color/ff')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'item 7 color 255', body)


class TestGroupWithFilters(unittest.TestCase):
    """Tests combining route groups with custom filters."""

    def setUp(self):
        self.app = Lcore()

    def test_group_with_custom_filter(self):
        """Custom filters should work inside route groups."""
        self.app.add_route_filter(
            'hex',
            r'[0-9a-fA-F]+',
            lambda x: int(x, 16),
            lambda x: format(x, 'x')
        )

        with self.app.group('/api') as api:
            @api.route('/color/<code:hex>')
            def color(code):
                return str(code)

        status, _, body = run_request(self.app, 'GET', '/api/color/ff')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'255', body)

    def test_group_with_builtin_int_filter(self):
        """Built-in int filter should work inside route groups."""
        with self.app.group('/api/v1') as api:
            @api.route('/users/<uid:int>')
            def get_user(uid):
                return 'user %d' % uid

        status, _, body = run_request(self.app, 'GET', '/api/v1/users/123')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'user 123', body)


class TestGroupHTTPMethods(unittest.TestCase):
    """Tests for route groups with different HTTP methods."""

    def setUp(self):
        self.app = Lcore()

    def test_group_with_method_kwarg(self):
        """Routes inside a group should support the method keyword argument."""
        with self.app.group('/api') as api:
            @api.route('/data', method='POST')
            def create_data():
                return 'created'

        status, _, body = run_request(self.app, 'POST', '/api/data')
        self.assertEqual(status, '200 OK')
        self.assertIn(b'created', body)

        # GET should not match a POST-only route
        status, _, _ = run_request(self.app, 'GET', '/api/data')
        self.assertIn('405', status)


if __name__ == '__main__':
    unittest.main()
