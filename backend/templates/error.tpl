<!DOCTYPE html>
<html>
<head>
  <title>Error {{status_code}}</title>
  <style>
    body { font-family: 'Inter', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 40px; max-width: 500px; text-align: center; }
    h1 { color: #f85149; font-size: 48px; margin: 0 0 8px 0; }
    h2 { color: #c9d1d9; font-weight: 400; margin: 0 0 16px 0; }
    p { color: #8b949e; line-height: 1.6; }
    a { color: #58a6ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .footer { margin-top: 24px; font-size: 12px; color: #484f58; }
  </style>
</head>
<body>
  <div class="card">
    <h1>{{status_code}}</h1>
    <h2>{{status_text}}</h2>
    <p>{{message}}</p>
    <p><a href="/">Back to Home</a></p>
    <div class="footer">Powered by Lcore Framework</div>
  </div>
</body>
</html>
