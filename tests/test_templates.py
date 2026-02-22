"""Tests for Lcore template engine."""

import unittest
import os
import tempfile
import shutil

from helpers import run_request

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lcore import Lcore, SimpleTemplate, template, view, TemplateError


class TestSimpleTemplate(unittest.TestCase):
    def test_basic_render(self):
        tpl = SimpleTemplate('Hello {{name}}!')
        result = tpl.render(name='Lusan')
        self.assertEqual(result, 'Hello Lusan!')

    def test_expression(self):
        tpl = SimpleTemplate('{{x + y}}')
        result = tpl.render(x=3, y=4)
        self.assertEqual(result, '7')

    def test_python_block(self):
        tpl = SimpleTemplate('''%for i in range(3):
{{i}}
%end''')
        result = tpl.render()
        self.assertEqual(result.strip(), '0\n1\n2')

    def test_if_block(self):
        tpl = SimpleTemplate('''%if show:
visible
%else:
hidden
%end''')
        self.assertIn('visible', tpl.render(show=True))
        self.assertIn('hidden', tpl.render(show=False))

    def test_html_escape(self):
        tpl = SimpleTemplate('{{name}}')
        result = tpl.render(name='<script>alert("xss")</script>')
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_raw_output(self):
        tpl = SimpleTemplate('{{!raw}}')
        result = tpl.render(raw='<b>bold</b>')
        self.assertIn('<b>bold</b>', result)

    def test_for_loop(self):
        tpl = SimpleTemplate('''%for item in items:
- {{item}}
%end''')
        result = tpl.render(items=['a', 'b', 'c'])
        self.assertIn('- a', result)
        self.assertIn('- b', result)
        self.assertIn('- c', result)


class TestTemplateFromFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(self.tmpdir, 'greet.tpl'), 'w') as f:
            f.write('Hello {{name}}, welcome!')

        with open(os.path.join(self.tmpdir, 'list.tpl'), 'w') as f:
            f.write('''<ul>
%for item in items:
<li>{{item}}</li>
%end
</ul>''')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_render_from_file(self):
        tpl = SimpleTemplate(name='greet', lookup=[self.tmpdir])
        result = tpl.render(name='Lusan')
        self.assertEqual(result, 'Hello Lusan, welcome!')

    def test_render_list_from_file(self):
        tpl = SimpleTemplate(name='list', lookup=[self.tmpdir])
        result = tpl.render(items=['one', 'two'])
        self.assertIn('<li>one</li>', result)
        self.assertIn('<li>two</li>', result)


class TestTemplateFunction(unittest.TestCase):
    def test_template_string(self):
        result = template('Hello {{name}}!', name='World')
        self.assertEqual(result, 'Hello World!')


class TestViewDecorator(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(self.tmpdir, 'profile.tpl'), 'w') as f:
            f.write('Name: {{name}}, Age: {{age}}')
        import lcore as lcore
        self._orig_path = lcore.TEMPLATE_PATH[:]
        lcore.TEMPLATE_PATH.insert(0, self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        import lcore as lcore
        lcore.TEMPLATE_PATH[:] = self._orig_path
        lcore.TEMPLATES.clear()

    def test_view_decorator(self):
        app = Lcore()

        @app.route('/profile')
        @view('profile')
        def profile():
            return dict(name='Lusan', age=25)

        _, _, body = run_request(app, 'GET', '/profile')
        self.assertEqual(body, b'Name: Lusan, Age: 25')


class TestTemplateErrors(unittest.TestCase):
    def test_missing_variable(self):
        tpl = SimpleTemplate('{{missing_var}}')
        with self.assertRaises(Exception):
            tpl.render()

    def test_missing_template_file(self):
        with self.assertRaises(Exception):
            SimpleTemplate(name='nonexistent', lookup=['/tmp'])


if __name__ == '__main__':
    unittest.main()
