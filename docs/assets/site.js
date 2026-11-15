// Keep the sidebar scroll position across page loads (runs before first paint)
(function () {
  var sb = document.querySelector('.sidebar');
  if (!sb) return;
  try { sb.scrollTop = +sessionStorage.getItem('lcore-sb') || 0; } catch (e) {}
  addEventListener('pagehide', function () { try { sessionStorage.setItem('lcore-sb', sb.scrollTop); } catch (e) {} });
})();

document.addEventListener('DOMContentLoaded', function () {
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var root = document.documentElement;
  var page = location.pathname.split('/').pop() || 'index.html';
  if (!/\.html$/.test(page)) page += '.html'; // extensionless URLs such as /routing

  if (typeof hljs !== 'undefined') {
    hljs.configure({ languages: ['python', 'bash', 'json', 'http', 'ini', 'xml', 'sql'] });
    hljs.highlightAll();
  }

  // Theme toggle (initial theme is set by the inline head script)
  var themeBtn = $('.theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = root.dataset.theme === 'light' ? 'dark' : 'light';
    root.dataset.theme = next;
    try { localStorage.setItem('lcore-theme', next); } catch (e) {}
  });

  // Slide-over menu: scroll lock, inert page, focus in and back out
  var toggle = $('.menu-toggle'), sidebar = $('.sidebar'), closeBtn = $('.drawer-close'), scrim = null;
  function setMenu(open) {
    if (!sidebar || sidebar.classList.contains('open') === open) return;
    sidebar.classList.toggle('open', open);
    toggle.setAttribute('aria-expanded', open);
    root.classList.toggle('menu-open', open);
    $$('.skip-link, .site-header, main.content, .toc, .site-footer').forEach(function (el) { el.inert = open; });
    if (!scrim) {
      scrim = document.createElement('div');
      scrim.className = 'scrim';
      scrim.addEventListener('click', function () { setMenu(false); });
      document.body.appendChild(scrim);
    }
    scrim.classList.toggle('show', open);
    if (open) closeBtn.focus({ preventScroll: true }); else toggle.focus({ preventScroll: true });
  }
  if (toggle && sidebar) {
    toggle.addEventListener('click', function () { setMenu(true); });
    closeBtn.addEventListener('click', function () { setMenu(false); });
    sidebar.addEventListener('click', function (e) { if (e.target.closest('a')) setMenu(false); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setMenu(false); });
    matchMedia('(min-width: 901px)').addEventListener('change', function (m) { if (m.matches) setMenu(false); });
    // Group titles announce their state; sub-link lists open from the chevron (phone only)
    $$('.sidebar-section').forEach(function (d) {
      var sum = d.firstElementChild;
      sum.setAttribute('aria-expanded', d.open);
      d.addEventListener('toggle', function () { sum.setAttribute('aria-expanded', d.open); });
    });
    $$('.sub-toggle').forEach(function (b) {
      b.addEventListener('click', function () {
        b.setAttribute('aria-expanded', document.getElementById(b.getAttribute('aria-controls')).classList.toggle('show'));
      });
    });
  }

  // Active nav + sidebar
  $$('.header-nav a, .drawer-nav a').forEach(function (a) { if (a.getAttribute('href') === page) a.classList.add('active'); });
  $$('.sidebar-link:not(.sub)').forEach(function (a) { if (a.getAttribute('href') === page) a.classList.add('active'); });
  var subs = $('.sidebar-subs[data-page="' + page + '"]');
  if (subs) subs.classList.add('open');

  // Heading anchors
  var headings = $$('.content h2[id], .content h3[id]');
  headings.forEach(function (h) {
    h.dataset.t = h.textContent;
    var a = document.createElement('a');
    a.className = 'heading-anchor';
    a.href = '#' + h.id;
    a.textContent = '#';
    a.setAttribute('aria-label', 'Link to this section');
    h.appendChild(a);
  });

  // "On this page" outline with scrollspy (doc pages only)
  var layout = $('.doc-layout');
  if (layout && !document.body.classList.contains('index-page') && headings.length > 1) {
    var toc = document.createElement('aside');
    toc.className = 'toc';
    toc.setAttribute('aria-label', 'On this page');
    var t = document.createElement('div');
    t.className = 'toc-title';
    t.textContent = 'On this page';
    toc.appendChild(t);
    headings.forEach(function (h) {
      var a = document.createElement('a');
      a.href = '#' + h.id;
      a.className = h.tagName === 'H3' ? 'l3' : 'l2';
      a.textContent = h.dataset.t;
      toc.appendChild(a);
    });
    layout.appendChild(toc);
  }
  if (headings.length) {
    var links = $$('.toc a, .sidebar-subs.open a');
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        links.forEach(function (l) {
          var on = l.getAttribute('href').split('#')[1] === en.target.id;
          l.classList.toggle('active', on);
          if (on) l.setAttribute('aria-current', 'location');
          else l.removeAttribute('aria-current');
        });
      });
    }, { rootMargin: '-80px 0px -75% 0px' });
    headings.forEach(function (h) { spy.observe(h); });
  }

  // API item expand/collapse (keyboard operable)
  $$('.api-header').forEach(function (h) {
    h.setAttribute('role', 'button');
    h.tabIndex = 0;
    h.setAttribute('aria-expanded', 'false');
    function flip() {
      var body = h.nextElementSibling;
      if (!body || !body.classList.contains('api-body')) return;
      var show = body.style.display !== 'block';
      body.style.display = show ? 'block' : 'none';
      h.setAttribute('aria-expanded', show);
    }
    h.addEventListener('click', flip);
    h.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); } });
  });

  // Code blocks: header with language label and copy button
  $$('pre').forEach(function (pre) {
    var code = pre.querySelector('code');
    var m = code && /language-([\w-]+)/.exec(code.className);
    var wrap = document.createElement('div');
    wrap.className = 'code-block';
    var head = document.createElement('div');
    head.className = 'code-head';
    var lang = document.createElement('span');
    lang.className = 'code-lang';
    lang.textContent = m ? m[1] : 'code';
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.addEventListener('click', function () {
      var text = code ? code.textContent : pre.textContent;
      function done(ok) {
        btn.textContent = ok ? 'Copied!' : 'Press Ctrl+C';
        setTimeout(function () { btn.textContent = 'Copy'; }, 2000);
      }
      try { navigator.clipboard.writeText(text).then(function () { done(true); }, function () { done(false); }); }
      catch (e) { done(false); }
    });
    head.appendChild(lang);
    head.appendChild(btn);
    pre.parentNode.insertBefore(wrap, pre);
    wrap.appendChild(head);
    wrap.appendChild(pre);
  });

  // Runnable code blocks load the playground on demand (tutorial only)
  if ($('pre[data-run]')) {
    var pgScript = document.createElement('script');
    pgScript.src = 'assets/playground.js';
    document.body.appendChild(pgScript);
  }

  // Standalone copy buttons (install commands)
  $$('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      function done(ok) { b.textContent = ok ? 'Copied!' : 'Press Ctrl+C'; setTimeout(function () { b.textContent = 'Copy'; }, 2000); }
      try { navigator.clipboard.writeText(b.dataset.copy).then(function () { done(true); }, function () { done(false); }); } catch (e) { done(false); }
    });
  });

  // Copy page: copies the generated Markdown twin of this page (see docs/build.py)
  var contentEl = $('main.content');
  if (contentEl && !document.body.classList.contains('index-page')) {
    var cp = document.createElement('button');
    cp.type = 'button';
    cp.className = 'copy-page';
    cp.setAttribute('aria-label', 'Copy page as Markdown');
    cp.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg><span>Copy page</span>';
    var label = cp.querySelector('span');
    cp.addEventListener('click', function () {
      function done(t) { label.textContent = t; cp.classList.toggle('done', t === 'Copied!'); setTimeout(function () { label.textContent = 'Copy page'; cp.classList.remove('done'); }, 2000); }
      fetch(page.replace(/\.html$/, '.md')).then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      }).then(function (t) { return navigator.clipboard.writeText(t); })
        .then(function () { done('Copied!'); }, function () { done('Copy failed'); });
    });
    var h1 = $('h1', contentEl);
    if (h1) { // title on the left, button on the right, same row
      var head = document.createElement('div');
      head.className = 'page-head';
      h1.parentNode.insertBefore(head, h1);
      head.appendChild(h1);
      head.appendChild(cp);
    }
  }

  // Previous / next page links
  var pages = $$('.sidebar-link:not(.sub)').filter(function (a) { return /^[a-z-]+\.html$/.test(a.getAttribute('href')); });
  var at = pages.findIndex(function (a) { return a.getAttribute('href') === page; });
  var mainEl = $('main.content');
  if (mainEl && at > -1 && !document.body.classList.contains('index-page')) {
    var pager = document.createElement('nav');
    pager.className = 'pager';
    pager.setAttribute('aria-label', 'Previous and next page');
    [[at - 1, 'Previous'], [at + 1, 'Next']].forEach(function (p) {
      var a = pages[p[0]];
      if (!a) return;
      var el = document.createElement('a');
      el.className = 'pager-' + p[1].toLowerCase();
      el.href = a.getAttribute('href');
      var small = document.createElement('small');
      small.textContent = p[1];
      el.appendChild(small);
      el.appendChild(document.createTextNode(a.textContent));
      pager.appendChild(el);
    });
    if (pager.children.length) mainEl.appendChild(pager);
  }

  // Scrollable tables
  $$('.content table').forEach(function (table) {
    if (table.parentNode.closest('.table-wrap, .comparison-container')) return;
    var wrap = document.createElement('div');
    wrap.className = 'table-wrap';
    table.parentNode.insertBefore(wrap, table);
    wrap.appendChild(table);
  });

  // Search (index built by docs/build.py into search-index.js)
  var btn = $('.search-btn');
  var data = window.LCORE_INDEX || [];
  var isMac = /Mac|iPhone|iPad/.test(navigator.platform);
  var kb = $('.search-btn kbd');
  if (kb && isMac) kb.textContent = '⌘ K';
  var dlg = document.createElement('dialog');
  dlg.className = 'search-dialog';
  dlg.setAttribute('aria-label', 'Search the docs');
  dlg.innerHTML = '<input class="search-input" type="search" placeholder="Search the docs" aria-label="Search" role="combobox" aria-expanded="true" aria-controls="search-list" autocomplete="off" spellcheck="false"><ul class="search-results" id="search-list" role="listbox"></ul>';
  document.body.appendChild(dlg);
  var input = $('.search-input', dlg), list = $('.search-results', dlg), sel = 0, hits = [];

  function esc(s) { return s.replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function mark(s, words) {
    var out = esc(s);
    words.forEach(function (w) {
      out = out.replace(new RegExp('(' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')(?![^<]*>)', 'ig'), '<mark>$1</mark>');
    });
    return out;
  }
  function render() {
    var q = input.value.trim().toLowerCase();
    var words = q.split(/\s+/).filter(Boolean);
    hits = [];
    if (words.length) {
      data.forEach(function (e) {
        var title = e[3].toLowerCase(), snip = e[4].toLowerCase(), score = 0;
        for (var i = 0; i < words.length; i++) {
          var w = words[i];
          if (title.indexOf(w) > -1) score += title === w ? 12 : title.indexOf(w) === 0 ? 8 : 5;
          else if (snip.indexOf(w) > -1 || e[1].toLowerCase().indexOf(w) > -1) score += 1;
          else return;
        }
        if (!e[2]) score += 2;
        hits.push([score, e]);
      });
      hits.sort(function (a, b) { return b[0] - a[0]; });
      hits = hits.slice(0, 30).map(function (h) { return h[1]; });
    } else {
      hits = data.filter(function (e) { return !e[2]; });
    }
    sel = 0;
    // Group by page, in order of best hit
    var order = [];
    hits.forEach(function (e) { if (order.indexOf(e[1]) < 0) order.push(e[1]); });
    hits = [].concat.apply([], order.map(function (t) { return hits.filter(function (e) { return e[1] === t; }); }));
    var last = null;
    list.innerHTML = hits.length ? hits.map(function (e, i) {
      var head = e[1] !== last ? '<li class="sr-group" role="presentation">' + esc(e[1]) + '</li>' : '';
      last = e[1];
      return head + '<li role="presentation"><a role="option" id="sr' + i + '" href="' + e[0] + (e[2] ? '#' + e[2] : '') + '"' + (i ? '' : ' aria-selected="true"') + '>' +
        '<span class="sr-title">' + mark(e[3], words) + '</span>' +
        (e[4] ? '<span class="sr-snip">' + mark(e[4], words) + '</span>' : '') + '</a></li>';
    }).join('') : '<li class="search-empty">No results for “' + esc(input.value) + '”</li>';
    input.setAttribute('aria-activedescendant', hits.length ? 'sr0' : '');
  }
  function pick(i, scroll) {
    var items = $$('a', list);
    if (!items.length) return;
    items[sel].removeAttribute('aria-selected');
    sel = (i + items.length) % items.length;
    items[sel].setAttribute('aria-selected', 'true');
    if (scroll) items[sel].scrollIntoView({ block: 'nearest' });
    input.setAttribute('aria-activedescendant', items[sel].id);
  }
  function move(d) { pick(sel + d, true); }
  // Hover moves the single selection so two rows are never highlighted at once
  list.addEventListener('mousemove', function (e) {
    var a = e.target.closest('a');
    if (a) pick($$('a', list).indexOf(a), false);
  });
  function open() { if (!dlg.open) { dlg.showModal(); input.value = ''; render(); input.focus(); } }
  if (btn) btn.addEventListener('click', open);
  input.addEventListener('input', render);
  input.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Escape') dlg.close();
    else if (e.key === 'Enter' && hits[sel]) {
      var a = $$('a', list)[sel];
      dlg.close();
      location.href = a.getAttribute('href');
    }
  });
  list.addEventListener('click', function () { dlg.close(); });
  dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); dlg.open ? dlg.close() : open(); }
    else if (e.key === '/' && !/input|textarea|select/i.test(document.activeElement.tagName) && !document.activeElement.isContentEditable) { e.preventDefault(); open(); }
  });
});
