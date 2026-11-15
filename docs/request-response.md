Source: https://lcore.lusansapkota.com.np/request-response.html

# Request & Response

Access incoming request data and control outgoing responses through thread-safe proxy objects.

## The Request Object

The `request` object is a thread-local proxy to the current `BaseRequest`. Import it from `lcore`:

```python
from lcore import request

@app.route('/info')
def info():
    return {
        'method': request.method,        # 'GET', 'POST', etc.
        'path': request.path,            # '/info'
        'url': request.url,              # 'http://localhost:8080/info?q=test'
        'fullpath': request.fullpath,    # '/info' (with script_name)
        'ip': request.remote_addr,       # '127.0.0.1'
        'content_type': request.content_type,
        'content_length': request.content_length,
        'is_ajax': request.is_xhr,       # True if X-Requested-With
        'chunked': request.chunked,      # True if chunked encoding
    }
```

### Request Properties

| Property | Type | Description |
|---|---|---|
| `method` | `str` | HTTP method (`GET`, `POST`, etc.) |
| `path` | `str` | Request path without query string |
| `url` | `str` | Full request URL including scheme, host, path, query |
| `fullpath` | `str` | Path with `script_name` prefix |
| `query_string` | `str` | Raw query string |
| `script_name` | `str` | WSGI SCRIPT_NAME |
| `remote_addr` | `str` | Client IP address |
| `remote_route` | `list` | List of IPs from X-Forwarded-For |
| `content_type` | `str` | Content-Type header value |
| `content_length` | `int` | Content-Length (-1 if invalid) |
| `is_xhr` | `bool` | True if XMLHttpRequest |
| `is_ajax` | `bool` | Alias for `is_xhr` |
| `auth` | `tuple` | Parsed Basic auth `(username, password)` or None |
| `chunked` | `bool` | True if chunked transfer encoding |

## Query Parameters

```python
# GET /search?q=python&page=2&tag=web&tag=api
@app.route('/search')
def search():
    q = request.query.get('q', '')          # 'python'
    page = request.query.get('page', '1')   # '2' (always strings)
    tags = request.query.getall('tag')       # ['web', 'api']
    return {'q': q, 'page': int(page), 'tags': tags}
```

`request.query` and `request.GET` are `FormsDict` instances. Use `request.params` to access combined query + form data.

## Form Data

```python
# POST with application/x-www-form-urlencoded
@app.post('/login')
def login():
    username = request.forms.get('username')
    password = request.forms.get('password')
    return {'user': username}
```

`request.forms` contains form fields from POST bodies. `request.POST` includes both form fields and file uploads from multipart requests.

## JSON Body

```python
# POST with application/json body
@app.post('/api/users')
def create_user():
    data = request.json  # Auto-parsed dict
    if data is None:
        abort(400, 'Invalid JSON')
    return {'created': data.get('name')}
```

> **Note**
> `request.json` returns `None` if the Content-Type is not `application/json` or the body is empty. A malformed body raises `HTTPError(400, 'Invalid JSON')`, so you never see half-parsed data. Use `request.json_or({})` to fall back to a default when the body is empty. To validate fields and types, see `@validate_request` in [Advanced](https://lcore.lusansapkota.com.np/advanced.html#request-validation): it returns 422 with a per-field `fields` map.

> **v0.0.4: No more 100KB silent limit**
> Previously `request.json` and URL-encoded POST bodies had a hard 100KB cap (`MEMFILE_MAX`) independent of `BodyLimitMiddleware`. A 150KB JSON payload would silently fail with 413 even when `BodyLimitMiddleware` allowed 50MB. v0.0.4 reads the full body via `self.body.read()`, which spills to disk for large payloads and respects `BodyLimitMiddleware` exclusively. No more mystery ceiling.

## File Uploads

```python
@app.post('/upload')
def upload():
    upload = request.files.get('document')
    if not upload:
        abort(400, 'No file uploaded')

    # FileUpload properties
    name = upload.filename        # Sanitized filename
    content_type = upload.content_type
    size = upload.content_length

    # Save to disk
    upload.save('/tmp/uploads/', overwrite=True)

    return {
        'filename': name,
        'content_type': content_type,
        'size': size
    }
```

> **v0.0.4: Multipart limits respect BodyLimitMiddleware**
> The multipart parser's `disk_limit` is now set from `environ['lcore.body_max_size']` (injected by `BodyLimitMiddleware`). Configure one limit and everything obeys it JSON bodies, URL-encoded forms, and file uploads all capped by the same setting.

### FileUpload Object

| Property/Method | Description |
|---|---|
| `.filename` | Sanitized filename (path components stripped) |
| `.file` | File-like object for reading content |
| `.content_type` | MIME type from Content-Type header |
| `.content_length` | File size in bytes |
| `.get_header(name)` | Get a specific multipart header |
| `.save(dest, overwrite=False)` | Save file to directory or path |

## Cookies

### Reading Cookies

```python
@app.route('/read')
def read_cookies():
    # Plain cookies
    session_id = request.cookies.get('session_id', 'none')

    # Signed cookies (HMAC-SHA256 + JSON, tamper-proof)
    user = request.get_cookie('user', secret='my-secret-key')

    return {'session': session_id, 'user': user}
```

### Setting Cookies

v0.0.4 sets **secure defaults**: `samesite='Lax'` and `httponly=True` are applied automatically unless you override them. This means a basic `set_cookie('session', 'abc')` is already reasonably locked down.

```python
from datetime import timedelta

@app.route('/set')
def set_cookies():
    # Plain cookie  secure by default (v0.0.4)
    response.set_cookie('session_id', 'abc123', path='/')
    # Automatically gets: samesite=Lax, httponly=True

    # Override defaults when needed (e.g. CSRF token must be JS-readable)
    response.set_cookie('_csrf_token', token,
        httponly=False,       # JS needs to read this
        samesite='Strict'     # Tighter CSRF protection
    )

    # Signed cookie (tamper-proof, HMAC-SHA256)
    response.set_cookie('user', 'alice',
        secret='my-secret-key',
        max_age=timedelta(days=7)
    )

    # Delete a cookie
    response.delete_cookie('old_cookie')

    return 'Cookies set!'
```

### Cookie Options

| Option | Type | Description |
|---|---|---|
| `max_age` | `int` / `timedelta` | Cookie lifetime in seconds (timedelta auto-converted) |
| `expires` | `datetime` | Absolute expiry time |
| `path` | `str` | Cookie path scope (default: current path) |
| `domain` | `str` | Cookie domain scope |
| `secure` | `bool` | Only send over HTTPS |
| `httponly` | `bool` | Prevent JavaScript access |
| `samesite` | `str` | `Lax`, `Strict`, or `None` |

> **Signed Cookie Security**
> Signed cookies use **HMAC-SHA256** with **JSON serialization** (not pickle). The signature prevents tampering, and JSON ensures safe deserialization. Always use a strong secret key.

## Headers

### Request Headers

```python
@app.route('/headers')
def show_headers():
    # Case-insensitive access
    auth = request.headers.get('Authorization')
    ct = request.get_header('Content-Type', 'none')
    custom = request.headers.get('X-Custom-Header')
    return {'auth': auth, 'content_type': ct, 'custom': custom}
```

### Response Headers

```python
@app.route('/api/data')
def data():
    response.set_header('X-Request-ID', 'abc-123')
    response.set_header('Cache-Control', 'max-age=3600')
    response.add_header('Set-Cookie', 'a=1')  # add_header allows duplicates
    response.content_type = 'application/json'
    return {'data': 'value'}
```

| Method | Description |
|---|---|
| `response.set_header(name, value)` | Set header (replaces existing) |
| `response.add_header(name, value)` | Add header (allows multiple values) |
| `response.get_header(name)` | Read a response header |

## The Response Object

```python
from lcore import response

@app.route('/custom')
def custom_response():
    response.status = 201
    response.content_type = 'application/json'
    response.set_header('X-Custom', 'value')
    return {'status': 'created'}
```

### Response Properties

| Property | Type | Description |
|---|---|---|
| `status` | `int` / `str` | Set with int (`200`) or string (`'200 OK'`) |
| `status_code` | `int` | Numeric status code (read-only) |
| `status_line` | `str` | Full status line (read-only) |
| `content_type` | `str` | Content-Type header (default: `text/html; charset=UTF-8`) |
| `content_length` | `int` | Content-Length header |
| `charset` | `str` | Character set from Content-Type |
| `expires` | `datetime` | Expires header |
| `headers` | `HeaderDict` | Mutable header dictionary |
| `body` | `str`/`bytes` | Response body |

### HTTPResponse for Immediate Return

```python
from lcore import HTTPResponse

@app.route('/immediate')
def immediate():
    raise HTTPResponse(
        body='{"error": "custom"}',
        status=418,
        headers={'Content-Type': 'application/json'}
    )
```

### HTTPError v0.0.4 Improvements

Raise `HTTPError` to trigger your registered error handlers. v0.0.4 fixes two long-standing papercuts:

#### Headers survive the raise

Previously, `HTTPError.apply()` **replaced** all response headers any header you set before raising was wiped. v0.0.4 **merges** instead:

```python
@app.post('/api/login')
def login():
    response.set_header('Content-Type', 'application/json')
    # ... auth logic ...
    raise HTTPError(401, '{"error":"Unauthorized"}')
    # v0.0.4: Content-Type: application/json survives. v0.0.3: gone.
```

#### One-liner with content_type

Skip the `response.set_header` dance entirely:

```python
raise HTTPError(401, body='{"error":"Unauthorized"}', content_type='application/json')
raise HTTPError(422, body=json_dumps({'error': 'Validation failed', 'fields': {...}}),
                content_type='application/json')
```

#### Global JSON errors

For pure API servers, one config line replaces every per-status-code error handler:

```python
app.config['error.format'] = 'json'
# All errors now return {"error": "...", "status": N}  no handlers needed

# Without the config, any request with Accept: application/json (listed before
# text/html) gets the same JSON, and browsers still get the HTML page.
```

## Static Files

```python
from lcore import static_file

@app.route('/static/<filepath:path>')
def serve_static(filepath):
    return static_file(filepath, root='./public')

# With download mode
@app.route('/download/<filename>')
def download(filename):
    return static_file(filename, root='./files', download=True)

# Custom headers and mimetype
@app.route('/assets/<path:path>')
def assets(path):
    return static_file(path, root='./assets',
        headers={'Cache-Control': 'max-age=86400'}
    )
```

### static_file Parameters

| Parameter | Type | Description |
|---|---|---|
| `filename` | `str` | Relative file path |
| `root` | `str` | Root directory to serve from |
| `mimetype` | `str`/`bool` | Override MIME type (`True` = auto-detect) |
| `download` | `bool`/`str` | `True` or filename for Content-Disposition |
| `charset` | `str` | Character set for text files (default: UTF-8) |
| `etag` | `str` | Custom ETag (default: SHA256 auto-generated) |
| `headers` | `dict` | Additional response headers |

> **Security**
> `static_file` uses `os.path.realpath()` to resolve symlinks and prevent path traversal attacks. Download filenames are sanitized with `os.path.basename()`. ETags use SHA256.

## Redirects

```python
from lcore import redirect

@app.route('/old-page')
def old_page():
    redirect('/new-page')           # 303 See Other (default)

@app.route('/moved')
def moved():
    redirect('/new-location', 301)  # Permanent redirect

@app.route('/login-required')
def login_required():
    redirect('/login', 307)         # Temporary, preserves method
```

### Redirect Codes

| Code | Name | Use Case |
|---|---|---|
| `301` | Moved Permanently | URL has permanently changed (SEO) |
| `302` | Found | Temporary redirect (legacy) |
| `303` | See Other | Redirect after POST (default) |
| `307` | Temporary Redirect | Preserves HTTP method |
| `308` | Permanent Redirect | Permanent, preserves method |
