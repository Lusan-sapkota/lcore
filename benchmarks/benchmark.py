"""
Benchmark: Lcore vs Flask vs Bottle
Comprehensive WSGI throughput benchmark measuring pure framework overhead.
Tests: plaintext, JSON, route params, middleware stack, error handling, multi-route dispatch.

Usage:
    python benchmark.py              # Standard run (50k iterations)
    python benchmark.py --quick      # Quick run (10k iterations)
    python benchmark.py --full       # Full run (100k iterations)
"""
import time
import io
import json
import sys
import os
import statistics

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Parse CLI args
if '--quick' in sys.argv:
    ITERATIONS = 10_000
    WARMUP = 500
    MODE = 'quick'
elif '--full' in sys.argv:
    ITERATIONS = 100_000
    WARMUP = 2_000
    MODE = 'full'
else:
    ITERATIONS = 50_000
    WARMUP = 1_000
    MODE = 'standard'

RUNS = 3  # Number of runs per test for statistical accuracy


def make_environ(path='/', method='GET', body=b'', content_type='', query_string='', headers=None):
    """Create a WSGI environ dict."""
    env = {
        'REQUEST_METHOD': method,
        'PATH_INFO': path,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '8080',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'HTTP_HOST': 'localhost:8080',
        'wsgi.input': io.BytesIO(body),
        'wsgi.errors': sys.stderr,
        'wsgi.url_scheme': 'http',
        'CONTENT_TYPE': content_type,
        'CONTENT_LENGTH': str(len(body)),
        'QUERY_STRING': query_string,
        'SCRIPT_NAME': '',
        'HTTP_ACCEPT': 'application/json',
        'HTTP_USER_AGENT': 'Benchmark/1.0',
    }
    if headers:
        for k, v in headers.items():
            env['HTTP_' + k.upper().replace('-', '_')] = v
    return env


def run_bench(app, path, method='GET', body=b'', content_type='', query_string='', headers=None):
    """Run a single benchmark: warmup + timed iterations x RUNS, return best run."""
    def start_response(status, headers, exc_info=None):
        pass

    run_results = []
    for _ in range(RUNS):
        # Warmup
        for _ in range(WARMUP):
            env = make_environ(path, method, body, content_type, query_string, headers)
            list(app(env, start_response))

        # Timed run
        start = time.perf_counter()
        for _ in range(ITERATIONS):
            env = make_environ(path, method, body, content_type, query_string, headers)
            list(app(env, start_response))
        elapsed = time.perf_counter() - start
        run_results.append(elapsed)

    best = min(run_results)
    median = statistics.median(run_results)
    rps_best = ITERATIONS / best
    rps_median = ITERATIONS / median
    avg_us = (median / ITERATIONS) * 1_000_000
    return {'rps': round(rps_best), 'rps_median': round(rps_median), 'avg_us': round(avg_us, 1)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LCORE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def bench_lcore():
    from lcore import Lcore, Middleware, CORSMiddleware, SecurityHeadersMiddleware

    results = {}

    # 1. Plaintext
    app = Lcore()
    @app.route('/')
    def index():
        return 'Hello, World!'
    results['plaintext'] = run_bench(app, '/')

    # 2. JSON response
    app = Lcore()
    @app.route('/json')
    def json_route():
        return {'message': 'Hello, World!', 'status': 'ok', 'code': 200}
    results['json'] = run_bench(app, '/json')

    # 3. Route with typed parameter
    app = Lcore()
    @app.route('/user/<id:int>')
    def user(id):
        return {'id': id, 'name': f'User {id}'}
    results['param'] = run_bench(app, '/user/42')

    # 4. Middleware stack (2 middleware layers)
    app = Lcore()
    app.use(CORSMiddleware(allow_origins=['*']))
    app.use(SecurityHeadersMiddleware())
    @app.route('/mw')
    def mw_route():
        return {'data': 'with middleware'}
    results['middleware'] = run_bench(app, '/mw')

    # 5. 404 Not Found (routing miss)
    app = Lcore()
    @app.route('/')
    def dummy():
        return 'ok'
    results['404'] = run_bench(app, '/nonexistent')

    # 6. Multi-route dispatch (app with 50 routes, hit the last one)
    app = Lcore()
    for i in range(50):
        path = f'/route/{i}'
        def make_handler(n):
            def handler():
                return {'route': n}
            handler.__name__ = f'route_{n}'
            return handler
        app.route(path)(make_handler(i))
    results['multi_route'] = run_bench(app, '/route/49')

    # 7. POST with JSON body
    app = Lcore()
    @app.post('/create')
    def create():
        from lcore import request
        data = request.json
        return {'created': True, 'name': data.get('name', '')}
    body = json.dumps({'name': 'test', 'email': 'test@example.com'}).encode()
    results['post_json'] = run_bench(app, '/create', method='POST', body=body, content_type='application/json')

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FLASK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def bench_flask():
    from flask import Flask, jsonify, request as flask_request

    results = {}

    # 1. Plaintext
    app = Flask(__name__)
    @app.route('/')
    def index():
        return 'Hello, World!'
    results['plaintext'] = run_bench(app, '/')

    # 2. JSON
    app = Flask(__name__)
    @app.route('/json')
    def json_route():
        return jsonify(message='Hello, World!', status='ok', code=200)
    results['json'] = run_bench(app, '/json')

    # 3. Param
    app = Flask(__name__)
    @app.route('/user/<int:id>')
    def user(id):
        return jsonify(id=id, name=f'User {id}')
    results['param'] = run_bench(app, '/user/42')

    # 4. Middleware (Flask uses before/after request)
    app = Flask(__name__)
    @app.before_request
    def before():
        pass
    @app.after_request
    def after(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    @app.route('/mw')
    def mw_route():
        return jsonify(data='with middleware')
    results['middleware'] = run_bench(app, '/mw')

    # 5. 404
    app = Flask(__name__)
    @app.route('/')
    def dummy():
        return 'ok'
    results['404'] = run_bench(app, '/nonexistent')

    # 6. Multi-route
    app = Flask(__name__)
    for i in range(50):
        path = f'/route/{i}'
        def make_handler(n):
            def handler():
                return jsonify(route=n)
            handler.__name__ = f'route_{n}'
            return handler
        app.route(path)(make_handler(i))
    results['multi_route'] = run_bench(app, '/route/49')

    # 7. POST JSON
    app = Flask(__name__)
    @app.route('/create', methods=['POST'])
    def create():
        data = flask_request.get_json(force=True)
        return jsonify(created=True, name=data.get('name', ''))
    body = json.dumps({'name': 'test', 'email': 'test@example.com'}).encode()
    results['post_json'] = run_bench(app, '/create', method='POST', body=body, content_type='application/json')

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BOTTLE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def bench_bottle():
    import bottle

    results = {}

    # 1. Plaintext
    app = bottle.Bottle()
    @app.route('/')
    def index():
        return 'Hello, World!'
    results['plaintext'] = run_bench(app, '/')

    # 2. JSON
    app = bottle.Bottle()
    @app.route('/json')
    def json_route():
        return {'message': 'Hello, World!', 'status': 'ok', 'code': 200}
    results['json'] = run_bench(app, '/json')

    # 3. Param
    app = bottle.Bottle()
    @app.route('/user/<id:int>')
    def user(id):
        return {'id': id, 'name': f'User {id}'}
    results['param'] = run_bench(app, '/user/42')

    # 4. Middleware (Bottle plugin)
    app = bottle.Bottle()
    def mw_plugin(callback):
        def wrapper(*a, **kw):
            bottle.response.headers['X-Frame-Options'] = 'DENY'
            bottle.response.headers['Access-Control-Allow-Origin'] = '*'
            return callback(*a, **kw)
        return wrapper
    app.install(mw_plugin)
    @app.route('/mw')
    def mw_route():
        return {'data': 'with middleware'}
    results['middleware'] = run_bench(app, '/mw')

    # 5. 404
    app = bottle.Bottle()
    @app.route('/')
    def dummy():
        return 'ok'
    results['404'] = run_bench(app, '/nonexistent')

    # 6. Multi-route
    app = bottle.Bottle()
    for i in range(50):
        path = f'/route/{i}'
        def make_handler(n):
            def handler():
                return {'route': n}
            handler.__name__ = f'route_{n}'
            return handler
        app.route(path)(make_handler(i))
    results['multi_route'] = run_bench(app, '/route/49')

    # 7. POST JSON
    app = bottle.Bottle()
    @app.route('/create', method='POST')
    def create():
        data = json.loads(bottle.request.body.read())
        return {'created': True, 'name': data.get('name', '')}
    body = json.dumps({'name': 'test', 'email': 'test@example.com'}).encode()
    results['post_json'] = run_bench(app, '/create', method='POST', body=body, content_type='application/json')

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEST_LABELS = {
    'plaintext': 'Plaintext',
    'json': 'JSON',
    'param': 'Params',
    'middleware': 'Middleware',
    '404': '404 Miss',
    'multi_route': 'Multi-Route',
    'post_json': 'POST JSON',
}

if __name__ == '__main__':
    print(f"Benchmark: {ITERATIONS:,} iterations x {RUNS} runs per test, {WARMUP:,} warmup ({MODE} mode)\n")
    print(f"{'Framework':<10} {'Test':<14} {'Best Req/s':>12} {'Median Req/s':>14} {'Avg (us)':>10}")
    print("-" * 64)

    all_results = {}
    frameworks = [('Lcore', bench_lcore), ('Flask', bench_flask), ('Bottle', bench_bottle)]

    for name, fn in frameworks:
        try:
            results = fn()
            all_results[name] = results
            for test in TEST_LABELS:
                if test in results:
                    d = results[test]
                    print(f"{name:<10} {TEST_LABELS[test]:<14} {d['rps']:>12,} {d['rps_median']:>14,} {d['avg_us']:>10.1f}")
            print()
        except ImportError as e:
            print(f"{name:<10} SKIPPED ({e})\n")
        except Exception as e:
            print(f"{name:<10} ERROR: {e}\n")

    # Summary table
    tests = list(TEST_LABELS.keys())
    print("=" * 80)
    print("SUMMARY — Best requests/second (higher is better)\n")
    header = f"{'Test':<14}"
    for fw in ['Lcore', 'Flask', 'Bottle']:
        if fw in all_results:
            header += f" {fw:>12}"
    header += f" {'Lcore vs Flask':>16}"
    print(header)
    print("-" * len(header))

    for test in tests:
        row = f"{TEST_LABELS[test]:<14}"
        lcore_rps = 0
        flask_rps = 0
        for fw in ['Lcore', 'Flask', 'Bottle']:
            if fw in all_results and test in all_results[fw]:
                rps = all_results[fw][test]['rps']
                row += f" {rps:>12,}"
                if fw == 'Lcore':
                    lcore_rps = rps
                elif fw == 'Flask':
                    flask_rps = rps
            else:
                row += f" {'N/A':>12}"
        if flask_rps > 0:
            ratio = lcore_rps / flask_rps
            row += f" {ratio:>15.1f}x"
        else:
            row += f" {'N/A':>16}"
        print(row)

    # JSON output
    print("\n--- JSON ---")
    print(json.dumps(all_results, indent=2))
