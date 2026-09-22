"""Tests for CompressionMiddleware, especially streamed bodies.

Buffering an iterable body whole meant a 20MB response cost about 40MB of RAM
per concurrent request and defeated streaming entirely. Large bodies now
compress incrementally; small ones still compress whole so they keep their
Content-Length, and the bytes/str path is untouched.
"""

import gzip
import os
import sys
import tracemalloc
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from helpers import run_request
from lcore import Lcore, CompressionMiddleware, response

GZIP = {'Accept-Encoding': 'gzip'}


def build(**options):
    app = Lcore()
    app.use(CompressionMiddleware(**options))
    return app


class TestWholeBodyCompression(unittest.TestCase):
    """The common path: an ordinary str or bytes body."""

    def setUp(self):
        self.app = build()
        self.payload = 'the quick brown fox ' * 100

        @self.app.route('/text')
        def text():
            response.content_type = 'text/plain'
            return self.payload

        @self.app.route('/tiny')
        def tiny():
            response.content_type = 'text/plain'
            return 'small'

    def test_body_is_compressed_with_content_length(self):
        _, headers, body = run_request(self.app, 'GET', '/text', headers=GZIP)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(headers.get('Content-Length'), str(len(body)))
        self.assertEqual(gzip.decompress(body), self.payload.encode())

    def test_vary_header_is_set(self):
        """Caches must not serve a gzipped body to a client that cannot read it."""
        _, headers, _ = run_request(self.app, 'GET', '/text', headers=GZIP)
        self.assertIn('Accept-Encoding', headers.get('Vary', ''))

    def test_small_body_is_left_alone(self):
        _, headers, body = run_request(self.app, 'GET', '/tiny', headers=GZIP)
        self.assertIsNone(headers.get('Content-Encoding'))
        self.assertEqual(body, b'small')

    def test_client_without_gzip_gets_plain_bytes(self):
        _, headers, body = run_request(self.app, 'GET', '/text')
        self.assertIsNone(headers.get('Content-Encoding'))
        self.assertEqual(body, self.payload.encode())


class TestStreamedCompression(unittest.TestCase):
    """Iterable bodies: buffer up to a threshold, then compress incrementally."""

    def _app(self, chunk_count, chunk_size=1000, **options):
        app = build(**options)
        self.pulled = 0

        @app.route('/stream')
        def stream():
            response.content_type = 'text/plain'

            def generate():
                for _ in range(chunk_count):
                    self.pulled += 1
                    yield 'x' * chunk_size

            return generate()

        return app

    def test_small_stream_keeps_content_length(self):
        """Anything inside the buffer behaves exactly as it always did."""
        app = self._app(chunk_count=1, chunk_size=1200)
        _, headers, body = run_request(app, 'GET', '/stream', headers=GZIP)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(headers.get('Content-Length'), str(len(body)))
        self.assertEqual(gzip.decompress(body), b'x' * 1200)

    def test_large_stream_round_trips(self):
        """The incremental output must still be a valid gzip stream."""
        app = self._app(chunk_count=2000, stream_threshold=64 * 1024)
        _, headers, body = run_request(app, 'GET', '/stream', headers=GZIP)
        self.assertEqual(headers.get('Content-Encoding'), 'gzip')
        self.assertEqual(gzip.decompress(body), b'x' * 2_000_000)

    def test_large_stream_drops_content_length(self):
        """The compressed size is unknown up front, so a stale length would lie."""
        app = self._app(chunk_count=2000, stream_threshold=64 * 1024)
        _, headers, _ = run_request(app, 'GET', '/stream', headers=GZIP)
        self.assertIsNone(headers.get('Content-Length'))

    def test_large_stream_does_not_buffer_the_whole_body(self):
        """The point of the change: memory must not track the body size."""
        app = self._app(chunk_count=5000, stream_threshold=64 * 1024)
        tracemalloc.start()
        try:
            _, _, body = run_request(app, 'GET', '/stream', headers=GZIP)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(gzip.decompress(body), b'x' * 5_000_000)
        # 5MB body. Buffering it whole previously peaked at roughly twice that.
        self.assertLess(peak, 2_000_000,
                        'peaked at %.1fMB, body was 5MB' % (peak / 1024 / 1024))

    def test_stream_threshold_is_configurable(self):
        """A body under a raised threshold is buffered and keeps its length."""
        app = self._app(chunk_count=100, stream_threshold=10 * 1024 * 1024)
        _, headers, body = run_request(app, 'GET', '/stream', headers=GZIP)
        self.assertIsNotNone(headers.get('Content-Length'))
        self.assertEqual(gzip.decompress(body), b'x' * 100_000)

    def test_uncompressed_stream_is_untouched(self):
        """No gzip in Accept-Encoding means the generator passes straight through."""
        app = self._app(chunk_count=10)
        _, headers, body = run_request(app, 'GET', '/stream')
        self.assertIsNone(headers.get('Content-Encoding'))
        self.assertEqual(body, b'x' * 10_000)


class TestCompressionSkips(unittest.TestCase):
    """Cases that must never be compressed."""

    def test_already_encoded_body_is_left_alone(self):
        app = build()

        @app.route('/pre')
        def pre():
            response.content_type = 'text/plain'
            response.set_header('Content-Encoding', 'br')
            return 'already encoded ' * 100

        _, headers, _ = run_request(app, 'GET', '/pre', headers=GZIP)
        self.assertEqual(headers.get('Content-Encoding'), 'br')

    def test_non_text_content_type_is_skipped(self):
        app = build()

        @app.route('/img')
        def img():
            response.content_type = 'image/png'
            return b'\x89PNG' + b'\x00' * 1000

        _, headers, _ = run_request(app, 'GET', '/img', headers=GZIP)
        self.assertIsNone(headers.get('Content-Encoding'))


if __name__ == '__main__':
    unittest.main()
