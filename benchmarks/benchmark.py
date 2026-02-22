"""
Benchmark: Lcore vs Flask vs Bottle
Measures requests/second for simple JSON responses using each framework's
built-in WSGI handler (wsgiref-style test without network overhead).
"""
import time
import io
import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

ITERATIONS = 10000
WARMUP = 500

def make_environ(path='/', method='GET'):
    """Create a minimal WSGI environ dict."""
    return {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8080',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'HTTP_HOST': 'localhost:8080',
        'wsgi.input': io.BytesIO(b''),
        'wsgi.errors': sys.stderr,
        'wsgi.url_scheme': 'http',
        'CONTENT_TYPE': '',
        'CONTENT_LENGTH': '0',
        'QUERY_STRING': '',
        'SCRIPT_NAME': '',
    }

def bench_lcore():
    from lcore import Lcore
    app = Lcore()

    @app.route('/')
    def index():
        return 'Hello, World!'

    @app.route('/json')
    def json_route():
        return {'message': 'Hello, World!', 'status': 'ok'}

    @app.route('/user/<id:int>')
    def user(id):
        return {'id': id, 'name': f'User {id}'}

    results = {}
    for name, path in [('plaintext', '/'), ('json', '/json'), ('param', '/user/42')]:
        captured = []
        def start_response(status, headers, exc_info=None):
            pass

        # Warmup
        for _ in range(WARMUP):
            env = make_environ(path)
            list(app(env, start_response))

        # Benchmark
        start = time.perf_counter()
        for _ in range(ITERATIONS):
            env = make_environ(path)
            list(app(env, start_response))
        elapsed = time.perf_counter() - start
        rps = ITERATIONS / elapsed
        results[name] = {'rps': rps, 'avg_us': (elapsed / ITERATIONS) * 1_000_000}

    return results

def bench_flask():
    from flask import Flask, jsonify
    app = Flask(__name__)

    @app.route('/')
    def index():
        return 'Hello, World!'

    @app.route('/json')
    def json_route():
        return jsonify(message='Hello, World!', status='ok')

    @app.route('/user/<int:id>')
    def user(id):
        return jsonify(id=id, name=f'User {id}')

    results = {}
    for name, path in [('plaintext', '/'), ('json', '/json'), ('param', '/user/42')]:
        captured = []
        def start_response(status, headers, exc_info=None):
            pass

        # Warmup
        for _ in range(WARMUP):
            env = make_environ(path)
            with app.request_context(env):
                list(app(env, start_response))

        # Benchmark
        start = time.perf_counter()
        for _ in range(ITERATIONS):
            env = make_environ(path)
            list(app(env, start_response))
        elapsed = time.perf_counter() - start
        rps = ITERATIONS / elapsed
        results[name] = {'rps': rps, 'avg_us': (elapsed / ITERATIONS) * 1_000_000}

    return results

def bench_bottle():
    import bottle
    app = bottle.Bottle()

    @app.route('/')
    def index():
        return 'Hello, World!'

    @app.route('/json')
    def json_route():
        return {'message': 'Hello, World!', 'status': 'ok'}

    @app.route('/user/<id:int>')
    def user(id):
        return {'id': id, 'name': f'User {id}'}

    results = {}
    for name, path in [('plaintext', '/'), ('json', '/json'), ('param', '/user/42')]:
        def start_response(status, headers, exc_info=None):
            pass

        # Warmup
        for _ in range(WARMUP):
            env = make_environ(path)
            list(app(env, start_response))

        # Benchmark
        start = time.perf_counter()
        for _ in range(ITERATIONS):
            env = make_environ(path)
            list(app(env, start_response))
        elapsed = time.perf_counter() - start
        rps = ITERATIONS / elapsed
        results[name] = {'rps': rps, 'avg_us': (elapsed / ITERATIONS) * 1_000_000}

    return results

if __name__ == '__main__':
    print(f"Benchmark: {ITERATIONS} iterations per test, {WARMUP} warmup\n")
    print(f"{'Framework':<12} {'Test':<12} {'Req/sec':>10} {'Avg (us)':>10}")
    print("-" * 48)

    all_results = {}
    for name, fn in [('Lcore', bench_lcore), ('Flask', bench_flask), ('Bottle', bench_bottle)]:
        try:
            results = fn()
            all_results[name] = results
            for test, data in results.items():
                print(f"{name:<12} {test:<12} {data['rps']:>10,.0f} {data['avg_us']:>10.1f}")
        except Exception as e:
            print(f"{name:<12} ERROR: {e}")

    # Summary
    print("\n" + "=" * 48)
    print("SUMMARY (requests/second, higher is better):\n")
    print(f"{'Test':<12} {'Lcore':>10} {'Flask':>10} {'Bottle':>10}")
    print("-" * 44)
    for test in ['plaintext', 'json', 'param']:
        row = f"{test:<12}"
        for fw in ['Lcore', 'Flask', 'Bottle']:
            if fw in all_results and test in all_results[fw]:
                row += f" {all_results[fw][test]['rps']:>10,.0f}"
            else:
                row += f" {'N/A':>10}"
        print(row)

    # JSON output for docs
    print("\n--- JSON ---")
    print(json.dumps(all_results, indent=2, default=lambda x: round(x, 1)))
