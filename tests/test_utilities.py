"""Tests for Lcore utility functions and classes."""

import unittest
import time

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import (
    tob, touni, makelist, html_escape, html_quote,
    http_date, parse_date, cookie_encode, cookie_decode, cookie_is_encoded,
    MultiDict, FormsDict, HeaderDict, BaseResponse
)


class TestStringHelpers(unittest.TestCase):
    def test_tob_from_string(self):
        self.assertEqual(tob('hello'), b'hello')

    def test_tob_from_none(self):
        self.assertEqual(tob(None), b'')

    def test_tob_from_bytes(self):
        self.assertEqual(tob(b'hello'), b'hello')

    def test_touni_from_bytes(self):
        self.assertEqual(touni(b'hello'), 'hello')

    def test_touni_from_none(self):
        self.assertEqual(touni(None), '')

    def test_touni_from_string(self):
        self.assertEqual(touni('hello'), 'hello')


class TestMakelist(unittest.TestCase):
    def test_from_list(self):
        self.assertEqual(makelist([1, 2]), [1, 2])

    def test_from_tuple(self):
        self.assertEqual(makelist((1, 2)), [1, 2])

    def test_from_single(self):
        self.assertEqual(makelist('hello'), ['hello'])

    def test_from_none(self):
        self.assertEqual(makelist(None), [])

    def test_from_empty(self):
        self.assertEqual(makelist(''), [])


class TestHTMLHelpers(unittest.TestCase):
    def test_html_escape(self):
        self.assertEqual(html_escape('<b>test</b>'), '&lt;b&gt;test&lt;/b&gt;')

    def test_html_escape_ampersand(self):
        self.assertIn('&amp;', html_escape('a&b'))

    def test_html_escape_quotes(self):
        result = html_escape('"hello"')
        self.assertIn('&quot;', result)

    def test_html_quote(self):
        result = html_quote('value with "quotes"')
        self.assertIn('&quot;', result)


class TestHTTPDate(unittest.TestCase):
    def test_http_date_from_timestamp(self):
        result = http_date(0)
        self.assertIn('1970', result)
        self.assertIn('GMT', result)

    def test_http_date_from_current(self):
        result = http_date(time.time())
        self.assertIsInstance(result, str)
        self.assertIn('GMT', result)

    def test_parse_date(self):
        date_str = http_date(1000000)
        parsed = parse_date(date_str)
        self.assertIsNotNone(parsed)
        self.assertAlmostEqual(parsed, 1000000, delta=1)


class TestCookieSigning(unittest.TestCase):
    def test_encode_decode_roundtrip(self):
        secret = 'test-secret'
        encoded = cookie_encode(('key', 'value'), secret)
        decoded = cookie_decode(encoded, secret)
        self.assertEqual(decoded, ('key', 'value'))

    def test_is_encoded(self):
        secret = 'test-secret'
        encoded = cookie_encode(('key', 'value'), secret)
        self.assertTrue(cookie_is_encoded(encoded))

    def test_not_encoded(self):
        self.assertFalse(cookie_is_encoded(b'plain-text'))

    def test_wrong_secret_fails(self):
        encoded = cookie_encode(('key', 'value'), 'secret1')
        decoded = cookie_decode(encoded, 'wrong-secret')
        self.assertIsNone(decoded)


class TestMultiDict(unittest.TestCase):
    def test_single_value(self):
        d = MultiDict()
        d['key'] = 'value'
        self.assertEqual(d['key'], 'value')

    def test_multiple_values(self):
        d = MultiDict()
        d.append('color', 'red')
        d.append('color', 'blue')
        self.assertEqual(d.getall('color'), ['red', 'blue'])

    def test_getall_missing(self):
        d = MultiDict()
        self.assertEqual(d.getall('missing'), [])


class TestFormsDict(unittest.TestCase):
    def test_attribute_access(self):
        d = FormsDict()
        d['name'] = 'lusan'
        self.assertEqual(d.name, 'lusan')

    def test_missing_attribute(self):
        d = FormsDict()
        self.assertEqual(d.missing, '')

    def test_getunicode(self):
        d = FormsDict()
        d['name'] = 'hello'
        self.assertEqual(d.getunicode('name'), 'hello')


class TestHeaderDict(unittest.TestCase):
    def test_case_insensitive(self):
        d = HeaderDict()
        d['Content-Type'] = 'text/html'
        self.assertEqual(d['content-type'], 'text/html')
        self.assertEqual(d['CONTENT-TYPE'], 'text/html')

    def test_append(self):
        d = HeaderDict()
        d.append('Set-Cookie', 'a=1')
        d.append('Set-Cookie', 'b=2')
        self.assertEqual(len(d.getall('Set-Cookie')), 2)


if __name__ == '__main__':
    unittest.main()
