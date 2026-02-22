<!DOCTYPE html>
<html>
<head>
  <title>{{title}}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    :root {
      --bg: #0b1222; --bg2: #111a2e; --bg3: #1a2540; --border: #1e3050;
      --border-hover: #2a4570; --text: #e2e8f0; --text2: #8b9cc0; --text3: #4a5e80;
      --blue: #60a5fa; --blue-dim: rgba(96,165,250,0.12);
      --green: #34d399; --green-dim: rgba(52,211,153,0.12);
      --yellow: #fbbf24; --yellow-dim: rgba(251,191,36,0.12);
      --red: #f87171; --red-dim: rgba(248,113,113,0.12);
      --purple: #c084fc; --purple-dim: rgba(192,132,252,0.12);
      --cyan: #22d3ee; --cyan-dim: rgba(34,211,238,0.1);
      --radius: 10px; --radius-sm: 6px;
      --shadow: 0 1px 3px rgba(0,0,0,0.3);
      --shadow-lg: 0 8px 30px rgba(0,0,0,0.4);
      --font: 'Inter', system-ui, -apple-system, sans-serif;
      --font-mono: 'JetBrains Mono', 'SF Mono', 'Cascadia Code', 'Fira Code', monospace;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: var(--font); background: var(--bg); color: var(--text); min-height: 100vh; -webkit-font-smoothing: antialiased; }
    .container { max-width: 1100px; margin: 0 auto; padding: 48px 24px; }
    h1 {
      color: var(--blue); font-size: 36px; font-weight: 800; margin-bottom: 8px;
      letter-spacing: -0.03em;
      background: linear-gradient(135deg, #e2e8f0 0%, #60a5fa 50%, #3b82f6 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
    }
    .subtitle { color: var(--text2); margin-bottom: 28px; font-size: 16px; line-height: 1.5; }

    /* Hero action */
    .hero-actions { display: flex; gap: 10px; margin-bottom: 36px; flex-wrap: wrap; }
    .btn {
      padding: 11px 24px; border-radius: 8px; font-size: 14px; font-weight: 600;
      cursor: pointer; border: none; transition: all 0.2s ease;
      display: inline-flex; align-items: center; gap: 8px; font-family: var(--font); text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, #1d4ed8, #3b82f6); color: #fff;
      box-shadow: 0 2px 8px rgba(37,99,235,0.3);
    }
    .btn-primary:hover { background: linear-gradient(135deg, #2563eb, #60a5fa); transform: translateY(-1px); box-shadow: 0 4px 16px rgba(37,99,235,0.4); }
    .btn-secondary { background: var(--bg2); color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover { background: var(--bg3); border-color: var(--border-hover); color: #fff; }
    .btn-sm { padding: 7px 14px; font-size: 13px; border-radius: var(--radius-sm); }

    /* Features grid */
    .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 36px; }
    .feature {
      background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 18px; transition: all 0.2s;
    }
    .feature:hover { border-color: var(--border-hover); transform: translateY(-2px); box-shadow: var(--shadow-lg); }
    .feature h3 { color: var(--blue); font-size: 13px; margin-bottom: 5px; font-weight: 700; }
    .feature p { color: var(--text3); font-size: 12px; line-height: 1.5; }

    /* Endpoints list */
    .endpoints { background: var(--bg2); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
    .endpoint-group { padding: 20px 24px; border-bottom: 1px solid var(--border); }
    .endpoint-group:last-child { border-bottom: none; }
    .group-title { color: var(--blue); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; margin-bottom: 12px; }
    .endpoint {
      display: flex; align-items: center; gap: 12px; font-family: var(--font-mono);
      font-size: 13px; cursor: pointer; border-radius: 8px; padding: 8px 10px;
      transition: all 0.15s;
    }
    .endpoint:hover { background: var(--bg3); }
    .method {
      display: inline-block; width: 58px; padding: 3px 8px; border-radius: 5px;
      text-align: center; font-size: 10px; font-weight: 700; flex-shrink: 0; letter-spacing: 0.3px;
    }
    .get { background: var(--green-dim); color: var(--green); }
    .post { background: var(--yellow-dim); color: var(--yellow); }
    .put { background: var(--blue-dim); color: var(--blue); }
    .patch { background: var(--purple-dim); color: var(--purple); }
    .delete { background: var(--red-dim); color: var(--red); }
    .path { color: var(--text); font-weight: 500; }
    .desc { color: var(--text3); font-family: var(--font); font-size: 12px; }
    .endpoint .try-icon { margin-left: auto; color: var(--text3); font-size: 12px; opacity: 0; transition: all 0.15s; font-family: var(--font); }
    .endpoint:hover .try-icon { opacity: 1; color: var(--blue); }

    .footer { text-align: center; margin-top: 40px; color: var(--text3); font-size: 13px; padding: 20px 0; border-top: 1px solid var(--border); }

    /* ── Playground Panel ── */
    .playground { display: none; margin-bottom: 36px; background: var(--bg2); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; box-shadow: var(--shadow-lg); }
    .playground.active { display: block; }
    .pg-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 24px; border-bottom: 1px solid var(--border); }
    .pg-header h2 { color: var(--text); font-size: 18px; font-weight: 700; }
    .pg-close { background: none; border: none; color: var(--text3); font-size: 22px; cursor: pointer; padding: 4px 8px; border-radius: var(--radius-sm); transition: all 0.15s; }
    .pg-close:hover { color: var(--red); background: var(--red-dim); }

    /* Tabs */
    .pg-tabs { display: flex; border-bottom: 1px solid var(--border); background: rgba(0,0,0,0.2); overflow-x: auto; }
    .pg-tab {
      padding: 12px 20px; font-size: 13px; font-weight: 600; color: var(--text3);
      cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap;
      transition: all 0.15s;
    }
    .pg-tab:hover { color: var(--text2); background: rgba(96,165,250,0.04); }
    .pg-tab.active { color: var(--blue); border-bottom-color: var(--blue); background: rgba(96,165,250,0.06); }
    .pg-content { padding: 24px; min-height: 300px; }
    .pg-panel { display: none; }
    .pg-panel.active { display: block; }

    /* API Tester */
    .api-tester { display: flex; gap: 20px; flex-wrap: wrap; }
    .api-form { flex: 1; min-width: 320px; }
    .api-result { flex: 1; min-width: 320px; }
    .input-row { display: flex; gap: 8px; margin-bottom: 12px; }
    .input-row select, .input-row input {
      background: var(--bg); border: 1px solid var(--border); color: var(--text);
      border-radius: var(--radius-sm); padding: 9px 12px; font-size: 13px; font-family: var(--font-mono);
      transition: border-color 0.2s;
    }
    .input-row select { width: 100px; cursor: pointer; }
    .input-row input { flex: 1; }
    .input-row input:focus, .input-row select:focus { border-color: var(--blue); outline: none; box-shadow: 0 0 0 3px rgba(96,165,250,0.1); }
    textarea.body-input {
      width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text);
      border-radius: var(--radius-sm); padding: 10px 12px; font-size: 13px; font-family: var(--font-mono);
      resize: vertical; min-height: 80px; transition: border-color 0.2s;
    }
    textarea.body-input:focus { border-color: var(--blue); outline: none; box-shadow: 0 0 0 3px rgba(96,165,250,0.1); }
    .token-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; font-size: 12px; }
    .token-bar label { color: var(--text2); white-space: nowrap; font-weight: 600; }
    .token-bar input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--green); border-radius: var(--radius-sm); padding: 7px 10px; font-size: 12px; font-family: var(--font-mono); }
    .token-bar input:focus { border-color: var(--blue); outline: none; }
    .token-status { font-size: 11px; margin-bottom: 10px; font-weight: 600; }
    .token-status.ok { color: var(--green); }
    .token-status.none { color: var(--yellow); }

    pre.response {
      background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 16px; font-size: 13px; font-family: var(--font-mono);
      overflow-x: auto; max-height: 400px; overflow-y: auto;
      white-space: pre-wrap; word-break: break-word; color: var(--text); line-height: 1.5;
    }
    .res-status { font-size: 13px; margin-bottom: 8px; font-weight: 700; }
    .res-status.s2xx { color: var(--green); }
    .res-status.s3xx { color: var(--yellow); }
    .res-status.s4xx { color: var(--red); }
    .res-status.s5xx { color: var(--red); }
    .res-time { color: var(--text3); font-size: 12px; margin-bottom: 12px; }

    /* Quick actions */
    .quick-actions { display: flex; gap: 8px; margin-bottom: 18px; flex-wrap: wrap; }
    .quick-btn {
      background: var(--bg3); border: 1px solid var(--border); color: var(--text);
      padding: 7px 14px; border-radius: var(--radius-sm); font-size: 12px; font-weight: 500;
      cursor: pointer; transition: all 0.15s; font-family: var(--font);
    }
    .quick-btn:hover { background: var(--border-hover); border-color: var(--blue); }
    .quick-btn .qm { font-size: 10px; font-weight: 700; margin-right: 4px; padding: 1px 5px; border-radius: 3px; }

    /* Framework Inspect panels */
    .inspect-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .inspect-card { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    .inspect-card-header { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
    .inspect-card-header h3 { color: var(--blue); font-size: 14px; font-weight: 700; }
    .inspect-card-body { padding: 16px 18px; font-size: 13px; }
    .inspect-card-body pre { font-family: var(--font-mono); font-size: 12px; color: var(--text); white-space: pre-wrap; }

    .mw-item { display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); }
    .mw-item:last-child { border: none; }
    .mw-order {
      background: var(--blue-dim); color: var(--blue); padding: 3px 10px; border-radius: 5px;
      font-size: 11px; font-weight: 700; font-family: var(--font-mono); min-width: 34px; text-align: center;
    }
    .mw-name { color: var(--text); font-size: 13px; font-weight: 500; }
    .mw-type { color: var(--text3); font-size: 11px; margin-left: auto; }

    .route-item { display: flex; gap: 10px; padding: 4px 0; font-size: 13px; font-family: var(--font-mono); }

    /* Auth demo */
    .auth-demo { max-width: 550px; }
    .auth-step {
      background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 18px; margin-bottom: 14px;
    }
    .auth-step h4 { color: var(--blue); font-size: 14px; margin-bottom: 8px; font-weight: 700; }
    .auth-step p { color: var(--text2); font-size: 13px; margin-bottom: 12px; line-height: 1.5; }
    .cred-grid { display: grid; grid-template-columns: auto 1fr 1fr; gap: 6px 14px; font-size: 12px; font-family: var(--font-mono); margin-bottom: 14px; }
    .cred-grid .label { color: var(--text3); font-weight: 600; }
    .cred-grid .val { color: var(--text); }
    .cred-grid .role { color: var(--purple); font-weight: 600; }

    /* Loading spinner */
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top: 2px solid var(--blue); border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 6px; }
    @keyframes spin { to { transform: rotate(360deg); } }

    .section-title { color: var(--text); font-size: 17px; font-weight: 700; margin-bottom: 16px; letter-spacing: -0.01em; }
    .hint { color: var(--text2); font-size: 13px; margin-bottom: 18px; line-height: 1.5; }

    /* Code Playground */
    .code-playground { display: flex; gap: 16px; flex-wrap: wrap; }
    .code-editor-wrap { flex: 1; min-width: 320px; display: flex; flex-direction: column; }
    .code-output-wrap { flex: 1; min-width: 320px; }
    .code-editor {
      width: 100%; min-height: 280px; background: var(--bg); border: 1px solid var(--border);
      color: var(--text); border-radius: var(--radius); padding: 16px; font-size: 13px;
      font-family: var(--font-mono); resize: vertical; line-height: 1.6; tab-size: 4;
      transition: border-color 0.2s;
    }
    .code-editor:focus { border-color: var(--blue); outline: none; box-shadow: 0 0 0 3px rgba(96,165,250,0.1); }
    .code-toolbar { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; flex-wrap: wrap; }
    .code-toolbar .run-btn {
      background: linear-gradient(135deg, #1d4ed8, #3b82f6); border: none; color: #fff;
      padding: 8px 22px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 600;
      cursor: pointer; display: inline-flex; align-items: center; gap: 6px; font-family: var(--font);
      transition: all 0.2s; box-shadow: 0 1px 4px rgba(37,99,235,0.3);
    }
    .code-toolbar .run-btn:hover { background: linear-gradient(135deg, #2563eb, #60a5fa); transform: translateY(-1px); }
    .code-toolbar .run-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
    .example-select {
      background: var(--bg3); border: 1px solid var(--border); color: var(--text);
      border-radius: var(--radius-sm); padding: 8px 12px; font-size: 12px; cursor: pointer; font-family: var(--font);
    }
    .code-output {
      background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 16px; min-height: 280px; font-size: 13px; font-family: var(--font-mono);
      white-space: pre-wrap; word-break: break-word; color: var(--text2);
      overflow: auto; max-height: 400px; line-height: 1.6;
    }
    .code-output .err { color: var(--red); }
    .code-output .ok { color: var(--green); }
    .code-label { font-size: 11px; color: var(--text3); margin-bottom: 8px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--border-hover); }

    /* ── Mobile Responsive ── */
    @media (max-width: 768px) {
      .container { padding: 24px 14px; }
      h1 { font-size: 26px; }
      .subtitle { font-size: 14px; }
      .hero-actions { flex-direction: column; }
      .btn { width: 100%; text-align: center; justify-content: center; padding: 12px 16px; font-size: 14px; }
      .features { grid-template-columns: 1fr 1fr; gap: 10px; }
      .feature { padding: 14px; }
      .feature h3 { font-size: 12px; }
      .feature p { font-size: 11px; }
      .endpoint-group { padding: 16px 14px; }
      .endpoint { flex-wrap: wrap; gap: 6px; font-size: 12px; padding: 8px 6px; }
      .method { width: 50px; font-size: 10px; padding: 2px 4px; }
      .desc { width: 100%; padding-left: 62px; }
      .pg-header { padding: 14px 16px; }
      .pg-header h2 { font-size: 16px; }
      .pg-tabs { gap: 0; }
      .pg-tab { padding: 10px 14px; font-size: 12px; }
      .pg-content { padding: 16px; }
      .api-tester { flex-direction: column; }
      .api-form { min-width: 0; }
      .api-result { min-width: 0; }
      .input-row { flex-direction: column; gap: 6px; }
      .input-row select { width: 100%; }
      .token-bar { flex-direction: column; align-items: stretch; gap: 4px; }
      pre.response { max-height: 300px; font-size: 11px; padding: 12px; }
      .quick-actions { gap: 6px; }
      .quick-btn { font-size: 11px; padding: 6px 10px; }
      .inspect-cards { grid-template-columns: 1fr; }
      .code-playground { flex-direction: column; }
      .code-editor-wrap { min-width: 0; }
      .code-output-wrap { min-width: 0; }
      .code-editor { min-height: 200px; font-size: 12px; }
      .code-output { min-height: 180px; font-size: 12px; }
      .code-toolbar { flex-wrap: wrap; }
      .auth-demo { max-width: 100%; }
      .cred-grid { grid-template-columns: 1fr 1fr; gap: 4px 8px; font-size: 11px; }
      .route-item { font-size: 11px; flex-wrap: wrap; }
    }

    @media (max-width: 480px) {
      .features { grid-template-columns: 1fr; }
      .endpoint .try-icon { display: none; }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>{{title}}</h1>
    <p class="subtitle">{{description}}</p>

    <div class="hero-actions">
      <a href="/frontend" class="btn btn-primary">
        &#9654; Open Frontend App
      </a>
      <button class="btn btn-secondary" onclick="togglePlayground(); switchTab('code-playground')">
        &#9654; Code Playground
      </button>
      <button class="btn btn-secondary" onclick="togglePlayground(); switchTab('api-tester')">
        &#9881; API Playground
      </button>
      <a href="/docs" class="btn btn-secondary">API Docs</a>
      <a href="/health" class="btn btn-secondary">Health Check</a>
    </div>

    <!-- ═══ Interactive Playground ═══ -->
    <div id="playground" class="playground">
      <div class="pg-header">
        <h2>Interactive Playground</h2>
        <button class="pg-close" onclick="togglePlayground()">&times;</button>
      </div>

      <div class="pg-tabs">
        <div class="pg-tab active" onclick="switchTab('api-tester')">API Tester</div>
        <div class="pg-tab" onclick="switchTab('code-playground')">Code Playground</div>
        <div class="pg-tab" onclick="switchTab('auth-demo')">Auth Flow</div>
        <div class="pg-tab" onclick="switchTab('middleware')">Middleware Stack</div>
        <div class="pg-tab" onclick="switchTab('routes')">All Routes</div>
        <div class="pg-tab" onclick="switchTab('config')">Config</div>
        <div class="pg-tab" onclick="switchTab('stats')">Stats</div>
      </div>

      <div class="pg-content">

        <!-- ── Tab: API Tester ── -->
        <div id="tab-api-tester" class="pg-panel active">
          <p class="hint">Click any endpoint below to load it, or type your own. Login first to get a token for protected routes.</p>

          <div class="quick-actions">
            <button class="quick-btn" onclick="quickLogin('admin','admin123')"><span class="qm post">POST</span>Login as admin</button>
            <button class="quick-btn" onclick="quickLogin('alice','alice123')"><span class="qm post">POST</span>Login as alice</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/api/users/')"><span class="qm get">GET</span>List Users</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/api/projects/')"><span class="qm get">GET</span>Projects</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/api/projects/1/tasks')"><span class="qm get">GET</span>Tasks</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/api/projects/dashboard/overview')"><span class="qm get">GET</span>Dashboard</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/health')"><span class="qm get">GET</span>Health</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/debug/routes')"><span class="qm get">GET</span>Routes</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/debug/middleware')"><span class="qm get">GET</span>Middleware</button>
            <button class="quick-btn" onclick="loadEndpoint('GET','/debug/stats')"><span class="qm get">GET</span>Stats</button>
          </div>

          <div class="api-tester">
            <div class="api-form">
              <div class="input-row">
                <select id="req-method">
                  <option>GET</option>
                  <option>POST</option>
                  <option>PUT</option>
                  <option>PATCH</option>
                  <option>DELETE</option>
                </select>
                <input type="text" id="req-url" placeholder="/api/users/" value="/health">
                <button class="btn btn-primary btn-sm" onclick="sendRequest()">Send</button>
              </div>

              <div class="token-bar">
                <label>Token:</label>
                <input type="text" id="auth-token" placeholder="Login to get a token...">
              </div>
              <div id="token-status" class="token-status none">No token — public routes only</div>

              <textarea id="req-body" class="body-input" placeholder='{"key": "value"} (for POST/PUT/PATCH)'></textarea>
            </div>

            <div class="api-result">
              <div id="res-status" class="res-status"></div>
              <div id="res-time" class="res-time"></div>
              <pre id="res-body" class="response">Click "Send" or use a quick action to see the response here.</pre>
            </div>
          </div>
        </div>

        <!-- ── Tab: Code Playground ── -->
        <div id="tab-code-playground" class="pg-panel">
          <div class="section-title">Lcore Code Playground</div>
          <p class="hint">Write and run Lcore framework code live. The full framework is available — create apps, routes, test with TestClient, hash passwords, and more.</p>

          <div class="code-toolbar">
            <button class="run-btn" id="run-code-btn" onclick="runCode()">&#9654; Run</button>
            <select class="example-select" onchange="loadExample(this.value)">
              <option value="">Load Example...</option>
              <option value="hello">Hello World</option>
              <option value="json-api">JSON API + TestClient</option>
              <option value="routing">Typed Route Parameters</option>
              <option value="middleware">Custom Middleware</option>
              <option value="password">Password Hashing</option>
              <option value="validation">Request Validation</option>
              <option value="hooks">Lifecycle Hooks</option>
            </select>
          </div>

          <div class="code-playground">
            <div class="code-editor-wrap">
              <div class="code-label">Code</div>
              <textarea id="code-input" class="code-editor" spellcheck="false">from lcore import Lcore, TestClient

app = Lcore()

@app.route('/hello/<name>')
def hello(name):
    return {'message': f'Hello, {name}!'}

# Test it without a server
client = TestClient(app)
resp = client.get('/hello/World')
print(f"Status: {resp.status_code}")
print(f"Body: {resp.json}")
</textarea>
            </div>
            <div class="code-output-wrap">
              <div class="code-label">Output</div>
              <div id="code-output" class="code-output">Click "Run" to execute your code.</div>
            </div>
          </div>
        </div>

        <!-- ── Tab: Auth Flow Demo ── -->
        <div id="tab-auth-demo" class="pg-panel">
          <div class="section-title">Authentication Flow</div>
          <p class="hint">This API uses HMAC-SHA256 signed tokens. Try the full auth flow below.</p>

          <div class="auth-demo">
            <div class="auth-step">
              <h4>Step 1 — Login to get a token</h4>
              <p>Click a user to login. The token will be saved automatically for API requests.</p>
              <div class="cred-grid">
                <span class="label">User</span><span class="label">Password</span><span class="label">Role</span>
                <span class="val">admin</span><span class="val">admin123</span><span class="role">admin</span>
                <span class="val">alice</span><span class="val">alice123</span><span class="role">member</span>
                <span class="val">bob</span><span class="val">bob123</span><span class="role">member</span>
              </div>
              <div style="display: flex; gap: 8px;">
                <button class="btn btn-primary btn-sm" onclick="quickLogin('admin','admin123')">Login as admin</button>
                <button class="btn btn-secondary btn-sm" onclick="quickLogin('alice','alice123')">Login as alice</button>
                <button class="btn btn-secondary btn-sm" onclick="quickLogin('bob','bob123')">Login as bob</button>
              </div>
              <pre id="auth-result" class="response" style="margin-top: 12px; max-height: 150px;"></pre>
            </div>

            <div class="auth-step">
              <h4>Step 2 — Access protected routes</h4>
              <p>With a token, try these protected endpoints:</p>
              <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="quick-btn" onclick="loadEndpoint('GET','/api/users/');switchTab('api-tester')">GET /api/users/</button>
                <button class="quick-btn" onclick="loadEndpoint('GET','/auth/me');switchTab('api-tester')">GET /auth/me</button>
                <button class="quick-btn" onclick="loadEndpoint('GET','/admin/dashboard');switchTab('api-tester')">GET /admin/dashboard</button>
              </div>
            </div>

            <div class="auth-step">
              <h4>Step 3 — Test RBAC (Role-Based Access)</h4>
              <p>Login as <strong>alice</strong> (member) and try <code>/admin/dashboard</code> — you'll get a 403 Forbidden. Login as <strong>admin</strong> and it works.</p>
              <div style="display: flex; gap: 8px;">
                <button class="quick-btn" onclick="quickLogin('alice','alice123');setTimeout(()=>{loadEndpoint('GET','/admin/dashboard');switchTab('api-tester')},500)">Try as alice (403)</button>
                <button class="quick-btn" onclick="quickLogin('admin','admin123');setTimeout(()=>{loadEndpoint('GET','/admin/dashboard');switchTab('api-tester')},500)">Try as admin (200)</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Tab: Middleware ── -->
        <div id="tab-middleware" class="pg-panel">
          <div class="section-title">Middleware Stack</div>
          <p class="hint">These run in order on every request. Lower order = runs first (outermost wrapper).</p>
          <div id="mw-list" style="max-width: 600px;">
            <div style="color: #484f58; font-size: 13px;">Loading...</div>
          </div>
        </div>

        <!-- ── Tab: Routes ── -->
        <div id="tab-routes" class="pg-panel">
          <div class="section-title">Registered Routes</div>
          <p class="hint">All routes registered in the application. Click any to load it in the API Tester.</p>
          <div id="routes-list">
            <div style="color: #484f58; font-size: 13px;">Loading...</div>
          </div>
        </div>

        <!-- ── Tab: Config ── -->
        <div id="tab-config" class="pg-panel">
          <div class="section-title">Application Configuration</div>
          <p class="hint">Config loaded from defaults + .env + environment variables. Secrets are redacted.</p>
          <pre id="config-data" class="response">Loading...</pre>
        </div>

        <!-- ── Tab: Stats ── -->
        <div id="tab-stats" class="pg-panel">
          <div class="section-title">Request Counter Stats</div>
          <p class="hint">The RequestCounterPlugin tracks per-route hit counts. Refresh to see updated counts.</p>
          <div style="margin-bottom: 12px;">
            <button class="btn btn-secondary btn-sm" onclick="loadStats()">Refresh Stats</button>
          </div>
          <pre id="stats-data" class="response">Loading...</pre>
        </div>

      </div>
    </div>

    <!-- ═══ Features Grid ═══ -->
    <div class="features">
      % for feature in features:
      <div class="feature">
        <h3>{{feature['name']}}</h3>
        <p>{{feature['desc']}}</p>
      </div>
      % end
    </div>

    <!-- ═══ Endpoints Reference ═══ -->
    <div class="endpoints">
      % for group in endpoint_groups:
      <div class="endpoint-group">
        <div class="group-title">{{group['name']}}</div>
        % for ep in group['endpoints']:
        <div class="endpoint" onclick="loadEndpoint('{{ep['method']}}','{{ep['path']}}');openPlayground()">
          <span class="method {{ep['method'].lower()}}">{{ep['method']}}</span>
          <span class="path">{{ep['path']}}</span>
          <span class="desc">{{ep['desc']}}</span>
          <span class="try-icon">Try &rarr;</span>
        </div>
        % end
      </div>
      % end
    </div>

    <div class="footer">
      Lcore Framework v{{version}} &middot; Running on {{host}}
      <br>
      <a href="https://github.com/Lusan-sapkota/lcore" target="_blank" style="color:var(--blue);text-decoration:none;font-weight:500;">GitHub</a>
      &middot;
      <a href="https://lusansapkota.com.np" target="_blank" style="color:var(--blue);text-decoration:none;font-weight:500;">lusansapkota.com.np</a>
    </div>
  </div>

  <script>
    // ═══ State ═══
    var authToken = '';
    var baseUrl = window.location.origin;

    // ═══ Playground toggle ═══
    function togglePlayground() {
      var pg = document.getElementById('playground');
      pg.classList.toggle('active');
      if (pg.classList.contains('active')) {
        loadMiddleware();
        loadRoutes();
        loadConfig();
        loadStats();
      } else {
        // Clear hash when closing playground
        if (window.location.hash) history.replaceState(null, '', window.location.pathname);
      }
    }

    function openPlayground() {
      var pg = document.getElementById('playground');
      if (!pg.classList.contains('active')) {
        togglePlayground();
      }
      switchTab('api-tester');
    }

    // ═══ Tab switching ═══
    function switchTab(tabId) {
      var tabs = document.querySelectorAll('.pg-tab');
      var panels = document.querySelectorAll('.pg-panel');
      tabs.forEach(function(t) { t.classList.remove('active'); });
      panels.forEach(function(p) { p.classList.remove('active'); });
      document.getElementById('tab-' + tabId).classList.add('active');
      // Update hash for refresh persistence
      window.location.hash = tabId;
      // activate corresponding tab button
      tabs.forEach(function(t) {
        if (t.textContent.toLowerCase().replace(/\s+/g, '-') === tabId ||
            t.getAttribute('onclick').indexOf(tabId) !== -1) {
          t.classList.add('active');
        }
      });
    }

    // ═══ API Request ═══
    function sendRequest() {
      var method = document.getElementById('req-method').value;
      var url = document.getElementById('req-url').value;
      var body = document.getElementById('req-body').value.trim();
      var statusEl = document.getElementById('res-status');
      var timeEl = document.getElementById('res-time');
      var bodyEl = document.getElementById('res-body');

      statusEl.innerHTML = '<span class="spinner"></span>Sending...';
      statusEl.className = 'res-status';
      timeEl.textContent = '';
      bodyEl.textContent = '';

      var headers = { 'Accept': 'application/json' };
      if (authToken) {
        headers['Authorization'] = 'Bearer ' + authToken;
      }

      var opts = { method: method, headers: headers };
      if (body && method !== 'GET') {
        headers['Content-Type'] = 'application/json';
        opts.body = body;
      }

      var start = performance.now();
      fetch(baseUrl + url, opts).then(function(res) {
        var elapsed = (performance.now() - start).toFixed(0);
        var statusCode = res.status;
        var statusText = res.statusText;
        var cls = 's' + Math.floor(statusCode / 100) + 'xx';

        statusEl.textContent = statusCode + ' ' + statusText;
        statusEl.className = 'res-status ' + cls;
        timeEl.textContent = elapsed + 'ms' + (res.headers.get('X-Response-Time') ? ' (server: ' + res.headers.get('X-Response-Time') + ')' : '');

        var ct = res.headers.get('Content-Type') || '';
        if (ct.indexOf('json') !== -1) {
          return res.json().then(function(data) {
            bodyEl.textContent = JSON.stringify(data, null, 2);
          });
        } else {
          return res.text().then(function(text) {
            bodyEl.textContent = text.substring(0, 3000);
          });
        }
      }).catch(function(err) {
        statusEl.textContent = 'Error';
        statusEl.className = 'res-status s5xx';
        bodyEl.textContent = err.message;
      });
    }

    // ═══ Load endpoint into tester ═══
    function loadEndpoint(method, path) {
      document.getElementById('req-method').value = method;
      document.getElementById('req-url').value = path;
      document.getElementById('req-body').value = '';

      // Pre-fill body for POST/PUT/PATCH
      if (method === 'POST' && path === '/auth/login') {
        document.getElementById('req-body').value = '{"username": "admin", "password": "admin123"}';
      } else if (method === 'POST' && path === '/auth/register') {
        document.getElementById('req-body').value = '{"username": "newuser", "email": "new@example.com", "password": "pass123"}';
      } else if (method === 'POST' && path.indexOf('/tasks') !== -1 && path.indexOf('/comments') !== -1) {
        document.getElementById('req-body').value = '{"body": "This is a comment"}';
      } else if (method === 'POST' && path.indexOf('/tasks') !== -1) {
        document.getElementById('req-body').value = '{"title": "New task", "description": "Task description", "priority": "high"}';
      } else if (method === 'POST' && path.indexOf('/projects') !== -1) {
        document.getElementById('req-body').value = '{"name": "New Project", "description": "Project description"}';
      } else if (method === 'POST' && path === '/api/users/') {
        document.getElementById('req-body').value = '{"username": "charlie", "email": "charlie@example.com", "password": "charlie123", "role": "member"}';
      } else if (method === 'POST' && path.indexOf('/email') !== -1) {
        document.getElementById('req-body').value = '{"to": "test@example.com", "subject": "Test Email", "body": "Hello from TaskFlow!"}';
      } else if (method === 'PUT' || method === 'PATCH') {
        document.getElementById('req-body').value = '{}';
      }

      sendRequest();
    }

    // ═══ Quick login ═══
    function quickLogin(username, password) {
      var statusEl = document.getElementById('res-status');
      var bodyEl = document.getElementById('res-body');
      var authResult = document.getElementById('auth-result');

      document.getElementById('req-method').value = 'POST';
      document.getElementById('req-url').value = '/auth/login';
      document.getElementById('req-body').value = JSON.stringify({username: username, password: password});

      fetch(baseUrl + '/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body: JSON.stringify({ username: username, password: password })
      }).then(function(res) {
        return res.json().then(function(data) {
          if (data.token) {
            authToken = data.token;
            document.getElementById('auth-token').value = authToken;
            var ts = document.getElementById('token-status');
            ts.textContent = 'Logged in as ' + data.user.username + ' (role: ' + data.user.role + ')';
            ts.className = 'token-status ok';
          }
          var pretty = JSON.stringify(data, null, 2);
          statusEl.textContent = res.status + ' ' + res.statusText;
          statusEl.className = 'res-status s2xx';
          bodyEl.textContent = pretty;
          if (authResult) authResult.textContent = pretty;
          return data;
        });
      }).catch(function(err) {
        statusEl.textContent = 'Error';
        bodyEl.textContent = err.message;
      });
    }

    // ═══ Load framework inspection data ═══
    function loadMiddleware() {
      fetch(baseUrl + '/debug/middleware', { headers: { 'Accept': 'application/json' } }).then(function(res) {
        return res.json();
      }).then(function(data) {
        var list = document.getElementById('mw-list');
        if (!data.middleware) { list.innerHTML = '<div style="color:#f85149">Failed to load</div>'; return; }
        var html = '';
        data.middleware.sort(function(a, b) { return a.order - b.order; });
        data.middleware.forEach(function(mw) {
          html += '<div class="mw-item">';
          html += '<span class="mw-order">' + mw.order + '</span>';
          html += '<span class="mw-name">' + mw.name + '</span>';
          html += '<span class="mw-type">' + mw.type + '</span>';
          html += '</div>';
        });
        list.innerHTML = html;
      });
    }

    function loadRoutes() {
      fetch(baseUrl + '/debug/routes', { headers: { 'Accept': 'application/json' } }).then(function(res) {
        return res.json();
      }).then(function(data) {
        var list = document.getElementById('routes-list');
        if (!data.routes) { list.innerHTML = '<div style="color:#f85149">Failed to load</div>'; return; }
        var html = '<div style="font-size:12px;color:#8b949e;margin-bottom:12px;">' + data.total + ' routes registered</div>';
        data.routes.forEach(function(r) {
          var m = (r.method || 'GET').toUpperCase();
          var cls = m.toLowerCase();
          html += '<div class="route-item endpoint" onclick="loadEndpoint(\'' + m + '\',\'' + r.rule + '\');switchTab(\'api-tester\')" style="cursor:pointer">';
          html += '<span class="method ' + cls + '">' + m + '</span>';
          html += '<span class="path">' + r.rule + '</span>';
          if (r.name) html += '<span class="desc" style="margin-left:auto">' + r.name + '</span>';
          html += '</div>';
        });
        list.innerHTML = html;
      });
    }

    function loadConfig() {
      fetch(baseUrl + '/debug/config', { headers: { 'Accept': 'application/json' } }).then(function(res) {
        return res.json();
      }).then(function(data) {
        document.getElementById('config-data').textContent = JSON.stringify(data.config || data, null, 2);
      });
    }

    function loadStats() {
      fetch(baseUrl + '/debug/stats', { headers: { 'Accept': 'application/json' } }).then(function(res) {
        return res.json();
      }).then(function(data) {
        document.getElementById('stats-data').textContent = JSON.stringify(data.route_stats || data, null, 2);
      });
    }

    // ═══ Code Playground ═══
    var codeExamples = {
      hello: 'from lcore import Lcore, TestClient\n\napp = Lcore()\n\n@app.route(\'/hello/<name>\')\ndef hello(name):\n    return {\'message\': f\'Hello, {name}!\'}\n\nclient = TestClient(app)\nresp = client.get(\'/hello/World\')\nprint(f"Status: {resp.status_code}")\nprint(f"Body: {resp.json}")',

      'json-api': 'from lcore import Lcore, TestClient\n\napp = Lcore()\nitems = []\n\n@app.get(\'/items\')\ndef list_items():\n    return {\'items\': items}\n\n@app.post(\'/items\')\ndef create_item():\n    from lcore import request\n    data = request.json\n    items.append(data)\n    return {\'created\': data, \'total\': len(items)}\n\nclient = TestClient(app)\n\n# Create items\nclient.post(\'/items\', json={\'name\': \'Widget\', \'price\': 9.99})\nclient.post(\'/items\', json={\'name\': \'Gadget\', \'price\': 24.99})\n\n# List them\nresp = client.get(\'/items\')\nprint(f"Status: {resp.status_code}")\nfor item in resp.json[\'items\']:\n    print(f"  - {item[\'name\']}: ${item[\'price\']}")',

      routing: 'from lcore import Lcore, TestClient\n\napp = Lcore()\n\n@app.get(\'/users/<id:int>\')\ndef get_user(id):\n    return {\'id\': id, \'type\': \'integer param\'}\n\n@app.get(\'/files/<filepath:path>\')\ndef get_file(filepath):\n    return {\'path\': filepath, \'type\': \'path param\'}\n\nclient = TestClient(app)\n\nprint("Typed integer param:")\nr = client.get(\'/users/42\')\nprint(f"  {r.json}")\n\nprint("\\nPath param:")\nr = client.get(\'/files/docs/readme.md\')\nprint(f"  {r.json}")\n\nprint("\\n404 on wrong type:")\nr = client.get(\'/users/abc\')\nprint(f"  Status: {r.status_code}")',

      middleware: 'from lcore import Lcore, TestClient, Middleware\n\nclass TimingMiddleware(Middleware):\n    name = \'timing\'\n    order = 1\n\n    def __call__(self, ctx, next_handler):\n        import time\n        start = time.time()\n        result = next_handler(ctx)\n        ms = (time.time() - start) * 1000\n        ctx.response.set_header(\'X-Response-Time\', f\'{ms:.2f}ms\')\n        print(f"  {ctx.request.method} {ctx.request.path} -> {ms:.2f}ms")\n        return result\n\napp = Lcore()\napp.use(TimingMiddleware())\n\n@app.route(\'/fast\')\ndef fast():\n    return {\'speed\': \'fast\'}\n\n@app.route(\'/slow\')\ndef slow():\n    import time; time.sleep(0.01)\n    return {\'speed\': \'slow\'}\n\nclient = TestClient(app)\nprint("Middleware timing:")\nclient.get(\'/fast\')\nclient.get(\'/slow\')\n\nr = client.get(\'/fast\')\nprint(f"\\nX-Response-Time: {r.headers.get(\'X-Response-Time\')}")',

      password: 'from lcore import hash_password, verify_password\n\n# Hash a password\nhashed = hash_password(\'my_secret_123\')\nprint(f"Hash: {hashed[:50]}...")\nprint(f"Format: pbkdf2:sha256:iterations$salt$hash")\n\n# Verify correct password\nresult = verify_password(\'my_secret_123\', hashed)\nprint(f"\\nCorrect password: {result}")\n\n# Verify wrong password\nresult = verify_password(\'wrong_password\', hashed)\nprint(f"Wrong password: {result}")\n\n# Each hash is unique (different salt)\nhash1 = hash_password(\'same\')\nhash2 = hash_password(\'same\')\nprint(f"\\nSame password, different hashes:")\nprint(f"  Hash 1: {hash1[:40]}...")\nprint(f"  Hash 2: {hash2[:40]}...")\nprint(f"  Equal: {hash1 == hash2}")\nprint(f"  Both verify: {verify_password(\'same\', hash1) and verify_password(\'same\', hash2)}")',

      validation: 'from lcore import Lcore, TestClient, validate_request\n\napp = Lcore()\n\n@app.post(\'/register\')\n@validate_request(body={\'username\': str, \'email\': str, \'age\': int})\ndef register():\n    from lcore import request\n    data = request.json\n    return {\'registered\': data[\'username\'], \'age\': data[\'age\']}\n\nclient = TestClient(app)\n\n# Valid request\nprint("Valid request:")\nr = client.post(\'/register\', json={\'username\': \'alice\', \'email\': \'a@b.com\', \'age\': 25})\nprint(f"  {r.status_code}: {r.json}")\n\n# Missing field\nprint("\\nMissing field:")\nr = client.post(\'/register\', json={\'username\': \'bob\'})\nprint(f"  {r.status_code}: {r.text[:80]}")\n\n# Wrong type\nprint("\\nWrong type:")\nr = client.post(\'/register\', json={\'username\': \'charlie\', \'email\': \'c@d.com\', \'age\': \'not_int\'})\nprint(f"  {r.status_code}: {r.text[:80]}")',

      hooks: 'from lcore import Lcore, TestClient\n\napp = Lcore()\nlog = []\n\n@app.hook(\'before_request\')\ndef before():\n    log.append(\'before_request fired\')\n\n@app.hook(\'after_request\')\ndef after():\n    log.append(\'after_request fired\')\n\n@app.route(\'/test\')\ndef test_route():\n    log.append(\'handler executed\')\n    return {\'ok\': True}\n\nclient = TestClient(app)\nresp = client.get(\'/test\')\n\nprint("Lifecycle hooks fired in order:")\nfor i, entry in enumerate(log):\n    print(f"  {i+1}. {entry}")\nprint(f"\\nResponse: {resp.json}")'
    };

    function loadExample(name) {
      if (name && codeExamples[name]) {
        document.getElementById('code-input').value = codeExamples[name];
        document.getElementById('code-output').innerHTML = 'Click "Run" to execute your code.';
      }
    }

    function runCode() {
      var code = document.getElementById('code-input').value;
      var outputEl = document.getElementById('code-output');
      var runBtn = document.getElementById('run-code-btn');

      runBtn.disabled = true;
      runBtn.innerHTML = '<span class="spinner"></span>Running...';
      outputEl.innerHTML = '<span style="color:#8b949e">Executing...</span>';

      fetch(baseUrl + '/playground/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      }).then(function(res) {
        return res.json();
      }).then(function(data) {
        var html = '';
        if (data.output) {
          html += '<span class="ok">' + escHtml(data.output) + '</span>';
        }
        if (data.error) {
          html += (html ? '\n' : '') + '<span class="err">' + escHtml(data.error) + '</span>';
        }
        if (!html) html = '<span style="color:#8b949e">(no output)</span>';
        outputEl.innerHTML = html;
      }).catch(function(err) {
        outputEl.innerHTML = '<span class="err">Request failed: ' + escHtml(err.message) + '</span>';
      }).finally(function() {
        runBtn.disabled = false;
        runBtn.innerHTML = '&#9654; Run';
      });
    }

    function escHtml(s) {
      return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // Tab key inserts spaces in code editor
    document.addEventListener('DOMContentLoaded', function() {
      var editor = document.getElementById('code-input');
      if (editor) {
        editor.addEventListener('keydown', function(e) {
          if (e.key === 'Tab') {
            e.preventDefault();
            var start = this.selectionStart;
            var end = this.selectionEnd;
            this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
            this.selectionStart = this.selectionEnd = start + 4;
          }
        });
      }
    });

    // ═══ Manual token input ═══
    document.addEventListener('DOMContentLoaded', function() {
      var tokenInput = document.getElementById('auth-token');
      tokenInput.addEventListener('input', function() {
        authToken = tokenInput.value.trim();
        var ts = document.getElementById('token-status');
        if (authToken) {
          ts.textContent = 'Token set (manually entered)';
          ts.className = 'token-status ok';
        } else {
          ts.textContent = 'No token — public routes only';
          ts.className = 'token-status none';
        }
      });
    });

    // ═══ Restore playground state from URL hash on page load ═══
    document.addEventListener('DOMContentLoaded', function() {
      var hash = window.location.hash.replace('#', '');
      var validTabs = ['api-tester', 'code-playground', 'auth-demo', 'middleware', 'routes', 'config', 'stats'];
      if (hash && validTabs.indexOf(hash) !== -1) {
        var pg = document.getElementById('playground');
        if (!pg.classList.contains('active')) {
          togglePlayground();
        }
        switchTab(hash);
      }
    });

    // Handle back/forward navigation
    window.addEventListener('hashchange', function() {
      var hash = window.location.hash.replace('#', '');
      var validTabs = ['api-tester', 'code-playground', 'auth-demo', 'middleware', 'routes', 'config', 'stats'];
      if (hash && validTabs.indexOf(hash) !== -1) {
        var pg = document.getElementById('playground');
        if (!pg.classList.contains('active')) togglePlayground();
        switchTab(hash);
      } else if (!hash) {
        var pg = document.getElementById('playground');
        if (pg.classList.contains('active')) pg.classList.remove('active');
      }
    });
  </script>
</body>
</html>
