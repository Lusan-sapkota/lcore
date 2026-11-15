// Runnable code blocks: self-hosted Pyodide runs the real lcore.py in the browser via TestClient.
(function () {
  var PG = [
    'import sys, json, types, hashlib, hmac',
    'def _pbkdf2(name, password, salt, iterations, dklen=None):',
    '    # browser only: Pyodide has no OpenSSL, so this pure-Python stand-in caps the iteration count',
    '    h = hmac.new(password, digestmod=name); out = b""; i = 1',
    '    while len(out) < (dklen or h.digest_size):',
    '        c = h.copy(); c.update(salt + i.to_bytes(4, "big")); u = c.digest(); t = int.from_bytes(u, "big")',
    '        for _ in range(min(iterations, 1000) - 1):',
    '            c = h.copy(); c.update(u); u = c.digest(); t ^= int.from_bytes(u, "big")',
    '        out += t.to_bytes(h.digest_size, "big"); i += 1',
    '    return out[:dklen or h.digest_size]',
    'if not hasattr(hashlib, "pbkdf2_hmac"): hashlib.pbkdf2_hmac = _pbkdf2',
    'from lcore import TestClient',
    'client = None',
    'def load(code):',
    '    global client',
    '    ns = {"__name__": "app"}',
    '    exec(compile(code, "app.py", "exec"), ns)',
    '    mod = types.ModuleType("app"); mod.__dict__.update(ns); sys.modules["app"] = mod',
    '    client = TestClient(ns["app"])',
    'def send(method, path, body):',
    '    kw = {"json": json.loads(body)} if body.strip() else {}',
    '    r = getattr(client, method.lower())(path, **kw)',
    '    return json.dumps({"status": r.status_code, "headers": dict(r.headers), "text": r.text})',
    'def run_test(app_code, code):',
    '    load(app_code)',
    '    ns = {"__name__": "test"}',
    '    exec(compile(code, "test_notes.py", "exec"), ns)',
    '    n = 0',
    '    for k, v in list(ns.items()):',
    '        if k.startswith("test_") and callable(v): v(); n += 1',
    '    return n'
  ].join('\n');

  var py = null, loading = null;

  function boot(say) {
    if (py) return Promise.resolve(py);
    if (loading) return loading;
    say('Loading Python (first run only, ~13 MB)…');
    var base = new URL('assets/pyodide/', location.href).href;
    loading = new Promise(function (ok, fail) {
      var s = document.createElement('script');
      s.src = base + 'pyodide.js';
      s.onload = ok;
      s.onerror = function () { fail(new Error('Could not load ' + s.src)); };
      document.head.appendChild(s);
    }).then(function () {
      return loadPyodide({ indexURL: base });
    }).then(function (p) {
      return fetch(base + 'lcore.py').then(function (r) {
        if (!r.ok) throw new Error('Could not load lcore.py');
        return r.text();
      }).then(function (src) {
        p.FS.writeFile('/home/pyodide/lcore.py', src);
        p.runPython('import sys\nsys.path.insert(0, "/home/pyodide")\n' + PG);
        py = p;
        return p;
      });
    });
    loading.catch(function () { loading = null; });
    return loading;
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function pretty(text) {
    try { return JSON.stringify(JSON.parse(text), null, 2); } catch (e) { return text; }
  }

  function setup(pre) {
    var wrap = pre.closest('.code-block');
    var code = pre.querySelector('code');
    if (!wrap || !code) return;
    var kind = pre.dataset.run;
    var head = wrap.querySelector('.code-head');
    var out = el('div', 'pg');
    var res = el('pre', 'pg-res');
    res.setAttribute('aria-live', 'polite');
    res.hidden = true;
    var method, path, body, status = el('div', 'pg-status');
    status.hidden = true;

    function show(text, cls) {
      res.hidden = false;
      res.className = 'pg-res ' + (cls || '');
      res.textContent = text;
    }
    function appCode() {
      var src = kind === 'test' ? document.querySelector('[data-final] code') : code;
      return src.textContent;
    }
    function fail(e) { show(String(e.message || e).replace(/^PythonError: /, ''), 'err'); }

    function runTest(btn) {
      btn.disabled = true;
      boot(function (m) { show(m); }).then(function (p) {
        show('Running…');
        return new Promise(function (r) { setTimeout(r, 30); }).then(function () {
          var n = p.globals.get('run_test')(appCode(), code.textContent);
          show('✓ ' + n + ' test passed', 'ok');
        });
      }).catch(fail).then(function () { btn.disabled = false; });
    }

    function load(btn) {
      btn.disabled = true;
      return boot(function (m) { show(m); }).then(function (p) {
        p.globals.get('load')(code.textContent);
        show('App loaded. Send a request below.', 'ok');
        return true;
      }).catch(function (e) { fail(e); return false; }).then(function (ok) { btn.disabled = false; return ok; });
    }

    function send(btn) {
      var go = py && loaded ? Promise.resolve(true) : load(runBtn);
      go.then(function (ok) {
        if (!ok) return;
        loaded = true;
        try {
          var r = JSON.parse(py.globals.get('send')(method.value, path.value, body.value));
          var lines = ['HTTP ' + r.status];
          Object.keys(r.headers).forEach(function (k) { lines.push(k + ': ' + r.headers[k]); });
          show(lines.join('\n') + '\n\n' + pretty(r.text), r.status < 400 ? 'ok' : 'err');
        } catch (e) { fail(e); }
      });
    }

    var loaded = false;
    var runBtn = el('button', 'copy-btn pg-run', kind === 'test' ? 'Run test' : 'Run');
    runBtn.type = 'button';
    var editBtn = el('button', 'copy-btn', 'Edit');
    editBtn.type = 'button';
    editBtn.setAttribute('aria-pressed', 'false');
    var ta = null;
    function highlight() {
      if (window.hljs) { code.className = 'hljs language-python'; code.innerHTML = hljs.highlight(ta.value, { language: 'python' }).value; }
      else code.textContent = ta.value;
      loaded = false;
    }
    // A real textarea sits exactly over the highlighted code: native selection, copy and undo
    editBtn.addEventListener('click', function () {
      var on = editBtn.getAttribute('aria-pressed') !== 'true';
      editBtn.setAttribute('aria-pressed', on);
      if (on) {
        ta = el('textarea', 'pg-ta');
        ta.value = code.textContent;
        ta.spellcheck = false;
        ta.wrap = 'off';
        ta.setAttribute('aria-label', 'Code editor. Press Escape to leave.');
        pre.classList.add('editing');
        pre.appendChild(ta);
        highlight();
        ta.focus();
        ta.addEventListener('input', highlight);
        ta.addEventListener('keydown', function (e) {
          if (e.key === 'Tab' && !e.shiftKey) {
            e.preventDefault();
            if (!document.execCommand('insertText', false, '    ')) { ta.setRangeText('    ', ta.selectionStart, ta.selectionEnd, 'end'); highlight(); }
          } else if (e.key === 'Escape') { editBtn.click(); editBtn.focus(); }
        });
      } else if (ta) {
        ta.remove(); ta = null;
        pre.classList.remove('editing');
      }
    });
    var actions = el('span', 'pg-actions');
    actions.appendChild(editBtn);
    actions.appendChild(runBtn);
    head.insertBefore(actions, head.querySelector('.copy-btn'));

    if (kind === 'app') {
      var bar = el('div', 'pg-bar');
      var presets = [];
      try { presets = JSON.parse(pre.dataset.presets || '[]'); } catch (e) {}
      if (presets.length) {
        var chips = el('div', 'pg-presets');
        presets.forEach(function (p) {
          var b = el('button', 'pg-chip', p[0]);
          b.type = 'button';
          b.addEventListener('click', function () { method.value = p[1]; path.value = p[2]; body.value = p[3]; send(b); });
          chips.appendChild(b);
        });
        out.appendChild(chips);
      }
      method = el('select', 'pg-method');
      ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].forEach(function (m) { method.appendChild(el('option', '', m)); });
      method.setAttribute('aria-label', 'HTTP method');
      path = el('input', 'pg-path');
      path.type = 'text'; path.value = pre.dataset.path || '/'; path.spellcheck = false;
      path.setAttribute('aria-label', 'Request path');
      body = el('textarea', 'pg-body');
      body.rows = 2; body.placeholder = 'JSON body (optional)'; body.spellcheck = false;
      body.setAttribute('aria-label', 'JSON request body');
      var sendBtn = el('button', 'btn btn-primary pg-send', 'Send');
      sendBtn.type = 'button';
      sendBtn.addEventListener('click', function () { send(sendBtn); });
      path.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(sendBtn); });
      bar.appendChild(method); bar.appendChild(path); bar.appendChild(sendBtn);
      out.appendChild(bar);
      out.appendChild(body);
      runBtn.addEventListener('click', function () { load(runBtn).then(function (ok) { loaded = ok; }); });
    } else {
      runBtn.addEventListener('click', function () { runTest(runBtn); });
    }
    out.appendChild(res);
    wrap.appendChild(out);
  }

  Array.prototype.forEach.call(document.querySelectorAll('pre[data-run]'), setup);
})();
