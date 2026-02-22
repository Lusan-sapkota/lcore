"""Tests for Lcore hooks/middleware system."""

import unittest

from helpers import run_request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, request, response


class TestBeforeRequestHook(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_before_request_runs(self):
        called = []

        @self.app.hook('before_request')
        def before():
            called.append(True)

        @self.app.route('/test')
        def test():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(len(called), 1)

    def test_before_request_modifies_response(self):
        @self.app.hook('before_request')
        def before():
            response.set_header('X-Before', 'yes')

        @self.app.route('/test')
        def test():
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/test')
        self.assertEqual(headers.get('X-Before'), 'yes')


class TestAfterRequestHook(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_after_request_runs(self):
        called = []

        @self.app.hook('after_request')
        def after():
            called.append(True)

        @self.app.route('/test')
        def test():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(len(called), 1)

    def test_after_request_adds_header(self):
        @self.app.hook('after_request')
        def after():
            response.set_header('X-After', 'done')

        @self.app.route('/test')
        def test():
            return 'ok'

        _, headers, _ = run_request(self.app, 'GET', '/test')
        self.assertEqual(headers.get('X-After'), 'done')


class TestMultipleHooks(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()

    def test_multiple_before_hooks(self):
        order = []

        @self.app.hook('before_request')
        def first():
            order.append('first')

        @self.app.hook('before_request')
        def second():
            order.append('second')

        @self.app.route('/test')
        def test():
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(order, ['first', 'second'])

    def test_before_and_after_order(self):
        order = []

        @self.app.hook('before_request')
        def before():
            order.append('before')

        @self.app.hook('after_request')
        def after():
            order.append('after')

        @self.app.route('/test')
        def test():
            order.append('handler')
            return 'ok'

        run_request(self.app, 'GET', '/test')
        self.assertEqual(order, ['before', 'handler', 'after'])


if __name__ == '__main__':
    unittest.main()
