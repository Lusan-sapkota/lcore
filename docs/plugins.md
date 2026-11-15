Source: https://lcore.lusansapkota.com.np/plugins.html

# Plugins

Extend route handling with plugins that transform callbacks, add features, and integrate external libraries.

## Overview

Plugins modify how individual routes process requests. Unlike middleware (which wraps the entire pipeline), plugins wrap specific route callbacks and can access route configuration.

| Feature | Plugins | Middleware |
|---|---|---|
| Wraps | Individual route callbacks | Entire request pipeline |
| Receives | `callback`, `route` object | `ctx`, `next_handler` |
| Per-route config | Yes (`route.config`) | Via route patterns only |
| Registration | `app.install(plugin)` | `app.use(middleware)` |
| Use case | JSON serialization, DB sessions, template rendering | CORS, auth, logging, rate limiting |

A plugin is an object with two key methods:

- `setup(app)` Called once when the plugin is installed
- `apply(callback, route)` Called for each route; must return a wrapper function

## Built-in Plugins

### JSONPlugin

Installed by default. Automatically converts `dict` and `list` return values to JSON responses with `application/json` Content-Type:

```python
@app.route('/api/users')
def list_users():
    # Automatically serialized to JSON
    return {'users': [{'id': 1, 'name': 'Alice'}]}

# Disable for a specific route
@app.route('/raw', json_disable=True)
def raw():
    return {'this': 'is not serialized'}
```

You can customize the JSON serializer:

```python
from lcore import JSONPlugin
import json

def custom_dumps(obj, **kwargs):
    return json.dumps(obj, default=str, ensure_ascii=False, **kwargs)

app.uninstall('json')
app.install(JSONPlugin(json_dumps=custom_dumps))
```

### TemplatePlugin

Installed by default. If a route has a `template` config and returns a `dict`, the dict is used as template context:

```python
@app.route('/page', template='page.html')
def page():
    return {'title': 'My Page', 'items': [1, 2, 3]}
```

## Writing Plugins

### Plugin Class Structure

```python
class MyPlugin:
    name = 'myplugin'  # Unique name
    api = 2            # Plugin API version (always 2)

    def __init__(self, option='default'):
        self.option = option

    def setup(self, app):
        """Called once when installed. Access app config here."""
        self.app = app

    def apply(self, callback, route):
        """Called for each route. Return a wrapper function."""
        # Check per-route config
        if route.config.get('myplugin_skip'):
            return callback  # Don't wrap this route

        def wrapper(*args, **kwargs):
            # Before handler
            start = time.time()
            result = callback(*args, **kwargs)
            # After handler
            duration = time.time() - start
            response.set_header('X-Duration', f'{duration:.4f}')
            return result

        return wrapper

app.install(MyPlugin(option='custom'))
```

### Example: Database Session Plugin

```python
class SQLAlchemyPlugin:
    name = 'sqlalchemy'
    api = 2

    def __init__(self, engine):
        self.engine = engine

    def setup(self, app):
        from sqlalchemy.orm import sessionmaker
        self.Session = sessionmaker(bind=self.engine)

    def apply(self, callback, route):
        # Skip if route doesn't need DB
        if route.config.get('no_db'):
            return callback

        def wrapper(*args, **kwargs):
            session = self.Session()
            try:
                # Inject session as keyword argument
                kwargs['db'] = session
                result = callback(*args, **kwargs)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return wrapper

# Usage
from sqlalchemy import create_engine
engine = create_engine('sqlite:///app.db')
app.install(SQLAlchemyPlugin(engine))

@app.route('/users')
def list_users(db):
    # db session is automatically injected
    return {'users': db.query(User).all()}

@app.route('/health', no_db=True)
def health():
    # Skipped by plugin (no_db=True)
    return {'status': 'ok'}
```

### Simple Function Plugin

For simple cases, a plugin can be just a function that wraps callbacks:

```python
def uppercase_plugin(callback, route):
    def wrapper(*args, **kwargs):
        result = callback(*args, **kwargs)
        if isinstance(result, str):
            return result.upper()
        return result
    return wrapper

app.install(uppercase_plugin)
```

## Plugin API

```python
# Install a plugin
app.install(MyPlugin())

# Install returns the plugin instance
plugin = app.install(MyPlugin())

# Uninstall by name
app.uninstall('myplugin')

# Uninstall by instance
app.uninstall(plugin)

# List all installed plugins
for p in app.plugins:
    print(getattr(p, 'name', type(p).__name__))

# Get all plugins for a specific route
route = app.routes[0]
all_plugins = route.all_plugins()

# Reset all routes (re-applies plugins)
app.reset()
```

| Method | Description |
|---|---|
| `app.install(plugin)` | Install plugin globally. Calls `setup(app)`. |
| `app.uninstall(plugin)` | Remove by name (string) or instance. Calls `close()` if available. |
| `app.plugins` | List of all installed plugins |
| `app.reset()` | Reset route cache and re-apply all plugins |
| `route.all_plugins()` | Get all plugins applied to a route |

## Skipping Plugins

Skip specific plugins on individual routes:

```python
# Skip the JSON plugin for this route
@app.route('/raw', skip=['json'])
def raw():
    response.content_type = 'text/plain'
    return 'plain text response'

# Skip all plugins (maximum performance)
@app.route('/health', skip=True)
def health():
    return 'ok'

# Skip multiple plugins by name
@app.route('/fast', skip=['json', 'template', 'sqlalchemy'])
def fast():
    return b'binary response'
```

> **Performance Tip**
> Use `skip=True` on health check endpoints and high-frequency internal routes where you don't need plugin processing. This reduces per-request overhead to the absolute minimum.
