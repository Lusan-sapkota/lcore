<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TaskFlow — Project Management</title>
  <style>
    :root {
      --bg: #0d1117; --bg2: #161b22; --bg3: #21262d; --border: #30363d;
      --text: #c9d1d9; --text2: #8b949e; --text3: #484f58;
      --blue: #58a6ff; --green: #3fb950; --yellow: #d29922; --red: #f85149;
      --purple: #bc8cff; --orange: #f0883e;
      --radius: 8px;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

    /* ── Layout ── */
    .app { display: flex; min-height: 100vh; }
    .sidebar { width: 240px; background: var(--bg2); border-right: 1px solid var(--border); display: flex; flex-direction: column; position: fixed; top: 0; bottom: 0; z-index: 100; }
    .main { margin-left: 240px; flex: 1; min-height: 100vh; }
    .topbar { height: 56px; background: var(--bg2); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 24px; position: sticky; top: 0; z-index: 50; }
    .content { padding: 24px; max-width: 1200px; }

    /* ── Sidebar ── */
    .sidebar-brand { padding: 16px 20px; border-bottom: 1px solid var(--border); }
    .sidebar-brand h1 { font-size: 18px; color: var(--blue); }
    .sidebar-brand span { font-size: 11px; color: var(--text3); }
    .sidebar-nav { flex: 1; padding: 12px 8px; overflow-y: auto; }
    .nav-section { margin-bottom: 16px; }
    .nav-section-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--text3); padding: 4px 12px; margin-bottom: 4px; }
    .nav-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 6px; cursor: pointer; color: var(--text2); font-size: 14px; transition: all 0.15s; }
    .nav-item:hover { background: var(--bg3); color: var(--text); }
    .nav-item.active { background: rgba(88,166,255,0.1); color: var(--blue); }
    .nav-icon { width: 18px; text-align: center; font-size: 16px; }
    .nav-badge { margin-left: auto; background: var(--bg3); color: var(--text2); font-size: 11px; padding: 1px 6px; border-radius: 10px; }
    .sidebar-footer { padding: 12px 16px; border-top: 1px solid var(--border); }
    .sidebar-user { display: flex; align-items: center; gap: 10px; }
    .avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--bg3); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; color: var(--blue); }
    .user-info { flex: 1; }
    .user-info .name { font-size: 13px; color: var(--text); }
    .user-info .role { font-size: 11px; color: var(--text3); }

    /* ── Topbar ── */
    .topbar-title { font-size: 16px; font-weight: 600; }
    .topbar-actions { display: flex; gap: 8px; align-items: center; }

    /* ── Buttons ── */
    .btn { padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid var(--border); transition: all 0.15s; display: inline-flex; align-items: center; gap: 6px; }
    .btn-primary { background: #238636; border-color: #238636; color: #fff; }
    .btn-primary:hover { background: #2ea043; }
    .btn-danger { background: var(--bg3); border-color: var(--border); color: var(--red); }
    .btn-danger:hover { background: #3a1a1a; }
    .btn-ghost { background: transparent; border-color: transparent; color: var(--text2); }
    .btn-ghost:hover { color: var(--text); background: var(--bg3); }
    .btn-secondary { background: var(--bg3); color: var(--text); }
    .btn-secondary:hover { background: var(--border); }
    .btn-sm { padding: 4px 10px; font-size: 12px; }
    .btn-back { background: transparent; border: none; color: var(--text2); cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; gap: 4px; padding: 4px 0; margin-bottom: 12px; }
    .btn-back:hover { color: var(--blue); }

    /* ── Cards ── */
    .card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    .card-header { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
    .card-header h3 { font-size: 14px; color: var(--text); }
    .card-body { padding: 18px; }

    /* ── Stats ── */
    .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .stat-card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
    .stat-card .label { font-size: 12px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
    .stat-card .value { font-size: 28px; font-weight: 700; color: var(--text); }
    .stat-card .sub { font-size: 12px; color: var(--text3); margin-top: 4px; }

    /* ── Tables ── */
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 10px 14px; color: var(--text2); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
    td { padding: 10px 14px; border-bottom: 1px solid var(--border); color: var(--text); }
    tr:hover td { background: rgba(88,166,255,0.03); }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: rgba(88,166,255,0.06); }

    /* ── Badges ── */
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
    .badge-green { background: #1a3a2a; color: var(--green); }
    .badge-yellow { background: #2a2a1a; color: var(--yellow); }
    .badge-red { background: #3a1a1a; color: var(--red); }
    .badge-blue { background: #1a2a3a; color: var(--blue); }
    .badge-purple { background: #2a1a3a; color: var(--purple); }
    .badge-gray { background: var(--bg3); color: var(--text2); }

    /* ── Forms ── */
    .form-group { margin-bottom: 14px; }
    .form-group label { display: block; font-size: 12px; color: var(--text2); margin-bottom: 4px; }
    .form-input { width: 100%; background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 8px 12px; font-size: 14px; font-family: inherit; }
    .form-input:focus { border-color: var(--blue); outline: none; }
    select.form-input { cursor: pointer; }
    textarea.form-input { min-height: 80px; resize: vertical; }
    .form-row { display: flex; gap: 12px; }
    .form-row .form-group { flex: 1; }

    /* ── Modal ── */
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 200; display: none; align-items: center; justify-content: center; }
    .modal-overlay.active { display: flex; }
    .modal { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; width: 480px; max-width: 90vw; max-height: 85vh; overflow-y: auto; }
    .modal-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
    .modal-header h3 { font-size: 16px; }
    .modal-close { background: none; border: none; color: var(--text2); font-size: 20px; cursor: pointer; padding: 2px 6px; }
    .modal-close:hover { color: var(--red); }
    .modal-body { padding: 20px; }
    .modal-footer { padding: 14px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }

    /* ── Task Board ── */
    .board { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
    .board-col { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); min-height: 200px; }
    .board-col-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
    .board-col-header h4 { font-size: 13px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; }
    .board-col-count { font-size: 12px; color: var(--text3); }
    .board-col-body { padding: 8px; }
    .task-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 8px; cursor: pointer; transition: border-color 0.15s; }
    .task-card:hover { border-color: var(--blue); }
    .task-card .title { font-size: 13px; color: var(--text); margin-bottom: 6px; }
    .task-card .meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text3); }

    /* ── Comments ── */
    .comment { padding: 12px 0; border-bottom: 1px solid var(--border); }
    .comment:last-child { border: none; }
    .comment-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
    .comment-author { font-size: 13px; font-weight: 600; color: var(--blue); }
    .comment-time { font-size: 11px; color: var(--text3); }
    .comment-body { font-size: 13px; color: var(--text); line-height: 1.5; }

    /* ── Login Screen ── */
    .login-screen { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: var(--bg); }
    .login-card { background: var(--bg2); border: 1px solid var(--border); border-radius: 12px; padding: 40px; width: 400px; max-width: 90vw; }
    .login-card h1 { color: var(--blue); font-size: 24px; margin-bottom: 4px; }
    .login-card .sub { color: var(--text2); font-size: 13px; margin-bottom: 24px; }
    .login-error { background: #3a1a1a; border: 1px solid #f8514950; color: var(--red); padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 12px; display: none; }
    .demo-creds { background: var(--bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 16px; }
    .demo-creds h4 { font-size: 12px; color: var(--text2); margin-bottom: 6px; }
    .demo-cred { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; cursor: pointer; color: var(--text); }
    .demo-cred:hover { color: var(--blue); }
    .demo-cred .cred-role { color: var(--purple); font-size: 11px; margin-left: auto; }

    /* ── Notifications ── */
    .notif-list { max-height: 400px; overflow-y: auto; }
    .notif-item { padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 13px; }
    .notif-item:last-child { border: none; }

    /* ── Empty state ── */
    .empty { text-align: center; padding: 40px 20px; color: var(--text3); }
    .empty-icon { font-size: 40px; margin-bottom: 8px; }
    .empty-text { font-size: 14px; }

    /* ── Toast ── */
    .toast-container { position: fixed; top: 16px; right: 16px; z-index: 1000; display: flex; flex-direction: column; gap: 8px; }
    .toast { background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; font-size: 13px; box-shadow: 0 8px 24px rgba(0,0,0,0.4); animation: toastIn 0.3s ease; min-width: 250px; }
    .toast.success { border-color: var(--green); }
    .toast.error { border-color: var(--red); }
    @keyframes toastIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }

    /* ── Playground ── */
    .pg-wrap { display: flex; gap: 16px; height: calc(100vh - 140px); min-height: 400px; }
    .pg-editor-pane { flex: 1; display: flex; flex-direction: column; }
    .pg-output-pane { flex: 1; display: flex; flex-direction: column; }
    .pg-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
    .pg-toolbar select { background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 6px; padding: 6px 10px; font-size: 13px; cursor: pointer; }
    .pg-toolbar select:focus { border-color: var(--blue); outline: none; }
    .pg-run-btn { background: #238636; border: 1px solid #238636; color: #fff; border-radius: 6px; padding: 6px 16px; font-size: 13px; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
    .pg-run-btn:hover { background: #2ea043; }
    .pg-run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .pg-editor { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); color: #e6edf3; font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6; padding: 14px; resize: none; tab-size: 4; white-space: pre; overflow: auto; }
    .pg-editor:focus { border-color: var(--blue); outline: none; }
    .pg-output-label { font-size: 12px; color: var(--text2); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
    .pg-output { flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius); font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6; padding: 14px; overflow: auto; white-space: pre-wrap; color: var(--text2); }
    .pg-output .ok { color: var(--green); }
    .pg-output .err { color: var(--red); }
    .pg-spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid #ffffff40; border-top-color: #fff; border-radius: 50%; animation: spin 0.6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @media (max-width: 900px) { .pg-wrap { flex-direction: column; height: auto; } .pg-editor { min-height: 250px; } .pg-output { min-height: 200px; } }

    /* ── Utilities ── */
    .hidden { display: none !important; }
    .flex-between { display: flex; align-items: center; justify-content: space-between; }
    .mb-16 { margin-bottom: 16px; }
    .mb-24 { margin-bottom: 24px; }
    .text-muted { color: var(--text2); }
    .text-sm { font-size: 12px; }
    .loading { color: var(--text3); font-size: 13px; padding: 20px; text-align: center; }

    @media (max-width: 768px) {
      .sidebar { width: 60px; }
      .sidebar .nav-item span, .sidebar .nav-section-title, .sidebar .sidebar-brand span,
      .sidebar .user-info, .sidebar-brand h1 { display: none; }
      .sidebar-brand { padding: 16px 12px; text-align: center; }
      .nav-item { justify-content: center; padding: 10px; }
      .nav-icon { width: auto; }
      .main { margin-left: 60px; }
      .board { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>

  <!-- ═══ Login Screen ═══ -->
  <div id="login-screen" class="login-screen">
    <div class="login-card">
      <h1>TaskFlow</h1>
      <p class="sub">Sign in to your project management workspace</p>

      <div id="login-error" class="login-error"></div>

      <div class="demo-creds">
        <h4>Demo accounts (click to fill)</h4>
        <div class="demo-cred" onclick="fillLogin('admin','admin123')">
          <span>admin / admin123</span>
          <span class="cred-role">admin</span>
        </div>
        <div class="demo-cred" onclick="fillLogin('alice','alice123')">
          <span>alice / alice123</span>
          <span class="cred-role">member</span>
        </div>
        <div class="demo-cred" onclick="fillLogin('bob','bob123')">
          <span>bob / bob123</span>
          <span class="cred-role">member</span>
        </div>
      </div>

      <div class="form-group">
        <label>Username</label>
        <input type="text" id="login-user" class="form-input" placeholder="Enter username">
      </div>
      <div class="form-group">
        <label>Password</label>
        <input type="password" id="login-pass" class="form-input" placeholder="Enter password">
      </div>
      <button class="btn btn-primary" style="width:100%;justify-content:center;margin-top:8px;" onclick="doLogin()">Sign In</button>
      <p style="text-align:center;margin-top:16px;">
        <a href="/" style="color:var(--text2);font-size:13px;text-decoration:none;">&larr; Back to API overview</a>
      </p>
    </div>
  </div>

  <!-- ═══ App Shell ═══ -->
  <div id="app" class="app hidden">

    <!-- Sidebar -->
    <div class="sidebar">
      <div class="sidebar-brand">
        <h1>TaskFlow</h1>
        <span>Powered by Lcore</span>
      </div>
      <div class="sidebar-nav">
        <div class="nav-section">
          <div class="nav-section-title">Main</div>
          <div class="nav-item active" onclick="navigate('dashboard')" data-nav="dashboard">
            <span class="nav-icon">&#9632;</span><span>Dashboard</span>
          </div>
          <div class="nav-item" onclick="navigate('projects')" data-nav="projects">
            <span class="nav-icon">&#9776;</span><span>Projects</span><span class="nav-badge" id="project-count">-</span>
          </div>
          <div class="nav-item" onclick="navigate('team')" data-nav="team">
            <span class="nav-icon">&#9679;</span><span>Team</span><span class="nav-badge" id="team-count">-</span>
          </div>
          <div class="nav-item" onclick="navigate('notifications')" data-nav="notifications">
            <span class="nav-icon">&#9993;</span><span>Notifications</span>
          </div>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">Account</div>
          <div class="nav-item" onclick="navigate('profile')" data-nav="profile">
            <span class="nav-icon">&#9787;</span><span>My Profile</span>
          </div>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">Tools</div>
          <div class="nav-item" onclick="navigate('playground')" data-nav="playground">
            <span class="nav-icon">&#9654;</span><span>Playground</span>
          </div>
        </div>
        <div class="nav-section">
          <div class="nav-section-title">Links</div>
          <div class="nav-item" onclick="window.location.href='/'">
            <span class="nav-icon">&#8617;</span><span>API Overview</span>
          </div>
          <div class="nav-item" onclick="window.open('/docs','_blank')">
            <span class="nav-icon">&#9998;</span><span>API Docs</span>
          </div>
        </div>
      </div>
      <div class="sidebar-footer">
        <div class="sidebar-user">
          <div class="avatar" id="user-avatar" style="cursor:pointer;" onclick="navigate('profile')" title="View profile">?</div>
          <div class="user-info" style="cursor:pointer;" onclick="navigate('profile')" title="View profile">
            <div class="name" id="user-name">-</div>
            <div class="role" id="user-role">-</div>
          </div>
          <button class="btn-ghost btn-sm" onclick="doLogout()" title="Logout" style="margin-left:auto;font-size:16px;padding:4px;">&#10005;</button>
        </div>
      </div>
    </div>

    <!-- Main Content -->
    <div class="main">
      <div class="topbar">
        <div class="topbar-title" id="page-title">Dashboard</div>
        <div class="topbar-actions" id="topbar-actions"></div>
      </div>
      <div class="content" id="page-content"></div>
    </div>
  </div>

  <!-- ═══ Modal ═══ -->
  <div id="modal-overlay" class="modal-overlay" onclick="if(event.target===this)closeModal()">
    <div class="modal">
      <div class="modal-header">
        <h3 id="modal-title">Modal</h3>
        <button class="modal-close" onclick="closeModal()">&times;</button>
      </div>
      <div class="modal-body" id="modal-body"></div>
      <div class="modal-footer" id="modal-footer"></div>
    </div>
  </div>

  <!-- ═══ Toast Container ═══ -->
  <div class="toast-container" id="toast-container"></div>

<script>
// ═══════════════════════════════════════════════════════════
//  STATE
// ═══════════════════════════════════════════════════════════
var state = {
  token: localStorage.getItem('tf_token') || '',
  user: JSON.parse(localStorage.getItem('tf_user') || 'null'),
  currentPage: 'dashboard',
  currentProject: null,
  currentTask: null,
};

var API = window.location.origin;

// ═══════════════════════════════════════════════════════════
//  API HELPERS
// ═══════════════════════════════════════════════════════════
function api(method, path, body) {
  var headers = { 'Accept': 'application/json' };
  if (state.token) headers['Authorization'] = 'Bearer ' + state.token;
  var opts = { method: method, headers: headers };
  if (body && method !== 'GET') {
    headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  return fetch(API + path, opts).then(function(res) {
    return res.json().then(function(data) {
      data._status = res.status;
      return data;
    });
  });
}

function toast(msg, type) {
  var el = document.createElement('div');
  el.className = 'toast ' + (type || '');
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(function() { el.remove(); }, 3500);
}

function formatDate(ts) {
  if (!ts) return '-';
  if (typeof ts === 'number') return new Date(ts * 1000).toLocaleDateString();
  return ts;
}

// ═══════════════════════════════════════════════════════════
//  AUTH
// ═══════════════════════════════════════════════════════════
function fillLogin(u, p) {
  document.getElementById('login-user').value = u;
  document.getElementById('login-pass').value = p;
}

function doLogin() {
  var u = document.getElementById('login-user').value.trim();
  var p = document.getElementById('login-pass').value.trim();
  if (!u || !p) return;
  var errEl = document.getElementById('login-error');
  errEl.style.display = 'none';

  api('POST', '/auth/login', { username: u, password: p }).then(function(data) {
    if (data.token) {
      state.token = data.token;
      state.user = data.user;
      localStorage.setItem('tf_token', data.token);
      localStorage.setItem('tf_user', JSON.stringify(data.user));
      showApp();
    } else {
      errEl.textContent = data.error || 'Login failed';
      errEl.style.display = 'block';
    }
  }).catch(function() {
    errEl.textContent = 'Connection error';
    errEl.style.display = 'block';
  });
}

function doLogout() {
  state.token = '';
  state.user = null;
  localStorage.removeItem('tf_token');
  localStorage.removeItem('tf_user');
  document.getElementById('app').classList.add('hidden');
  document.getElementById('login-screen').classList.remove('hidden');
}

function showApp() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  document.getElementById('user-name').textContent = state.user.username;
  document.getElementById('user-role').textContent = state.user.role;
  document.getElementById('user-avatar').textContent = state.user.username[0].toUpperCase();
  navigateFromHash();
}

// ═══════════════════════════════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════════════════════════════
function navigate(page, data) {
  state.currentPage = page;
  document.querySelectorAll('.nav-item').forEach(function(el) { el.classList.remove('active'); });
  var navEl = document.querySelector('[data-nav="' + page + '"]');
  if (navEl) navEl.classList.add('active');

  // Update URL hash for refresh persistence
  var hash = page;
  if (data && page === 'project-detail') hash = 'project/' + data;
  else if (data && page === 'task-detail') hash = 'task/' + data.projectId + '/' + data.taskId;
  window.location.hash = hash;

  var title = page.charAt(0).toUpperCase() + page.slice(1);
  document.getElementById('topbar-actions').innerHTML = '';

  if (page === 'dashboard') renderDashboard();
  else if (page === 'projects') renderProjects();
  else if (page === 'project-detail') renderProjectDetail(data);
  else if (page === 'task-detail') renderTaskDetail(data.projectId, data.taskId);
  else if (page === 'team') renderTeam();
  else if (page === 'notifications') renderNotifications();
  else if (page === 'profile') renderProfile();
  else if (page === 'playground') renderPlayground();

  document.getElementById('page-title').textContent = title === 'Project-detail' ? 'Project' : title === 'Task-detail' ? 'Task' : title === 'Profile' ? 'My Profile' : title === 'Playground' ? 'Code Playground' : title;
}

function navigateFromHash() {
  var hash = window.location.hash.replace('#', '');
  if (!hash) return navigate('dashboard');
  if (hash.indexOf('project/') === 0) {
    var pid = parseInt(hash.split('/')[1]);
    if (pid) return navigate('project-detail', pid);
  }
  if (hash.indexOf('task/') === 0) {
    var parts = hash.split('/');
    var projId = parseInt(parts[1]);
    var taskId = parseInt(parts[2]);
    if (projId && taskId) return navigate('task-detail', { projectId: projId, taskId: taskId });
  }
  var pages = ['dashboard', 'projects', 'team', 'notifications', 'profile', 'playground'];
  if (pages.indexOf(hash) !== -1) return navigate(hash);
  navigate('dashboard');
}

// ═══════════════════════════════════════════════════════════
//  DASHBOARD
// ═══════════════════════════════════════════════════════════
function renderDashboard() {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading dashboard...</div>';

  Promise.all([
    api('GET', '/api/projects/dashboard/overview'),
    api('GET', '/api/projects/dashboard/activity'),
    api('GET', '/health')
  ]).then(function(results) {
    var overview = results[0];
    var activity = results[1];
    var health = results[2];

    var totals = overview.totals || {};

    var html = '<div class="stats-grid">';
    html += statCard('Projects', totals.projects || 0, 'Active workspaces');
    html += statCard('Tasks', totals.tasks || 0, 'Across all projects');
    html += statCard('Team Members', totals.users || 0, 'Registered users');
    html += statCard('Overdue', totals.overdue || 0, 'Need attention');
    html += '</div>';

    // Quick actions
    html += '<div class="card mb-24" style="border-color:var(--blue);border-style:dashed;cursor:pointer;" onclick="navigate(\'playground\')">';
    html += '<div class="card-body" style="display:flex;align-items:center;gap:14px;padding:16px 20px;">';
    html += '<span style="font-size:28px;">&#9654;</span>';
    html += '<div><div style="font-size:14px;font-weight:600;color:var(--blue);">Code Playground</div>';
    html += '<div style="font-size:12px;color:var(--text2);">Write and run Lcore code directly in the browser — try routing, middleware, password hashing, and more</div></div>';
    html += '</div></div>';

    // Projects overview
    html += '<div class="card mb-24"><div class="card-header"><h3>Projects</h3></div><div class="card-body"><div class="table-wrap"><table>';
    html += '<tr><th>Project</th><th>Status</th><th>Tasks</th><th>Done</th></tr>';
    (overview.projects || []).forEach(function(p) {
      var pct = p.task_count > 0 ? Math.round((p.done_count / p.task_count) * 100) : 0;
      html += '<tr class="clickable" onclick="navigate(\'project-detail\',' + p.id + ')"><td>' + esc(p.name) + '</td><td>' + statusBadge(p.status) + '</td><td>' + p.task_count + '</td><td>' + pct + '%</td></tr>';
    });
    html += '</table></div></div></div>';

    // Recent activity
    html += '<div class="card"><div class="card-header"><h3>Recent Activity</h3></div><div class="card-body">';
    if (activity.recent_tasks && activity.recent_tasks.length > 0) {
      html += '<div class="table-wrap"><table><tr><th>Task</th><th>Project</th><th>Status</th><th>Priority</th><th>Assignee</th></tr>';
      activity.recent_tasks.slice(0, 10).forEach(function(t) {
        html += '<tr><td>' + esc(t.title) + '</td><td>' + esc(t.project_name) + '</td><td>' + statusBadge(t.status) + '</td><td>' + priorityBadge(t.priority) + '</td><td>' + esc(t.assignee || '-') + '</td></tr>';
      });
      html += '</table></div>';
    } else {
      html += '<div class="empty"><div class="empty-text">No recent activity</div></div>';
    }
    html += '</div></div>';

    content.innerHTML = html;
    document.getElementById('project-count').textContent = totals.projects || 0;
    document.getElementById('team-count').textContent = totals.users || 0;
  });
}

function statCard(label, value, sub) {
  return '<div class="stat-card"><div class="label">' + label + '</div><div class="value">' + value + '</div><div class="sub">' + sub + '</div></div>';
}

// ═══════════════════════════════════════════════════════════
//  PROJECTS
// ═══════════════════════════════════════════════════════════
function renderProjects() {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading projects...</div>';
  document.getElementById('topbar-actions').innerHTML = isAdmin() ? '<button class="btn btn-primary" onclick="openNewProjectModal()">+ New Project</button>' : '';

  api('GET', '/api/projects/').then(function(data) {
    var html = '<div class="card"><div class="card-body"><div class="table-wrap"><table>';
    html += '<tr><th>Name</th><th>Owner</th><th>Status</th><th>Created</th>' + (isAdmin() ? '<th></th>' : '') + '</tr>';
    (data.projects || []).forEach(function(p) {
      html += '<tr class="clickable" onclick="navigate(\'project-detail\',' + p.id + ')">';
      html += '<td><strong>' + esc(p.name) + '</strong><br><span class="text-muted text-sm">' + esc(p.description || '') + '</span></td>';
      html += '<td>' + esc(p.owner_name) + '</td>';
      html += '<td>' + statusBadge(p.status) + '</td>';
      html += '<td class="text-sm text-muted">' + formatDate(p.created_at) + '</td>';
      if (isAdmin()) html += '<td><button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteProject(' + p.id + ',\'' + esc(p.name) + '\')">Delete</button></td>';
      html += '</tr>';
    });
    if (!data.projects || data.projects.length === 0) {
      html += '<tr><td colspan="' + (isAdmin() ? 5 : 4) + '" class="empty">No projects yet.' + (isAdmin() ? ' Create one!' : '') + '</td></tr>';
    }
    html += '</table></div></div></div>';
    content.innerHTML = html;
  });
}

function openNewProjectModal() {
  openModal('New Project',
    '<div class="form-group"><label>Project Name</label><input class="form-input" id="m-proj-name" placeholder="e.g. Website Redesign"></div>' +
    '<div class="form-group"><label>Description</label><textarea class="form-input" id="m-proj-desc" placeholder="What is this project about?"></textarea></div>',
    '<button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="createProject()">Create Project</button>'
  );
}

function createProject() {
  var name = document.getElementById('m-proj-name').value.trim();
  var desc = document.getElementById('m-proj-desc').value.trim();
  if (!name) return toast('Project name is required', 'error');
  api('POST', '/api/projects/', { name: name, description: desc, owner_id: state.user.id }).then(function(data) {
    if (data.created) { toast('Project created!', 'success'); closeModal(); renderProjects(); }
    else toast(data.error || 'Failed', 'error');
  });
}

function deleteProject(id, name) {
  if (!confirm('Delete "' + name + '" and all its tasks?')) return;
  api('DELETE', '/api/projects/' + id).then(function(data) {
    if (data.deleted) { toast('Project deleted', 'success'); renderProjects(); }
    else toast(data.error || 'Failed', 'error');
  });
}

// ═══════════════════════════════════════════════════════════
//  PROJECT DETAIL (Task Board)
// ═══════════════════════════════════════════════════════════
function renderProjectDetail(projectId) {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading project...</div>';
  state.currentProject = projectId;

  document.getElementById('topbar-actions').innerHTML = '<button class="btn btn-primary" onclick="openNewTaskModal(' + projectId + ')">+ New Task</button>';

  Promise.all([
    api('GET', '/api/projects/' + projectId),
    api('GET', '/api/projects/' + projectId + '/tasks')
  ]).then(function(results) {
    var project = results[0];
    var taskData = results[1];

    var html = '<button class="btn-back" onclick="navigate(\'projects\')">&larr; Back to Projects</button>';
    html += '<div class="flex-between mb-16"><div><h2 style="font-size:20px;margin-bottom:4px;">' + esc(project.name) + '</h2><p class="text-muted text-sm">' + esc(project.description || '') + '</p></div><div>' + statusBadge(project.status) + '</div></div>';

    var stats = project.task_stats || {};
    html += '<div class="stats-grid" style="grid-template-columns: repeat(4,1fr);">';
    html += statCard('Total', stats.total || 0, 'Tasks');
    html += statCard('To Do', stats.todo || 0, 'Pending');
    html += statCard('In Progress', stats.in_progress || 0, 'Active');
    html += statCard('Done', stats.done || 0, 'Completed');
    html += '</div>';

    // Task board
    var tasks = taskData.tasks || [];
    var todo = tasks.filter(function(t) { return t.status === 'todo'; });
    var inprog = tasks.filter(function(t) { return t.status === 'in_progress'; });
    var done = tasks.filter(function(t) { return t.status === 'done'; });

    html += '<div class="board">';
    html += boardColumn('To Do', todo, projectId);
    html += boardColumn('In Progress', inprog, projectId);
    html += boardColumn('Done', done, projectId);
    html += '</div>';

    content.innerHTML = html;
    document.getElementById('page-title').textContent = project.name;
  });
}

function boardColumn(title, tasks, projectId) {
  var html = '<div class="board-col"><div class="board-col-header"><h4>' + title + '</h4><span class="board-col-count">' + tasks.length + '</span></div><div class="board-col-body">';
  if (tasks.length === 0) {
    html += '<div class="empty" style="padding:20px;"><div class="empty-text text-sm">No tasks</div></div>';
  }
  tasks.forEach(function(t) {
    html += '<div class="task-card" onclick="navigate(\'task-detail\',{projectId:' + projectId + ',taskId:' + t.id + '})">';
    html += '<div class="title">' + esc(t.title) + '</div>';
    html += '<div class="meta">' + priorityBadge(t.priority) + '<span>' + esc(t.assignee_name || 'Unassigned') + '</span>';
    if (t.due_date) html += '<span>' + t.due_date + '</span>';
    html += '</div></div>';
  });
  html += '</div></div>';
  return html;
}

function openNewTaskModal(projectId) {
  api('GET', '/api/users/').then(function(data) {
    var userOpts = '<option value="">Unassigned</option>';
    (data.users || []).forEach(function(u) {
      userOpts += '<option value="' + u.id + '">' + esc(u.username) + '</option>';
    });

    openModal('New Task',
      '<div class="form-group"><label>Title</label><input class="form-input" id="m-task-title" placeholder="e.g. Design homepage"></div>' +
      '<div class="form-group"><label>Description</label><textarea class="form-input" id="m-task-desc" placeholder="Task details..."></textarea></div>' +
      '<div class="form-row"><div class="form-group"><label>Priority</label><select class="form-input" id="m-task-priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></div>' +
      '<div class="form-group"><label>Assignee</label><select class="form-input" id="m-task-assignee">' + userOpts + '</select></div></div>' +
      '<div class="form-group"><label>Due Date</label><input type="date" class="form-input" id="m-task-due"></div>',
      '<button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="createTask(' + projectId + ')">Create Task</button>'
    );
  });
}

function createTask(projectId) {
  var title = document.getElementById('m-task-title').value.trim();
  if (!title) return toast('Title is required', 'error');
  var body = {
    title: title,
    description: document.getElementById('m-task-desc').value.trim(),
    priority: document.getElementById('m-task-priority').value,
    creator_id: state.user.id,
    status: 'todo'
  };
  var assignee = document.getElementById('m-task-assignee').value;
  if (assignee) body.assignee_id = parseInt(assignee);
  var due = document.getElementById('m-task-due').value;
  if (due) body.due_date = due;

  api('POST', '/api/projects/' + projectId + '/tasks', body).then(function(data) {
    if (data.created) { toast('Task created!', 'success'); closeModal(); renderProjectDetail(projectId); }
    else toast(data.error || 'Failed', 'error');
  });
}

// ═══════════════════════════════════════════════════════════
//  TASK DETAIL
// ═══════════════════════════════════════════════════════════
function renderTaskDetail(projectId, taskId) {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading task...</div>';

  api('GET', '/api/projects/' + projectId + '/tasks/' + taskId).then(function(task) {
    var html = '<button class="btn-back" onclick="navigate(\'project-detail\',' + projectId + ')">&larr; Back to Project</button>';

    html += '<div class="card mb-24"><div class="card-header"><h3>' + esc(task.title) + '</h3><div style="display:flex;gap:8px">' + statusBadge(task.status) + priorityBadge(task.priority) + '</div></div><div class="card-body">';
    html += '<p style="margin-bottom:16px;">' + esc(task.description || 'No description') + '</p>';
    html += '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;font-size:13px;">';
    html += '<div><span class="text-muted">Assignee:</span> ' + esc(task.assignee_name || 'Unassigned') + '</div>';
    html += '<div><span class="text-muted">Created by:</span> ' + esc(task.creator_name) + '</div>';
    html += '<div><span class="text-muted">Due date:</span> ' + (task.due_date || 'None') + '</div>';
    html += '<div><span class="text-muted">Created:</span> ' + formatDate(task.created_at) + '</div>';
    html += '</div>';

    // Status change buttons
    html += '<div style="margin-top:16px;display:flex;gap:8px;">';
    if (task.status !== 'todo') html += '<button class="btn btn-secondary btn-sm" onclick="updateTaskStatus(' + projectId + ',' + taskId + ',\'todo\')">Move to To Do</button>';
    if (task.status !== 'in_progress') html += '<button class="btn btn-secondary btn-sm" onclick="updateTaskStatus(' + projectId + ',' + taskId + ',\'in_progress\')">Move to In Progress</button>';
    if (task.status !== 'done') html += '<button class="btn btn-primary btn-sm" onclick="updateTaskStatus(' + projectId + ',' + taskId + ',\'done\')">Mark Done</button>';
    if (isAdmin()) html += '<button class="btn btn-danger btn-sm" style="margin-left:auto;" onclick="deleteTask(' + projectId + ',' + taskId + ')">Delete Task</button>';
    html += '</div>';
    html += '</div></div>';

    // Comments
    html += '<div class="card"><div class="card-header"><h3>Comments (' + (task.comments || []).length + ')</h3></div><div class="card-body">';
    if (task.comments && task.comments.length > 0) {
      task.comments.forEach(function(c) {
        html += '<div class="comment"><div class="comment-header"><span class="comment-author">' + esc(c.author) + '</span><span class="comment-time">' + formatDate(c.created_at) + '</span></div><div class="comment-body">' + esc(c.body) + '</div></div>';
      });
    } else {
      html += '<div class="empty" style="padding:12px;"><div class="empty-text text-sm">No comments yet</div></div>';
    }
    html += '<div style="margin-top:16px;display:flex;gap:8px;">';
    html += '<input class="form-input" id="comment-input" placeholder="Write a comment..." style="flex:1;">';
    html += '<button class="btn btn-primary" onclick="addComment(' + projectId + ',' + taskId + ')">Post</button>';
    html += '</div></div></div>';

    content.innerHTML = html;
    document.getElementById('page-title').textContent = task.title;
  });
}

function updateTaskStatus(projectId, taskId, status) {
  api('PATCH', '/api/projects/' + projectId + '/tasks/' + taskId, { status: status }).then(function(data) {
    if (data.updated) { toast('Task updated!', 'success'); renderTaskDetail(projectId, taskId); }
    else toast(data.error || 'Failed', 'error');
  });
}

function deleteTask(projectId, taskId) {
  if (!confirm('Delete this task?')) return;
  api('DELETE', '/api/projects/' + projectId + '/tasks/' + taskId).then(function(data) {
    if (data.deleted) { toast('Task deleted', 'success'); navigate('project-detail', projectId); }
    else toast(data.error || 'Failed', 'error');
  });
}

function addComment(projectId, taskId) {
  var input = document.getElementById('comment-input');
  var body = input.value.trim();
  if (!body) return;
  api('POST', '/api/projects/' + projectId + '/tasks/' + taskId + '/comments', { user_id: state.user.id, body: body }).then(function(data) {
    if (data.created) { toast('Comment posted!', 'success'); renderTaskDetail(projectId, taskId); }
    else toast(data.error || 'Failed', 'error');
  });
}

// ═══════════════════════════════════════════════════════════
//  TEAM
// ═══════════════════════════════════════════════════════════
function renderTeam() {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading team...</div>';
  document.getElementById('topbar-actions').innerHTML = isAdmin() ? '<button class="btn btn-primary" onclick="openNewUserModal()">+ Add Member</button>' : '';

  api('GET', '/api/users/').then(function(data) {
    var html = '<div class="card"><div class="card-body"><div class="table-wrap"><table>';
    html += '<tr><th></th><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Joined</th>' + (isAdmin() ? '<th></th>' : '') + '</tr>';
    (data.users || []).forEach(function(u) {
      html += '<tr>';
      html += '<td><div class="avatar" style="width:28px;height:28px;font-size:11px;">' + u.username[0].toUpperCase() + '</div></td>';
      html += '<td><strong>' + esc(u.username) + '</strong></td>';
      html += '<td class="text-muted">' + esc(u.email) + '</td>';
      html += '<td>' + (u.role === 'admin' ? '<span class="badge badge-purple">admin</span>' : '<span class="badge badge-gray">member</span>') + '</td>';
      html += '<td>' + (u.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-red">Inactive</span>') + '</td>';
      html += '<td class="text-muted text-sm">' + formatDate(u.created_at) + '</td>';
      if (isAdmin()) html += '<td><button class="btn btn-danger btn-sm" onclick="deleteUser(' + u.id + ',\'' + esc(u.username) + '\')">Remove</button></td>';
      html += '</tr>';
    });
    html += '</table></div></div></div>';
    content.innerHTML = html;
  });
}

function openNewUserModal() {
  openModal('Add Team Member',
    '<div class="form-group"><label>Username</label><input class="form-input" id="m-user-name" placeholder="e.g. charlie"></div>' +
    '<div class="form-group"><label>Email</label><input class="form-input" id="m-user-email" placeholder="charlie@example.com"></div>' +
    '<div class="form-group"><label>Password</label><input type="password" class="form-input" id="m-user-pass" placeholder="Set a password"></div>' +
    '<div class="form-group"><label>Role</label><select class="form-input" id="m-user-role"><option value="member">Member</option><option value="admin">Admin</option></select></div>',
    '<button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="createUser()">Add Member</button>'
  );
}

function createUser() {
  var name = document.getElementById('m-user-name').value.trim();
  var email = document.getElementById('m-user-email').value.trim();
  var pass = document.getElementById('m-user-pass').value.trim();
  var role = document.getElementById('m-user-role').value;
  if (!name || !email || !pass) return toast('All fields are required', 'error');
  api('POST', '/api/users/', { username: name, email: email, password: pass, role: role }).then(function(data) {
    if (data.created) { toast('Member added!', 'success'); closeModal(); renderTeam(); }
    else toast(data.error || 'Failed', 'error');
    });
  }

  function deleteUser(id, name) {
    if (!confirm('Remove "' + name + '" from the team?')) return;
    api('DELETE', '/api/users/' + id).then(function(data) {
    if (data.deleted) { toast('Member removed', 'success'); renderTeam(); }
    else toast(data.error || 'Failed', 'error');
    });
  }

  // ═══════════════════════════════════════════════════════════
  //  NOTIFICATIONS
  // ═══════════════════════════════════════════════════════════
  function renderNotifications() {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading notifications...</div>';
  document.getElementById('topbar-actions').innerHTML = '<button class="btn btn-primary" onclick="openSendEmailModal()">Send Email</button>';

  api('GET', '/api/notifications/history').then(function(data) {
    var html = '';
    // Info banner
    html += '<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:10px;">';
    html += '<span style="font-size:18px;">&#9432;</span>';
    html += '<div><span style="font-size:13px;color:var(--text);">Emails are simulated in this playground</span>';
    html += '<span style="font-size:12px;color:var(--text3);display:block;">No real emails are sent. Messages are stored and displayed here for demonstration purposes.</span></div>';
    html += '</div>';

    html += '<div class="card"><div class="card-header"><h3>Email History</h3></div><div class="card-body">';
    if (data.notifications && data.notifications.length > 0) {
      html += '<div class="table-wrap"><table><tr><th>Recipient</th><th>Subject</th><th>Type</th><th>Status</th><th>Sent</th></tr>';
      data.notifications.forEach(function(n) {
        var sBadge = n.status === 'sent' ? 'badge-green' : n.status === 'simulated' || n.status === 'simulated_async' ? 'badge-yellow' : 'badge-red';
        html += '<tr><td>' + esc(n.recipient) + '</td><td>' + esc(n.subject) + '</td><td>' + esc(n.type) + '</td><td><span class="badge ' + sBadge + '">' + esc(n.status) + '</span></td><td class="text-muted text-sm">' + formatDate(n.created_at) + '</td></tr>';
      });
      html += '</table></div>';
    } else {
      html += '<div class="empty"><div class="empty-text">No notifications sent yet. Click "Send Email" to try it out.</div></div>';
    }
    html += '</div></div>';
    content.innerHTML = html;
  });
}

function openSendEmailModal() {
  openModal('Send Email',
    '<div class="form-group"><label>To</label><input class="form-input" id="m-email-to" placeholder="recipient@example.com"></div>' +
    '<div class="form-group"><label>Subject</label><input class="form-input" id="m-email-subj" placeholder="Email subject"></div>' +
    '<div class="form-group"><label>Body</label><textarea class="form-input" id="m-email-body" placeholder="Email content..."></textarea></div>',
    '<button class="btn btn-secondary" onclick="closeModal()">Cancel</button><button class="btn btn-primary" onclick="sendEmail()">Send</button>'
  );
}

function sendEmail() {
  var to = document.getElementById('m-email-to').value.trim();
  var subj = document.getElementById('m-email-subj').value.trim();
  var body = document.getElementById('m-email-body').value.trim();
  if (!to || !subj || !body) return toast('All fields are required', 'error');
  api('POST', '/api/notifications/email', { to: to, subject: subj, body: body }).then(function(data) {
    if (data.status === 'simulated') toast('Email simulated and stored!', 'success');
    else toast('Email ' + (data.status || 'sent') + '!', 'success');
    closeModal();
    renderNotifications();
  });
}

// ═══════════════════════════════════════════════════════════
//  PROFILE
// ═══════════════════════════════════════════════════════════
function renderProfile() {
  var content = document.getElementById('page-content');
  content.innerHTML = '<div class="loading">Loading profile...</div>';
  document.getElementById('topbar-actions').innerHTML = '';

  api('GET', '/api/users/' + state.user.id).then(function(user) {
    var html = '<div style="max-width:600px;">';

    // Profile card
    html += '<div class="card mb-24"><div class="card-body" style="text-align:center;padding:32px;">';
    html += '<div class="avatar" style="width:72px;height:72px;font-size:28px;margin:0 auto 12px;">' + esc(user.username[0]).toUpperCase() + '</div>';
    html += '<h2 style="font-size:20px;margin-bottom:4px;">' + esc(user.username) + '</h2>';
    html += '<p class="text-muted">' + esc(user.email) + '</p>';
    html += '<div style="margin-top:8px;">' + (user.role === 'admin' ? '<span class="badge badge-purple">admin</span>' : '<span class="badge badge-gray">member</span>') + ' ';
    html += (user.is_active ? '<span class="badge badge-green">Active</span>' : '<span class="badge badge-red">Inactive</span>');
    html += '</div>';
    html += '<p class="text-muted text-sm" style="margin-top:8px;">Member since ' + formatDate(user.created_at) + '</p>';
    html += '</div></div>';

    // Edit profile
    html += '<div class="card mb-24"><div class="card-header"><h3>Edit Profile</h3></div><div class="card-body">';
    html += '<div class="form-group"><label>Username</label><input class="form-input" id="prof-username" value="' + esc(user.username) + '"></div>';
    html += '<div class="form-group"><label>Email</label><input class="form-input" id="prof-email" value="' + esc(user.email) + '"></div>';
    html += '<button class="btn btn-primary" onclick="updateProfile()">Save Changes</button>';
    html += '</div></div>';

    // Account info
    html += '<div class="card"><div class="card-header"><h3>Account Info</h3></div><div class="card-body">';
    html += '<div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px;">';
    html += '<span class="text-muted">User ID:</span><span>' + user.id + '</span>';
    html += '<span class="text-muted">Role:</span><span>' + esc(user.role) + '</span>';
    html += '<span class="text-muted">Status:</span><span>' + (user.is_active ? 'Active' : 'Inactive') + '</span>';
    html += '<span class="text-muted">Permissions:</span><span>' + (user.role === 'admin' ? 'Full access — create/edit/delete projects, tasks, and team members' : 'View all, create/edit tasks and comments') + '</span>';
    html += '</div>';
    html += '</div></div>';

    html += '</div>';
    content.innerHTML = html;
  });
}

function updateProfile() {
  var username = document.getElementById('prof-username').value.trim();
  var email = document.getElementById('prof-email').value.trim();
  if (!username || !email) return toast('Username and email are required', 'error');
  api('PUT', '/api/users/' + state.user.id, { username: username, email: email }).then(function(data) {
    if (data.updated) {
      state.user.username = username;
      localStorage.setItem('tf_user', JSON.stringify(state.user));
      document.getElementById('user-name').textContent = username;
      document.getElementById('user-avatar').textContent = username[0].toUpperCase();
      toast('Profile updated!', 'success');
      renderProfile();
    } else {
      toast(data.error || 'Failed to update profile', 'error');
    }
  });
}

// ═══════════════════════════════════════════════════════════
//  PLAYGROUND
// ═══════════════════════════════════════════════════════════
var pgExamples = {
  hello: 'from lcore import Lcore, TestClient\n\napp = Lcore()\n\n@app.route(\'/hello/<name>\')\ndef hello(name):\n    return {\'message\': f\'Hello, {name}!\'}\n\nclient = TestClient(app)\nresp = client.get(\'/hello/World\')\nprint(f"Status: {resp.status_code}")\nprint(f"Body: {resp.json}")',

  'json-api': 'from lcore import Lcore, TestClient\n\napp = Lcore()\nitems = []\n\n@app.get(\'/items\')\ndef list_items():\n    return {\'items\': items}\n\n@app.post(\'/items\')\ndef create_item():\n    from lcore import request\n    data = request.json\n    items.append(data)\n    return {\'created\': data, \'total\': len(items)}\n\nclient = TestClient(app)\nclient.post(\'/items\', json={\'name\': \'Widget\', \'price\': 9.99})\nclient.post(\'/items\', json={\'name\': \'Gadget\', \'price\': 24.99})\n\nresp = client.get(\'/items\')\nprint(f"Status: {resp.status_code}")\nfor item in resp.json[\'items\']:\n    print(f"  - {item[\'name\']}: ${item[\'price\']}")',

  routing: 'from lcore import Lcore, TestClient\n\napp = Lcore()\n\n@app.get(\'/users/<id:int>\')\ndef get_user(id):\n    return {\'id\': id, \'type\': \'integer param\'}\n\n@app.get(\'/files/<filepath:path>\')\ndef get_file(filepath):\n    return {\'path\': filepath, \'type\': \'path param\'}\n\nclient = TestClient(app)\n\nprint("Typed integer param:")\nr = client.get(\'/users/42\')\nprint(f"  {r.json}")\n\nprint("\\nPath param:")\nr = client.get(\'/files/docs/readme.md\')\nprint(f"  {r.json}")\n\nprint("\\n404 on wrong type:")\nr = client.get(\'/users/abc\')\nprint(f"  Status: {r.status_code}")',

  middleware: 'from lcore import Lcore, TestClient, Middleware\n\nclass TimingMiddleware(Middleware):\n    name = \'timing\'\n    order = 1\n\n    def __call__(self, ctx, next_handler):\n        import time\n        start = time.time()\n        result = next_handler(ctx)\n        ms = (time.time() - start) * 1000\n        ctx.response.set_header(\'X-Response-Time\', f\'{ms:.2f}ms\')\n        print(f"  {ctx.request.method} {ctx.request.path} -> {ms:.2f}ms")\n        return result\n\napp = Lcore()\napp.use(TimingMiddleware())\n\n@app.route(\'/fast\')\ndef fast():\n    return {\'speed\': \'fast\'}\n\n@app.route(\'/slow\')\ndef slow():\n    import time; time.sleep(0.01)\n    return {\'speed\': \'slow\'}\n\nclient = TestClient(app)\nprint("Middleware timing:")\nclient.get(\'/fast\')\nclient.get(\'/slow\')\n\nr = client.get(\'/fast\')\nprint(f"\\nX-Response-Time: {r.headers.get(\'X-Response-Time\')}")',

  password: 'from lcore import hash_password, verify_password\n\nhashed = hash_password(\'my_secret_123\')\nprint(f"Hash: {hashed[:50]}...")\nprint(f"Format: pbkdf2:sha256:iterations$salt$hash")\n\nresult = verify_password(\'my_secret_123\', hashed)\nprint(f"\\nCorrect password: {result}")\n\nresult = verify_password(\'wrong_password\', hashed)\nprint(f"Wrong password: {result}")\n\nhash1 = hash_password(\'same\')\nhash2 = hash_password(\'same\')\nprint(f"\\nSame password, different hashes:")\nprint(f"  Hash 1: {hash1[:40]}...")\nprint(f"  Hash 2: {hash2[:40]}...")\nprint(f"  Equal: {hash1 == hash2}")\nprint(f"  Both verify: {verify_password(\'same\', hash1) and verify_password(\'same\', hash2)}")',

  validation: 'from lcore import Lcore, TestClient, validate_request\n\napp = Lcore()\n\n@app.post(\'/register\')\n@validate_request(body={\'username\': str, \'email\': str, \'age\': int})\ndef register():\n    from lcore import request\n    data = request.json\n    return {\'registered\': data[\'username\'], \'age\': data[\'age\']}\n\nclient = TestClient(app)\n\nprint("Valid request:")\nr = client.post(\'/register\', json={\'username\': \'alice\', \'email\': \'a@b.com\', \'age\': 25})\nprint(f"  {r.status_code}: {r.json}")\n\nprint("\\nMissing field:")\nr = client.post(\'/register\', json={\'username\': \'bob\'})\nprint(f"  {r.status_code}: {r.text[:80]}")\n\nprint("\\nWrong type:")\nr = client.post(\'/register\', json={\'username\': \'charlie\', \'email\': \'c@d.com\', \'age\': \'not_int\'})\nprint(f"  {r.status_code}: {r.text[:80]}")',

  hooks: 'from lcore import Lcore, TestClient\n\napp = Lcore()\nlog = []\n\n@app.hook(\'before_request\')\ndef before():\n    log.append(\'before_request fired\')\n\n@app.hook(\'after_request\')\ndef after():\n    log.append(\'after_request fired\')\n\n@app.route(\'/test\')\ndef test_route():\n    log.append(\'handler executed\')\n    return {\'ok\': True}\n\nclient = TestClient(app)\nresp = client.get(\'/test\')\n\nprint("Lifecycle hooks fired in order:")\nfor i, entry in enumerate(log):\n    print(f"  {i+1}. {entry}")\nprint(f"\\nResponse: {resp.json}")'
};

function renderPlayground() {
  var content = document.getElementById('page-content');
  var html = '';

  html += '<div class="pg-wrap">';

  // Editor pane
  html += '<div class="pg-editor-pane">';
  html += '<div class="pg-toolbar">';
  html += '<select id="pg-examples" onchange="pgLoadExample(this.value)">';
  html += '<option value="">Load example...</option>';
  html += '<option value="hello">Hello World</option>';
  html += '<option value="json-api">JSON API (CRUD)</option>';
  html += '<option value="routing">Typed Routing</option>';
  html += '<option value="middleware">Custom Middleware</option>';
  html += '<option value="password">Password Hashing</option>';
  html += '<option value="validation">Request Validation</option>';
  html += '<option value="hooks">Lifecycle Hooks</option>';
  html += '</select>';
  html += '<button class="pg-run-btn" id="pg-run-btn" onclick="pgRun()">&#9654; Run</button>';
  html += '<span style="font-size:11px;color:var(--text3);margin-left:auto;">Ctrl+Enter to run</span>';
  html += '</div>';
  html += '<textarea class="pg-editor" id="pg-editor" spellcheck="false" placeholder="# Write Lcore code here...&#10;from lcore import Lcore, TestClient&#10;&#10;app = Lcore()&#10;..."></textarea>';
  html += '</div>';

  // Output pane
  html += '<div class="pg-output-pane">';
  html += '<div class="pg-output-label">Output</div>';
  html += '<div class="pg-output" id="pg-output">Click "Run" to execute your code.</div>';
  html += '</div>';

  html += '</div>';
  content.innerHTML = html;

  // Tab key support
  var editor = document.getElementById('pg-editor');
  editor.addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      var s = this.selectionStart, end = this.selectionEnd;
      this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
      this.selectionStart = this.selectionEnd = s + 4;
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      pgRun();
    }
  });
}

function pgLoadExample(name) {
  if (name && pgExamples[name]) {
    document.getElementById('pg-editor').value = pgExamples[name];
    document.getElementById('pg-output').innerHTML = 'Click "Run" to execute your code.';
    document.getElementById('pg-examples').value = '';
  }
}

function pgRun() {
  var code = document.getElementById('pg-editor').value;
  var out = document.getElementById('pg-output');
  var btn = document.getElementById('pg-run-btn');

  if (!code.trim()) { out.innerHTML = '<span class="err">No code to run.</span>'; return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="pg-spinner"></span> Running...';
  out.innerHTML = '<span style="color:var(--text3)">Executing...</span>';

  fetch('/playground/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code: code })
  }).then(function(r) { return r.json(); }).then(function(data) {
    var h = '';
    if (data.output) h += '<span class="ok">' + esc(data.output) + '</span>';
    if (data.error) h += (h ? '\n' : '') + '<span class="err">' + esc(data.error) + '</span>';
    if (!h) h = '<span style="color:var(--text3)">(no output)</span>';
    out.innerHTML = h;
  }).catch(function(err) {
    out.innerHTML = '<span class="err">Request failed: ' + esc(err.message) + '</span>';
  }).finally(function() {
    btn.disabled = false;
    btn.innerHTML = '&#9654; Run';
  });
}

// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════
function isAdmin() {
  return state.user && state.user.role === 'admin';
}
function esc(s) {
  if (s === null || s === undefined) return '';
  var d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function statusBadge(s) {
  var map = { active: 'badge-green', todo: 'badge-gray', in_progress: 'badge-blue', done: 'badge-green', archived: 'badge-gray' };
  var label = (s || '').replace(/_/g, ' ');
  return '<span class="badge ' + (map[s] || 'badge-gray') + '">' + label + '</span>';
}

function priorityBadge(p) {
  var map = { high: 'badge-red', medium: 'badge-yellow', low: 'badge-gray' };
  return '<span class="badge ' + (map[p] || 'badge-gray') + '">' + (p || '-') + '</span>';
}

function openModal(title, bodyHtml, footerHtml) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-footer').innerHTML = footerHtml;
  document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

// ═══════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', function() {
  // Enter key on login
  document.getElementById('login-pass').addEventListener('keydown', function(e) { if (e.key === 'Enter') doLogin(); });
  document.getElementById('login-user').addEventListener('keydown', function(e) { if (e.key === 'Enter') document.getElementById('login-pass').focus(); });

  // Hash-based navigation on back/forward
  window.addEventListener('hashchange', function() {
    if (state.token && state.user) navigateFromHash();
  });

  // Check stored token
  if (state.token && state.user) {
    // Verify token is still valid
    api('GET', '/api/users/' + state.user.id).then(function(data) {
      if (data._status === 200) showApp();
      else doLogout();
    }).catch(function() { doLogout(); });
  }
});
</script>
</body>
</html>
