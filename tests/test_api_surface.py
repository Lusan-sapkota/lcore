"""Guards against parameters that are accepted but never read.

Three shipped bugs had this exact shape: ProxyFixMiddleware(num_proxies=N) was
stored and never consulted, set_cookie(domain=None) was read but rendered as
the literal string "None", and load(**namespace) outlived the eval() it fed.
None of them raised, none failed a test, and all of them were invisible with
default arguments. These tests fail the build if another one appears.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LCORE_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lcore.py')

# Signatures fixed by an external protocol: the parameter is part of a contract
# someone else calls us through, so an unused one is correct, not dead.
PROTOCOL_SIGNATURES = {
    'find_spec',      # importlib MetaPathFinder
    'find_module',    # importlib MetaPathFinder
    'exec_module',    # importlib Loader
    'start_response', # WSGI
    'decode',         # codec-compatible shim
    'getunicode',     # cgi.FieldStorage-compatible shim
}

# Parameters a caller passes us by contract, so the default implementation may
# legitimately ignore them. Keyed by (qualified name, parameter) so this cannot
# accidentally exempt an unrelated method that shares a name.
ALLOWED_UNUSED = {
    # Overridable hook: __call__ always passes ctx, subclasses use it, and the
    # default implementation is a pass-through.
    ('MiddlewareHook.post', 'ctx'),
    # Plugin interface. Route._make_callback calls plugin.apply(callback, route),
    # so every plugin accepts route whether or not it needs it.
    ('JSONPlugin.apply', 'route'),
    # Swallows unknown template settings, matching Bottle's behaviour.
    ('SimpleTemplate.prepare', 'ka'),
}

# Module-level names that lack a leading underscore but are intentionally not
# public API, so test_no_public_definition_is_forgotten must not demand they
# be added to __all__ (doing so would itself create the shadowing hazard
# __all__ exists to prevent, given how generic these names are).
UNDOCUMENTED_MODULE_NAMES = {
    'py',   # sys.version_info, for internal version checks only.
    'UTC',  # timezone.utc, used internally by the `expires` HeaderProperty.
}


def _parse():
    with open(LCORE_PY) as handle:
        return ast.parse(handle.read(), LCORE_PY)


def _is_stub(fn):
    """True for a body that is only a docstring, pass, ... or NotImplementedError.

    Abstract methods and base-class hooks legitimately ignore their arguments.
    """
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and \
            isinstance(body[0].value, ast.Constant) and \
            isinstance(body[0].value.value, str):
        body = body[1:]
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue
        if isinstance(stmt, ast.Raise):
            exc = stmt.exc
            name = getattr(exc, 'id', None) or getattr(
                getattr(exc, 'func', None), 'id', None)
            if name == 'NotImplementedError':
                continue
        return False
    return True


def _params(args):
    names = []
    for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        if arg.arg not in ('self', 'cls'):
            names.append(arg.arg)
    if args.vararg:
        names.append(args.vararg.arg)
    if args.kwarg:
        names.append(args.kwarg.arg)
    return names


def _names_read(fn):
    return {node.id for node in ast.walk(fn)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}


def _self_assignments(fn):
    """{attribute: source param name} for `self.attr = param`."""
    out = {}
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == 'self'
                    and isinstance(node.value, ast.Name)):
                out[target.attr] = node.value.id
    return out


class TestNoDeadParameters(unittest.TestCase):
    """Every public parameter must actually reach something."""

    @classmethod
    def setUpClass(cls):
        cls.tree = _parse()
        cls.attr_reads = set()
        cls.text_blobs = []
        for node in ast.walk(cls.tree):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                cls.attr_reads.add(node.attr)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                cls.text_blobs.append(node.value)

    def _referenced_in_text(self, attr):
        """Templates reach attributes through strings, e.g. {{e.traceback}}."""
        needle = '.%s' % attr
        return any(needle in blob for blob in self.text_blobs)

    def test_no_parameter_is_ignored(self):
        """A parameter that is never read is a promise the code does not keep."""
        dead = []
        for parent in ast.walk(self.tree):
            container = getattr(parent, 'name', None)
            for node in ast.iter_child_nodes(parent):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name.startswith('_') and node.name != '__init__':
                    continue
                if isinstance(parent, ast.ClassDef) and parent.name.startswith('_'):
                    continue
                if node.name in PROTOCOL_SIGNATURES or _is_stub(node):
                    continue
                label = '%s.%s' % (container, node.name) if container else node.name
                read = _names_read(node)
                for param in _params(node.args):
                    if param == '_' or param.startswith('_'):
                        continue
                    if param in read:
                        continue
                    if (label, param) in ALLOWED_UNUSED:
                        continue
                    dead.append('%s(%s=...) is never read  [line %d]'
                                % (label, param, node.lineno))
        self.assertEqual(dead, [], 'Parameters accepted but ignored:\n  '
                         + '\n  '.join(dead))

    def test_no_constructor_argument_is_stored_then_forgotten(self):
        """The ProxyFixMiddleware(num_proxies=N) shape: assigned, never consulted."""
        forgotten = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.ClassDef) or node.name.startswith('_'):
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef) or item.name != '__init__':
                    continue
                params = set(_params(item.args))
                for attr, source in _self_assignments(item).items():
                    if source not in params:
                        continue
                    if attr in self.attr_reads or self._referenced_in_text(attr):
                        continue
                    forgotten.append(
                        '%s.__init__ stores %s as self.%s, which is never read '
                        '[line %d]' % (node.name, source, attr, item.lineno))
        self.assertEqual(forgotten, [],
                         'Constructor arguments stored but never used:\n  '
                         + '\n  '.join(forgotten))


class TestPublicExports(unittest.TestCase):
    """__all__ must stay in step with the module as it grows."""

    def test_every_exported_name_exists(self):
        """A typo or a renamed class would break `from lcore import *`."""
        import lcore
        missing = [n for n in lcore.__all__ if not hasattr(lcore, n)]
        self.assertEqual(missing, [], 'names in __all__ that do not exist')

    def test_no_stdlib_module_is_exported(self):
        """Without __all__, import * shadows the caller's os, re, time and sys."""
        import types
        # 'ext' is a deliberate module object, Bottle's plugin-namespace
        # trick (lcore.ext.sqlite etc. via a sys.meta_path redirect), not an
        # accidentally-leaked stdlib import -- the only kind this test
        # guards against.
        allowed_modules = {'ext'}
        namespace = {}
        exec('from lcore import *', namespace)
        leaked = sorted(name for name, value in namespace.items()
                        if isinstance(value, types.ModuleType)
                        and name not in allowed_modules)
        self.assertEqual(leaked, [], 'stdlib modules leaked by import *')

    def test_no_public_definition_is_forgotten(self):
        """A new public class, function or module-level assignment (a
        functools.partial shortcut, an alias, a constant, ...) must be
        exported or explicitly skipped.

        Assignments matter as much as def/class here: jinja2_template,
        mako_view and friends are `functools.partial(...)` assignments, not
        defs, and were missing from __all__ in the first cut of this guard
        without it ever going red.
        """
        import lcore
        tree = _parse()
        defined = {node.name for node in tree.body
                   if isinstance(node, (ast.ClassDef, ast.FunctionDef))
                   and not node.name.startswith('_')}
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith('_'):
                        defined.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) \
                    and not node.target.id.startswith('_'):
                defined.add(node.target.id)
        forgotten = sorted(defined - set(lcore.__all__) - UNDOCUMENTED_MODULE_NAMES)
        self.assertEqual(forgotten, [],
                         'public definitions missing from __all__')


class TestCookieAttributesReachTheHeader(unittest.TestCase):
    """set_cookie() renders every attribute it is given, and omits the rest.

    This is where the Domain=None bug lived: the value was accepted, stored,
    and emitted as the four-character string "None".
    """

    def setUp(self):
        from lcore import BaseResponse
        self.response = BaseResponse()

    def _cookie_header(self):
        return [v for k, v in self.response.headerlist if k == 'Set-Cookie'][0]

    def test_none_valued_attributes_are_omitted(self):
        """An unset attribute must vanish, not render as "None"."""
        self.response.set_cookie('sid', 'abc', domain=None, path=None,
                                 expires=None, max_age=None)
        header = self._cookie_header().lower()
        self.assertNotIn('none', header.replace('samesite=lax', ''))

    def test_supplied_attributes_are_rendered(self):
        """Every attribute passed with a value reaches the header."""
        self.response.set_cookie('sid', 'abc', domain='example.com',
                                 path='/app', max_age=60, secure=True,
                                 httponly=True, samesite='Strict')
        header = self._cookie_header()
        self.assertIn('Domain=example.com', header)
        self.assertIn('Path=/app', header)
        self.assertIn('Max-Age=60', header)
        self.assertIn('secure', header.lower())
        self.assertIn('HttpOnly', header)
        self.assertIn('strict', header.lower())

    def test_delete_cookie_still_expires(self):
        """delete_cookie() relies on falsy values that must survive the filter."""
        self.response.delete_cookie('sid')
        header = self._cookie_header()
        self.assertIn('Max-Age=-1', header)
        self.assertIn('1970', header)


if __name__ == '__main__':
    unittest.main()
