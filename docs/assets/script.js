document.addEventListener('DOMContentLoaded', function () {
  // ── Syntax highlighting ──
  (function loadHLJS() {
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github.min.css';
    link.media = '(prefers-color-scheme: light)';
    document.head.appendChild(link);
    var linkDark = document.createElement('link');
    linkDark.rel = 'stylesheet';
    linkDark.href = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/styles/github-dark.min.css';
    linkDark.media = '(prefers-color-scheme: dark)';
    document.head.appendChild(linkDark);
    var s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.11.1/highlight.min.js';
    s.onload = function () { hljs.highlightAll(); };
    document.head.appendChild(s);
  })();

  // Mobile menu toggle
  var toggle = document.querySelector('.menu-toggle');
  var sidebar = document.querySelector('.sidebar');
  var headerNav = document.querySelector('.header-nav');
  if (toggle) {
    toggle.addEventListener('click', function () {
      if (sidebar) sidebar.classList.toggle('open');
      if (headerNav) headerNav.classList.toggle('open');
    });
    document.addEventListener('click', function (e) {
      if (!toggle.contains(e.target)) {
        if (sidebar && !sidebar.contains(e.target)) sidebar.classList.remove('open');
        if (headerNav && !headerNav.contains(e.target)) headerNav.classList.remove('open');
      }
    });
  }

  // Active nav highlighting
  var page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.header-nav a').forEach(function (a) {
    if (a.getAttribute('href') === page) a.classList.add('active');
  });
  document.querySelectorAll('.sidebar-link').forEach(function (a) {
    var href = a.getAttribute('href');
    if (href === page || (href && page.indexOf(href.split('#')[0]) === 0 && href.indexOf('#') > -1)) {
      a.classList.add('active');
    }
  });

  // API item expand/collapse
  document.querySelectorAll('.api-header').forEach(function (header) {
    header.addEventListener('click', function () {
      var body = this.nextElementSibling;
      if (body && body.classList.contains('api-body')) {
        body.style.display = body.style.display === 'none' ? 'block' : 'none';
      }
    });
  });

  // Copy button
  document.querySelectorAll('pre').forEach(function (block) {
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.addEventListener('click', function () {
      var code = block.querySelector('code');
      var text = code ? code.textContent : block.textContent;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = 'Copied!';
        setTimeout(function () { btn.textContent = 'Copy'; }, 2000);
      });
    });
    block.style.position = 'relative';
    block.appendChild(btn);
  });

  // TOC scroll spy
  var toc = document.querySelector('.toc');
  if (toc) {
    var headings = document.querySelectorAll('.content h2[id], .content h3[id]');
    var tocLinks = document.querySelectorAll('.toc a');
    if (headings.length && tocLinks.length) {
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            tocLinks.forEach(function (l) { l.classList.remove('active'); });
            var active = document.querySelector('.toc a[href="#' + entry.target.id + '"]');
            if (active) active.classList.add('active');
          }
        });
      }, { rootMargin: '-80px 0px -80% 0px' });
      headings.forEach(function (h) { observer.observe(h); });
    }
  }
});
