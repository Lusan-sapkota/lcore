"""API-level tests for SessionMiddleware and the Memory/SQLite session backends."""
import json, threading, time, socket
import pytest
import lcore
from lcore import (Lcore, HTTPError, request, response, SessionMiddleware, MemorySessionBackend,
                   SQLiteSessionBackend, SessionBackend, ctx as gctx, TestClient)

SECRET = 'test-secret'


def _redis_url():
    try:
        import redis
        redis.Redis(socket_connect_timeout=0.3).ping()
    except Exception:
        return None
    return 'redis://localhost:6379/15'  # db 15: keeps test keys away from real data


@pytest.fixture(params=['memory', 'sqlite', 'redis'])
def backend(request, tmp_path):
    if request.param == 'memory':
        b = MemorySessionBackend(warn=False)
    elif request.param == 'sqlite':
        b = SQLiteSessionBackend(str(tmp_path / 's.db'), cleanup_every=0)
    else:
        url = _redis_url()
        if not url:
            pytest.skip('no redis server / redis-py')
        import uuid
        b = lcore.RedisSessionBackend(url, prefix='t%s:' % uuid.uuid4().hex[:8])
        yield b
        for k in b._r.scan_iter(b._prefix + '*'): b._r.delete(k)  # leave nothing behind
        b.close()
        return
    yield b
    b.close()


def make_app(backend, **kw):
    app = Lcore()
    app.use(SessionMiddleware(backend=backend, secret=SECRET, **kw))

    @app.get('/peek')
    def peek(): return json.dumps(dict(request.session.items()))

    @app.get('/set')
    def set_(): request.session[request.query.get('k', 'k')] = request.query.get('v', 'v'); return 'ok'

    @app.get('/sid')
    def sid(): return request.session.sid

    @app.get('/login')
    def login():
        old = request.session.sid
        request.session.bind_user(request.query.get('u', 'alice'))
        return json.dumps([old, request.session.sid])

    @app.get('/whoami')
    def who(): return str(request.session.user_id)

    @app.get('/logout')
    def logout(): request.session.destroy(); return 'bye'

    @app.get('/list')
    def lst(): return str(len(request.session.list_sessions()))

    @app.get('/revoke_others')
    def ro(): return str(request.session.revoke_other_sessions())

    @app.get('/revoke_all')
    def ra(): return str(request.session.revoke_all_sessions())

    @app.get('/flash/set')
    def fset(): request.session['flash'] = 'hi'; return 'ok'

    @app.get('/flash/pop')
    def fpop(): return str(request.session.pop('flash', None))

    @app.get('/read_only')
    def ro2(): return str(request.session.get('nothing'))

    @app.get('/touch_nothing')
    def tn(): return 'no session access'

    @app.get('/redirect_login')
    def rl():
        request.session['x'] = 1
        lcore.redirect('/peek')

    @app.get('/err_after_set')
    def eas():
        request.session['e'] = 1
        raise HTTPError(400, 'bad')
    return app


def sc(r, name='lcore_session'):
    return [c for c in r.get_all('Set-Cookie') if c.startswith(name + '=')]


def mk(backend, **kw):
    return TestClient(make_app(backend, **kw))


# ---------------------------------------------------------------- basic life cycle
def test_anonymous_read_sets_no_cookie_and_no_write(backend):
    c = mk(backend)
    for path in ('/peek', '/read_only', '/touch_nothing', '/sid'):
        assert not sc(c.get(path)), path
    assert c.cookies == {}


def test_write_sets_cookie_and_persists(backend):
    c = mk(backend)
    r = c.get('/set', query_string='k=a&v=1')
    assert len(sc(r)) == 1
    assert json.loads(c.get('/peek').text) == {'a': '1'}


def test_cookie_flags_default(backend):
    c = mk(backend)
    ck = sc(c.get('/set'))[0]
    assert 'HttpOnly' in ck and 'samesite=lax' in ck.lower() and 'Path=/' in ck
    assert 'Secure' not in ck and 'max-age=1209600' in ck.lower()


def test_cookie_flags_custom(backend):
    c = mk(backend, secure=True, httponly=False, samesite='Strict', path='/', domain=None, cookie_name='sid', ttl=100)
    ck = sc(c.get('/set'), 'sid')[0]
    assert 'Secure' in ck and 'HttpOnly' not in ck and 'samesite=strict' in ck.lower() and 'max-age=100' in ck.lower()


def test_session_isolated_between_clients(backend):
    app = make_app(backend)
    a, b = TestClient(app), TestClient(app)
    a.get('/set', query_string='v=A')
    assert json.loads(b.get('/peek').text) == {}


def test_overwrite_and_delete_keys(backend):
    c = mk(backend)
    c.get('/set', query_string='k=a&v=1'); c.get('/set', query_string='k=a&v=2')
    assert json.loads(c.get('/peek').text) == {'a': '2'}


def test_destroy_logout(backend):
    c = mk(backend)
    c.get('/set'); old = c.cookies['lcore_session']
    r = c.get('/logout')
    assert 'lcore_session' in ''.join(r.get_all('Set-Cookie')) and 'max-age=-1' in ''.join(r.get_all('Set-Cookie')).lower()
    assert json.loads(c.get('/peek').text) == {}
    c.cookies['lcore_session'] = old  # replay the old cookie
    assert json.loads(c.get('/peek').text) == {}


def test_sid_is_stable_across_requests(backend):
    c = mk(backend); c.get('/set')
    assert c.get('/sid').text == c.get('/sid').text


def test_sid_entropy_and_uniqueness(backend):
    app = make_app(backend); sids = set()
    for _ in range(20):
        cl = TestClient(app); cl.get('/set'); sids.add(cl.get('/sid').text)
    assert len(sids) == 20 and all(len(s) == 64 for s in sids)


def test_session_state_does_not_leak_between_requests(backend):
    app = make_app(backend)
    a = TestClient(app); a.get('/set', query_string='v=secret')
    b = TestClient(app)
    for _ in range(3):
        assert json.loads(b.get('/peek').text) == {}


# ---------------------------------------------------------------- cookie tampering
def test_tampered_signature_ignored(backend):
    c = mk(backend); c.get('/set', query_string='v=x')
    ck = c.cookies['lcore_session']
    c.cookies['lcore_session'] = ck[:-2] + ('AA' if not ck.endswith('AA') else 'BB')
    assert json.loads(c.get('/peek').text) == {}


def test_forged_sid_with_wrong_secret_ignored(backend):
    app = make_app(backend)
    a = TestClient(app); a.get('/set', query_string='v=victim'); sid = a.get('/sid').text
    r = lcore.BaseResponse(); r.set_cookie('lcore_session', sid, secret='attacker')
    b = TestClient(app); b.cookies['lcore_session'] = r._cookies['lcore_session'].value
    assert json.loads(b.get('/peek').text) == {}


def test_raw_unsigned_sid_not_accepted(backend):
    app = make_app(backend)
    a = TestClient(app); a.get('/set', query_string='v=victim'); sid = a.get('/sid').text
    b = TestClient(app); b.cookies['lcore_session'] = sid
    assert json.loads(b.get('/peek').text) == {}


def test_unknown_but_validly_signed_sid_gets_fresh_session(backend):
    # attacker can't sign, but a server-restart (memory) leaves valid signature w/ no record
    app = make_app(backend)
    r = lcore.BaseResponse(); r.set_cookie('lcore_session', 'f' * 64, secret=SECRET)
    c = TestClient(app); c.cookies['lcore_session'] = r._cookies['lcore_session'].value
    c.get('/set')
    assert c.get('/sid').text != 'f' * 64  # fixation: client-chosen sid is never adopted


def test_fixation_validly_signed_unknown_sid_not_adopted(backend):
    app = make_app(backend)
    r = lcore.BaseResponse(); r.set_cookie('lcore_session', 'a' * 64, secret=SECRET)
    c = TestClient(app); c.cookies['lcore_session'] = r._cookies['lcore_session'].value
    c.get('/login')
    assert c.get('/sid').text != 'a' * 64


@pytest.mark.parametrize('junk', ['', '!', 'abc', '!x?y', '\x00', 'A' * 5000, '!' + 'A' * 44 + '?' + 'B' * 40])
def test_garbage_cookie_values_never_500(backend, junk):
    c = mk(backend); c.cookies['lcore_session'] = junk
    assert c.get('/peek').status_code == 200 and c.get('/set').status_code == 200


# ---------------------------------------------------------------- login / fixation
def test_bind_user_regenerates_sid_and_kills_old(backend):
    c = mk(backend); c.get('/set')
    old_cookie = c.cookies['lcore_session']
    pre, post = json.loads(c.get('/login').text)
    assert pre != post
    attacker = TestClient(c.app); attacker.cookies['lcore_session'] = old_cookie
    assert attacker.get('/whoami').text == 'None'
    assert c.get('/whoami').text == 'alice'


def test_bind_user_data_preserved(backend):
    c = mk(backend); c.get('/set', query_string='k=cart&v=3'); c.get('/login')
    assert json.loads(c.get('/peek').text) == {'cart': '3'}


def test_bind_user_without_prior_session(backend):
    c = mk(backend); c.get('/login')
    assert c.get('/whoami').text == 'alice'


def test_bind_user_numeric_uid_stringified(backend):
    app = make_app(backend)
    @app.get('/n')
    def n(): request.session.bind_user(42); return str(request.session.user_id)
    assert TestClient(app).get('/n').text == '42'


def test_list_sessions_multiple_devices(backend):
    app = make_app(backend)
    a, b, c3 = TestClient(app), TestClient(app), TestClient(app)
    for cl in (a, b, c3): cl.get('/login')
    assert a.get('/list').text == '3'


def test_list_sessions_anonymous_empty(backend):
    assert mk(backend).get('/list').text == '0'


def test_revoke_other_sessions_keeps_current(backend):
    app = make_app(backend)
    a, b, c3 = TestClient(app), TestClient(app), TestClient(app)
    for cl in (a, b, c3): cl.get('/login')
    assert a.get('/revoke_others').text == '2'
    assert a.get('/whoami').text == 'alice'
    assert b.get('/whoami').text == 'None' and c3.get('/whoami').text == 'None'


def test_revoke_all_kills_everything_including_self(backend):
    app = make_app(backend)
    a, b = TestClient(app), TestClient(app)
    a.get('/login'); b.get('/login')
    assert a.get('/revoke_all').text == '2'
    assert a.get('/whoami').text == 'None' and b.get('/whoami').text == 'None'


def test_revoke_all_does_not_touch_other_users(backend):
    app = make_app(backend)
    a, bob = TestClient(app), TestClient(app)
    a.get('/login', query_string='u=alice'); bob.get('/login', query_string='u=bob')
    a.get('/revoke_all')
    assert bob.get('/whoami').text == 'bob'


def test_bump_epoch_invalidates_existing(backend):
    app = make_app(backend, ); a = TestClient(app); a.get('/login')
    backend.bump_epoch('alice')
    assert a.get('/whoami').text == 'None'


def test_bump_epoch_new_login_after_bump_works(backend):
    app = make_app(backend); a = TestClient(app); a.get('/login')
    backend.bump_epoch('alice')
    a.get('/login')
    assert a.get('/whoami').text == 'alice'


def test_bump_epoch_monotonic(backend):
    assert [backend.bump_epoch('u') for _ in range(3)] == [1, 2, 3]
    assert backend.get_epoch('u') == 3 and backend.get_epoch('other') == 0


def test_bump_epoch_does_not_affect_other_user(backend):
    app = make_app(backend); a = TestClient(app); a.get('/login', query_string='u=bob')
    backend.bump_epoch('alice')
    assert a.get('/whoami').text == 'bob'


def test_rebind_to_other_user_without_regenerate(backend):
    app = make_app(backend)
    @app.get('/rebind')
    def rb(): request.session.bind_user('mallory', regenerate=False); return 'ok'
    a = TestClient(app); a.get('/login')
    a.get('/rebind')
    assert backend.list_user('alice') == []
    assert len(backend.list_user('mallory')) == 1


def test_epoch_cache_local_bump_immediate(backend):
    backend.epoch_cache_ttl = 60
    app = make_app(backend); a = TestClient(app); a.get('/login'); a.get('/whoami')
    backend.bump_epoch('alice')
    assert a.get('/whoami').text == 'None'


# ---------------------------------------------------------------- flash / dirty tracking
def test_flash_pop_miss_not_dirty_no_cookie(backend):
    c = mk(backend); c.get('/set')
    r = c.get('/flash/pop')
    assert r.text == 'None' and not sc(r)


def test_flash_set_then_pop_once(backend):
    c = mk(backend)
    c.get('/flash/set')
    assert c.get('/flash/pop').text == 'hi'
    assert c.get('/flash/pop').text == 'None'


def test_setdefault_existing_not_dirty(backend):
    app = make_app(backend)
    @app.get('/sd')
    def sd(): request.session.setdefault('k', 'd'); return str(request.session.modified)
    c = TestClient(app); c.get('/sd')
    assert c.get('/sd').text == 'False'


def test_setdefault_new_is_dirty(backend):
    app = make_app(backend)
    @app.get('/sd')
    def sd(): request.session.setdefault('new', 1); return str(request.session.modified)
    assert TestClient(app).get('/sd').text == 'True'


def test_in_place_nested_mutation_not_persisted_documented(backend):
    app = make_app(backend)
    @app.get('/n1')
    def n1(): request.session['lst'] = []; return 'ok'
    @app.get('/n2')
    def n2(): request.session['lst'].append(1); return 'ok'
    @app.get('/n3')
    def n3(): return json.dumps(request.session['lst'])
    c = TestClient(app); c.get('/n1'); c.get('/n2')
    assert json.loads(c.get('/n3').text) == []  # documented gotcha


def test_clear_empty_not_dirty(backend):
    app = make_app(backend)
    @app.get('/c')
    def cl(): request.session.clear(); return str(request.session.modified)
    assert TestClient(app).get('/c').text == 'False'


def test_clear_keeps_sid(backend):
    app = make_app(backend)
    @app.get('/c')
    def cl(): request.session.clear(); return 'ok'
    c = TestClient(app); c.get('/set'); sid = c.get('/sid').text; c.get('/c')
    assert c.get('/sid').text == sid and json.loads(c.get('/peek').text) == {}


def test_update_and_items_api(backend):
    app = make_app(backend)
    @app.get('/u')
    def u():
        s = request.session; s.update(a=1, b=2); del s['a']
        return json.dumps([sorted(s.keys()), len(s), 'b' in s, s.get('zz', 'dflt')])
    assert json.loads(TestClient(app).get('/u').text) == [['b'], 1, True, 'dflt']


def test_missing_key_keyerror_is_500_not_leak(backend):
    app = make_app(backend)
    @app.get('/k')
    def k(): return request.session['missing']
    assert TestClient(app).get('/k').status_code == 500


def test_session_saved_on_redirect(backend):
    c = mk(backend)
    assert c.get('/redirect_login').status_code in (302, 303)
    assert json.loads(c.get('/peek').text) == {'x': 1}


def test_session_saved_on_httperror(backend):
    c = mk(backend)
    assert c.get('/err_after_set').status_code == 400
    assert json.loads(c.get('/peek').text) == {'e': 1}


def test_ctx_session_lazy_accessor(backend):
    app = make_app(backend)
    @app.get('/ctx')
    def h(): gctx.session['via'] = 'ctx'; return 'ok'
    c = TestClient(app); c.get('/ctx')
    assert json.loads(c.get('/peek').text) == {'via': 'ctx'}


def test_request_session_without_middleware_raises(client):
    app = Lcore(); app.get('/')(lambda: str(request.session))
    assert client(app).get('/').status_code == 500


# ---------------------------------------------------------------- data fidelity
@pytest.mark.parametrize('val', ['héllo ✓ 世界 🙂', 'x' * 100000, [1, 2, {'a': [None, True, 1.5]}], {'nested': {'deep': {'k': 'v'}}}, None, 0, False, '', '\x00\n\t"\\'])
def test_value_roundtrip(backend, val):
    app = make_app(backend)
    @app.get('/w')
    def w(): request.session['v'] = val; return 'ok'
    @app.get('/r')
    def r(): return json.dumps(request.session['v'])
    c = TestClient(app); c.get('/w')
    assert json.loads(c.get('/r').text) == val


def test_large_session_does_not_bloat_cookie(backend):
    c = mk(backend)
    app = c.app
    @app.get('/big')
    def big(): request.session['b'] = 'x' * 1_000_000; return 'ok'
    r = c.get('/big')
    assert len(sc(r)[0]) < 400


def test_unicode_keys(backend):
    app = make_app(backend)
    @app.get('/w')
    def w(): request.session['ключ✓'] = 'v'; return 'ok'
    @app.get('/r')
    def r(): return request.session['ключ✓']
    c = TestClient(app); c.get('/w')
    assert c.get('/r').text == 'v'


def test_non_json_serializable_value_clean_failure(backend):
    app = make_app(backend)
    @app.get('/w')
    def w(): request.session['v'] = object(); return 'ok'
    r = TestClient(app).get('/w')
    assert r.status_code in (500, 503)


def test_non_string_keys_become_strings_after_roundtrip(backend):
    app = make_app(backend)
    @app.get('/w')
    def w(): request.session[1] = 'v'; return 'ok'
    c = TestClient(app); c.get('/w')
    assert c.get('/peek').status_code == 200


# ---------------------------------------------------------------- TTL
def test_idle_ttl_expiry(backend):
    c = mk(backend, ttl=1, refresh_every=0)
    c.get('/set'); assert json.loads(c.get('/peek').text) != {}
    time.sleep(1.3)
    assert json.loads(c.get('/peek').text) == {}


def test_idle_ttl_refreshed_by_activity(backend):
    c = mk(backend, ttl=2, refresh_every=0.1)
    c.get('/set')
    for _ in range(4):
        time.sleep(0.7); assert json.loads(c.get('/peek').text) != {}


def test_refresh_sets_new_cookie_when_due(backend):
    c = mk(backend, ttl=100, refresh_every=0.2)
    c.get('/set'); time.sleep(0.3)
    assert sc(c.get('/peek'))


def test_refresh_not_every_request(backend):
    c = mk(backend, ttl=100, refresh_every=50)
    c.get('/set')
    assert not sc(c.get('/peek'))


def test_absolute_ttl_expiry_despite_activity(backend):
    c = mk(backend, ttl=100, absolute_ttl=1, refresh_every=0.05)
    c.get('/set')
    for _ in range(3):
        time.sleep(0.25); c.get('/peek')
    time.sleep(0.5)
    assert json.loads(c.get('/peek').text) == {}


def test_absolute_ttl_deletes_record(backend):
    c = mk(backend, ttl=100, absolute_ttl=0.3)
    c.get('/set'); sid = c.get('/sid').text; time.sleep(0.5)
    c.get('/peek')
    assert backend.load(sid) is None


def test_expired_session_reuse_creates_new_not_resurrect(backend):
    c = mk(backend, ttl=1, refresh_every=0)
    c.get('/set'); sid = c.get('/sid').text; time.sleep(1.2)
    c.get('/set', query_string='v=new')
    assert c.get('/sid').text != sid


def test_backend_ttl_boundary_direct(backend):
    backend.save('s1', lcore._blank_session_record(), 0.3)
    assert backend.load('s1') is not None
    time.sleep(0.4)
    assert backend.load('s1') is None


def test_expired_not_listed_for_user(backend):
    rec = lcore._blank_session_record(); rec['uid'] = 'u'
    backend.save('s1', rec, 0.2); backend.save('s2', dict(rec), 100)
    time.sleep(0.3)
    assert [s for s, _ in backend.list_user('u')] == ['s2']


def test_revoke_user_count_excludes_expired(backend):
    rec = lcore._blank_session_record(); rec['uid'] = 'u'
    backend.save('s1', rec, 0.2); backend.save('s2', dict(rec), 100)
    time.sleep(0.3)
    assert backend.revoke_user('u') == 1


def test_max_age_cookie_matches_ttl(backend):
    c = mk(backend, ttl=777)
    assert 'max-age=777' in sc(c.get('/set'))[0].lower()


# ---------------------------------------------------------------- max_sessions (memory)
def test_memory_max_sessions_evicts_oldest():
    b = MemorySessionBackend(max_sessions=5, warn=False)
    for i in range(20):
        b.save('s%d' % i, lcore._blank_session_record(), 100)
    assert len(b._store) <= 5
    assert b.load('s19') is not None and b.load('s0') is None


def test_memory_max_sessions_prefers_expired_eviction():
    b = MemorySessionBackend(max_sessions=3, warn=False)
    b.save('old', lcore._blank_session_record(), 0.05)
    b.save('a', lcore._blank_session_record(), 100); b.save('b', lcore._blank_session_record(), 100)
    time.sleep(0.1)
    b.save('c', lcore._blank_session_record(), 100)
    assert b.load('a') and b.load('b') and b.load('c')


def test_memory_max_sessions_resave_existing_no_evict():
    b = MemorySessionBackend(max_sessions=2, warn=False)
    b.save('a', lcore._blank_session_record(), 100); b.save('b', lcore._blank_session_record(), 100)
    for _ in range(5): b.save('a', lcore._blank_session_record(), 100)
    assert b.load('b') is not None


def test_memory_eviction_cleans_user_index():
    b = MemorySessionBackend(max_sessions=2, warn=False)
    rec = lcore._blank_session_record(); rec['uid'] = 'u'
    b.save('a', dict(rec), 100); b.save('b', dict(rec), 100); b.save('c', dict(rec), 100)
    assert len(b.list_user('u')) == 2 and len(b._index['u']) == 2


def test_memory_warns_by_default():
    with pytest.warns(UserWarning):
        MemorySessionBackend()


def test_session_middleware_no_secret_warns():
    with pytest.warns(UserWarning):
        SessionMiddleware(backend=MemorySessionBackend(warn=False))


def test_invalid_on_backend_error_mode():
    with pytest.raises(ValueError):
        SessionMiddleware(secret='s', on_backend_error='whatever')


def test_session_name_collision_with_di():
    app = Lcore(); app.inject('session', lambda: 1)
    app.use(SessionMiddleware(backend=MemorySessionBackend(warn=False), secret='s'))
    app.get('/')(lambda: 'x')
    assert TestClient(app).get('/').status_code == 500


# ---------------------------------------------------------------- backend errors
class Flaky(MemorySessionBackend):
    def __init__(self): super().__init__(warn=False); self.fail_load = False; self.fail_save = False
    def load(self, sid):
        if self.fail_load: raise RuntimeError('load down')
        return super().load(sid)
    def save(self, sid, record, ttl):
        if self.fail_save: raise RuntimeError('save down')
        return super().save(sid, record, ttl)


@pytest.mark.parametrize('mode,status', [('unavailable', 503), ('raise', 500)])
def test_backend_load_error_modes(mode, status):
    b = Flaky(); app = make_app(b, on_backend_error=mode)
    c = TestClient(app); c.get('/set'); b.fail_load = True
    assert c.get('/peek').status_code == status


def test_backend_load_error_anonymous_mode():
    b = Flaky(); app = make_app(b, on_backend_error='anonymous')
    c = TestClient(app); c.get('/set'); b.fail_load = True
    r = c.get('/peek')
    assert r.status_code == 200 and json.loads(r.text) == {}


@pytest.mark.parametrize('mode,status', [('unavailable', 503), ('raise', 500)])
def test_backend_save_error_modes(mode, status):
    b = Flaky(); b.fail_save = True
    c = TestClient(make_app(b, on_backend_error=mode))
    r = c.get('/set')
    assert r.status_code == status and not sc(r)


def test_backend_save_error_anonymous_mode_no_cookie_for_unsaved():
    b = Flaky(); b.fail_save = True
    c = TestClient(make_app(b, on_backend_error='anonymous'))
    r = c.get('/set')
    assert r.status_code == 200 and not sc(r)


def test_backend_load_error_after_recover_session_survives():
    b = Flaky(); app = make_app(b)
    c = TestClient(app); c.get('/set', query_string='v=keep')
    b.fail_load = True; assert c.get('/peek').status_code == 503
    b.fail_load = False
    assert json.loads(c.get('/peek').text) == {'k': 'keep'}


def test_refresh_failure_does_not_fail_request():
    b = Flaky(); app = make_app(b, ttl=100, refresh_every=0.1)
    c = TestClient(app); c.get('/set'); time.sleep(0.2); b.fail_save = True
    assert c.get('/peek').status_code == 200


def test_anonymous_mode_still_reads_ok_when_save_works():
    b = Flaky(); c = TestClient(make_app(b, on_backend_error='anonymous'))
    c.get('/set'); assert json.loads(c.get('/peek').text) == {'k': 'v'}


def test_sqlite_unwritable_path_errors_at_construction(tmp_path):
    with pytest.raises(Exception):
        SQLiteSessionBackend(str(tmp_path / 'nodir' / 'x.db'))


# ---------------------------------------------------------------- concurrency
def test_concurrent_distinct_sessions_in_process(backend):
    app = make_app(backend); errs = []
    def w(i):
        try:
            c = TestClient(app)
            c.get('/set', query_string='k=me&v=%d' % i)
            for _ in range(5):
                assert json.loads(c.get('/peek').text) == {'me': str(i)}
        except Exception as e: errs.append(repr(e))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(16)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs[:3]


def test_concurrent_updates_same_session_no_corruption(backend):
    app = make_app(backend)
    c = TestClient(app); c.get('/set')
    cookie = c.cookies['lcore_session']; errs = []
    def w(i):
        try:
            cl = TestClient(app); cl.cookies['lcore_session'] = cookie
            assert cl.get('/set', query_string='k=k%d&v=%d' % (i, i)).status_code == 200
        except Exception as e: errs.append(repr(e))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(12)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs[:3]
    data = json.loads(c.get('/peek').text)
    assert isinstance(data, dict) and len(data) >= 1  # last-writer-wins is fine; must stay valid json


@pytest.mark.xfail(strict=True, reason="BUG: session writes are whole-record last-writer-wins: concurrent requests on one session silently lose each other's keys (lcore.py:3893 save of full record)")
def test_concurrent_updates_do_not_lose_keys(backend):
    app = make_app(backend)
    @app.get('/slow')
    def slow():
        request.session[request.query.get('k')] = 1; time.sleep(0.1); return 'ok'
    c = TestClient(app); c.get('/set')
    cookie = c.cookies['lcore_session']
    def w(i):
        cl = TestClient(app); cl.cookies['lcore_session'] = cookie
        cl.get('/slow', query_string='k=k%d' % i)
    ts = [threading.Thread(target=w, args=(i,)) for i in range(6)]
    [t.start() for t in ts]; [t.join() for t in ts]
    keys = json.loads(c.get('/peek').text)
    assert all(('k%d' % i) in keys for i in range(6)), keys


def test_live_sessions_concurrent_clients(live, backend):
    import http.client
    app = make_app(backend); lv = live(app); errs = []
    def w(i):
        try:
            cj = {}
            def req(path):
                conn = http.client.HTTPConnection('127.0.0.1', lv.port, timeout=10)
                h = {'Cookie': '; '.join('%s=%s' % kv for kv in cj.items())} if cj else {}
                conn.request('GET', path, headers=h); r = conn.getresponse(); body = r.read()
                for k, v in r.getheaders():
                    if k.lower() == 'set-cookie':
                        n, val = v.split(';', 1)[0].split('=', 1); cj[n] = val
                conn.close(); return body
            req('/set?k=me&v=%d' % i)
            for _ in range(3):
                assert json.loads(req('/peek')) == {'me': str(i)}
        except Exception as e: errs.append(repr(e))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs[:3]


def test_live_cookie_roundtrip_signed_value_survives_wire(live, backend):
    lv = live(make_app(backend))
    s, h, b = lv.request('GET', '/set?k=a&v=%E2%9C%93')
    ck = h['set-cookie'].split(';', 1)[0]
    s, h, b = lv.request('GET', '/peek', headers={'Cookie': ck})
    assert json.loads(b) == {'a': '✓'}


def test_concurrent_login_revoke_consistency(backend):
    app = make_app(backend); clients = [TestClient(app) for _ in range(8)]
    ts = [threading.Thread(target=cl.get, args=('/login',)) for cl in clients]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert clients[0].get('/list').text == '8'
    assert clients[0].get('/revoke_others').text == '7'


# ---------------------------------------------------------------- SQLite specifics
def test_sqlite_persists_across_instances(tmp_path):
    path = str(tmp_path / 'p.db')
    b1 = SQLiteSessionBackend(path)
    rec = lcore._blank_session_record(); rec['data']['k'] = 'v'
    b1.save('sid1', rec, 100); b1.close()
    b2 = SQLiteSessionBackend(path)
    assert b2.load('sid1')['data'] == {'k': 'v'}


def test_sqlite_two_apps_share_store(tmp_path):
    path = str(tmp_path / 'p.db')
    a1 = make_app(SQLiteSessionBackend(path)); a2 = make_app(SQLiteSessionBackend(path))
    c1 = TestClient(a1); c1.get('/login')
    c2 = TestClient(a2); c2.cookies.update(c1.cookies)
    assert c2.get('/whoami').text == 'alice'
    c2.get('/revoke_all')
    assert c1.get('/whoami').text == 'None'


def test_sqlite_epoch_shared_across_instances_after_cache(tmp_path):
    path = str(tmp_path / 'p.db')
    b1, b2 = SQLiteSessionBackend(path), SQLiteSessionBackend(path)
    b1.epoch_cache_ttl = 0; b2.epoch_cache_ttl = 0
    a1 = make_app(b1); a2 = make_app(b2)
    c = TestClient(a1); c.get('/login')
    b2.bump_epoch('alice')
    assert c.get('/whoami').text == 'None'


def test_sqlite_threads_use_own_connections(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 't.db')); errs = []
    def w(i):
        try:
            for j in range(20):
                rec = lcore._blank_session_record(); rec['data']['i'] = i
                b.save('s%d-%d' % (i, j), rec, 100)
                assert b.load('s%d-%d' % (i, j))['data']['i'] == i
        except Exception as e: errs.append(repr(e))
    ts = [threading.Thread(target=w, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errs, errs[:3]


def test_sqlite_cleanup_sweeps_expired(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'c.db'), cleanup_every=0.1, cleanup_batch=10)
    for i in range(5): b.save('e%d' % i, lcore._blank_session_record(), 0.05)
    time.sleep(0.3); b.save('live', lcore._blank_session_record(), 100)
    n = b._conn.execute('select count(*) from lcore_sessions').fetchone()[0]
    assert n == 1


def test_sqlite_cleanup_batch_bounded(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'c.db'), cleanup_every=0.05, cleanup_batch=3)
    for i in range(10): b.save('e%d' % i, lcore._blank_session_record(), 0.01)
    time.sleep(0.2); b.save('live', lcore._blank_session_record(), 100)
    n = b._conn.execute('select count(*) from lcore_sessions').fetchone()[0]
    assert 1 < n < 11


def test_sqlite_sql_injection_in_sid_and_uid(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'i.db'))
    evil = "x'; DROP TABLE lcore_sessions; --"
    rec = lcore._blank_session_record(); rec['uid'] = evil
    b.save(evil, rec, 100)
    assert b.load(evil) is not None and len(b.list_user(evil)) == 1
    assert b.revoke_user(evil) == 1 and b.bump_epoch(evil) == 1
    assert b.load("' OR '1'='1") is None


def test_sqlite_delete_returns_bool(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'd.db'))
    b.save('a', lcore._blank_session_record(), 100)
    assert b.delete('a') is True and b.delete('a') is False


def test_sqlite_close_then_reuse_reconnects(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'd.db'))
    b.save('a', lcore._blank_session_record(), 100); b.close()
    assert b.load('a') is not None


def test_sqlite_unicode_data(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'u.db'))
    rec = lcore._blank_session_record(); rec['data']['k'] = '世界🙂'
    b.save('a', rec, 100)
    assert b.load('a')['data']['k'] == '世界🙂'


def test_sqlite_corrupt_record_clean_failure(tmp_path):
    b = SQLiteSessionBackend(str(tmp_path / 'z.db'))
    b._conn.execute("INSERT INTO lcore_sessions VALUES ('bad', NULL, 9999999999, 'not json{')"); b._conn.commit()
    app = make_app(b)
    r = lcore.BaseResponse(); r.set_cookie('lcore_session', 'bad', secret=SECRET)
    c = TestClient(app); c.cookies['lcore_session'] = r._cookies['lcore_session'].value
    assert c.get('/peek').status_code in (200, 503)


# ---------------------------------------------------------------- misc backend contract
def test_backend_abstract():
    with pytest.raises(TypeError):
        SessionBackend()


def test_backend_load_returns_copy(backend):
    rec = lcore._blank_session_record(); rec['data']['a'] = 1
    backend.save('s', rec, 100)
    got = backend.load('s'); got['data']['a'] = 99
    assert backend.load('s')['data']['a'] == 1


def test_backend_save_snapshot_not_alias(backend):
    rec = lcore._blank_session_record(); rec['data']['a'] = 1
    backend.save('s', rec, 100); rec['data']['a'] = 2
    assert backend.load('s')['data']['a'] == 1


def test_backend_delete_nonexistent(backend):
    assert not backend.delete('nope')


def test_backend_touch(backend):
    assert backend.touch('nope', 10) is False
    backend.save('s', lcore._blank_session_record(), 0.2)
    assert backend.touch('s', 100) is True
    time.sleep(0.3)
    assert backend.load('s') is not None


def test_backend_revoke_except_sid(backend):
    rec = lcore._blank_session_record(); rec['uid'] = 'u'
    for s in 'abc': backend.save(s, dict(rec), 100)
    assert backend.revoke_user('u', except_sid='b') == 2
    assert [s for s, _ in backend.list_user('u')] == ['b']


def test_backend_uid_int_and_str_same_user(backend):
    rec = lcore._blank_session_record(); rec['uid'] = 7
    backend.save('s', rec, 100)
    assert len(backend.list_user('7')) == 1 and len(backend.list_user(7)) == 1


def test_backend_resave_changing_uid_moves_index(backend):
    rec = lcore._blank_session_record(); rec['uid'] = 'a'
    backend.save('s', rec, 100)
    rec2 = dict(rec); rec2['uid'] = 'b'; backend.save('s', rec2, 100)
    assert backend.list_user('a') == [] and len(backend.list_user('b')) == 1


def test_redis_backend_if_available():
    try:
        import redis
        r = redis.Redis(socket_connect_timeout=0.3); r.ping()
    except Exception:
        pytest.skip('no redis server')
    b = lcore.RedisSessionBackend()
    rec = lcore._blank_session_record(); rec['uid'] = 'rtest'
    b.save('rs1', rec, 5)
    assert b.load('rs1') is not None and b.revoke_user('rtest') == 1
