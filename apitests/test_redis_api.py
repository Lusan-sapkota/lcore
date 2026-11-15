"""RedisRateLimitBackend against a live Redis (skipped when none is reachable)."""
import time, uuid, warnings
import pytest
import lcore
from lcore import Lcore, TestClient, rate_limit, ProxyFixMiddleware, RedisRateLimitBackend

URL = 'redis://localhost:6379/15'  # db 15: keeps test keys away from real data


def _up():
    try:
        import redis
        redis.Redis.from_url(URL, socket_connect_timeout=0.3).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason='no redis server / redis-py')


@pytest.fixture
def rb():
    b = RedisRateLimitBackend(URL, prefix='t%s:' % uuid.uuid4().hex[:8])
    yield b
    for k in b._r.scan_iter(b._prefix + '*'): b._r.delete(k)
    b.close()


def test_allows_up_to_limit_then_denies(rb):
    assert [rb.consume('k', 3, 60) for _ in range(5)] == [True, True, True, False, False]


def test_keys_are_isolated(rb):
    for _ in range(2): rb.consume('a', 2, 60)
    assert rb.consume('a', 2, 60) is False and rb.consume('b', 2, 60) is True


def test_window_resets_after_per(rb):
    assert rb.consume('k', 1, 1) is True and rb.consume('k', 1, 1) is False
    time.sleep(1.2)
    assert rb.consume('k', 1, 1) is True


def test_counter_is_atomic_across_threads(rb):
    import threading
    allowed = []

    def w():
        for _ in range(20): allowed.append(rb.consume('t', 50, 60))

    ts = [threading.Thread(target=w) for _ in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sum(allowed) == 50  # exactly the limit, 160 attempts


def test_decorator_with_redis_backend_returns_429(rb):
    app = Lcore(); app.use(ProxyFixMiddleware(num_proxies=1))

    @app.get('/')
    @rate_limit(2, 60, backend=rb)
    def h(): return 'ok'

    c = TestClient(app, cookies=False)
    codes = [c.get('/', headers={'X-Forwarded-For': '9.9.9.9'}).status_code for _ in range(4)]
    assert codes == [200, 200, 429, 429]
    assert c.get('/', headers={'X-Forwarded-For': '8.8.8.8'}).status_code == 200


def test_fails_open_when_redis_is_unreachable():
    b = RedisRateLimitBackend('redis://localhost:1/0', socket_connect_timeout=0.2)
    try:
        assert b.consume('k', 1, 60) is True and b.consume('k', 1, 60) is True
    finally:
        b.close()
