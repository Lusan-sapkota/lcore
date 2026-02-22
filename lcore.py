#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

__author__ = 'Lusan Sapkota'
__version__ = '0.0.1'
__license__ = 'MIT'

def _cli_parse(args):
    from argparse import ArgumentParser

    parser = ArgumentParser(prog=args[0], usage="%(prog)s [options] package.module:app")
    opt = parser.add_argument
    opt("--version", action="store_true", help="show version number.")
    opt("-b", "--bind", metavar="ADDRESS", help="bind socket to ADDRESS.")
    opt("-s", "--server", default='wsgiref', help="use SERVER as backend.")
    opt("-p", "--plugin", action="append", help="install additional plugin/s.")
    opt("-c", "--conf", action="append", metavar="FILE",
        help="load config values from FILE.")
    opt("-C", "--param", action="append", metavar="NAME=VALUE",
        help="override config values.")
    opt("--debug", action="store_true", help="start server in debug mode.")
    opt("--reload", action="store_true", help="auto-reload on file changes.")
    opt("--docs", action="store_true", help="open documentation in browser.")
    opt('app', help='WSGI app entry point.', nargs='?')

    cli_args = parser.parse_args(args[1:])

    return cli_args, parser

def _cli_patch(cli_args):
    parsed_args, _ = _cli_parse(cli_args)
    opts = parsed_args
    if opts.server:
        if opts.server.startswith('gevent'):
            import gevent.monkey
            gevent.monkey.patch_all()
        elif opts.server.startswith('eventlet'):
            import eventlet
            eventlet.monkey_patch()

if __name__ == '__main__':
    _cli_patch(sys.argv)

import asyncio, base64, calendar, concurrent.futures, email.utils, functools, \
    gzip, hmac, itertools, logging, mimetypes, os, re, tempfile, threading, \
    time, uuid, warnings, weakref, hashlib

from types import FunctionType
from datetime import date as datedate, datetime, timedelta
from tempfile import NamedTemporaryFile
from traceback import format_exc, print_exc
from unicodedata import normalize

try:
    from ujson import dumps as json_dumps, loads as json_lds
except ImportError:
    from json import dumps as json_dumps, loads as json_lds

py = sys.version_info

import http.client as httplib
import _thread as thread
from urllib.parse import urljoin, SplitResult as UrlSplitResult
from urllib.parse import urlencode, quote as urlquote, unquote as urlunquote
from http.cookies import SimpleCookie, Morsel, CookieError
from collections.abc import MutableMapping as DictMixin
from types import ModuleType as new_module
import pickle
from io import BytesIO
import configparser
from datetime import timezone
UTC = timezone.utc
import inspect

json_loads = lambda s: json_lds(touni(s))
_UNSET = object()

def _is_async(func):
    return inspect.iscoroutinefunction(func)

def _run_async(coro):
    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        return asyncio.run(coro)

def _wsgi_recode(src):
    if src.isascii():
        return src
    return src.encode('latin1').decode('utf8', 'surrogateescape')

def _raise(*a):
    raise a[0](a[1]).with_traceback(a[2])

def tob(s, enc='utf8'):
    if isinstance(s, str):
        return s.encode(enc)
    return b'' if s is None else bytes(s)

def touni(s, enc='utf8', err='strict'):
    if isinstance(s, (bytes, bytearray)):
        return str(s, enc, err)
    return "" if s is None else str(s)

def _stderr(*args):
    try:
        print(*args, file=sys.stderr)
    except (IOError, AttributeError):
        pass

def update_wrapper(wrapper, wrapped, *a, **ka):
    try:
        functools.update_wrapper(wrapper, wrapped, *a, **ka)
    except AttributeError:
        pass

def depr(major, minor, cause, fix, stacklevel=3):
    text = "Use of feature or API deprecated since Lcore-%d.%d\n"\
        "Cause: %s\n"\
        "Fix: %s\n" % (major, minor, cause, fix)
    if DEBUG == 'strict':
        raise DeprecationWarning(text)
    warnings.warn(text, DeprecationWarning, stacklevel=stacklevel)
    return DeprecationWarning(text)

def makelist(data):
    if isinstance(data, (tuple, list, set, dict)):
        return list(data)
    elif data:
        return [data]
    else:
        return []

class DictProperty:

    def __init__(self, attr, key=None, read_only=False):
        self.attr, self.key, self.read_only = attr, key, read_only

    def __call__(self, func):
        functools.update_wrapper(self, func, updated=[])
        self.getter, self.key = func, self.key or func.__name__
        return self

    def __get__(self, obj, cls):
        if obj is None: return self
        key, storage = self.key, getattr(obj, self.attr)
        if key not in storage: storage[key] = self.getter(obj)
        return storage[key]

    def __set__(self, obj, value):
        if self.read_only: raise AttributeError("Read-Only property.")
        getattr(obj, self.attr)[self.key] = value

    def __delete__(self, obj):
        if self.read_only: raise AttributeError("Read-Only property.")
        del getattr(obj, self.attr)[self.key]

class cached_property:

    def __init__(self, func):
        update_wrapper(self, func)
        self.func = func
        self.lock = threading.RLock()

    def __get__(self, obj, cls):
        if obj is None: return self
        name = self.func.__name__
        try:
            return obj.__dict__[name]
        except KeyError:
            pass
        with self.lock:
            if name not in obj.__dict__:
                obj.__dict__[name] = self.func(obj)
            return obj.__dict__[name]

class lazy_attribute:

    def __init__(self, func):
        functools.update_wrapper(self, func, updated=[])
        self.getter = func

    def __get__(self, obj, cls):
        value = self.getter(cls)
        setattr(cls, self.__name__, value)
        return value

class LcoreException(Exception):
    pass

class RouteError(LcoreException):
    pass

class RouterUnknownModeError(RouteError):
    pass

class RouteSyntaxError(RouteError):
    pass

class RouteBuildError(RouteError):
    pass

def _re_flatten(p):
    if '(' not in p:
        return p
    return re.sub(r'(\\*)(\(\?P<[^>]+>|\((?!\?))', lambda m: m.group(0) if
                  len(m.group(1)) % 2 else m.group(1) + '(?:', p)

class Router:

    default_pattern = '[^/]+'
    default_filter = 're'

    _MAX_GROUPS_PER_PATTERN = 99

    def __init__(self, strict=False):
        self.rules = []
        self._groups = {}
        self.builder = {}
        self.static = {}
        self.dyna_routes = {}
        self.dyna_regexes = {}
        self.strict_order = strict
        self.filters = {
            're': lambda conf: (_re_flatten(conf or self.default_pattern),
                                None, None),
            'int': lambda conf: (r'-?\d+', int, lambda x: str(int(x))),
            'float': lambda conf: (r'-?[\d.]+', float, lambda x: str(float(x))),
            'path': lambda conf: (r'.+?', None, None)
        }

    def add_filter(self, name, func):
        self.filters[name] = func

    rule_syntax = re.compile('(\\\\*)'
        '(?:(?::([a-zA-Z_][a-zA-Z_0-9]*)?()(?:#(.*?)#)?)'
          '|(?:<([a-zA-Z_][a-zA-Z_0-9]*)?(?::([a-zA-Z_]*)'
            '(?::((?:\\\\.|[^\\\\>])+)?)?)?>))')

    def _itertokens(self, rule):
        offset, prefix = 0, ''
        for match in self.rule_syntax.finditer(rule):
            prefix += rule[offset:match.start()]
            g = match.groups()
            if g[2] is not None:
                depr(0, 13, "Use of old route syntax.",
                            "Use <name> instead of :name in routes.",
                            stacklevel=4)
            if len(g[0]) % 2:
                prefix += match.group(0)[len(g[0]):]
                offset = match.end()
                continue
            if prefix:
                yield prefix, None, None
            name, filtr, conf = g[4:7] if g[2] is None else g[1:4]
            yield name, filtr or 'default', conf or None
            offset, prefix = match.end(), ''
        if offset <= len(rule) or prefix:
            yield prefix + rule[offset:], None, None

    def add(self, rule, method, target, name=None):
        anons = []
        keys = []
        pattern = ''
        filters = []
        builder = []
        is_static = True

        for key, mode, conf in self._itertokens(rule):
            if mode:
                is_static = False
                if mode == 'default': mode = self.default_filter
                mask, in_filter, out_filter = self.filters[mode](conf)
                if not key:
                    key = 'anon%d' % len(anons)
                    anons.append(key)
                pattern += '(?P<%s>%s)' % (key, mask)
                keys.append(key)
                if in_filter: filters.append((key, in_filter))
                builder.append((key, out_filter or str))
            elif key:
                pattern += re.escape(key)
                builder.append((None, key))

        self.builder[rule] = builder
        if name: self.builder[name] = builder

        if is_static and not self.strict_order:
            self.static.setdefault(method, {})
            self.static[method][self.build(rule)] = (target, None)
            return

        try:
            re_pattern = re.compile('^(%s)$' % pattern)
            re_match = re_pattern.match
        except re.error as e:
            raise RouteSyntaxError("Could not add Route: %s (%s)" % (rule, e))

        if filters:

            def getargs(path):
                url_args = re_match(path).groupdict()
                for name, wildcard_filter in filters:
                    try:
                        url_args[name] = wildcard_filter(url_args[name])
                    except ValueError:
                        raise HTTPError(400, 'Path has wrong format.')
                for key in anons:
                    del url_args[key]
                return url_args
        elif re_pattern.groupindex:

            def getargs(path):
                url_args = re_match(path).groupdict()
                for key in anons:
                    del url_args[key]
                return url_args
        else:
            getargs = None

        flatpat = _re_flatten(pattern)
        whole_rule = (rule, flatpat, target, getargs)

        if (flatpat, method) in self._groups:
            if DEBUG:
                msg = 'Route <%s %s> overwrites a previously defined route'
                warnings.warn(msg % (method, rule), RuntimeWarning, stacklevel=3)
            self.dyna_routes[method][
                self._groups[flatpat, method]] = whole_rule
        else:
            self.dyna_routes.setdefault(method, []).append(whole_rule)
            self._groups[flatpat, method] = len(self.dyna_routes[method]) - 1

        self._compile(method)

    def _compile(self, method):
        all_rules = self.dyna_routes[method]
        comborules = self.dyna_regexes[method] = []
        maxgroups = self._MAX_GROUPS_PER_PATTERN
        for x in range(0, len(all_rules), maxgroups):
            some = all_rules[x:x + maxgroups]
            combined = (flatpat for (_, flatpat, _, _) in some)
            combined = '|'.join('(^%s$)' % flatpat for flatpat in combined)
            combined = re.compile(combined).match
            rules = [(target, getargs) for (_, _, target, getargs) in some]
            comborules.append((combined, rules))

    def build(self, _name, *anons, **query):
        builder = self.builder.get(_name)
        if not builder:
            raise RouteBuildError("No route with that name.", _name)
        try:
            for i, value in enumerate(anons):
                query['anon%d' % i] = value
            url = ''.join([f(query.pop(n)) if n else f for (n, f) in builder])
            return url if not query else url + '?' + urlencode(query, doseq=True)
        except KeyError as E:
            raise RouteBuildError('Missing URL argument: %r' % E.args[0])

    def match(self, environ):
        verb = environ['REQUEST_METHOD'].upper()
        path = environ['PATH_INFO'] or '/'

        methods = ('PROXY', 'HEAD', 'GET', 'ANY') if verb == 'HEAD' else ('PROXY', verb, 'ANY')

        for method in methods:
            if method in self.static and path in self.static[method]:
                target, getargs = self.static[method][path]
                return target, getargs(path) if getargs else {}
            elif method in self.dyna_regexes:
                for combined, rules in self.dyna_regexes[method]:
                    match = combined(path)
                    if match:
                        target, getargs = rules[match.lastindex - 1]
                        return target, getargs(path) if getargs else {}

        allowed = set([])
        nocheck = set(methods)
        for method in set(self.static) - nocheck:
            if path in self.static[method]:
                allowed.add(method)
        for method in set(self.dyna_regexes) - allowed - nocheck:
            for combined, rules in self.dyna_regexes[method]:
                match = combined(path)
                if match:
                    allowed.add(method)
        if allowed:
            allow_header = ",".join(sorted(allowed))
            raise HTTPError(405, "Method not allowed.", Allow=allow_header)

        raise HTTPError(404, "Not found: " + repr(path))

class Route:

    def __init__(self, app, rule, method, callback,
                 name=None,
                 plugins=None,
                 skiplist=None, **config):
        self.app = app
        self.rule = rule
        self.method = method
        self.callback = callback
        self.name = name or None
        self.plugins = plugins or []
        self.skiplist = skiplist or []
        self.config = app.config._make_overlay()
        self.config.load_dict(config)

    @cached_property
    def call(self):
        return self._make_callback()

    def reset(self):
        self.__dict__.pop('call', None)

    def prepare(self):
        self.call

    def all_plugins(self):
        unique = set()
        for p in reversed(self.app.plugins + self.plugins):
            if True in self.skiplist: break
            name = getattr(p, 'name', False)
            if name and (name in self.skiplist or name in unique): continue
            if p in self.skiplist or type(p) in self.skiplist: continue
            if name: unique.add(name)
            yield p

    def _make_callback(self):
        callback = self.callback
        for plugin in self.all_plugins():
            if hasattr(plugin, 'apply'):
                callback = plugin.apply(callback, self)
            else:
                callback = plugin(callback)
            if callback is not self.callback:
                update_wrapper(callback, self.callback)
        if _is_async(callback):
            original = callback
            @functools.wraps(original)
            def async_wrapper(*a, **ka):
                return _run_async(original(*a, **ka))
            callback = async_wrapper
        return callback

    def get_undecorated_callback(self):
        func = self.callback
        while True:
            if getattr(func, '__wrapped__', False):
                func = func.__wrapped__
            elif getattr(func, '__func__', False):
                func = func.__func__
            elif getattr(func, '__closure__', False):
                depr(0, 14, "Decorated callback without __wrapped__",
                     "When applying decorators to route callbacks, make sure"
                     " the decorator uses @functools.wraps or update_wrapper."
                     " This warning may also trigger if you reference callables"
                     " from a nonlocal scope.")
                cells_values = (cell.cell_contents for cell in func.__closure__)
                isfunc = lambda x: isinstance(x, FunctionType) or hasattr(x, '__call__')
                func = next(filter(isfunc, cells_values), func)
            else:
                return func

    def get_callback_args(self):
        sig = inspect.signature(self.get_undecorated_callback())
        return [p.name for p in sig.parameters.values() if p.kind in (
            p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY
        )]

    def get_config(self, key, default=None):
        depr(0, 13, "Route.get_config() is deprecated.",
                    "The Route.config property already includes values from the"
                    " application config for missing keys. Access it directly.")
        return self.config.get(key, default)

    def __repr__(self):
        cb = self.get_undecorated_callback()
        return '<%s %s -> %s:%s>' % (
            self.method, self.rule, cb.__module__, getattr(cb, '__name__', '?')
        )

_DOCS_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API Documentation - Lcore %(version)s</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
background:#0A0F1A;color:#E6EDF3;line-height:1.6}
.container{max-width:960px;margin:0 auto;padding:24px}
header{padding:32px 0 24px;border-bottom:1px solid #1a2d4d;margin-bottom:24px}
header h1{font-size:24px;font-weight:600;color:#E6EDF3}
header h1 span{color:#00B8D9}
header p{color:#9cb3cc;font-size:14px;margin-top:4px}
.endpoint{background:#0f1a2e;border:1px solid #1a2d4d;border-radius:8px;
margin-bottom:12px;overflow:hidden;transition:border-color .2s}
.endpoint:hover{border-color:#264170}
.endpoint-header{display:flex;align-items:center;gap:12px;padding:14px 18px;cursor:pointer}
.badge{display:inline-block;padding:3px 10px;border-radius:4px;font-size:12px;
font-weight:700;font-family:monospace;text-transform:uppercase;min-width:64px;text-align:center}
.method-get{background:rgba(16,185,129,.15);color:#10b981}
.method-post{background:rgba(0,184,217,.15);color:#00B8D9}
.method-put{background:rgba(245,158,11,.15);color:#f59e0b}
.method-delete{background:rgba(239,68,68,.15);color:#ef4444}
.method-other{background:rgba(156,179,204,.1);color:#9cb3cc}
.path{font-family:monospace;font-size:15px;color:#E6EDF3;font-weight:500}
.ret{font-family:monospace;font-size:13px;color:#9cb3cc;margin-left:auto}
.docstring{padding:0 18px 14px;color:#9cb3cc;font-size:14px}
.params{width:calc(100%% - 36px);margin:0 18px 14px;border-collapse:collapse;font-size:13px}
.params th{text-align:left;padding:8px 12px;background:#0a1220;color:#9cb3cc;
font-weight:500;border-bottom:1px solid #1a2d4d;font-size:12px;text-transform:uppercase;letter-spacing:.5px}
.params td{padding:8px 12px;border-bottom:1px solid #1a2d4d;font-family:monospace;color:#E6EDF3}
.json-link{display:inline-block;margin-top:16px;color:#00B8D9;font-size:13px;text-decoration:none}
.json-link:hover{text-decoration:underline}
.count{color:#9cb3cc;font-size:14px;margin-bottom:16px}
</style>
</head>
<body>
<div class="container">
<header>
<h1><span>Lcore</span> API Documentation</h1>
<p>v%(version)s &middot; Interactive API reference</p>
</header>
%(routes)s
<a class="json-link" href="%(json_url)s">View raw JSON &rarr;</a>
</div>
</body>
</html>"""

class Lcore:

    @lazy_attribute
    def _global_config(cls):
        cfg = ConfigDict()
        cfg.meta_set('catchall', 'validate', bool)
        return cfg

    def __init__(self, **kwargs):
        self.config = self._global_config._make_overlay()
        self.config._add_change_listener(
            functools.partial(self.trigger_hook, 'config'))

        self.config.update({
            "catchall": True
        })

        if kwargs.get('catchall') is False:
            depr(0, 13, "Lcore(catchall) keyword argument.",
                        "The 'catchall' setting is now part of the app "
                        "configuration. Fix: `app.config['catchall'] = False`")
            self.config['catchall'] = False
        if kwargs.get('autojson') is False:
            depr(0, 13, "Lcore(autojson) keyword argument.",
                 "The 'autojson' setting is now part of the app "
                 "configuration. Fix: `app.config['json.enable'] = False`")
            self.config['json.enable'] = False

        self._mounts = []
        self._module_hooks = {}
        self._dependencies = None

        self.resources = ResourceManager()

        self.routes = []
        self.router = Router()
        self.error_handler = {}
        self.middleware = MiddlewarePipeline()

        self.plugins = []
        self.install(JSONPlugin())
        self.install(TemplatePlugin())

    catchall = DictProperty('config', 'catchall')

    __hook_names = ('before_request', 'after_request', 'app_reset', 'config',
                    'on_request_start', 'on_auth_resolved', 'on_handler_enter',
                    'on_handler_exit', 'on_response_build', 'on_response_send',
                    'on_module_mount', 'on_module_request')
    __hook_reversed = {'after_request', 'on_handler_exit', 'on_response_build',
                       'on_response_send'}

    @cached_property
    def _hooks(self):
        return dict((name, []) for name in self.__hook_names)

    def add_hook(self, name, func):
        if name in self.__hook_reversed:
            self._hooks[name].insert(0, func)
        else:
            self._hooks[name].append(func)

    def remove_hook(self, name, func):
        if name in self._hooks and func in self._hooks[name]:
            self._hooks[name].remove(func)
            return True

    def trigger_hook(self, __name, *args, **kwargs):
        hooks = self._hooks[__name]
        if not hooks:
            return []
        return [hook(*args, **kwargs) for hook in hooks[:]]

    def trigger_module_hooks(self, prefix, hook_name, *args, **kwargs):
        key = (prefix, hook_name)
        for func in self._module_hooks.get(key, []):
            func(*args, **kwargs)

    def hook(self, name):

        def decorator(func):
            self.add_hook(name, func)
            return func

        return decorator

    def _mount_wsgi(self, prefix, app, **options):
        segments = [p for p in prefix.split('/') if p]
        if not segments:
            raise ValueError('WSGI applications cannot be mounted to "/".')
        path_depth = len(segments)

        def mountpoint_wrapper():
            try:
                request.path_shift(path_depth)
                rs = HTTPResponse([])

                def start_response(status, headerlist, exc_info=None):
                    if exc_info:
                        _raise(*exc_info)
                    status = _wsgi_recode(status)
                    headerlist = [(k, _wsgi_recode(v)) for (k, v) in headerlist]
                    rs.status = status
                    for name, value in headerlist:
                        rs.add_header(name, value)
                    return rs.body.append

                body = app(request.environ, start_response)
                rs.body = itertools.chain(rs.body, body) if rs.body else body
                return rs
            finally:
                request.path_shift(-path_depth)

        options.setdefault('skip', True)
        options.setdefault('method', 'PROXY')
        options.setdefault('mountpoint', {'prefix': prefix, 'target': app})
        options['callback'] = mountpoint_wrapper

        self.route('/%s/<:re:.*>' % '/'.join(segments), **options)
        if not prefix.endswith('/'):
            self.route('/' + '/'.join(segments), **options)

    def _mount_app(self, prefix, app, **options):
        if app in self._mounts or '_mount.app' in app.config:
            depr(0, 13, "Application mounted multiple times. Falling back to WSGI mount.",
                 "Clone application before mounting to a different location.")
            return self._mount_wsgi(prefix, app, **options)

        if options:
            depr(0, 13, "Unsupported mount options. Falling back to WSGI mount.",
                 "Do not specify any route options when mounting lcore application.")
            return self._mount_wsgi(prefix, app, **options)

        if not prefix.endswith("/"):
            depr(0, 13, "Prefix must end in '/'. Falling back to WSGI mount.",
                 "Consider adding an explicit redirect from '/prefix' to '/prefix/' in the parent application.")
            return self._mount_wsgi(prefix, app, **options)

        self._mounts.append(app)
        app.config['_mount.prefix'] = prefix
        app.config['_mount.app'] = self
        for route in app.routes:
            route.rule = prefix + route.rule.lstrip('/')
            route.config['_mount.prefix'] = prefix
            self.add_route(route)
        for hook_name in self.__hook_names:
            for func in app._hooks.get(hook_name, []):
                self.add_module_hook(prefix, hook_name, func)
        self.trigger_hook('on_module_mount', prefix, app)

    def mount(self, prefix, app, **options):

        if not prefix.startswith('/'):
            raise ValueError("Prefix must start with '/'")

        if isinstance(app, Lcore):
            return self._mount_app(prefix, app, **options)
        else:
            return self._mount_wsgi(prefix, app, **options)

    def merge(self, routes):
        if isinstance(routes, Lcore):
            routes = routes.routes
        for route in routes:
            self.add_route(route)

    def use(self, middleware, routes=None, order=None):
        self.middleware.add(middleware, routes=routes, order=order)
        return middleware

    def inject(self, name, factory, lifetime='singleton'):
        if self._dependencies is None:
            object.__setattr__(self, '_dependencies', DependencyContainer())
        self._dependencies.register(name, factory, lifetime)
        return factory

    def add_module_hook(self, prefix, hook_name, func):
        key = (prefix, hook_name)
        self._module_hooks.setdefault(key, [])
        self._module_hooks[key].append(func)

    def module_hook(self, prefix, hook_name):
        def decorator(func):
            self.add_module_hook(prefix, hook_name, func)
            return func
        return decorator

    def group(self, prefix, **common_config):
        from contextlib import contextmanager

        @contextmanager
        def _group_ctx():
            original_route = self.route

            def prefixed_route(path='/', method=None, **kwargs):
                merged = {**common_config, **kwargs}
                full_path = prefix.rstrip('/') + '/' + path.lstrip('/')
                if method is not None:
                    return original_route(full_path, method, **merged)
                return original_route(full_path, **merged)

            object.__setattr__(self, 'route', prefixed_route)
            try:
                yield self
            finally:
                try:
                    object.__delattr__(self, 'route')
                except AttributeError:
                    pass

        return _group_ctx()

    def add_route_filter(self, name, pattern, to_python=None, to_url=None):
        self.router.add_filter(name, lambda conf: (pattern, to_python, to_url))

    def install(self, plugin):
        if hasattr(plugin, 'setup'): plugin.setup(self)
        if not callable(plugin) and not hasattr(plugin, 'apply'):
            raise TypeError("Plugins must be callable or implement .apply()")
        self.plugins.append(plugin)
        self.reset()
        return plugin

    def uninstall(self, plugin):
        removed, remove = [], plugin
        for i, plugin in list(enumerate(self.plugins))[::-1]:
            if remove is True or remove is plugin or remove is type(plugin) \
               or getattr(plugin, 'name', True) == remove:
                removed.append(plugin)
                del self.plugins[i]
                if hasattr(plugin, 'close'): plugin.close()
        if removed: self.reset()
        return removed

    def reset(self, route=None):
        if route is None: routes = self.routes
        elif isinstance(route, Route): routes = [route]
        else: routes = [self.routes[route]]
        for route in routes:
            route.reset()
        if DEBUG:
            for route in routes:
                route.prepare()
        self.trigger_hook('app_reset')

    def close(self):
        for plugin in self.plugins:
            if hasattr(plugin, 'close'): plugin.close()

    def run(self, **kwargs):
        run(self, **kwargs)

    def show_routes(self):
        lines = []
        for r in self.routes:
            cb = r.get_undecorated_callback()
            mod = getattr(cb, '__module__', '?')
            name = getattr(cb, '__name__', '?')
            plugins = [getattr(p, 'name', type(p).__name__)
                       for p in r.all_plugins()]
            line = {
                'method': r.method,
                'rule': r.rule,
                'name': r.name or '',
                'callback': '%s:%s' % (mod, name),
                'plugins': plugins,
            }
            lines.append(line)
        return lines

    def show_middleware(self):
        entries = []
        for mw, pattern in self.middleware._middleware:
            entry = {
                'name': getattr(mw, 'name', None) or type(mw).__name__,
                'order': getattr(mw, 'order', 50),
                'routes': pattern.pattern if pattern else '*',
                'type': type(mw).__name__,
            }
            entries.append(entry)
        entries.sort(key=lambda x: x['order'])
        return entries

    def api_docs(self):
        docs = {'routes': [], 'version': __version__}
        hidden = getattr(self, '_docs_paths', set())
        for r in self.routes:
            if r.rule in hidden:
                continue
            cb = r.get_undecorated_callback()
            sig = inspect.signature(cb)
            params = []
            for pname, p in sig.parameters.items():
                param_info = {'name': pname, 'kind': str(p.kind.name)}
                if p.default is not p.empty:
                    param_info['default'] = repr(p.default)
                if p.annotation is not p.empty:
                    param_info['type'] = getattr(p.annotation, '__name__',
                                                 str(p.annotation))
                params.append(param_info)
            return_type = None
            if sig.return_annotation is not sig.empty:
                return_type = getattr(sig.return_annotation, '__name__',
                                      str(sig.return_annotation))
            doc_entry = {
                'method': r.method,
                'rule': r.rule,
                'name': r.name or '',
                'callback': getattr(cb, '__name__', '?'),
                'module': getattr(cb, '__module__', '?'),
                'docstring': inspect.getdoc(cb) or '',
                'parameters': params,
            }
            if return_type:
                doc_entry['return_type'] = return_type
            docs['routes'].append(doc_entry)
        return docs

    def api_docs_json(self):
        return json_dumps(self.api_docs())

    def enable_docs(self, path='/docs'):
        app = self
        json_path = path.rstrip('/') + '/json'
        self._docs_paths = {path, json_path}

        @app.route(json_path)
        def _docs_json():
            response.content_type = 'application/json'
            return app.api_docs_json()

        @app.route(path)
        def _docs_ui():
            data = app.api_docs()
            routes_html = []
            for r in data['routes']:
                method = r['method']
                if isinstance(method, (list, tuple)):
                    method = ', '.join(method)
                method_upper = method.upper()
                if 'GET' in method_upper:
                    badge_cls = 'method-get'
                elif 'POST' in method_upper:
                    badge_cls = 'method-post'
                elif 'PUT' in method_upper:
                    badge_cls = 'method-put'
                elif 'DELETE' in method_upper:
                    badge_cls = 'method-delete'
                else:
                    badge_cls = 'method-other'
                params_html = ''
                if r['parameters']:
                    rows = ''
                    for p in r['parameters']:
                        rows += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                            html_escape(p['name']),
                            html_escape(p.get('type', '-')),
                            html_escape(p.get('default', 'required')))
                    params_html = (
                        '<table class="params"><thead><tr>'
                        '<th>Parameter</th><th>Type</th><th>Default</th>'
                        '</tr></thead><tbody>%s</tbody></table>' % rows)
                doc = html_escape(r.get('docstring', ''))
                ret = r.get('return_type', '')
                ret_html = (' <span class="ret">&#8594; %s</span>' %
                            html_escape(ret)) if ret else ''
                routes_html.append(
                    '<div class="endpoint">'
                    '<div class="endpoint-header">'
                    '<span class="badge %s">%s</span>'
                    '<span class="path">%s</span>%s</div>'
                    '%s%s</div>' % (
                        badge_cls, html_escape(method),
                        html_escape(r['rule']), ret_html,
                        ('<p class="docstring">%s</p>' % doc) if doc else '',
                        params_html))
            return _DOCS_HTML % {
                'version': html_escape(data.get('version', '')),
                'routes': '\n'.join(routes_html),
                'json_url': json_path}

    def match(self, environ):
        return self.router.match(environ)

    def get_url(self, routename, **kargs):
        scriptname = request.environ.get('SCRIPT_NAME', '').strip('/') + '/'
        location = self.router.build(routename, **kargs).lstrip('/')
        return urljoin(urljoin('/', scriptname), location)

    def add_route(self, route):
        self.routes.append(route)
        self.router.add(route.rule, route.method, route, name=route.name)
        if DEBUG: route.prepare()

    def route(self,
              path=None,
              method='GET',
              callback=None,
              name=None,
              apply=None,
              skip=None, **config):
        if callable(path): path, callback = None, path
        plugins = makelist(apply)
        skiplist = makelist(skip)

        def decorator(callback):
            if isinstance(callback, str):
                callback = load(callback)
            for rule in makelist(path) or yieldroutes(callback):
                for verb in makelist(method):
                    verb = verb.upper()
                    route = Route(self, rule, verb, callback,
                                  name=name,
                                  plugins=plugins,
                                  skiplist=skiplist, **config)
                    self.add_route(route)
            return callback

        return decorator(callback) if callback else decorator

    def get(self, path=None, method='GET', **options):
        return self.route(path, method, **options)

    def post(self, path=None, method='POST', **options):
        return self.route(path, method, **options)

    def put(self, path=None, method='PUT', **options):
        return self.route(path, method, **options)

    def delete(self, path=None, method='DELETE', **options):
        return self.route(path, method, **options)

    def patch(self, path=None, method='PATCH', **options):
        return self.route(path, method, **options)

    def error(self, code=500, callback=None):

        def decorator(callback):
            if isinstance(callback, str): callback = load(callback)
            self.error_handler[int(code)] = callback
            return callback

        return decorator(callback) if callback else decorator

    def default_error_handler(self, res):
        return tob(template(ERROR_PAGE_TEMPLATE, e=res, template_settings=dict(name='__ERROR_PAGE_TEMPLATE')))

    def _handle(self, environ):
        path = environ['lcore.raw_path'] = environ['PATH_INFO']
        environ['PATH_INFO'] = _wsgi_recode(path)

        environ['lcore.app'] = self
        request.bind(environ)
        response.bind()
        ctx.bind(request, response, self)
        if self._dependencies:
            self._dependencies._begin_scope(ctx)
        out = None
        mount_prefix = None

        try:
            try:
                self.trigger_hook('on_request_start')
                self.trigger_hook('before_request')
                route, args = self.router.match(environ)
                environ['route.handle'] = route
                environ['lcore.route'] = route
                environ['route.url_args'] = args
                ctx.route = route

                mount_prefix = getattr(route, 'config', {}).get('_mount.prefix')
                if mount_prefix:
                    self.trigger_hook('on_module_request', mount_prefix, ctx)
                    self.trigger_module_hooks(mount_prefix, 'before_request')

                self.trigger_hook('on_auth_resolved')

                self.trigger_hook('on_handler_enter')

                def call_route():
                    return route.call(**args)

                if self.middleware._middleware:
                    out = self.middleware.execute(ctx, call_route)
                else:
                    out = call_route()

                self.trigger_hook('on_handler_exit')
            except HTTPResponse as E:
                out = E
            finally:
                if isinstance(out, HTTPResponse):
                    out.apply(response)
                self.trigger_hook('on_response_build')
                try:
                    if mount_prefix:
                        self.trigger_module_hooks(mount_prefix, 'after_request')
                    self.trigger_hook('after_request')
                except HTTPResponse as E:
                    out = E
                    out.apply(response)
                self.trigger_hook('on_response_send')
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as E:
            _try_close(out)
            if not self.catchall: raise
            stacktrace = format_exc()
            environ['wsgi.errors'].write(stacktrace)
            environ['wsgi.errors'].flush()
            environ['lcore.exc_info'] = sys.exc_info()
            out = HTTPError(500, "Internal Server Error", E, stacktrace)
            out.apply(response)
        finally:
            if self._dependencies:
                self._dependencies._end_scope(ctx)

        return out

    def _cast(self, out, peek=None):

        if inspect.iscoroutine(out):
            out = _run_async(out)

        if not out:
            if 'Content-Length' not in response:
                response['Content-Length'] = 0
            return []
        if isinstance(out, (tuple, list)) and isinstance(out[0], (bytes, str)):
            out = out[0][0:0].join(out)
        if isinstance(out, str):
            out = out.encode(response.charset)
        if isinstance(out, bytes):
            if 'Content-Length' not in response:
                response['Content-Length'] = len(out)
            return [out]
        if isinstance(out, HTTPError):
            out.apply(response)
            out = self.error_handler.get(out.status_code,
                                         self.default_error_handler)(out)
            return self._cast(out)
        if isinstance(out, HTTPResponse):
            out.apply(response)
            return self._cast(out.body)

        if hasattr(out, 'read'):
            if 'wsgi.file_wrapper' in request.environ:
                return request.environ['wsgi.file_wrapper'](out)
            elif hasattr(out, 'close') or not hasattr(out, '__iter__'):
                return WSGIFileWrapper(out)

        try:
            iout = iter(out)
            first = next(iout)
            while not first:
                first = next(iout)
        except StopIteration:
            _try_close(out)
            return self._cast('')
        except HTTPResponse as E:
            first = E
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as error:
            _try_close(out)
            if not self.catchall: raise
            first = HTTPError(500, 'Unhandled exception', error, format_exc())

        if isinstance(first, HTTPResponse):
            return self._cast(first)
        elif isinstance(first, bytes):
            new_iter = itertools.chain([first], iout)
        elif isinstance(first, str):
            encoder = lambda x: x.encode(response.charset)
            new_iter = map(encoder, itertools.chain([first], iout))
        else:
            _try_close(out)
            msg = 'Unsupported response type: %s' % type(first)
            return self._cast(HTTPError(500, msg))
        if hasattr(out, 'close'):
            new_iter = _closeiter(new_iter, out.close)
        return new_iter

    def wsgi(self, environ, start_response):
        out = None
        try:
            out = self._cast(self._handle(environ))
            if response._status_code in (100, 101, 204, 304) \
               or environ['REQUEST_METHOD'] == 'HEAD':
                if hasattr(out, 'close'): out.close()
                out = []
            exc_info = environ.get('lcore.exc_info')
            if exc_info is not None:
                del environ['lcore.exc_info']
            start_response(response._wsgi_status_line(), response.headerlist, exc_info)
            return out
        except (KeyboardInterrupt, SystemExit, MemoryError):
            raise
        except Exception as E:
            _try_close(out)
            if not self.catchall: raise
            err = '<h1>Critical error while processing request: %s</h1>' \
                  % html_escape(environ.get('PATH_INFO', '/'))
            if DEBUG:
                err += '<h2>Error:</h2>\n<pre>\n%s\n</pre>\n' \
                       '<h2>Traceback:</h2>\n<pre>\n%s\n</pre>\n' \
                       % (html_escape(repr(E)), html_escape(format_exc()))
            environ['wsgi.errors'].write(err)
            environ['wsgi.errors'].flush()
            headers = [('Content-Type', 'text/html; charset=UTF-8')]
            start_response('500 INTERNAL SERVER ERROR', headers, sys.exc_info())
            return [tob(err)]

    def __call__(self, environ, start_response):
        return self.wsgi(environ, start_response)

    def __enter__(self):
        default_app.push(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        default_app.pop()

    def __setattr__(self, name, value):
        if name in self.__dict__:
            raise AttributeError("Attribute %s already defined. Plugin conflict?" % name)
        object.__setattr__(self, name, value)

class BaseRequest:

    __slots__ = ('environ', )

    MEMFILE_MAX = 102400

    def __init__(self, environ=None):
        self.environ = {} if environ is None else environ
        self.environ['lcore.request'] = self

    @DictProperty('environ', 'lcore.app', read_only=True)
    def app(self):
        raise RuntimeError('This request is not connected to an application.')

    @DictProperty('environ', 'lcore.route', read_only=True)
    def route(self):
        raise RuntimeError('This request is not connected to a route.')

    @DictProperty('environ', 'route.url_args', read_only=True)
    def url_args(self):
        raise RuntimeError('This request is not connected to a route.')

    @property
    def path(self):
        return '/' + self.environ.get('PATH_INFO', '').lstrip('/')

    @property
    def method(self):
        return self.environ.get('REQUEST_METHOD', 'GET').upper()

    @DictProperty('environ', 'lcore.request.headers', read_only=True)
    def headers(self):
        return WSGIHeaderDict(self.environ)

    def get_header(self, name, default=None):
        return self.headers.get(name, default)

    @DictProperty('environ', 'lcore.request.cookies', read_only=True)
    def cookies(self):
        cookie_header = _wsgi_recode(self.environ.get('HTTP_COOKIE', ''))
        cookies = SimpleCookie(cookie_header).values()
        return FormsDict((c.key, c.value) for c in cookies)

    def get_cookie(self, key, default=None, secret=None, digestmod=hashlib.sha256):
        value = self.cookies.get(key)
        if secret:
            if value and value.startswith('!') and '?' in value:
                sig, msg = map(tob, value[1:].split('?', 1))
                hashed = hmac.new(tob(secret), msg, digestmod=digestmod).digest()
                if _lscmp(sig, base64.b64encode(hashed)):
                    try:
                        dst = json_loads(base64.b64decode(msg))
                    except (ValueError, TypeError):
                        return default
                    if dst and dst[0] == key:
                        return dst[1]
            return default
        return value or default

    @DictProperty('environ', 'lcore.request.query', read_only=True)
    def query(self):
        get = self.environ['lcore.get'] = FormsDict()
        pairs = _parse_qsl(self.environ.get('QUERY_STRING', ''), 'utf8')
        for key, value in pairs:
            get[key] = value
        return get

    @DictProperty('environ', 'lcore.request.forms', read_only=True)
    def forms(self):
        forms = FormsDict()
        for name, item in self.POST.allitems():
            if not isinstance(item, FileUpload):
                forms[name] = item
        return forms

    @DictProperty('environ', 'lcore.request.params', read_only=True)
    def params(self):
        params = FormsDict()
        for key, value in self.query.allitems():
            params[key] = value
        for key, value in self.forms.allitems():
            params[key] = value
        return params

    @DictProperty('environ', 'lcore.request.files', read_only=True)
    def files(self):
        files = FormsDict()
        for name, item in self.POST.allitems():
            if isinstance(item, FileUpload):
                files[name] = item
        return files

    @DictProperty('environ', 'lcore.request.json', read_only=True)
    def json(self):
        ctype = self.environ.get('CONTENT_TYPE', '').lower().split(';')[0]
        if ctype in ('application/json', 'application/json-rpc'):
            b = self._get_body_string(self.MEMFILE_MAX)
            if not b:
                return None
            try:
                return json_loads(b)
            except (ValueError, TypeError) as err:
                raise HTTPError(400, 'Invalid JSON', exception=err)
        return None

    def _iter_body(self, read, bufsize):
        maxread = max(0, self.content_length)
        while maxread:
            part = read(min(maxread, bufsize))
            if not part: break
            yield part
            maxread -= len(part)

    @staticmethod
    def _iter_chunked(read, bufsize):
        err = HTTPError(400, 'Error while parsing chunked transfer body.')
        rn, sem, bs = b'\r\n', b';', b''
        while True:
            header = read(1)
            while header[-2:] != rn:
                c = read(1)
                header += c
                if not c: raise err
                if len(header) > bufsize: raise err
            size, _, _ = header.partition(sem)
            try:
                maxread = int(size.strip(), 16)
            except ValueError:
                raise err
            if maxread == 0: break
            buff = bs
            while maxread > 0:
                if not buff:
                    buff = read(min(maxread, bufsize))
                part, buff = buff[:maxread], buff[maxread:]
                if not part: raise err
                yield part
                maxread -= len(part)
            if read(2) != rn:
                raise err

    @DictProperty('environ', 'lcore.request.body', read_only=True)
    def _body(self):
        try:
            read_func = self.environ['wsgi.input'].read
        except KeyError:
            self.environ['wsgi.input'] = BytesIO()
            return self.environ['wsgi.input']
        body_iter = self._iter_chunked if self.chunked else self._iter_body
        body, body_size, is_temp_file = BytesIO(), 0, False
        for part in body_iter(read_func, self.MEMFILE_MAX):
            body.write(part)
            body_size += len(part)
            if not is_temp_file and body_size > self.MEMFILE_MAX:
                body, tmp = NamedTemporaryFile(mode='w+b'), body
                body.write(tmp.getvalue())
                del tmp
                is_temp_file = True
        self.environ['wsgi.input'] = body
        body.seek(0)
        return body

    def _get_body_string(self, maxread):
        if self.content_length > maxread:
            raise HTTPError(413, 'Request entity too large')
        data = self.body.read(maxread + 1)
        if len(data) > maxread:
            raise HTTPError(413, 'Request entity too large')
        return data

    @property
    def body(self):
        self._body.seek(0)
        return self._body

    @property
    def chunked(self):
        return 'chunked' in self.environ.get(
            'HTTP_TRANSFER_ENCODING', '').lower()

    GET = query

    @DictProperty('environ', 'lcore.request.post', read_only=True)
    def POST(self):
        post = FormsDict()
        content_type = self.environ.get('CONTENT_TYPE', '')
        content_type, options = _parse_http_header(content_type)[0]
        if not content_type.startswith('multipart/'):
            body = self._get_body_string(self.MEMFILE_MAX).decode('utf8', 'surrogateescape')
            for key, value in _parse_qsl(body, 'utf8'):
                post[key] = value
            return post

        charset = options.get("charset", "utf8")
        boundary = options.get("boundary")
        if not boundary:
            raise MultipartError("Invalid content type header, missing boundary")
        parser = _MultipartParser(self.body, boundary, self.content_length,
            mem_limit=self.MEMFILE_MAX, memfile_limit=self.MEMFILE_MAX,
            charset=charset)

        for part in parser.parse():
            if not part.filename and part.is_buffered():
                post[part.name] = part.value
            else:
                post[part.name] = FileUpload(part.file, part.name,
                                            part.filename, part.headerlist)

        return post

    @property
    def url(self):
        return self.urlparts.geturl()

    @DictProperty('environ', 'lcore.request.urlparts', read_only=True)
    def urlparts(self):
        env = self.environ
        http = env.get('HTTP_X_FORWARDED_PROTO') or env.get('wsgi.url_scheme', 'http')
        host = env.get('HTTP_X_FORWARDED_HOST') or env.get('HTTP_HOST')
        if not host:
            host = env.get('SERVER_NAME', '127.0.0.1')
            port = env.get('SERVER_PORT')
            if port and port != ('80' if http == 'http' else '443'):
                host += ':' + port
        path = urlquote(self.fullpath)
        return UrlSplitResult(http, host, path, env.get('QUERY_STRING'), '')

    @property
    def fullpath(self):
        return urljoin(self.script_name, self.path.lstrip('/'))

    @property
    def query_string(self):
        return self.environ.get('QUERY_STRING', '')

    @property
    def script_name(self):
        script_name = self.environ.get('SCRIPT_NAME', '').strip('/')
        return '/' + script_name + '/' if script_name else '/'

    def path_shift(self, shift=1):
        script, path = path_shift(self.environ.get('SCRIPT_NAME', '/'), self.path, shift)
        self['SCRIPT_NAME'], self['PATH_INFO'] = script, path

    @property
    def content_length(self):
        try:
            return int(self.environ.get('CONTENT_LENGTH') or -1)
        except (ValueError, TypeError):
            return -1

    @property
    def content_type(self):
        return self.environ.get('CONTENT_TYPE', '').lower()

    @property
    def is_xhr(self):
        requested_with = self.environ.get('HTTP_X_REQUESTED_WITH', '')
        return requested_with.lower() == 'xmlhttprequest'

    @property
    def is_ajax(self):
        return self.is_xhr

    @property
    def auth(self):
        basic = parse_auth(self.environ.get('HTTP_AUTHORIZATION', ''))
        if basic: return basic
        ruser = self.environ.get('REMOTE_USER')
        if ruser: return (ruser, None)
        return None

    @property
    def remote_route(self):
        proxy = self.environ.get('HTTP_X_FORWARDED_FOR')
        if proxy: return [ip.strip() for ip in proxy.split(',')]
        remote = self.environ.get('REMOTE_ADDR')
        return [remote] if remote else []

    @property
    def remote_addr(self):
        route = self.remote_route
        return route[0] if route else None

    def copy(self):
        return Request(self.environ.copy())

    def get(self, key, default=None):
        return self.environ.get(key, default)

    def __getitem__(self, key):
        return self.environ[key]

    def __delitem__(self, key):
        self[key] = ""
        del (self.environ[key])

    def __iter__(self):
        return iter(self.environ)

    def __len__(self):
        return len(self.environ)

    def keys(self):
        return self.environ.keys()

    def __setitem__(self, key, value):

        if self.environ.get('lcore.request.readonly'):
            raise KeyError('The environ dictionary is read-only.')

        self.environ[key] = value
        todelete = ()

        if key == 'wsgi.input':
            todelete = ('body', 'forms', 'files', 'params', 'post', 'json')
        elif key == 'QUERY_STRING':
            todelete = ('query', 'params')
        elif key.startswith('HTTP_'):
            todelete = ('headers', 'cookies')

        for key in todelete:
            self.environ.pop('lcore.request.' + key, None)

    def __repr__(self):
        return '<%s: %s %s>' % (self.__class__.__name__, self.method, self.url)

    def __getattr__(self, name):
        try:
            var = self.environ['lcore.request.ext.%s' % name]
            return var.__get__(self) if hasattr(var, '__get__') else var
        except KeyError:
            raise AttributeError('Attribute %r not defined.' % name)

    def __setattr__(self, name, value):
        if name == 'environ': return object.__setattr__(self, name, value)
        key = 'lcore.request.ext.%s' % name
        if hasattr(self, name):
            raise AttributeError("Attribute already defined: %s" % name)
        self.environ[key] = value

    def __delattr__(self, name):
        try:
            del self.environ['lcore.request.ext.%s' % name]
        except KeyError:
            raise AttributeError("Attribute not defined: %s" % name)

def _hkey(key):
    key = touni(key)
    if '\n' in key or '\r' in key or '\0' in key:
        raise ValueError("Header names must not contain control characters: %r" % key)
    return key.title().replace('_', '-')

def _hval(value):
    value = touni(value)
    if '\n' in value or '\r' in value or '\0' in value:
        raise ValueError("Header value must not contain control characters: %r" % value)
    return value

class HeaderProperty:
    def __init__(self, name, reader=None, writer=None, default=''):
        self.name, self.default = name, default
        self.reader, self.writer = reader, writer
        self.__doc__ = 'Current value of the %r header.' % name.title()

    def __get__(self, obj, _):
        if obj is None: return self
        value = obj.get_header(self.name, self.default)
        return self.reader(value) if self.reader else value

    def __set__(self, obj, value):
        obj[self.name] = self.writer(value) if self.writer else value

    def __delete__(self, obj):
        del obj[self.name]

class BaseResponse:

    default_status = 200
    default_content_type = 'text/html; charset=UTF-8'

    bad_headers = {
        204: frozenset(('Content-Type', 'Content-Length')),
        304: frozenset(('Allow', 'Content-Encoding', 'Content-Language',
                  'Content-Length', 'Content-Range', 'Content-Type',
                  'Content-Md5', 'Last-Modified'))
    }

    def __init__(self, body='', status=None, headers=None, **more_headers):
        self._cookies = None
        self._headers = {}
        self.body = body
        self.status = status or self.default_status
        if headers:
            if isinstance(headers, dict):
                headers = headers.items()
            for name, value in headers:
                self.add_header(name, value)
        if more_headers:
            for name, value in more_headers.items():
                self.add_header(name, value)

    def copy(self, cls=None):
        cls = cls or BaseResponse
        assert issubclass(cls, BaseResponse)
        copy = cls()
        copy.status = self.status
        copy._headers = dict((k, v[:]) for (k, v) in self._headers.items())
        if self._cookies:
            cookies = copy._cookies = SimpleCookie()
            for k, v in self._cookies.items():
                cookies[k] = v.value
                cookies[k].update(v)
        return copy

    def __iter__(self):
        return iter(self.body)

    def close(self):
        if hasattr(self.body, 'close'):
            self.body.close()

    @property
    def status_line(self):
        return self._status_line

    @property
    def status_code(self):
        return self._status_code

    def _set_status(self, status):
        if isinstance(status, int):
            code, status = status, _HTTP_STATUS_LINES.get(status)
        elif ' ' in status:
            if '\n' in status or '\r' in status or '\0' in status:
                raise ValueError('Status line must not include control chars.')
            status = status.strip()
            code = int(status.split()[0])
        else:
            raise ValueError('String status line without a reason phrase.')
        if not 100 <= code <= 999:
            raise ValueError('Status code out of range.')
        self._status_code = code
        self._status_line = str(status or ('%d Unknown' % code))

    def _get_status(self):
        return self._status_line

    status = property(
        _get_status, _set_status, None,
        ''' A writeable property to change the HTTP response status. It accepts
            either a numeric code (100-999) or a string with a custom reason
            phrase (e.g. "404 Brain not found"). Both :data:`status_line` and
            :data:`status_code` are updated accordingly. The return value is
            always a status string. ''')
    del _get_status, _set_status

    @property
    def headers(self):
        hdict = HeaderDict()
        hdict.dict = self._headers
        return hdict

    def __contains__(self, name):
        return _hkey(name) in self._headers

    def __delitem__(self, name):
        del self._headers[_hkey(name)]

    def __getitem__(self, name):
        return self._headers[_hkey(name)][-1]

    def __setitem__(self, name, value):
        self._headers[_hkey(name)] = [_hval(value)]

    def get_header(self, name, default=None):
        return self._headers.get(_hkey(name), [default])[-1]

    def set_header(self, name, value):
        self._headers[_hkey(name)] = [_hval(value)]

    def add_header(self, name, value):
        self._headers.setdefault(_hkey(name), []).append(_hval(value))

    def iter_headers(self):
        return self.headerlist

    def _wsgi_status_line(self):
        return self._status_line.encode('utf8', 'surrogateescape').decode('latin1')

    @property
    def headerlist(self):
        out = []
        headers = list(self._headers.items())
        if 'Content-Type' not in self._headers:
            headers.append(('Content-Type', [self.default_content_type]))
        if self._status_code in self.bad_headers:
            bad_headers = self.bad_headers[self._status_code]
            headers = [h for h in headers if h[0] not in bad_headers]
        out += [(name, val) for (name, vals) in headers for val in vals]
        if self._cookies:
            for c in self._cookies.values():
                out.append(('Set-Cookie', _hval(c.OutputString())))
        out = [(k, v.encode('utf8', 'surrogateescape').decode('latin1')) for (k, v) in out]
        return out

    content_type = HeaderProperty('Content-Type')
    content_length = HeaderProperty('Content-Length', reader=int, default=-1)
    expires = HeaderProperty(
        'Expires',
        reader=lambda x: datetime.fromtimestamp(parse_date(x), UTC),
        writer=lambda x: http_date(x))

    @property
    def charset(self, default='UTF-8'):
        if 'charset=' in self.content_type:
            return self.content_type.split('charset=')[-1].split(';')[0].strip()
        return default

    def set_cookie(self, name, value, secret=None, digestmod=hashlib.sha256, **options):
        if not self._cookies:
            self._cookies = SimpleCookie()

        if py < (3, 8, 0):
            Morsel._reserved.setdefault('samesite', 'SameSite')

        if secret:
            encoded = base64.b64encode(tob(json_dumps([name, str(value)])))
            sig = base64.b64encode(hmac.new(tob(secret), encoded,
                                            digestmod=digestmod).digest())
            value = touni(b'!' + sig + b'?' + encoded)
        elif not isinstance(value, str):
            raise TypeError('Secret key required for non-string cookies.')

        if len(name) + len(value) > 3800:
            raise ValueError('Content does not fit into a cookie.')

        self._cookies[name] = value

        for key, value in options.items():
            if key in ('max_age', 'maxage'):
                key = 'max-age'
                if isinstance(value, timedelta):
                    value = int(value.total_seconds())
            if key == 'expires':
                value = http_date(value)
            if key in ('same_site', 'samesite'):
                key, value = 'samesite', (value or "none").lower()
                if value not in ('lax', 'strict', 'none'):
                    raise CookieError("Invalid value for SameSite")
            if key in ('secure', 'httponly') and not value:
                continue
            self._cookies[name][key] = value

    def delete_cookie(self, key, **kwargs):
        kwargs['max_age'] = -1
        kwargs['expires'] = 0
        self.set_cookie(key, '', **kwargs)

    def __repr__(self):
        out = ''
        for name, value in self.headerlist:
            out += '%s: %s\n' % (name.title(), value.strip())
        return out

def _local_property():
    ls = threading.local()

    def fget(_):
        try:
            return ls.var
        except AttributeError:
            raise RuntimeError("Request context not initialized.")

    def fset(_, value):
        ls.var = value

    def fdel(_):
        del ls.var

    return property(fget, fset, fdel, 'Thread-local property')

class LocalRequest(BaseRequest):
    bind = BaseRequest.__init__
    environ = _local_property()

class LocalResponse(BaseResponse):
    bind = BaseResponse.__init__
    _status_line = _local_property()
    _status_code = _local_property()
    _cookies = _local_property()
    _headers = _local_property()
    body = _local_property()

Request = BaseRequest
Response = BaseResponse

class RequestContext:

    __slots__ = ('request', 'response', 'app', 'route',
                 'request_id', 'user', 'state', '_lazy')

    def __init__(self, req=None, resp=None, app=None):
        self.request = req
        self.response = resp
        self.app = app
        self.route = None
        self.request_id = None
        self.user = None
        self.state = {}
        self._lazy = {}

    def lazy(self, key, factory):
        self._lazy[key] = factory

    def __getattr__(self, name):
        if name in ('state', '_lazy'):
            raise AttributeError(name)
        try:
            state = object.__getattribute__(self, 'state')
            if name in state:
                return state[name]
        except AttributeError:
            pass
        try:
            lazy = object.__getattribute__(self, '_lazy')
            if name in lazy:
                val = lazy[name]()
                state = object.__getattribute__(self, 'state')
                state[name] = val
                return val
        except AttributeError:
            pass
        raise AttributeError(f'RequestContext has no attribute {name!r}')

    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            self.state[name] = value

class LocalContext(RequestContext):
    bind = RequestContext.__init__
    request = _local_property()
    response = _local_property()
    app = _local_property()
    route = _local_property()
    request_id = _local_property()
    user = _local_property()
    state = _local_property()
    _lazy = _local_property()

class Middleware:
    name = None
    order = 50

    def __call__(self, ctx, next_handler):
        return next_handler(ctx)

class MiddlewarePipeline:

    def __init__(self):
        self._middleware = []
        self._sorted = False
        self._global_chain = None

    def add(self, middleware, routes=None, order=None):
        if order is not None:
            middleware.order = order
        pattern = re.compile(routes) if isinstance(routes, str) else routes
        self._middleware.append((middleware, pattern))
        self._sorted = False
        self._global_chain = None

    def remove(self, middleware):
        self._middleware = [(m, p) for m, p in self._middleware
                           if m is not middleware]
        self._global_chain = None

    def _get_chain(self, path):
        if not self._sorted:
            self._middleware.sort(key=lambda x: getattr(x[0], 'order', 50))
            self._sorted = True
        has_patterns = any(pat is not None for _, pat in self._middleware)
        if not has_patterns:
            if self._global_chain is None:
                self._global_chain = [m for m, _ in self._middleware]
            return self._global_chain
        return [m for m, pat in self._middleware
                if pat is None or pat.match(path)]

    def execute(self, ctx, handler):
        chain = self._get_chain(ctx.request.path)

        def build(remaining, final):
            if not remaining:
                return final
            current = remaining[0]
            rest = remaining[1:]

            def step(c):
                nxt = build(rest, final)
                result = current(c, nxt)
                if inspect.iscoroutine(result):
                    result = _run_async(result)
                return result

            return step

        pipeline = build(chain, lambda c: handler())
        return pipeline(ctx)

class RequestIDMiddleware(Middleware):
    name = 'request_id'
    order = 1

    def __call__(self, ctx, next_handler):
        req_id = ctx.request.get_header('X-Request-ID',
                                         str(uuid.uuid4()))
        ctx.request_id = req_id
        result = next_handler(ctx)
        ctx.response.set_header('X-Request-ID', req_id)
        return result

class RequestLoggerMiddleware(Middleware):
    name = 'request_logger'
    order = 2

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger('lcore.access')

    def __call__(self, ctx, next_handler):
        start = time.monotonic()
        try:
            result = next_handler(ctx)
            return result
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            self.logger.info(json_dumps({
                'timestamp': datetime.now(UTC).isoformat(),
                'request_id': getattr(ctx, 'request_id', None),
                'method': ctx.request.method,
                'path': ctx.request.path,
                'status': ctx.response.status_code,
                'duration_ms': round(duration_ms, 2),
                'remote_addr': ctx.request.remote_addr,
            }))

class SecurityHeadersMiddleware(Middleware):
    name = 'security_headers'
    order = 5

    DEFAULTS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    }

    def __init__(self, hsts=False, hsts_max_age=31536000, **overrides):
        self.headers = {**self.DEFAULTS, **overrides}
        if hsts:
            self.headers['Strict-Transport-Security'] = \
                'max-age=%d; includeSubDomains' % hsts_max_age

    def __call__(self, ctx, next_handler):
        result = next_handler(ctx)
        for key, value in self.headers.items():
            ctx.response.set_header(key, value)
        return result

class CSRFMiddleware(Middleware):
    name = 'csrf'
    order = 10

    def __init__(self, secret=None, cookie_name='_csrf_token',
                 header_name='X-CSRF-Token',
                 safe_methods=('GET', 'HEAD', 'OPTIONS')):
        self.secret = secret or hashlib.sha256(os.urandom(32)).hexdigest()
        self.cookie_name = cookie_name
        self.header_name = header_name
        self.safe_methods = safe_methods

    def _generate_token(self):
        return hashlib.sha256(os.urandom(32)).hexdigest()

    def __call__(self, ctx, next_handler):
        token = ctx.request.get_cookie(self.cookie_name)
        if not token:
            token = self._generate_token()
            ctx.response.set_cookie(self.cookie_name, token,
                                     httponly=True, samesite='Strict')
        ctx.csrf_token = token

        if ctx.request.method not in self.safe_methods:
            submitted = (ctx.request.get_header(self.header_name)
                         or ctx.request.forms.get(self.cookie_name))
            if not submitted or not _lscmp(submitted, token):
                raise HTTPError(403, 'CSRF token validation failed')

        return next_handler(ctx)

class CORSMiddleware(Middleware):
    name = 'cors'
    order = 3

    def __init__(self, allow_origins='*', allow_methods=None,
                 allow_headers=None, expose_headers=None,
                 allow_credentials=False, max_age=86400):
        self.allow_origins = allow_origins
        self.allow_methods = allow_methods or ['GET', 'POST', 'PUT', 'DELETE',
                                               'PATCH', 'OPTIONS']
        self.allow_headers = allow_headers or ['Content-Type', 'Authorization',
                                               'X-Requested-With']
        self.expose_headers = expose_headers or []
        self.allow_credentials = allow_credentials
        self.max_age = max_age

    def _origin_allowed(self, origin):
        if not origin:
            return False
        if self.allow_origins == '*':
            return True
        if isinstance(self.allow_origins, str):
            return origin == self.allow_origins
        return origin in self.allow_origins

    def _set_cors_headers(self, ctx, origin):
        resp = ctx.response
        if self.allow_origins == '*' and not self.allow_credentials:
            resp.set_header('Access-Control-Allow-Origin', '*')
        else:
            resp.set_header('Access-Control-Allow-Origin', origin)
            resp.add_header('Vary', 'Origin')
        if self.allow_credentials:
            resp.set_header('Access-Control-Allow-Credentials', 'true')
        if self.expose_headers:
            resp.set_header('Access-Control-Expose-Headers',
                            ', '.join(self.expose_headers))

    def __call__(self, ctx, next_handler):
        origin = ctx.request.get_header('Origin')
        if not self._origin_allowed(origin):
            return next_handler(ctx)

        if ctx.request.method == 'OPTIONS':
            ctx.response.status = 204
            self._set_cors_headers(ctx, origin)
            ctx.response.set_header('Access-Control-Allow-Methods',
                                     ', '.join(self.allow_methods))
            ctx.response.set_header('Access-Control-Allow-Headers',
                                     ', '.join(self.allow_headers))
            ctx.response.set_header('Access-Control-Max-Age',
                                     str(self.max_age))
            return ''

        result = next_handler(ctx)
        self._set_cors_headers(ctx, origin)
        return result


class CompressionMiddleware(Middleware):
    name = 'compression'
    order = 90

    def __init__(self, min_size=256, level=6,
                 content_types=None):
        self.min_size = min_size
        self.level = level
        self.content_types = content_types or (
            'text/', 'application/json', 'application/javascript',
            'application/xml', 'application/xhtml+xml',
        )

    def _should_compress(self, ctx):
        ct = ctx.response.get_header('Content-Type', '') or 'text/html'
        return any(ct.startswith(t) for t in self.content_types)

    def __call__(self, ctx, next_handler):
        result = next_handler(ctx)
        accept = ctx.request.get_header('Accept-Encoding', '')
        if 'gzip' not in accept:
            return result
        if not self._should_compress(ctx):
            return result
        if ctx.response.get_header('Content-Encoding'):
            return result
        body = result if isinstance(result, bytes) else tob(str(result))
        if len(body) < self.min_size:
            return result
        compressed = gzip.compress(body, compresslevel=self.level)
        ctx.response.set_header('Content-Encoding', 'gzip')
        ctx.response.set_header('Content-Length', str(len(compressed)))
        ctx.response.set_header('Vary', 'Accept-Encoding')
        return compressed


class BodyLimitMiddleware(Middleware):
    name = 'body_limit'
    order = 0

    def __init__(self, max_size=10 * 1024 * 1024):
        self.max_size = max_size

    def __call__(self, ctx, next_handler):
        cl = ctx.request.content_length
        if cl > self.max_size:
            raise HTTPError(413, 'Request entity too large (limit: %d bytes)'
                            % self.max_size)
        return next_handler(ctx)


class MiddlewareHook(Middleware):
    name = None
    order = 50

    def pre(self, ctx):
        pass

    def post(self, ctx, result):
        return result

    def __call__(self, ctx, next_handler):
        pre_result = self.pre(ctx)
        if _is_async(self.pre):
            pre_result = _run_async(pre_result)
        if isinstance(pre_result, HTTPResponse):
            return pre_result
        result = next_handler(ctx)
        post_result = self.post(ctx, result)
        if _is_async(self.post):
            post_result = _run_async(post_result)
        return post_result if post_result is not None else result


class DependencyContainer:

    SINGLETON = 'singleton'
    SCOPED = 'scoped'
    TRANSIENT = 'transient'

    def __init__(self):
        self._registry = {}
        self._singletons = {}

    def register(self, name, factory, lifetime='singleton'):
        if lifetime not in (self.SINGLETON, self.SCOPED, self.TRANSIENT):
            raise ValueError("lifetime must be 'singleton', 'scoped', or 'transient'")
        self._registry[name] = (factory, lifetime)

    def resolve(self, name, ctx=None):
        if name not in self._registry:
            raise KeyError("Dependency %r not registered" % name)
        factory, lifetime = self._registry[name]
        if lifetime == self.SINGLETON:
            if name not in self._singletons:
                self._singletons[name] = factory()
            return self._singletons[name]
        elif lifetime == self.SCOPED:
            if ctx is None:
                raise RuntimeError("Scoped dependency %r requires a request context" % name)
            scoped = ctx.state.get('_di_scoped')
            if scoped is None:
                scoped = {}
                ctx.state['_di_scoped'] = scoped
            if name not in scoped:
                scoped[name] = factory()
            return scoped[name]
        else:
            return factory()

    def _begin_scope(self, ctx):
        for name, (factory, lifetime) in self._registry.items():
            if lifetime == self.TRANSIENT:
                ctx.lazy(name, factory)
            elif lifetime == self.SCOPED:
                ctx.lazy(name, lambda n=name: self.resolve(n, ctx))
            else:
                ctx.state[name] = self.resolve(name)

    def _end_scope(self, ctx):
        scoped = ctx.state.get('_di_scoped')
        if scoped:
            for val in scoped.values():
                if hasattr(val, 'close'):
                    try:
                        result = val.close()
                        if inspect.iscoroutine(result):
                            _run_async(result)
                    except Exception:
                        pass
            scoped.clear()

    def __contains__(self, name):
        return name in self._registry

    def __len__(self):
        return len(self._registry)


class BackgroundTaskPool:
    """Thread-pool for fire-and-forget background tasks."""

    def __init__(self, max_workers=4):
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self._futures = []
        self._lock = threading.Lock()

    def submit(self, fn, *args, **kwargs):
        """Submit a task for background execution. Returns a Future."""
        future = self._pool.submit(fn, *args, **kwargs)
        with self._lock:
            self._futures = [f for f in self._futures if not f.done()]
            self._futures.append(future)
        return future

    @property
    def pending(self):
        """Number of tasks still running or queued."""
        with self._lock:
            self._futures = [f for f in self._futures if not f.done()]
            return len(self._futures)

    def shutdown(self, wait=True):
        """Shut down the pool, optionally waiting for pending tasks."""
        self._pool.shutdown(wait=wait)


def rate_limit(limit, per=60, max_buckets=10000):
    buckets = {}
    lock = threading.Lock()
    _last_cleanup = [0.0]

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*a, **ka):
            addr = request.remote_addr or '0.0.0.0'
            now = time.monotonic()
            with lock:
                if now - _last_cleanup[0] > per:
                    _last_cleanup[0] = now
                    stale = [k for k, v in buckets.items()
                             if now - v[0] > per]
                    for k in stale:
                        del buckets[k]
                    if len(buckets) > max_buckets:
                        oldest = sorted(buckets, key=lambda k: buckets[k][0])
                        for k in oldest[:len(buckets) - max_buckets]:
                            del buckets[k]
                if addr not in buckets:
                    buckets[addr] = [now, limit]
                tokens_info = buckets[addr]
                elapsed = now - tokens_info[0]
                tokens_info[0] = now
                tokens_info[1] = min(limit,
                                     tokens_info[1] + elapsed * (limit / per))
                if tokens_info[1] < 1:
                    raise HTTPError(429, 'Too Many Requests')
                tokens_info[1] -= 1
            return func(*a, **ka)
        return wrapper
    return decorator

def validate_request(body=None, query=None):
    import dataclasses

    def _validate_dict_schema(data, schema, label='field'):
        errors = []
        for name, expected_type in schema.items():
            if name not in data:
                errors.append('Missing %s: %s' % (label, name))
            elif expected_type in (int, float, str, bool) and \
                 not isinstance(data[name], expected_type):
                errors.append('%s: expected %s' % (name, expected_type.__name__))
        return errors

    def _validate_dataclass_schema(data, schema):
        errors = []
        for field in dataclasses.fields(schema):
            if field.name not in data:
                if field.default is dataclasses.MISSING and \
                   field.default_factory is dataclasses.MISSING:
                    errors.append('Missing field: %s' % field.name)
            else:
                val = data[field.name]
                if field.type in (int, float, str, bool) and \
                   not isinstance(val, field.type):
                    errors.append('%s: expected %s'
                                  % (field.name, field.type.__name__))
        return errors

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*a, **ka):
            if body and request.json is not None:
                data = request.json
                if not isinstance(data, dict):
                    raise HTTPError(400, 'Request body must be a JSON object')
                if isinstance(body, dict):
                    errors = _validate_dict_schema(data, body)
                else:
                    errors = _validate_dataclass_schema(data, body)
                if errors:
                    raise HTTPError(422,
                                    'Validation failed: ' + '; '.join(errors))
            if query:
                errors = []
                if isinstance(query, dict):
                    for name, expected_type in query.items():
                        val = request.query.get(name)
                        if val is None:
                            errors.append('Missing query param: %s' % name)
                else:
                    for field in dataclasses.fields(query):
                        val = request.query.get(field.name)
                        if val is None and field.default is dataclasses.MISSING \
                           and field.default_factory is dataclasses.MISSING:
                            errors.append('Missing query param: %s' % field.name)
                if errors:
                    raise HTTPError(400,
                                    'Validation failed: ' + '; '.join(errors))
            return func(*a, **ka)
        return wrapper
    return decorator

class HTTPResponse(Response, LcoreException):

    def __init__(self, body='', status=None, headers=None, **more_headers):
        super(HTTPResponse, self).__init__(body, status, headers, **more_headers)

    def apply(self, other):
        other._status_code = self._status_code
        other._status_line = self._status_line
        other._headers = self._headers
        other._cookies = self._cookies
        other.body = self.body

class HTTPError(HTTPResponse):

    default_status = 500

    def __init__(self,
                 status=None,
                 body=None,
                 exception=None,
                 traceback=None, **more_headers):
        self.exception = exception
        self.traceback = traceback
        super(HTTPError, self).__init__(body, status, **more_headers)

class PluginError(LcoreException):
    pass

class JSONPlugin:
    name = 'json'
    api = 2

    def __init__(self, json_dumps=json_dumps):
        self.json_dumps = json_dumps

    def setup(self, app):
        app.config._define('json.enable', default=True, validate=bool,
                          help="Enable or disable automatic dict->json filter.")
        app.config._define('json.ascii', default=False, validate=bool,
                          help="Use only 7-bit ASCII characters in output.")
        app.config._define('json.indent', default=True, validate=bool,
                          help="Add whitespace to make json more readable.")
        app.config._define('json.dump_func', default=None,
                          help="If defined, use this function to transform"
                               " dict into json. The other options no longer"
                               " apply.")

    def apply(self, callback, route):
        dumps = self.json_dumps
        if not self.json_dumps: return callback

        def _json_convert(rv):
            if isinstance(rv, dict):
                json_response = dumps(rv)
                response.content_type = 'application/json'
                return json_response
            elif isinstance(rv, HTTPResponse) and isinstance(rv.body, dict):
                rv.body = dumps(rv.body)
                rv.content_type = 'application/json'
            return rv

        @functools.wraps(callback)
        def wrapper(*a, **ka):
            try:
                rv = callback(*a, **ka)
            except HTTPResponse as resp:
                rv = resp

            if inspect.iscoroutine(rv):
                rv = _run_async(rv)
            return _json_convert(rv)

        return wrapper

class TemplatePlugin:
    name = 'template'
    api = 2

    def setup(self, app):
        app.tpl = self

    def apply(self, callback, route):
        conf = route.config.get('template')
        if isinstance(conf, (tuple, list)) and len(conf) == 2:
            return view(conf[0], **conf[1])(callback)
        elif isinstance(conf, str):
            return view(conf)(callback)
        else:
            return callback

class _ImportRedirect:
    def __init__(self, name, impmask):
        self.name = name
        self.impmask = impmask
        self.module = sys.modules.setdefault(name, new_module(name))
        self.module.__dict__.update({
            '__file__': __file__,
            '__path__': [],
            '__all__': [],
            '__loader__': self
        })
        sys.meta_path.append(self)

    def find_spec(self, fullname, path, target=None):
        if '.' not in fullname: return
        if fullname.rsplit('.', 1)[0] != self.name: return
        from importlib.util import spec_from_loader
        return spec_from_loader(fullname, self)

    def find_module(self, fullname, path=None):
        if '.' not in fullname: return
        if fullname.rsplit('.', 1)[0] != self.name: return
        return self

    def create_module(self, spec):
        return self.load_module(spec.name)

    def exec_module(self, module):
        pass

    def load_module(self, fullname):
        if fullname in sys.modules: return sys.modules[fullname]
        modname = fullname.rsplit('.', 1)[1]
        realname = self.impmask % modname
        __import__(realname)
        module = sys.modules[fullname] = sys.modules[realname]
        setattr(self.module, modname, module)
        module.__loader__ = self
        return module

class MultiDict(DictMixin):

    def __init__(self, *a, **k):
        self.dict = dict((k, [v]) for (k, v) in dict(*a, **k).items())

    def __len__(self):
        return len(self.dict)

    def __iter__(self):
        return iter(self.dict)

    def __contains__(self, key):
        return key in self.dict

    def __delitem__(self, key):
        del self.dict[key]

    def __getitem__(self, key):
        return self.dict[key][-1]

    def __setitem__(self, key, value):
        self.append(key, value)

    def keys(self):
        return self.dict.keys()

    def values(self):
        return (v[-1] for v in self.dict.values())

    def items(self):
        return ((k, v[-1]) for k, v in self.dict.items())

    def allitems(self):
        return ((k, v) for k, vl in self.dict.items() for v in vl)

    iterkeys = keys
    itervalues = values
    iteritems = items
    iterallitems = allitems

    def get(self, key, default=None, index=-1, type=None):
        try:
            val = self.dict[key][index]
            return type(val) if type else val
        except Exception:
            pass
        return default

    def append(self, key, value):
        self.dict.setdefault(key, []).append(value)

    def replace(self, key, value):
        self.dict[key] = [value]

    def getall(self, key):
        return self.dict.get(key) or []

    getone = get
    getlist = getall

class FormsDict(MultiDict):

    def decode(self, encoding=None):
        copy = FormsDict()
        for key, value in self.allitems():
            copy[key] = value
        return copy

    def getunicode(self, name, default=None, encoding=None):
        return self.get(name, default)

    def __getattr__(self, name, default=str()):
        if name.startswith('__') and name.endswith('__'):
            return super(FormsDict, self).__getattr__(name)
        return self.get(name, default=default)

class HeaderDict(MultiDict):

    def __init__(self, *a, **ka):
        self.dict = {}
        if a or ka: self.update(*a, **ka)

    def __contains__(self, key):
        return _hkey(key) in self.dict

    def __delitem__(self, key):
        del self.dict[_hkey(key)]

    def __getitem__(self, key):
        return self.dict[_hkey(key)][-1]

    def __setitem__(self, key, value):
        self.dict[_hkey(key)] = [_hval(value)]

    def append(self, key, value):
        self.dict.setdefault(_hkey(key), []).append(_hval(value))

    def replace(self, key, value):
        self.dict[_hkey(key)] = [_hval(value)]

    def getall(self, key):
        return self.dict.get(_hkey(key)) or []

    def get(self, key, default=None, index=-1):
        return MultiDict.get(self, _hkey(key), default, index)

    def filter(self, names):
        for name in (_hkey(n) for n in names):
            if name in self.dict:
                del self.dict[name]

class WSGIHeaderDict(DictMixin):
    cgikeys = ('CONTENT_TYPE', 'CONTENT_LENGTH')

    def __init__(self, environ):
        self.environ = environ

    def _ekey(self, key):
        key = key.replace('-', '_').upper()
        if key in self.cgikeys:
            return key
        return 'HTTP_' + key

    def raw(self, key, default=None):
        return self.environ.get(self._ekey(key), default)

    def __getitem__(self, key):
        return _wsgi_recode(self.environ[self._ekey(key)])

    def __setitem__(self, key, value):
        raise TypeError("%s is read-only." % self.__class__)

    def __delitem__(self, key):
        raise TypeError("%s is read-only." % self.__class__)

    def __iter__(self):
        for key in self.environ:
            if key[:5] == 'HTTP_':
                yield _hkey(key[5:])
            elif key in self.cgikeys:
                yield _hkey(key)

    def keys(self):
        return [x for x in self]

    def __len__(self):
        return len(self.keys())

    def __contains__(self, key):
        return self._ekey(key) in self.environ

class ConfigDict(dict):

    __slots__ = ('_meta', '_change_listener', '_overlays', '_virtual_keys', '_source', '__weakref__')

    def __init__(self):
        self._meta = {}
        self._change_listener = []
        self._overlays = []
        self._source = None
        self._virtual_keys = set()

    def load_module(self, name, squash=True):
        config_obj = load(name)
        obj = {key: getattr(config_obj, key)
               for key in dir(config_obj) if key.isupper()}

        if squash:
            self.load_dict(obj)
        else:
            self.update(obj)
        return self

    def load_config(self, filename, **options):
        options.setdefault('allow_no_value', True)
        options.setdefault('interpolation', configparser.ExtendedInterpolation())
        conf = configparser.ConfigParser(**options)
        conf.read(filename)
        for section in conf.sections():
            for key in conf.options(section):
                value = conf.get(section, key)
                if section not in ('lcore', 'ROOT'):
                    key = section + '.' + key
                self[key.lower()] = value
        return self

    def load_dict(self, source, namespace=''):
        for key, value in source.items():
            if isinstance(key, str):
                nskey = (namespace + '.' + key).strip('.')
                if isinstance(value, dict):
                    self.load_dict(value, namespace=nskey)
                else:
                    self[nskey] = value
            else:
                raise TypeError('Key has type %r (not a string)' % type(key))
        return self

    def update(self, *a, **ka):
        prefix = ''
        if a and isinstance(a[0], str):
            prefix = a[0].strip('.') + '.'
            a = a[1:]
        for key, value in dict(*a, **ka).items():
            self[prefix + key] = value

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]

    def __setitem__(self, key, value):
        if not isinstance(key, str):
            raise TypeError('Key has type %r (not a string)' % type(key))

        self._virtual_keys.discard(key)

        value = self.meta_get(key, 'filter', lambda x: x)(value)
        if key in self and self[key] is value:
            return

        self._on_change(key, value)
        dict.__setitem__(self, key, value)

        for overlay in self._iter_overlays():
            overlay._set_virtual(key, value)

    def __delitem__(self, key):
        if key not in self:
            raise KeyError(key)
        if key in self._virtual_keys:
            raise KeyError("Virtual keys cannot be deleted: %s" % key)

        if self._source and key in self._source:
            dict.__delitem__(self, key)
            self._set_virtual(key, self._source[key])
        else:
            self._on_change(key, None)
            dict.__delitem__(self, key)
            for overlay in self._iter_overlays():
                overlay._delete_virtual(key)

    def _set_virtual(self, key, value):
        if key in self and key not in self._virtual_keys:
            return

        self._virtual_keys.add(key)
        if key in self and self[key] is not value:
            self._on_change(key, value)
        dict.__setitem__(self, key, value)
        for overlay in self._iter_overlays():
            overlay._set_virtual(key, value)

    def _delete_virtual(self, key):
        if key not in self._virtual_keys:
            return

        if key in self:
            self._on_change(key, None)
        dict.__delitem__(self, key)
        self._virtual_keys.discard(key)
        for overlay in self._iter_overlays():
            overlay._delete_virtual(key)

    def _on_change(self, key, value):
        for cb in self._change_listener:
            if cb(self, key, value):
                return True

    def _add_change_listener(self, func):
        self._change_listener.append(func)
        return func

    def meta_get(self, key, metafield, default=None):
        return self._meta.get(key, {}).get(metafield, default)

    def meta_set(self, key, metafield, value):
        self._meta.setdefault(key, {})[metafield] = value

    def meta_list(self, key):
        return self._meta.get(key, {}).keys()

    def _define(self, key, default=_UNSET, help=_UNSET, validate=_UNSET):
        if default is not _UNSET:
            self.setdefault(key, default)
        if help is not _UNSET:
            self.meta_set(key, 'help', help)
        if validate is not _UNSET:
            self.meta_set(key, 'validate', validate)

    def _iter_overlays(self):
        for ref in self._overlays:
            overlay = ref()
            if overlay is not None:
                yield overlay

    def _make_overlay(self):
        self._overlays[:] = [ref for ref in self._overlays if ref() is not None]

        overlay = ConfigDict()
        overlay._meta = self._meta
        overlay._source = self
        self._overlays.append(weakref.ref(overlay))
        for key in self:
            overlay._set_virtual(key, self[key])
        return overlay

    def load_env(self, prefix='LCORE_', strip_prefix=True):
        for key, value in os.environ.items():
            if key.startswith(prefix):
                conf_key = key[len(prefix):].lower().replace('__', '.') \
                    if strip_prefix else key.lower()
                self[conf_key] = value
        return self

    def load_json(self, filename):
        with open(filename, 'r') as f:
            data = json_loads(f.read())
        return self.load_dict(data)

    def load_dotenv(self, filename='.env'):
        if not os.path.isfile(filename):
            return self
        with open(filename, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                key = key.strip()
                if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
                    continue
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
        return self

    def validate_config(self, schema):
        import dataclasses
        if not dataclasses.is_dataclass(schema):
            raise TypeError('Schema must be a dataclass')
        errors = []
        for field in dataclasses.fields(schema):
            key = field.name.replace('_', '.')
            if key not in self and field.default is dataclasses.MISSING \
               and field.default_factory is dataclasses.MISSING:
                errors.append('Missing required config key: %s' % key)
            elif key in self:
                val = self[key]
                if field.type in (int, float, bool, str) \
                   and not isinstance(val, field.type):
                    try:
                        if field.type is bool:
                            self[key] = val.lower() in ('true', '1', 'yes')
                        else:
                            self[key] = field.type(val)
                    except (ValueError, AttributeError):
                        errors.append('Config key %s: expected %s, got %s'
                                      % (key, field.type.__name__,
                                         type(val).__name__))
        if errors:
            raise ValueError('Config validation errors:\n' + '\n'.join(errors))
        return self

class AppStack(list):

    def __call__(self):
        return self.default

    def push(self, value=None):
        if not isinstance(value, Lcore):
            value = Lcore()
        self.append(value)
        return value
    new_app = push

    @property
    def default(self):
        try:
            return self[-1]
        except IndexError:
            return self.push()

class WSGIFileWrapper:
    def __init__(self, fp, buffer_size=1024 * 64):
        self.fp, self.buffer_size = fp, buffer_size
        for attr in 'fileno', 'close', 'read', 'readlines', 'tell', 'seek':
            if hasattr(fp, attr): setattr(self, attr, getattr(fp, attr))

    def __iter__(self):
        buff, read = self.buffer_size, self.read
        part = read(buff)
        while part:
            yield part
            part = read(buff)

class _closeiter:

    def __init__(self, iterator, close=None):
        self.iterator = iterator
        self.close_callbacks = makelist(close)

    def __iter__(self):
        return iter(self.iterator)

    def close(self):
        for func in self.close_callbacks:
            func()

def _try_close(obj):
    try:
        if hasattr(obj, 'close'):
            obj.close()
    except Exception:
        pass

class ResourceManager:

    def __init__(self, base='./', opener=open, cachemode='all'):
        self.opener = opener
        self.base = base
        self.cachemode = cachemode

        self.path = []
        self.cache = {}

    def add_path(self, path, base=None, index=None, create=False):
        base = os.path.abspath(os.path.dirname(base or self.base))
        path = os.path.abspath(os.path.join(base, os.path.dirname(path)))
        path += os.sep
        if path in self.path:
            self.path.remove(path)
        if create and not os.path.isdir(path):
            os.makedirs(path)
        if index is None:
            self.path.append(path)
        else:
            self.path.insert(index, path)
        self.cache.clear()
        return os.path.exists(path)

    def __iter__(self):
        search = self.path[:]
        while search:
            path = search.pop()
            if not os.path.isdir(path): continue
            for name in os.listdir(path):
                full = os.path.join(path, name)
                if os.path.isdir(full): search.append(full)
                else: yield full

    def lookup(self, name):
        if name not in self.cache or DEBUG:
            for path in self.path:
                fpath = os.path.join(path, name)
                if os.path.isfile(fpath):
                    if self.cachemode in ('all', 'found'):
                        self.cache[name] = fpath
                    return fpath
            if self.cachemode == 'all':
                self.cache[name] = None
        return self.cache[name]

    def open(self, name, mode='r', *args, **kwargs):
        fname = self.lookup(name)
        if not fname: raise IOError("Resource %r not found." % name)
        return self.opener(fname, mode=mode, *args, **kwargs)

class FileUpload:
    def __init__(self, fileobj, name, filename, headers=None):
        self.file = fileobj
        self.name = name
        self.raw_filename = filename
        self.headers = HeaderDict(headers) if headers else HeaderDict()

    content_type = HeaderProperty('Content-Type')
    content_length = HeaderProperty('Content-Length', reader=int, default=-1)

    def get_header(self, name, default=None):
        return self.headers.get(name, default)

    @cached_property
    def filename(self):
        fname = self.raw_filename
        fname = normalize('NFKD', fname)
        fname = fname.encode('ASCII', 'ignore').decode('ASCII')
        fname = os.path.basename(fname.replace('\\', os.path.sep))
        fname = re.sub(r'[^a-zA-Z0-9-_.\s]', '', fname).strip()
        fname = re.sub(r'[-\s]+', '-', fname).strip('.-')
        return fname[:255] or 'empty'

    def _copy_file(self, fp, chunk_size=2 ** 16):
        read, write, offset = self.file.read, fp.write, self.file.tell()
        while 1:
            buf = read(chunk_size)
            if not buf: break
            write(buf)
        self.file.seek(offset)

    def save(self, destination, overwrite=False, chunk_size=2 ** 16):
        if isinstance(destination, str):
            if os.path.isdir(destination):
                destination = os.path.join(destination, self.filename)
            if not overwrite and os.path.exists(destination):
                raise IOError('File exists.')
            with open(destination, 'wb') as fp:
                self._copy_file(fp, chunk_size)
        else:
            self._copy_file(destination, chunk_size)

def pretty_error_page(exception, traceback_str=None):
    if traceback_str is None:
        traceback_str = format_exc()
    status = getattr(exception, 'status_code', 500)
    body = getattr(exception, 'body', None) or str(exception)
    exc_type = type(exception).__name__
    exc_repr = repr(exception)
    page = (
        '<!DOCTYPE html>\n'
        '<html>\n'
        '<head><title>%d %s</title>\n'
        '<style>\n'
        'body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;'
        'margin:0;padding:0;background:#1a1a2e;color:#e0e0e0;}\n'
        '.container{max-width:900px;margin:40px auto;padding:0 20px;}\n'
        '.error-box{background:#16213e;border-left:4px solid #e94560;'
        'border-radius:4px;padding:24px 32px;margin-bottom:24px;}\n'
        '.error-box h1{color:#e94560;margin:0 0 8px 0;font-size:28px;}\n'
        '.error-box p{color:#a0a0b8;margin:0;font-size:16px;}\n'
        '.section{background:#16213e;border-radius:4px;padding:20px 28px;margin-bottom:16px;}\n'
        '.section h2{color:#0f3460;margin:0 0 12px 0;font-size:18px;'
        'border-bottom:1px solid #0f3460;padding-bottom:8px;}\n'
        'pre{background:#0a0a1a;color:#53d769;padding:16px;border-radius:4px;'
        'overflow-x:auto;font-size:13px;line-height:1.5;margin:0;}\n'
        '.meta{display:flex;gap:24px;flex-wrap:wrap;}\n'
        '.meta-item{background:#0f3460;border-radius:4px;padding:8px 16px;font-size:13px;}\n'
        '.meta-item span{color:#e94560;font-weight:bold;}\n'
        '</style></head>\n'
        '<body><div class="container">\n'
        '<div class="error-box"><h1>%d %s</h1><p>%s</p></div>\n'
        '<div class="meta">'
        '<div class="meta-item">Type: <span>%s</span></div>'
        '<div class="meta-item">Status: <span>%d</span></div>'
        '</div>\n'
        '<div class="section"><h2>Exception</h2><pre>%s</pre></div>\n'
        '<div class="section"><h2>Traceback</h2><pre>%s</pre></div>\n'
        '</div></body></html>'
    ) % (
        status, html_escape(HTTP_CODES.get(status, 'Error')),
        status, html_escape(HTTP_CODES.get(status, 'Error')),
        html_escape(body),
        html_escape(exc_type), status,
        html_escape(exc_repr),
        html_escape(traceback_str),
    )
    return page

def abort(code=500, text='Unknown Error.'):
    raise HTTPError(code, text)

def redirect(url, code=None):
    if not code:
        code = 303 if request.get('SERVER_PROTOCOL') == "HTTP/1.1" else 302
    res = response.copy(cls=HTTPResponse)
    res.status = code
    res.body = ""
    res.set_header('Location', urljoin(request.url, url))
    raise res

def _rangeiter(fp, offset, limit, bufsize=1024 * 1024):
    fp.seek(offset)
    while limit > 0:
        part = fp.read(min(limit, bufsize))
        if not part:
            break
        limit -= len(part)
        yield part

def static_file(filename, root,
                mimetype=True,
                download=False,
                charset='UTF-8',
                etag=None,
                headers=None):

    root = os.path.join(os.path.realpath(root), '')
    filename = os.path.realpath(os.path.join(root, filename.strip('/\\')))
    headers = headers.copy() if headers else {}
    getenv = request.environ.get

    if not filename.startswith(root):
        return HTTPError(403, "Access denied.")
    if not os.path.isfile(filename):
        return HTTPError(404, "File does not exist.")
    if not os.access(filename, os.R_OK):
        return HTTPError(403, "You do not have permission to access this file.")

    if mimetype is True:
        name = download if isinstance(download, str) else filename
        mimetype, encoding = mimetypes.guess_type(name)
        if encoding == 'gzip':
            mimetype = 'application/gzip'
        elif encoding:
            mimetype = 'application/x-' + encoding

    if charset and mimetype and 'charset=' not in mimetype \
       and (mimetype[:5] == 'text/' or mimetype == 'application/javascript'):
        mimetype += '; charset=%s' % charset

    if mimetype:
        headers['Content-Type'] = mimetype

    if download is True:
        download = os.path.basename(filename)

    if download:
        download = os.path.basename(download).replace('"', '')
        headers['Content-Disposition'] = 'attachment; filename="%s"' % download

    stats = os.stat(filename)
    headers['Content-Length'] = clen = stats.st_size
    headers['Last-Modified'] = email.utils.formatdate(stats.st_mtime, usegmt=True)
    headers['Date'] = email.utils.formatdate(time.time(), usegmt=True)

    if etag is None:
        etag = '%d:%d:%d:%d:%s' % (stats.st_dev, stats.st_ino, stats.st_mtime,
                                   clen, filename)
        etag = hashlib.sha256(tob(etag)).hexdigest()

    if etag:
        headers['ETag'] = etag
        check = getenv('HTTP_IF_NONE_MATCH')
        if check and check == etag:
            return HTTPResponse(status=304, **headers)

    ims = getenv('HTTP_IF_MODIFIED_SINCE')
    if ims:
        ims = parse_date(ims.split(";")[0].strip())
        if ims is not None and ims >= int(stats.st_mtime):
            return HTTPResponse(status=304, **headers)

    body = '' if request.method == 'HEAD' else open(filename, 'rb')

    headers["Accept-Ranges"] = "bytes"
    range_header = getenv('HTTP_RANGE')
    if range_header:
        ranges = list(parse_range_header(range_header, clen))
        if not ranges:
            return HTTPError(416, "Requested Range Not Satisfiable")
        offset, end = ranges[0]
        rlen = end - offset
        headers["Content-Range"] = "bytes %d-%d/%d" % (offset, end - 1, clen)
        headers["Content-Length"] = str(rlen)
        if body: body = _closeiter(_rangeiter(body, offset, rlen), body.close)
        return HTTPResponse(body, status=206, **headers)
    return HTTPResponse(body, **headers)

def debug(mode=True):
    global DEBUG
    if mode: warnings.simplefilter('default')
    DEBUG = bool(mode)

def http_date(value):
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        value = value.utctimetuple()
    elif isinstance(value, datedate):
        value = value.timetuple()
    if not isinstance(value, (int, float)):
        value = calendar.timegm(value)
    return email.utils.formatdate(value, usegmt=True)

def parse_date(ims):
    try:
        ts = email.utils.parsedate_tz(ims)
        return calendar.timegm(ts[:8] + (0, )) - (ts[9] or 0)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None

def parse_auth(header):
    try:
        method, data = header.split(None, 1)
        if method.lower() == 'basic':
            user, pwd = touni(base64.b64decode(tob(data))).split(':', 1)
            return user, pwd
    except (KeyError, ValueError):
        return None

def parse_range_header(header, maxlen=0):
    if not header or header[:6] != 'bytes=': return
    ranges = [r.split('-', 1) for r in header[6:].split(',') if '-' in r]
    for start, end in ranges:
        try:
            if not start:
                start, end = max(0, maxlen - int(end)), maxlen
            elif not end:
                start, end = int(start), maxlen
            else:
                start, end = int(start), min(int(end) + 1, maxlen)
            if 0 <= start < end <= maxlen:
                yield start, end
        except ValueError:
            pass

_hsplit = re.compile('(?:(?:"((?:[^"\\\\]|\\\\.)*)")|([^;,=]+))([;,=]?)').findall

def _parse_http_header(h):
    values = []
    if '"' not in h:
        for value in h.split(','):
            parts = value.split(';')
            values.append((parts[0].strip(), {}))
            for attr in parts[1:]:
                name, value = attr.split('=', 1)
                values[-1][1][name.strip().lower()] = value.strip()
    else:
        lop, key, attrs = ',', None, {}
        for quoted, plain, tok in _hsplit(h):
            value = plain.strip() if plain else quoted.replace('\\"', '"')
            if lop == ',':
                attrs = {}
                values.append((value, attrs))
            elif lop == ';':
                if tok == '=':
                    key = value
                else:
                    attrs[value.strip().lower()] = ''
            elif lop == '=' and key:
                attrs[key.strip().lower()] = value
                key = None
            lop = tok
    return values

def _parse_qsl(qs, encoding="utf8"):
    r = []
    for pair in qs.split('&'):
        if not pair: continue
        nv = pair.split('=', 1)
        if len(nv) != 2: nv.append('')
        key = urlunquote(nv[0].replace('+', ' '), encoding)
        value = urlunquote(nv[1].replace('+', ' '), encoding)
        r.append((key, value))
    return r

def _lscmp(a, b):
    try:
        return hmac.compare_digest(tob(a), tob(b))
    except TypeError:
        return False

def cookie_encode(data, key, digestmod=None):
    depr(0, 13, "cookie_encode() will be removed soon.",
                "Do not use this API directly.")
    digestmod = digestmod or hashlib.sha256
    msg = base64.b64encode(pickle.dumps(data, -1))
    sig = base64.b64encode(hmac.new(tob(key), msg, digestmod=digestmod).digest())
    return b'!' + sig + b'?' + msg

def cookie_decode(data, key, digestmod=None):
    depr(0, 13, "cookie_decode() will be removed soon.",
                "Do not use this API directly.")
    data = tob(data)
    if cookie_is_encoded(data):
        sig, msg = data.split(b'?', 1)
        digestmod = digestmod or hashlib.sha256
        hashed = hmac.new(tob(key), msg, digestmod=digestmod).digest()
        if _lscmp(sig[1:], base64.b64encode(hashed)):
            return pickle.loads(base64.b64decode(msg))
    return None

def cookie_is_encoded(data):
    depr(0, 13, "cookie_is_encoded() will be removed soon.",
                "Do not use this API directly.")
    return bool(data.startswith(b'!') and b'?' in data)

def html_escape(string):
    return string.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')\
                 .replace('"', '&quot;').replace("'", '&#039;')

def html_quote(string):
    return '"%s"' % html_escape(string).replace('\n', '&#10;') \
        .replace('\r', '&#13;').replace('\t', '&#9;')

def yieldroutes(func):
    path = '/' + func.__name__.replace('__', '/').lstrip('/')
    sig = inspect.signature(func, follow_wrapped=False)
    for p in sig.parameters.values():
        if p.kind == p.POSITIONAL_ONLY:
            raise ValueError("Invalid signature for yieldroutes: %s" % sig)
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            if p.default != p.empty:
                yield path
            path += "/<%s>" % p.name
    yield path

def path_shift(script_name, path_info, shift=1):
    if shift == 0: return script_name, path_info
    pathlist = path_info.strip('/').split('/')
    scriptlist = script_name.strip('/').split('/')
    if pathlist and pathlist[0] == '': pathlist = []
    if scriptlist and scriptlist[0] == '': scriptlist = []
    if 0 < shift <= len(pathlist):
        moved = pathlist[:shift]
        scriptlist = scriptlist + moved
        pathlist = pathlist[shift:]
    elif 0 > shift >= -len(scriptlist):
        moved = scriptlist[shift:]
        pathlist = moved + pathlist
        scriptlist = scriptlist[:shift]
    else:
        empty = 'SCRIPT_NAME' if shift < 0 else 'PATH_INFO'
        raise AssertionError("Cannot shift. Nothing left from %s" % empty)
    new_script_name = '/' + '/'.join(scriptlist)
    new_path_info = '/' + '/'.join(pathlist)
    if path_info.endswith('/') and pathlist: new_path_info += '/'
    return new_script_name, new_path_info

def auth_basic(check, realm="private", text="Access denied"):

    def decorator(func):

        @functools.wraps(func)
        def wrapper(*a, **ka):
            user, password = request.auth or (None, None)
            if user is None or not check(user, password):
                err = HTTPError(401, text)
                err.add_header('WWW-Authenticate', 'Basic realm="%s"' % realm)
                return err
            return func(*a, **ka)

        return wrapper

    return decorator


# --- Password Hashing (PBKDF2-SHA256) ---

def hash_password(password, iterations=600000):
    """Hash a password using PBKDF2-SHA256 with a random salt.
    Returns a string: 'pbkdf2:sha256:iterations$salt_hex$hash_hex'"""
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac('sha256', tob(password), salt, iterations)
    return 'pbkdf2:sha256:%d$%s$%s' % (iterations, salt.hex(), dk.hex())


def verify_password(password, hash_string):
    """Verify a password against a PBKDF2 hash string. Timing-safe."""
    try:
        if not isinstance(hash_string, str):
            return False
        method, rest = hash_string.split(':', 1)
        algo, rest = rest.split(':', 1)
        iters_s, salt_hex, hash_hex = rest.split('$', 2)
        dk = hashlib.pbkdf2_hmac(
            algo, tob(password), bytes.fromhex(salt_hex), int(iters_s)
        )
        return hmac.compare_digest(dk, bytes.fromhex(hash_hex))
    except (ValueError, TypeError):
        return False


# --- Test Client ---

class TestResponse:
    """Response object returned by TestClient."""

    __slots__ = ('status', 'headers', 'body')

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def status_code(self):
        return int(self.status.split(' ', 1)[0])

    @property
    def text(self):
        return self.body.decode('utf-8', errors='replace')

    @property
    def json(self):
        return json_lds(self.body)


class TestClient:
    """WSGI test client — calls app directly, no HTTP needed."""

    def __init__(self, app):
        self.app = app

    def request(self, method, path, body=b'', headers=None,
                query_string='', content_type=None, json=None):
        if json is not None:
            body = tob(json_dumps(json))
            content_type = content_type or 'application/json'
        environ = {
            'REQUEST_METHOD': method.upper(),
            'PATH_INFO': path,
            'SERVER_NAME': 'localhost',
            'SERVER_PORT': '80',
            'SERVER_PROTOCOL': 'HTTP/1.1',
            'wsgi.input': BytesIO(body),
            'wsgi.errors': BytesIO(),
            'wsgi.url_scheme': 'http',
            'QUERY_STRING': query_string,
            'CONTENT_LENGTH': str(len(body)),
            'HTTP_HOST': 'localhost',
        }
        if content_type:
            environ['CONTENT_TYPE'] = content_type
        if headers:
            for key, value in headers.items():
                k = key.upper().replace('-', '_')
                if k not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                    k = 'HTTP_' + k
                environ[k] = value
        status_line = [None]
        response_headers = [None]

        def start_response(status, headers, exc_info=None):
            status_line[0] = status
            response_headers[0] = dict(headers)

        chunks = self.app(environ, start_response)
        body_out = b''.join(chunks)
        if hasattr(chunks, 'close'):
            chunks.close()
        return TestResponse(status_line[0], response_headers[0], body_out)

    def get(self, path, **kw):
        return self.request('GET', path, **kw)

    def post(self, path, **kw):
        return self.request('POST', path, **kw)

    def put(self, path, **kw):
        return self.request('PUT', path, **kw)

    def patch(self, path, **kw):
        return self.request('PATCH', path, **kw)

    def delete(self, path, **kw):
        return self.request('DELETE', path, **kw)

    def head(self, path, **kw):
        return self.request('HEAD', path, **kw)

    def options(self, path, **kw):
        return self.request('OPTIONS', path, **kw)


def make_default_app_wrapper(name):

    @functools.wraps(getattr(Lcore, name))
    def wrapper(*a, **ka):
        return getattr(app(), name)(*a, **ka)

    return wrapper

route = make_default_app_wrapper('route')
get = make_default_app_wrapper('get')
post = make_default_app_wrapper('post')
put = make_default_app_wrapper('put')
delete = make_default_app_wrapper('delete')
patch = make_default_app_wrapper('patch')
error = make_default_app_wrapper('error')
mount = make_default_app_wrapper('mount')
hook = make_default_app_wrapper('hook')
install = make_default_app_wrapper('install')
uninstall = make_default_app_wrapper('uninstall')
url = make_default_app_wrapper('get_url')
use = make_default_app_wrapper('use')

class MultipartError(HTTPError):
    def __init__(self, msg):
        HTTPError.__init__(self, 400, "MultipartError: " + msg)

class _MultipartParser:
    def __init__(
        self,
        stream,
        boundary,
        content_length=-1,
        disk_limit=2 ** 30,
        mem_limit=2 ** 20,
        memfile_limit=2 ** 18,
        buffer_size=2 ** 16,
        charset="latin1",
    ):
        self.stream = stream
        self.boundary = boundary
        self.content_length = content_length
        self.disk_limit = disk_limit
        self.memfile_limit = memfile_limit
        self.mem_limit = min(mem_limit, self.disk_limit)
        self.buffer_size = min(buffer_size, self.mem_limit)
        self.charset = charset

        if not boundary:
            raise MultipartError("No boundary.")

        if self.buffer_size - 6 < len(boundary):
            raise MultipartError("Boundary does not fit into buffer_size.")

    def _lineiter(self):
        read = self.stream.read
        maxread, maxbuf = self.content_length, self.buffer_size
        partial = b""

        while True:
            chunk = read(maxbuf if maxread < 0 else min(maxbuf, maxread))
            maxread -= len(chunk)
            if not chunk:
                if partial:
                    yield partial, b''
                break

            if partial:
                chunk = partial + chunk

            scanpos = 0
            while True:
                i = chunk.find(b'\r\n', scanpos)
                if i >= 0:
                    yield chunk[scanpos:i], b'\r\n'
                    scanpos = i + 2
                else:
                    partial = chunk[scanpos:] if scanpos else chunk
                    break

            if len(partial) > maxbuf:
                yield partial[:-1], b""
                partial = partial[-1:]

    def parse(self):

        lines, line = self._lineiter(), ""
        separator = b"--" + tob(self.boundary)
        terminator = separator + b"--"
        mem_used, disk_used = 0, 0
        is_tail = False
        for line, nl in lines:
            if line in (separator, terminator):
                break
        else:
            raise MultipartError("Stream does not contain boundary")

        if line == terminator:
            for _ in lines:
                raise MultipartError("Found data after empty multipart stream")
            return

        part_options = {
            "buffer_size": self.buffer_size,
            "memfile_limit": self.memfile_limit,
            "charset": self.charset,
        }
        part = _MultipartPart(**part_options)

        for line, nl in lines:
            if not is_tail and (line == separator or line == terminator):
                part.finish()
                if part.is_buffered():
                    mem_used += part.size
                else:
                    disk_used += part.size
                yield part
                if line == terminator:
                    break
                part = _MultipartPart(**part_options)
            else:
                is_tail = not nl
                try:
                    part.feed(line, nl)
                    if part.is_buffered():
                        if part.size + mem_used > self.mem_limit:
                            raise MultipartError("Memory limit reached.")
                    elif part.size + disk_used > self.disk_limit:
                        raise MultipartError("Disk limit reached.")
                except MultipartError:
                    part.close()
                    raise
        else:
            part.close()

        if line != terminator:
            raise MultipartError("Unexpected end of multipart stream.")

class _MultipartPart:
    def __init__(self, buffer_size=2 ** 16, memfile_limit=2 ** 18, charset="latin1"):
        self.headerlist = []
        self.headers = None
        self.file = False
        self.size = 0
        self._buf = b""
        self.disposition = None
        self.name = None
        self.filename = None
        self.content_type = None
        self.charset = charset
        self.memfile_limit = memfile_limit
        self.buffer_size = buffer_size

    def feed(self, line, nl=""):
        if self.file:
            return self.write_body(line, nl)
        return self.write_header(line, nl)

    def write_header(self, line, nl):
        line = str(line, self.charset)

        if not nl:
            raise MultipartError("Unexpected end of line in header.")

        if not line.strip():
            self.finish_header()
        elif line[0] in " \t" and self.headerlist:
            name, value = self.headerlist.pop()
            self.headerlist.append((name, value + line.strip()))
        else:
            if ":" not in line:
                raise MultipartError("Syntax error in header: No colon.")

            name, value = line.split(":", 1)
            self.headerlist.append((name.strip(), value.strip()))

    def write_body(self, line, nl):
        if not line and not nl:
            return

        self.size += len(line) + len(self._buf)
        self.file.write(self._buf + line)
        self._buf = nl

        if self.content_length > 0 and self.size > self.content_length:
            raise MultipartError("Size of body exceeds Content-Length header.")

        if self.size > self.memfile_limit and isinstance(self.file, BytesIO):
            self.file, old = NamedTemporaryFile(mode="w+b"), self.file
            old.seek(0)

            copied, maxcopy, chunksize = 0, self.size, self.buffer_size
            read, write = old.read, self.file.write
            while copied < maxcopy:
                chunk = read(min(chunksize, maxcopy - copied))
                write(chunk)
                copied += len(chunk)

    def finish_header(self):
        self.file = BytesIO()
        self.headers = HeaderDict(self.headerlist)
        content_disposition = self.headers.get("Content-Disposition")
        content_type = self.headers.get("Content-Type")

        if not content_disposition:
            raise MultipartError("Content-Disposition header is missing.")

        self.disposition, self.options = _parse_http_header(content_disposition)[0]
        self.name = self.options.get("name")
        if "filename" in self.options:
            self.filename = self.options.get("filename")
            if self.filename[1:3] == ":\\" or self.filename[:2] == "\\\\":
                self.filename = self.filename.split("\\")[-1]

        self.content_type, options = _parse_http_header(content_type)[0] if content_type else (None, {})
        self.charset = options.get("charset") or self.charset

        self.content_length = int(self.headers.get("Content-Length", "-1"))

    def finish(self):
        if not self.file:
            raise MultipartError("Incomplete part: Header section not closed.")
        self.file.seek(0)

    def is_buffered(self):
        return isinstance(self.file, BytesIO)

    @property
    def value(self):
        return str(self.raw, self.charset)

    @property
    def raw(self):
        pos = self.file.tell()
        self.file.seek(0)

        try:
            return self.file.read()
        finally:
            self.file.seek(pos)

    def close(self):
        if self.file:
            self.file.close()
            self.file = False

class ServerAdapter:
    quiet = False

    def __init__(self, host='127.0.0.1', port=8080, **options):
        self.options = options
        self.host = host
        self.port = int(port)

    def run(self, handler):
        pass

    @property
    def _listen_url(self):
        if self.host.startswith("unix:"):
            return self.host
        elif ':' in self.host:
            return "http://[%s]:%d/" % (self.host, self.port)
        else:
            return "http://%s:%d/" % (self.host, self.port)

    def __repr__(self):
        args = ', '.join('%s=%r' % kv for kv in self.options.items())
        return "%s(%s)" % (self.__class__.__name__, args)

class CGIServer(ServerAdapter):
    quiet = True

    def run(self, handler):
        from wsgiref.handlers import CGIHandler

        def fixed_environ(environ, start_response):
            environ.setdefault('PATH_INFO', '')
            return handler(environ, start_response)

        CGIHandler().run(fixed_environ)

class FlupFCGIServer(ServerAdapter):
    def run(self, handler):
        import flup.server.fcgi
        self.options.setdefault('bindAddress', (self.host, self.port))
        flup.server.fcgi.WSGIServer(handler, **self.options).run()

class WSGIRefServer(ServerAdapter):
    def run(self, app):
        from wsgiref.simple_server import make_server
        from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
        import socket

        class FixedHandler(WSGIRequestHandler):
            def log_message(other, format, *args):
                if not self.quiet:
                    return WSGIRequestHandler.log_message(other, format, *args)

        handler_cls = self.options.get('handler_class', FixedHandler)
        server_cls = self.options.get('server_class', WSGIServer)

        if ':' in self.host:
            if getattr(server_cls, 'address_family') == socket.AF_INET:

                class server_cls(server_cls):
                    address_family = socket.AF_INET6

        self.srv = make_server(self.host, self.port, app, server_cls,
                               handler_cls)
        self.port = self.srv.server_port
        try:
            self.srv.serve_forever()
        except KeyboardInterrupt:
            self.srv.server_close()
            raise

class CherryPyServer(ServerAdapter):
    def run(self, handler):
        depr(0, 13, "The wsgi server part of cherrypy was split into a new "
                    "project called 'cheroot'.", "Use the 'cheroot' server "
                    "adapter instead of cherrypy.")
        from cherrypy import wsgiserver

        self.options['bind_addr'] = (self.host, self.port)
        self.options['wsgi_app'] = handler

        certfile = self.options.get('certfile')
        if certfile:
            del self.options['certfile']
        keyfile = self.options.get('keyfile')
        if keyfile:
            del self.options['keyfile']

        server = wsgiserver.CherryPyWSGIServer(**self.options)
        if certfile:
            server.ssl_certificate = certfile
        if keyfile:
            server.ssl_private_key = keyfile

        try:
            server.start()
        finally:
            server.stop()

class CherootServer(ServerAdapter):
    def run(self, handler):
        from cheroot import wsgi
        from cheroot.ssl import builtin
        self.options['bind_addr'] = (self.host, self.port)
        self.options['wsgi_app'] = handler
        certfile = self.options.pop('certfile', None)
        keyfile = self.options.pop('keyfile', None)
        chainfile = self.options.pop('chainfile', None)
        server = wsgi.Server(**self.options)
        if certfile and keyfile:
            server.ssl_adapter = builtin.BuiltinSSLAdapter(
                certfile, keyfile, chainfile)
        try:
            server.start()
        finally:
            server.stop()

class WaitressServer(ServerAdapter):
    def run(self, handler):
        from waitress import serve
        serve(handler, host=self.host, port=self.port, _quiet=self.quiet, **self.options)

class PasteServer(ServerAdapter):
    def run(self, handler):
        from paste import httpserver
        from paste.translogger import TransLogger
        handler = TransLogger(handler, setup_console_handler=(not self.quiet))
        httpserver.serve(handler,
                         host=self.host,
                         port=str(self.port), **self.options)

class MeinheldServer(ServerAdapter):
    def run(self, handler):
        from meinheld import server
        server.listen((self.host, self.port))
        server.run(handler)

class FapwsServer(ServerAdapter):

    def run(self, handler):
        depr(0, 13, "fapws3 is not maintained and support will be dropped.")
        import fapws._evwsgi as evwsgi
        from fapws import base, config
        port = self.port
        if float(config.SERVER_IDENT[-2:]) > 0.4:
            port = str(port)
        evwsgi.start(self.host, port)
        if 'LCORE_CHILD' in os.environ and not self.quiet:
            _stderr("WARNING: Auto-reloading does not work with Fapws3.")
            _stderr("         (Fapws3 breaks python thread support)")
        evwsgi.set_base_module(base)

        def app(environ, start_response):
            environ['wsgi.multiprocess'] = False
            return handler(environ, start_response)

        evwsgi.wsgi_cb(('', app))
        evwsgi.run()

class TornadoServer(ServerAdapter):

    def run(self, handler):
        import tornado.wsgi, tornado.httpserver, tornado.ioloop
        container = tornado.wsgi.WSGIContainer(handler)
        server = tornado.httpserver.HTTPServer(container)
        server.listen(port=self.port, address=self.host)
        tornado.ioloop.IOLoop.instance().start()

class AppEngineServer(ServerAdapter):
    quiet = True

    def run(self, handler):
        depr(0, 13, "AppEngineServer no longer required",
             "Configure your application directly in your app.yaml")
        from google.appengine.ext.webapp import util
        module = sys.modules.get('__main__')
        if module and not hasattr(module, 'main'):
            module.main = lambda: util.run_wsgi_app(handler)
        util.run_wsgi_app(handler)

class TwistedServer(ServerAdapter):

    def run(self, handler):
        from twisted.web import server, wsgi
        from twisted.python.threadpool import ThreadPool
        from twisted.internet import reactor
        thread_pool = ThreadPool()
        thread_pool.start()
        reactor.addSystemEventTrigger('after', 'shutdown', thread_pool.stop)
        factory = server.Site(wsgi.WSGIResource(reactor, thread_pool, handler))
        reactor.listenTCP(self.port, factory, interface=self.host)
        if not reactor.running:
            reactor.run()

class DieselServer(ServerAdapter):

    def run(self, handler):
        depr(0, 13, "Diesel is not tested or supported and will be removed.")
        from diesel.protocols.wsgi import WSGIApplication
        app = WSGIApplication(handler, port=self.port)
        app.run()

class GeventServer(ServerAdapter):

    def run(self, handler):
        from gevent import pywsgi, local
        if not isinstance(threading.local(), local.local):
            msg = "Lcore requires gevent.monkey.patch_all() (before import)"
            raise RuntimeError(msg)
        if self.quiet:
            self.options['log'] = None
        address = (self.host, self.port)
        server = pywsgi.WSGIServer(address, handler, **self.options)
        if 'LCORE_CHILD' in os.environ:
            import signal
            signal.signal(signal.SIGINT, lambda s, f: server.stop())
        server.serve_forever()

class GunicornServer(ServerAdapter):

    def run(self, handler):
        from gunicorn.app.base import BaseApplication

        if self.host.startswith("unix:"):
            config = {'bind': self.host}
        else:
            config = {'bind': "%s:%d" % (self.host, self.port)}

        config.update(self.options)

        class GunicornApplication(BaseApplication):
            def load_config(self):
                for key, value in config.items():
                    self.cfg.set(key, value)

            def load(self):
                return handler

        GunicornApplication().run()

class EventletServer(ServerAdapter):
    def run(self, handler):
        from eventlet import wsgi, listen, patcher
        if not patcher.is_monkey_patched(os):
            msg = "Lcore requires eventlet.monkey_patch() (before import)"
            raise RuntimeError(msg)
        socket_args = {}
        for arg in ('backlog', 'family'):
            try:
                socket_args[arg] = self.options.pop(arg)
            except KeyError:
                pass
        address = (self.host, self.port)
        try:
            wsgi.server(listen(address, **socket_args), handler,
                        log_output=(not self.quiet))
        except TypeError:
            wsgi.server(listen(address), handler)

class BjoernServer(ServerAdapter):

    def run(self, handler):
        from bjoern import run
        run(handler, self.host, self.port, reuse_port=True)

class AsyncioServerAdapter(ServerAdapter):
    def get_event_loop(self):
        pass

class AiohttpServer(AsyncioServerAdapter):

    def get_event_loop(self):
        import asyncio
        return asyncio.new_event_loop()

    def run(self, handler):
        import asyncio
        from aiohttp_wsgi.wsgi import serve
        self.loop = self.get_event_loop()
        asyncio.set_event_loop(self.loop)

        if 'LCORE_CHILD' in os.environ:
            import signal
            signal.signal(signal.SIGINT, lambda s, f: self.loop.stop())

        serve(handler, host=self.host, port=self.port)

class AiohttpUVLoopServer(AiohttpServer):
    def get_event_loop(self):
        import uvloop
        return uvloop.new_event_loop()

class AutoServer(ServerAdapter):
    adapters = [WaitressServer, PasteServer, TwistedServer, CherryPyServer,
                CherootServer, WSGIRefServer]

    def run(self, handler):
        for sa in self.adapters:
            try:
                return sa(self.host, self.port, **self.options).run(handler)
            except ImportError:
                pass

server_names = {
    'cgi': CGIServer,
    'flup': FlupFCGIServer,
    'wsgiref': WSGIRefServer,
    'waitress': WaitressServer,
    'cherrypy': CherryPyServer,
    'cheroot': CherootServer,
    'paste': PasteServer,
    'fapws3': FapwsServer,
    'tornado': TornadoServer,
    'gae': AppEngineServer,
    'twisted': TwistedServer,
    'diesel': DieselServer,
    'meinheld': MeinheldServer,
    'gunicorn': GunicornServer,
    'eventlet': EventletServer,
    'gevent': GeventServer,
    'bjoern': BjoernServer,
    'aiohttp': AiohttpServer,
    'uvloop': AiohttpUVLoopServer,
    'auto': AutoServer,
}

def load(target, **namespace):
    module, target = target.split(":", 1) if ':' in target else (target, None)
    if module not in sys.modules: __import__(module)
    if not target: return sys.modules[module]
    obj = sys.modules[module]
    for part in target.split('.'):
        if not part.isidentifier():
            raise AttributeError("Invalid attribute name: %r" % part)
        obj = getattr(obj, part)
    return obj

def load_app(target):
    if target.endswith('.py'):
        target = target[:-3].replace(os.sep, '.').replace('/', '.')
    global NORUN
    NORUN, nr_old = True, NORUN
    tmp = default_app.push()
    try:
        rv = load(target)
        if callable(rv):
            return rv
        # Search the loaded module for a Lcore app instance
        if hasattr(rv, '__dict__'):
            for obj in rv.__dict__.values():
                if isinstance(obj, Lcore):
                    return obj
        return tmp
    finally:
        default_app.remove(tmp)
        NORUN = nr_old

_debug = debug

_shutdown_hooks = []

def on_shutdown(func):
    _shutdown_hooks.append(func)
    return func

def _run_shutdown_hooks():
    for hook in reversed(_shutdown_hooks):
        try:
            result = hook()
            if inspect.iscoroutine(result):
                _run_async(result)
        except Exception:
            pass

def run(app=None,
        server='wsgiref',
        host='127.0.0.1',
        port=8080,
        interval=1,
        reloader=False,
        quiet=False,
        plugins=None,
        debug=None,
        config=None, **kargs):
    if NORUN: return
    if reloader and not os.environ.get('LCORE_CHILD'):
        import subprocess
        fd, lockfile = tempfile.mkstemp(prefix='lcore.', suffix='.lock')
        environ = os.environ.copy()
        environ['LCORE_CHILD'] = 'true'
        environ['LCORE_LOCKFILE'] = lockfile
        args = [sys.executable] + sys.argv
        if getattr(sys.modules.get('__main__'), '__package__', None):
            args[1:1] = ["-m", sys.modules['__main__'].__package__]

        try:
            os.close(fd)
            while os.path.exists(lockfile):
                p = subprocess.Popen(args, env=environ)
                while p.poll() is None:
                    os.utime(lockfile, None)
                    time.sleep(interval)
                if p.returncode == 3:
                    continue
                sys.exit(p.returncode)
        except KeyboardInterrupt:
            pass
        finally:
            if os.path.exists(lockfile):
                os.unlink(lockfile)
        return

    try:
        if debug is not None: _debug(debug)
        app = app or default_app()
        if isinstance(app, str):
            app = load_app(app)
        if not callable(app):
            raise ValueError("Application is not callable: %r" % app)

        if debug and isinstance(app, Lcore) and not getattr(app, '_docs_paths', None):
            app.enable_docs()

        for plugin in plugins or []:
            if isinstance(plugin, str):
                plugin = load(plugin)
            app.install(plugin)

        if config:
            app.config.update(config)

        if server in server_names:
            server = server_names.get(server)
        if isinstance(server, str):
            server = load(server)
        if isinstance(server, type):
            server = server(host=host, port=port, **kargs)
        if not isinstance(server, ServerAdapter):
            raise ValueError("Unknown or unsupported server: %r" % server)

        server.quiet = server.quiet or quiet
        if not server.quiet:
            _stderr("Lcore v%s server starting up (using %s)..." %
                    (__version__, repr(server)))
            _stderr("Listening on %s" % server._listen_url)
            _stderr("Hit Ctrl-C to quit.\n")

        if reloader:
            lockfile = os.environ.get('LCORE_LOCKFILE')
            bgcheck = FileCheckerThread(lockfile, interval)
            with bgcheck:
                server.run(app)
            if bgcheck.status == 'reload':
                sys.exit(3)
        else:
            server.run(app)
    except KeyboardInterrupt:
        pass
    except (SystemExit, MemoryError):
        raise
    except:
        if not reloader: raise
        if not getattr(server, 'quiet', quiet):
            print_exc()
        time.sleep(interval)
        sys.exit(3)
    finally:
        _run_shutdown_hooks()
        if hasattr(app, 'close'):
            app.close()

class FileCheckerThread(threading.Thread):

    def __init__(self, lockfile, interval):
        threading.Thread.__init__(self)
        self.daemon = True
        self.lockfile, self.interval = lockfile, interval
        self.status = None

    def run(self):
        exists = os.path.exists
        mtime = lambda p: os.stat(p).st_mtime
        files = {}

        for module in list(sys.modules.values()):
            path = getattr(module, '__file__', '') or ''
            if path[-4:] in ('.pyo', '.pyc'): path = path[:-1]
            if path and exists(path): files[path] = mtime(path)

        while not self.status:
            if not exists(self.lockfile)\
               or mtime(self.lockfile) < time.time() - self.interval - 5:
                self.status = 'error'
                thread.interrupt_main()
            for path, lmtime in list(files.items()):
                if not exists(path) or mtime(path) > lmtime:
                    self.status = 'reload'
                    thread.interrupt_main()
                    break
            time.sleep(self.interval)

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, *_):
        if not self.status: self.status = 'exit'
        self.join()
        return exc_type is not None and issubclass(exc_type, KeyboardInterrupt)

class WatchdogReloader:

    def __init__(self, app, paths=None, interval=1, callback=None):
        self.app = app
        self.paths = paths or ['.']
        self.interval = interval
        self.callback = callback or self._default_reload
        self._observer = None

    def _default_reload(self, changed_path):
        _stderr("File changed: %s — reloading..." % changed_path)
        self.app.reset()

    def start(self):
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            _stderr("watchdog not installed, falling back to polling reloader")
            return self._start_polling()

        reloader = self

        class _Handler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                if event.src_path.endswith(('.py', '.html', '.tpl', '.json', '.yaml', '.yml')):
                    reloader.callback(event.src_path)

        self._observer = Observer()
        handler = _Handler()
        for path in self.paths:
            if os.path.isdir(path):
                self._observer.schedule(handler, path, recursive=True)
        self._observer.daemon = True
        self._observer.start()
        return self

    def _start_polling(self):
        files = {}
        for path in self.paths:
            for dirpath, _, filenames in os.walk(path):
                for fn in filenames:
                    if fn.endswith(('.py', '.html', '.tpl', '.json', '.yaml', '.yml')):
                        fp = os.path.join(dirpath, fn)
                        try:
                            files[fp] = os.stat(fp).st_mtime
                        except OSError:
                            pass

        reloader = self

        def _poll():
            while True:
                time.sleep(reloader.interval)
                for fp, old_mtime in list(files.items()):
                    try:
                        new_mtime = os.stat(fp).st_mtime
                    except OSError:
                        continue
                    if new_mtime > old_mtime:
                        files[fp] = new_mtime
                        reloader.callback(fp)

        t = threading.Thread(target=_poll, daemon=True)
        t.start()
        return self

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()


class AsyncReloader:

    def __init__(self, app, paths=None, interval=1.0, callback=None):
        self.app = app
        self.paths = paths or ['.']
        self.interval = interval
        self.callback = callback or self._default_reload
        self._task = None
        self._files = {}

    def _default_reload(self, changed_path):
        _stderr("File changed: %s — reloading..." % changed_path)
        self.app.reset()

    def _scan(self):
        for path in self.paths:
            for dirpath, _, filenames in os.walk(path):
                for fn in filenames:
                    if fn.endswith(('.py', '.html', '.tpl', '.json', '.yaml', '.yml')):
                        yield os.path.join(dirpath, fn)

    async def _watch(self):
        for fp in self._scan():
            try:
                self._files[fp] = os.stat(fp).st_mtime
            except OSError:
                pass
        while True:
            await asyncio.sleep(self.interval)
            for fp in self._scan():
                try:
                    mtime = os.stat(fp).st_mtime
                except OSError:
                    continue
                old = self._files.get(fp)
                if old is None:
                    self._files[fp] = mtime
                    self.callback(fp)
                elif mtime > old:
                    self._files[fp] = mtime
                    self.callback(fp)

    def start(self, loop=None):
        loop = loop or asyncio.get_event_loop()
        self._task = loop.create_task(self._watch())
        return self

    def stop(self):
        if self._task:
            self._task.cancel()

class TemplateError(LcoreException):
    pass

class BaseTemplate:
    extensions = ['tpl', 'html', 'thtml', 'stpl']
    settings = {}
    defaults = {}

    def __init__(self,
                 source=None,
                 name=None,
                 lookup=None,
                 encoding='utf8', **settings):
        self.name = name
        self.source = source.read() if hasattr(source, 'read') else source
        self.filename = source.filename if hasattr(source, 'filename') else None
        self.lookup = [os.path.abspath(x) for x in lookup] if lookup else []
        self.encoding = encoding
        self.settings = self.settings.copy()
        self.settings.update(settings)
        if not self.source and self.name:
            self.filename = self.search(self.name, self.lookup)
            if not self.filename:
                raise TemplateError('Template %s not found.' % repr(name))
        if not self.source and not self.filename:
            raise TemplateError('No template specified.')
        self.prepare(**self.settings)

    @classmethod
    def search(cls, name, lookup=None):
        if not lookup:
            raise depr(0, 12, "Empty template lookup path.", "Configure a template lookup path.")

        if os.path.isabs(name):
            raise depr(0, 12, "Use of absolute path for template name.",
                       "Refer to templates with names or paths relative to the lookup path.")

        for spath in lookup:
            spath = os.path.abspath(spath) + os.sep
            fname = os.path.abspath(os.path.join(spath, name))
            if not fname.startswith(spath): continue
            if os.path.isfile(fname): return fname
            for ext in cls.extensions:
                if os.path.isfile('%s.%s' % (fname, ext)):
                    return '%s.%s' % (fname, ext)

    @classmethod
    def global_config(cls, key, *args):
        if args:
            cls.settings = cls.settings.copy()
            cls.settings[key] = args[0]
        else:
            return cls.settings[key]

    def prepare(self, **options):
        raise NotImplementedError

    def render(self, *args, **kwargs):
        raise NotImplementedError

class MakoTemplate(BaseTemplate):
    def prepare(self, **options):
        from mako.template import Template
        from mako.lookup import TemplateLookup
        options.update({'input_encoding': self.encoding})
        options.setdefault('format_exceptions', bool(DEBUG))
        lookup = TemplateLookup(directories=self.lookup, **options)
        if self.source:
            self.tpl = Template(self.source, lookup=lookup, **options)
        else:
            self.tpl = Template(uri=self.name,
                                filename=self.filename,
                                lookup=lookup, **options)

    def render(self, *args, **kwargs):
        for dictarg in args:
            kwargs.update(dictarg)
        _defaults = self.defaults.copy()
        _defaults.update(kwargs)
        return self.tpl.render(**_defaults)

class CheetahTemplate(BaseTemplate):
    def prepare(self, **options):
        from Cheetah.Template import Template
        self.context = threading.local()
        self.context.vars = {}
        options['searchList'] = [self.context.vars]
        if self.source:
            self.tpl = Template(source=self.source, **options)
        else:
            self.tpl = Template(file=self.filename, **options)

    def render(self, *args, **kwargs):
        for dictarg in args:
            kwargs.update(dictarg)
        self.context.vars.update(self.defaults)
        self.context.vars.update(kwargs)
        out = str(self.tpl)
        self.context.vars.clear()
        return out

class Jinja2Template(BaseTemplate):
    def prepare(self, filters=None, tests=None, globals=None, **kwargs):
        from jinja2 import Environment, FunctionLoader
        self.env = Environment(loader=FunctionLoader(self.loader), **kwargs)
        if filters: self.env.filters.update(filters)
        if tests: self.env.tests.update(tests)
        if globals: self.env.globals.update(globals)
        if self.source:
            self.tpl = self.env.from_string(self.source)
        else:
            self.tpl = self.env.get_template(self.name)

    def render(self, *args, **kwargs):
        for dictarg in args:
            kwargs.update(dictarg)
        _defaults = self.defaults.copy()
        _defaults.update(kwargs)
        return self.tpl.render(**_defaults)

    def loader(self, name):
        if name == self.filename:
            fname = name
        else:
            fname = self.search(name, self.lookup)
        if not fname: return
        with open(fname, "rb") as f:
            return (f.read().decode(self.encoding), fname, lambda: False)

class SimpleTemplate(BaseTemplate):
    def prepare(self,
                escape_func=html_escape,
                noescape=False,
                syntax=None, **ka):
        self.cache = {}
        enc = self.encoding
        self._str = lambda x: touni(x, enc)
        self._escape = lambda x: escape_func(touni(x, enc))
        self.syntax = syntax
        if noescape:
            self._str, self._escape = self._escape, self._str

    @cached_property
    def co(self):
        return compile(self.code, self.filename or '<string>', 'exec')

    @cached_property
    def code(self):
        source = self.source
        if not source:
            with open(self.filename, 'rb') as f:
                source = f.read()
        try:
            source, encoding = touni(source), 'utf8'
        except UnicodeError:
            raise depr(0, 11, 'Unsupported template encodings.', 'Use utf-8 for templates.')
        parser = StplParser(source, encoding=encoding, syntax=self.syntax)
        code = parser.translate()
        self.encoding = parser.encoding
        return code

    def _rebase(self, _env, _name=None, **kwargs):
        _env['_rebase'] = (_name, kwargs)

    def _include(self, _env, _name=None, **kwargs):
        env = _env.copy()
        env.update(kwargs)
        if _name not in self.cache:
            self.cache[_name] = self.__class__(name=_name, lookup=self.lookup, syntax=self.syntax)
        return self.cache[_name].execute(env['_stdout'], env)

    def execute(self, _stdout, kwargs):
        env = self.defaults.copy()
        env.update(kwargs)
        env.update({
            '_stdout': _stdout,
            '_printlist': _stdout.extend,
            'include': functools.partial(self._include, env),
            'rebase': functools.partial(self._rebase, env),
            '_rebase': None,
            '_str': self._str,
            '_escape': self._escape,
            'get': env.get,
            'setdefault': env.setdefault,
            'defined': env.__contains__
        })
        exec(self.co, env)
        if env.get('_rebase'):
            subtpl, rargs = env.pop('_rebase')
            rargs['base'] = ''.join(_stdout)
            del _stdout[:]
            return self._include(env, subtpl, **rargs)
        return env

    def render(self, *args, **kwargs):
        env = {}
        stdout = []
        for dictarg in args:
            env.update(dictarg)
        env.update(kwargs)
        self.execute(stdout, env)
        return ''.join(stdout)

class StplSyntaxError(TemplateError):
    pass

class StplParser:
    _re_cache = {}

    _re_tok = r'''(
        [urbURB]*
        (?:  ''(?!')
            |""(?!")
            |'{6}
            |"{6}
            |'(?:[^\\']|\\.)+?'
            |"(?:[^\\"]|\\.)+?"
            |'{3}(?:[^\\]|\\.|\n)+?'{3}
            |"{3}(?:[^\\]|\\.|\n)+?"{3}
        )
    )'''

    _re_inl = _re_tok.replace(r'|\n', '')
    _re_tok += r'''
        |(\#.*)
        |([\[\{\(])
        |([\]\}\)])
        |^([\ \t]*(?:if|for|while|with|try|def|class)\b)
        |^([\ \t]*(?:elif|else|except|finally)\b)
        |((?:^|;)[\ \t]*end[\ \t]*(?=(?:%(block_close)s[\ \t]*)?\r?$|;|\#))
        |(%(block_close)s[\ \t]*(?=\r?$))
        |(\r?\n)
    '''

    _re_split = r'''(?m)^[ \t]*(\\?)((%(line_start)s)|(%(block_start)s))'''
    _re_inl = r'''%%(inline_start)s((?:%s|[^'"\n])*?)%%(inline_end)s''' % _re_inl
    _re_tok = '(?mx)' + _re_tok
    _re_inl = '(?mx)' + _re_inl

    default_syntax = '<% %> % {{ }}'

    def __init__(self, source, syntax=None, encoding='utf8'):
        self.source, self.encoding = touni(source, encoding), encoding
        self.set_syntax(syntax or self.default_syntax)
        self.code_buffer, self.text_buffer = [], []
        self.lineno, self.offset = 1, 0
        self.indent, self.indent_mod = 0, 0
        self.paren_depth = 0

    def get_syntax(self):
        return self._syntax

    def set_syntax(self, syntax):
        self._syntax = syntax
        self._tokens = syntax.split()
        if syntax not in self._re_cache:
            names = 'block_start block_close line_start inline_start inline_end'
            etokens = map(re.escape, self._tokens)
            pattern_vars = dict(zip(names.split(), etokens))
            patterns = (self._re_split, self._re_tok, self._re_inl)
            patterns = [re.compile(p % pattern_vars) for p in patterns]
            self._re_cache[syntax] = patterns
        self.re_split, self.re_tok, self.re_inl = self._re_cache[syntax]

    syntax = property(get_syntax, set_syntax)

    def translate(self):
        if self.offset: raise RuntimeError('Parser is a one time instance.')
        while True:
            m = self.re_split.search(self.source, pos=self.offset)
            if m:
                text = self.source[self.offset:m.start()]
                self.text_buffer.append(text)
                self.offset = m.end()
                if m.group(1):
                    line, sep, _ = self.source[self.offset:].partition('\n')
                    self.text_buffer.append(
                        self.source[m.start():m.start(1)] + m.group(2) + line + sep)
                    self.offset += len(line + sep)
                    continue
                self.flush_text()
                self.offset += self.read_code(self.source[self.offset:],
                                              multiline=bool(m.group(4)))
            else:
                break
        self.text_buffer.append(self.source[self.offset:])
        self.flush_text()
        return ''.join(self.code_buffer)

    def read_code(self, pysource, multiline):
        code_line, comment = '', ''
        offset = 0
        while True:
            m = self.re_tok.search(pysource, pos=offset)
            if not m:
                code_line += pysource[offset:]
                offset = len(pysource)
                self.write_code(code_line.strip(), comment)
                break
            code_line += pysource[offset:m.start()]
            offset = m.end()
            _str, _com, _po, _pc, _blk1, _blk2, _end, _cend, _nl = m.groups()
            if self.paren_depth > 0 and (_blk1 or _blk2):
                code_line += _blk1 or _blk2
                continue
            if _str:
                code_line += _str
            elif _com:
                comment = _com
                if multiline and _com.strip().endswith(self._tokens[1]):
                    multiline = False
            elif _po:
                self.paren_depth += 1
                code_line += _po
            elif _pc:
                if self.paren_depth > 0:
                    self.paren_depth -= 1
                code_line += _pc
            elif _blk1:
                code_line = _blk1
                self.indent += 1
                self.indent_mod -= 1
            elif _blk2:
                code_line = _blk2
                self.indent_mod -= 1
            elif _cend:
                if multiline: multiline = False
                else: code_line += _cend
            elif _end:
                self.indent -= 1
                self.indent_mod += 1
            else:
                self.write_code(code_line.strip(), comment)
                self.lineno += 1
                code_line, comment, self.indent_mod = '', '', 0
                if not multiline:
                    break

        return offset

    def flush_text(self):
        text = ''.join(self.text_buffer)
        del self.text_buffer[:]
        if not text: return
        parts, pos, nl = [], 0, '\\\n' + '  ' * self.indent
        for m in self.re_inl.finditer(text):
            prefix, pos = text[pos:m.start()], m.end()
            if prefix:
                parts.append(nl.join(map(repr, prefix.splitlines(True))))
            if prefix.endswith('\n'): parts[-1] += nl
            parts.append(self.process_inline(m.group(1).strip()))
        if pos < len(text):
            prefix = text[pos:]
            lines = prefix.splitlines(True)
            if lines[-1].endswith('\\\\\n'): lines[-1] = lines[-1][:-3]
            elif lines[-1].endswith('\\\\\r\n'): lines[-1] = lines[-1][:-4]
            parts.append(nl.join(map(repr, lines)))
        code = '_printlist((%s,))' % ', '.join(parts)
        self.lineno += code.count('\n') + 1
        self.write_code(code)

    @staticmethod
    def process_inline(chunk):
        if chunk[0] == '!': return '_str(%s)' % chunk[1:]
        return '_escape(%s)' % chunk

    def write_code(self, line, comment=''):
        code = '  ' * (self.indent + self.indent_mod)
        code += line.lstrip() + comment + '\n'
        self.code_buffer.append(code)

def template(*args, **kwargs):
    tpl = args[0] if args else None
    for dictarg in args[1:]:
        kwargs.update(dictarg)
    adapter = kwargs.pop('template_adapter', SimpleTemplate)
    lookup = kwargs.pop('template_lookup', TEMPLATE_PATH)
    tplid = (id(lookup), tpl)
    if tplid not in TEMPLATES or DEBUG:
        settings = kwargs.pop('template_settings', {})
        if isinstance(tpl, adapter):
            TEMPLATES[tplid] = tpl
            if settings: TEMPLATES[tplid].prepare(**settings)
        elif "\n" in tpl or "{" in tpl or "%" in tpl or '$' in tpl:
            TEMPLATES[tplid] = adapter(source=tpl, lookup=lookup, **settings)
        else:
            TEMPLATES[tplid] = adapter(name=tpl, lookup=lookup, **settings)
    if not TEMPLATES[tplid]:
        abort(500, 'Template (%s) not found' % tpl)
    return TEMPLATES[tplid].render(kwargs)

mako_template = functools.partial(template, template_adapter=MakoTemplate)
cheetah_template = functools.partial(template,
                                     template_adapter=CheetahTemplate)
jinja2_template = functools.partial(template, template_adapter=Jinja2Template)

def view(tpl_name, **defaults):

    def decorator(func):

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if isinstance(result, (dict, DictMixin)):
                tplvars = defaults.copy()
                tplvars.update(result)
                return template(tpl_name, **tplvars)
            elif result is None:
                return template(tpl_name, **defaults)
            return result

        return wrapper

    return decorator

mako_view = functools.partial(view, template_adapter=MakoTemplate)
cheetah_view = functools.partial(view, template_adapter=CheetahTemplate)
jinja2_view = functools.partial(view, template_adapter=Jinja2Template)

TEMPLATE_PATH = ['./', './views/']
TEMPLATES = {}
DEBUG = False
NORUN = False

HTTP_CODES = httplib.responses.copy()
HTTP_CODES[418] = "I'm a teapot"
HTTP_CODES[428] = "Precondition Required"
HTTP_CODES[429] = "Too Many Requests"
HTTP_CODES[431] = "Request Header Fields Too Large"
HTTP_CODES[451] = "Unavailable For Legal Reasons"
HTTP_CODES[511] = "Network Authentication Required"
_HTTP_STATUS_LINES = dict((k, '%d %s' % (k, v))
                          for (k, v) in HTTP_CODES.items())

ERROR_PAGE_TEMPLATE = """
%%try:
    %%from %s import DEBUG, request
    <!DOCTYPE HTML PUBLIC "-//IETF//DTD HTML 2.0//EN">
    <html>
        <head>
            <title>Error: {{e.status}}</title>
            <style type="text/css">
              html {background-color: #eee; font-family: sans-serif;}
              body {background-color: #fff; border: 1px solid #ddd;
                    padding: 15px; margin: 15px;}
              pre {background-color: #eee; border: 1px solid #ddd; padding: 5px;}
            </style>
        </head>
        <body>
            <h1>Error: {{e.status}}</h1>
            <p>Sorry, the requested URL <tt>{{repr(request.url)}}</tt>
               caused an error:</p>
            <pre>{{e.body}}</pre>
            %%if DEBUG and e.exception:
              <h2>Exception:</h2>
              %%try:
                %%exc = repr(e.exception)
              %%except:
                %%exc = '<unprintable %%s object>' %% type(e.exception).__name__
              %%end
              <pre>{{exc}}</pre>
            %%end
            %%if DEBUG and e.traceback:
              <h2>Traceback:</h2>
              <pre>{{e.traceback}}</pre>
            %%end
        </body>
    </html>
%%except ImportError:
    <b>ImportError:</b> Could not generate the error page. Please add lcore to
    the import path.
%%end
""" % __name__

request = LocalRequest()

response = LocalResponse()

ctx = LocalContext.__new__(LocalContext)

local = threading.local()

apps = app = default_app = AppStack()

ext = _ImportRedirect('lcore.ext' if __name__ == '__main__' else
                      __name__ + ".ext", 'lcore_%s').module

def _main(argv):
    args, parser = _cli_parse(argv)

    def _cli_error(cli_msg):
        parser.print_help()
        _stderr('\nError: %s\n' % cli_msg)
        sys.exit(1)

    if args.version:
        print(__version__)
        sys.exit(0)
    if args.docs:
        import webbrowser
        webbrowser.open('https://lcore.lusansapkota.com.np')
        print("Opening documentation in browser...")
        sys.exit(0)
    if not args.app:
        _cli_error("No application entry point specified.")

    sys.path.insert(0, '.')
    sys.modules.setdefault('lcore', sys.modules['__main__'])

    host, port = (args.bind or 'localhost'), 8080
    if ':' in host and host.rfind(']') < host.rfind(':'):
        host, port = host.rsplit(':', 1)
    host = host.strip('[]')

    config = ConfigDict()

    for cfile in args.conf or []:
        try:
            if cfile.endswith('.json'):
                with open(cfile, 'rb') as fp:
                    config.load_dict(json_loads(fp.read()))
            else:
                config.load_config(cfile)
        except configparser.Error as parse_error:
            _cli_error(parse_error)
        except IOError:
            _cli_error("Unable to read config file %r" % cfile)
        except (UnicodeError, TypeError, ValueError) as error:
            _cli_error("Unable to parse config file %r: %s" % (cfile, error))

    for cval in args.param or []:
        if '=' in cval:
            config.update((cval.split('=', 1),))
        else:
            config[cval] = True

    run(args.app,
        host=host,
        port=int(port),
        server=args.server,
        reloader=args.reload,
        plugins=args.plugin,
        debug=args.debug,
        config=config)

def main():
    _main(sys.argv)

if __name__ == '__main__':
    main()
