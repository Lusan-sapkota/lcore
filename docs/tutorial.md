Source: https://lcore.lusansapkota.com.np/tutorial.html

# Tutorial: Build a Notes API

Build and test a small JSON API from scratch: routes, validation, middleware, sessions, error handling and tests. About 15 minutes, one file.

## Set up

You need Python 3.8+ and nothing else. Create a folder, install Lcore and add an `app.py`:

```bash
uv add lcore        # uv (recommended)
pip install lcore     # pip
curl -O https://raw.githubusercontent.com/Lusan-sapkota/lcore/main/lcore.py   # single file
```

```python
from lcore import Lcore

app = Lcore()


@app.get('/ping')
def ping():
    return {'ok': True}


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080)
```

Press **Run**, then **Send**: the code runs in your browser against the real `lcore.py`, no server needed. You can edit it first. On your machine, run `python app.py` and open `http://127.0.0.1:8080/ping`. Returning a `dict` or `list` sends JSON automatically. See [Running Your App](https://lcore.lusansapkota.com.np/getting-started.html#running) for servers and hot reload.

## Routes and URL parameters

Replace `app.py` with a notes store kept in a dict. `<id:int>` only matches digits and passes an `int` to your handler; `abort()` raises an HTTP error that Lcore turns into a response. Setting `response.status` changes the status code.

```python
from lcore import Lcore, request, response, abort

app = Lcore()

NOTES = {}
next_id = 1


@app.get('/notes')
def list_notes():
    return {'notes': list(NOTES.values())}


@app.get('/notes/<id:int>')
def get_note(id):
    if id not in NOTES:
        abort(404, 'No such note')
    return NOTES[id]


@app.post('/notes')
def create_note():
    global next_id
    data = request.json_or({})
    note = {'id': next_id, 'title': data.get('title', ''), 'body': data.get('body', '')}
    NOTES[next_id] = note
    next_id += 1
    response.status = 201
    return note
```

More patterns (wildcards, regex filters, async handlers) are in [Routing](https://lcore.lusansapkota.com.np/routing.html).

## Validate input

Right now a request with no body creates an empty note. `@validate_request` checks the JSON body against a schema, coerces types, strips whitespace and answers `422` with a per-field `fields` map on failure. Put it under the route decorator and read the cleaned data from `request.json`:

```python
from lcore import validate_request


@app.post('/notes')
@validate_request(body={'title': str, 'body': str})
def create_note():
    global next_id
    data = request.json
    note = {'id': next_id, 'title': data['title'], 'body': data['body']}
    ...
```

Try `POST /notes` with `{"title": "x"}` and you get `{"error": "Validation failed", "fields": {"body": "body is required"}}`. Optional fields and query validation are covered in [Request Validation](https://lcore.lusansapkota.com.np/advanced.html#request-validation).

## Group routes under /api/v1

A route group adds a shared prefix. Register routes on the group object (`api`), not on `app`. The prefix applies only to routes registered through the group.

```python
with app.group('/api/v1') as api:

    @api.get('/notes')
    def list_notes():
        ...

    @api.get('/notes/<id:int>')
    def get_note(id):
        ...
```

The routes are now `/api/v1/notes` and `/api/v1/notes/<id>`. Every route in the rest of this tutorial uses `@api`.

## Add middleware

Middleware wraps every request. These four give each response a request id, standard security headers and CORS for one browser origin, and give each client a signed session cookie:

```python
from lcore import (RequestIDMiddleware, SecurityHeadersMiddleware,
                   CORSMiddleware, SessionMiddleware, MemorySessionBackend)

app.use(RequestIDMiddleware())
app.use(SecurityHeadersMiddleware())
app.use(CORSMiddleware(allow_origins=['https://notes.example.com']))
app.use(SessionMiddleware(backend=MemorySessionBackend(warn=False), secret='change-me'))
```

> **Sessions need a real secret.** Replace `change-me` with a long random value from your environment. `MemorySessionBackend` keeps sessions in process memory, so use `SQLiteSessionBackend` or `RedisSessionBackend` when you run more than one worker. See [Sessions](https://lcore.lusansapkota.com.np/middleware.html#sessions).

Everything built in is listed in [Built-in Middleware](https://lcore.lusansapkota.com.np/middleware.html#built-in).

## Log in, and protect deleting

`hash_password` and `verify_password` use PBKDF2-SHA256 with a random salt and a timing-safe comparison. After a successful login, store the user in `request.session`; protected routes check it. Add a rate limit to the create route too:

```python
from lcore import hash_password, verify_password

USERS = {'alice': hash_password('wonderland')}


@api.post('/login')
def login():
    data = request.json_or({})
    stored = USERS.get(data.get('user'))
    if not stored or not verify_password(data.get('password', ''), stored):
        abort(401, 'Bad credentials')
    request.session['user'] = data['user']
    return {'ok': True}


@api.delete('/notes/<id:int>')
def delete_note(id):
    if not request.session.get('user'):
        abort(401, 'Log in first')
    if NOTES.pop(id, None) is None:
        abort(404, 'No such note')
    response.status = 204
    return ''
```

```python
from lcore import rate_limit


@api.post('/notes')
@rate_limit(30, per=60, single_process=True)
@validate_request(body={'title': str, 'body': str})
def create_note():
    ...
```

> **Rate limiting behind a proxy.** `rate_limit` keys on the client address. Behind a reverse proxy, add `ProxyFixMiddleware(trusted_proxies=[...])` or every client shares one bucket. `single_process=True` silences the in-process warning; use a shared backend such as `RedisRateLimitBackend` for multiple workers. See [Security](https://lcore.lusansapkota.com.np/advanced.html#security).

## Custom error responses

Error handlers take the `HTTPError`; its `body` is the message you passed to `abort()`. Unmatched URLs also land here:

```python
@app.error(404)
def not_found(err):
    return {'error': err.body}
```

Lcore already answers JSON errors to clients that send `Accept: application/json`; a handler like this is for when you want your own shape. More in [Error Routes](https://lcore.lusansapkota.com.np/routing.html#error-routes).

## The finished app

Put it all together. This is the exact file the tests below run against. Press **Run**, then try the buttons in order: create a note, delete it (401), log in, delete it again (204).

> **Browser playground note.** Pyodide has no OpenSSL, so in the browser `hash_password` uses a pure-Python PBKDF2 with a lower iteration count. On a real server Lcore uses the standard 600,000 iterations.

```python
from lcore import (Lcore, request, response, abort, validate_request, rate_limit,
                   RequestIDMiddleware, SecurityHeadersMiddleware, CORSMiddleware,
                   SessionMiddleware, MemorySessionBackend, hash_password, verify_password)

app = Lcore()

app.use(RequestIDMiddleware())
app.use(SecurityHeadersMiddleware())
app.use(CORSMiddleware(allow_origins=['https://notes.example.com']))
app.use(SessionMiddleware(backend=MemorySessionBackend(warn=False), secret='change-me'))

NOTES = {}
USERS = {'alice': hash_password('wonderland')}
next_id = 1


@app.error(404)
def not_found(err):
    return {'error': err.body}


with app.group('/api/v1') as api:

    @api.get('/notes')
    def list_notes():
        return {'notes': list(NOTES.values())}

    @api.get('/notes/<id:int>')
    def get_note(id):
        if id not in NOTES:
            abort(404, 'No such note')
        return NOTES[id]

    @api.post('/notes')
    @rate_limit(30, per=60, single_process=True)
    @validate_request(body={'title': str, 'body': str})
    def create_note():
        global next_id
        data = request.json
        note = {'id': next_id, 'title': data['title'], 'body': data['body']}
        NOTES[next_id] = note
        next_id += 1
        response.status = 201
        return note

    @api.delete('/notes/<id:int>')
    def delete_note(id):
        if not request.session.get('user'):
            abort(401, 'Log in first')
        if NOTES.pop(id, None) is None:
            abort(404, 'No such note')
        response.status = 204
        return ''

    @api.post('/login')
    def login():
        data = request.json_or({})
        stored = USERS.get(data.get('user'))
        if not stored or not verify_password(data.get('password', ''), stored):
            abort(401, 'Bad credentials')
        request.session['user'] = data['user']
        return {'ok': True}
```

## Test it without a server

`TestClient` calls your WSGI app directly, keeps cookies between calls (so the login carries over) and needs no network. Save as `test_notes.py` next to `app.py` and run `pytest`:

```python
from lcore import TestClient
from app import app


def test_notes_flow():
    c = TestClient(app)

    r = c.post('/api/v1/notes', json={'title': 'Hi', 'body': 'First note'})
    assert r.status_code == 201
    assert r.json == {'id': 1, 'title': 'Hi', 'body': 'First note'}

    assert c.get('/api/v1/notes/1').json['title'] == 'Hi'
    assert c.get('/api/v1/notes/99').status_code == 404

    r = c.post('/api/v1/notes', json={'title': 'No body'})
    assert r.status_code == 422 and 'fields' in r.json

    assert c.delete('/api/v1/notes/1').status_code == 401
    c.post('/api/v1/login', json={'user': 'alice', 'password': 'wonderland'})
    assert c.delete('/api/v1/notes/1').status_code == 204
```

Lcore's own suite works the same way, and also drives real sockets for things `TestClient` cannot see. Look at `apitests/` in the repository for examples of both.

## Run it for real

The built-in server is for development. Install gunicorn (or waitress) and let `run()` hand off to it, or run it yourself with `gunicorn app:app`:

```python
app.run(server='gunicorn', host='0.0.0.0', port=8080)
```

Put it behind a reverse proxy, add `ProxyFixMiddleware` and a shared session and rate-limit backend, and you have the production setup described in [Production](https://lcore.lusansapkota.com.np/advanced.html#production).

> **Where next?** Browse [Request & Response](https://lcore.lusansapkota.com.np/request-response.html) for uploads and cookies, [Plugins](https://lcore.lusansapkota.com.np/plugins.html) for templates and custom hooks, and the [API Reference](https://lcore.lusansapkota.com.np/api-reference.html) for everything else.
