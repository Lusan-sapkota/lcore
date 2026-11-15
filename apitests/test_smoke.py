from lcore import Lcore

def test_live_harness(live):
    app = Lcore()

    @app.get('/hi')
    def hi(): return 'hi'

    lv = live(app)
    s, h, b = lv.request('GET', '/hi')
    assert (s, b) == (200, b'hi')
