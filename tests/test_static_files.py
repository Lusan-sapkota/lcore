"""Tests for Lcore static file serving."""

import unittest
import os
import tempfile

from helpers import run_request

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, static_file


class TestStaticFile(unittest.TestCase):
    def setUp(self):
        self.app = Lcore()
        self.tmpdir = tempfile.mkdtemp()
        # Create test files
        with open(os.path.join(self.tmpdir, 'hello.txt'), 'w') as f:
            f.write('Hello from static file!')
        with open(os.path.join(self.tmpdir, 'data.json'), 'w') as f:
            f.write('{"key": "value"}')
        with open(os.path.join(self.tmpdir, 'style.css'), 'w') as f:
            f.write('body { color: red; }')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_serve_text_file(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        status, headers, body = run_request(self.app, 'GET', '/static/hello.txt')
        self.assertIn('200', status)
        self.assertEqual(body, b'Hello from static file!')
        self.assertIn('text/plain', headers.get('Content-Type', ''))

    def test_serve_json_file(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        _, headers, body = run_request(self.app, 'GET', '/static/data.json')
        self.assertIn(b'"key"', body)
        self.assertIn('json', headers.get('Content-Type', ''))

    def test_serve_css_file(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        _, headers, body = run_request(self.app, 'GET', '/static/style.css')
        self.assertIn(b'body', body)
        self.assertIn('css', headers.get('Content-Type', ''))

    def test_missing_file_404(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        status, _, _ = run_request(self.app, 'GET', '/static/nonexistent.txt')
        self.assertIn('404', status)

    def test_path_traversal_blocked(self):
        @self.app.route('/static/<filepath:path>')
        def serve(filepath):
            return static_file(filepath, root=self.tmpdir)

        status, _, _ = run_request(self.app, 'GET', '/static/../../../etc/passwd')
        self.assertIn('40', status)

    def test_download_disposition(self):
        @self.app.route('/download/<filename>')
        def download(filename):
            return static_file(filename, root=self.tmpdir, download=True)

        _, headers, _ = run_request(self.app, 'GET', '/download/hello.txt')
        disposition = headers.get('Content-Disposition', '')
        self.assertIn('attachment', disposition)

    def test_custom_download_name(self):
        @self.app.route('/download/<filename>')
        def download(filename):
            return static_file(filename, root=self.tmpdir, download='renamed.txt')

        _, headers, _ = run_request(self.app, 'GET', '/download/hello.txt')
        disposition = headers.get('Content-Disposition', '')
        self.assertIn('renamed.txt', disposition)

    def test_etag_header(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        _, headers, _ = run_request(self.app, 'GET', '/static/hello.txt')
        has_etag = any(k.lower() == 'etag' for k in headers)
        self.assertTrue(has_etag, 'ETag header not found')

    def test_last_modified_header(self):
        @self.app.route('/static/<filename>')
        def serve(filename):
            return static_file(filename, root=self.tmpdir)

        _, headers, _ = run_request(self.app, 'GET', '/static/hello.txt')
        self.assertIn('Last-Modified', headers)


if __name__ == '__main__':
    unittest.main()
