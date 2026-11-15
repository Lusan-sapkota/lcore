#!/usr/bin/env python3
"""Regenerate the shared header, sidebar, head/script chrome and search index. Usage: python3 docs/build.py [page.html ...]"""
import html, json, re, sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).parent
VERSION = re.search(r"__version__ = '([^']+)'", (DOCS.parent / 'lcore.py').read_text()).group(1)
PAGES = ['index', 'getting-started', 'tutorial', 'routing', 'request-response', 'middleware', 'plugins', 'advanced', 'api-reference']
GROUPS = [('Getting Started', ['getting-started', 'tutorial']), ('Core', ['routing', 'request-response', 'middleware', 'plugins']),
          ('Advanced', ['advanced']), ('Reference', ['api-reference'])]
SITE = 'https://lcore.lusansapkota.com.np'
GH = 'https://github.com/Lusan-sapkota/lcore'
GH_ICON = '<svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>'
SVG = 'width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'

THEME_JS = """<script>(function(){var t;try{t=localStorage.getItem('lcore-theme')}catch(e){}if(t!=='light'&&t!=='dark')t=matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';document.documentElement.dataset.theme=t})()</script>"""

HEADER = f"""<a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="header-inner">
      <div class="header-side">
        <button class="icon-btn menu-toggle" type="button" aria-label="Menu" aria-expanded="false" aria-controls="sidebar"><svg {SVG}><path d="M3 6h18M3 12h18M3 18h18"/></svg></button>
        <a href="index.html" class="logo"><img src="lcore.png" alt="" class="logo-icon" width="30" height="30">Lcore</a>
        <span class="version-badge">v{VERSION}</span>
      </div>
      <button class="search-btn" type="button" aria-label="Search docs"><svg {SVG}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><span>Search</span><kbd>Ctrl K</kbd></button>
      <div class="header-side header-end">
        <nav class="header-nav" aria-label="Primary">
          <a href="getting-started.html">Guide</a>
          <a href="middleware.html">Middleware</a>
          <a href="api-reference.html">API</a>
          <a href="{GH}/blob/main/CHANGELOG.md">Changelog</a>
        </nav>
        <div class="header-right">
          <button class="icon-btn theme-toggle" type="button" aria-label="Toggle light/dark theme"><svg class="moon" {SVG}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg><svg class="sun" {SVG}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
          <a href="{GH}" class="github-link" aria-label="GitHub">{GH_ICON}<span class="gh-label">GitHub</span></a>
        </div>
      </div>
    </div>
  </header>"""


class Headings(HTMLParser):
    """Collects h1/h2/h3 (with ids) and the first paragraph after each, inside <main>."""
    def __init__(self):
        super().__init__()
        self.in_main = False; self.cur = None; self.buf = []; self.items = []; self.para = False; self.pbuf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'main': self.in_main = True
        if not self.in_main: return
        if tag in ('h1', 'h2', 'h3'):
            self.cur = tag; self.buf = []; self.hid = a.get('id', '')
        elif tag == 'p' and self.items and not self.items[-1][4] and not self.para:
            self.para = True; self.pbuf = []

    def handle_endtag(self, tag):
        if tag == 'main': self.in_main = False
        if tag == self.cur:
            self.items.append([tag, self.hid, ' '.join(''.join(self.buf).split()), '', ''])
            self.cur = None
        elif tag == 'p' and self.para:
            self.para = False
            if self.items: self.items[-1][3] = ' '.join(''.join(self.pbuf).split())[:150]; self.items[-1][4] = 'x'

    def handle_data(self, d):
        if self.cur: self.buf.append(d)
        if self.para: self.pbuf.append(d)


def headings(path):
    p = Headings(); p.feed(path.read_text())
    return [(t, i, x, s) for t, i, x, s, _ in p.items]


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def sidebar(info, cur=''):
    out = ['<aside class="sidebar" id="sidebar" aria-label="Documentation">', '      <nav aria-label="Docs">']
    for title, pages in GROUPS:
        out.append(f'      <details class="sidebar-section" open>\n        <summary class="sidebar-title">{title}</summary>')
        for pg in pages:
            h = info[pg]
            on = pg == cur  # active state is baked in so nothing shifts after load
            out.append(f'        <a href="{pg}.html" class="sidebar-link{" active" if on else ""}">{html.escape(h[0])}</a>')
            out.append(f'        <div class="sidebar-subs{" open" if on else ""}" data-page="{pg}.html">')
            out += [f'          <a href="{pg}.html#{i}" class="sidebar-link sub">{html.escape(x)}</a>' for i, x in h[1]]
            out.append('        </div>')
        out.append('      </details>')
    out.append(f'      <details class="sidebar-section" open>\n        <summary class="sidebar-title">Project</summary>\n'
               f'        <a href="{GH}/blob/main/CHANGELOG.md" class="sidebar-link">Changelog</a>\n'
               f'        <a href="{GH}" class="sidebar-link">GitHub</a>\n      </details>')
    out.append('      </nav>\n    </aside>')
    return '\n'.join(out)


def region(src, name, new, fallback=None, where=None):
    """Replace <!--chrome:name-->...<!--/chrome:name-->; on first run swap `fallback` or insert at `where`."""
    block = f'<!--chrome:{name}-->{new}<!--/chrome:{name}-->'
    pat = re.compile(rf'<!--chrome:{name}-->.*?<!--/chrome:{name}-->', re.S)
    if pat.search(src): return pat.sub(lambda m: block, src)
    if fallback and re.search(fallback, src, re.S): return re.sub(fallback, lambda m: block, src, count=1, flags=re.S)
    return src.replace(where, block + where, 1) if where else src


def main():
    info, index = {}, []
    for pg in PAGES:
        src = (DOCS / f'{pg}.html').read_text()
        if pg == 'index':  # give bare h2s an id so search and the sidebar can link to them
            src = re.sub(r'<h2>([^<]+)</h2>', lambda m: f'<h2 id="{slug(m.group(1))}">{m.group(1)}</h2>', src)
            (DOCS / 'index.html').write_text(src)
        hs = headings(DOCS / f'{pg}.html')
        title = next((x for t, i, x, s in hs if t == 'h1'), 'Lcore')
        if pg == 'index': title = 'Overview'
        info[pg] = (title, [(i, x) for t, i, x, s in hs if t == 'h2' and i])
        index.append([f'{pg}.html', title, '', title, next((s for t, i, x, s in hs if t == 'h1'), '')])
        index += [[f'{pg}.html', title, i, x, s] for t, i, x, s in hs if t != 'h1' and i]
    (DOCS / 'assets' / 'search-index.js').write_text('window.LCORE_INDEX=' + json.dumps(index, ensure_ascii=False, separators=(',', ':')) + ';\n')

    for pg in (sys.argv[1:] and [a.removesuffix('.html') for a in sys.argv[1:]] or PAGES):
        f = DOCS / f'{pg}.html'; s = f.read_text()
        s = re.sub(r'\s*<link rel="preconnect" href="https://fonts[^>]*>|\s*<link href="https://fonts[^>]*>|\s*<link rel="stylesheet" href="assets/github(-dark)?\.min\.css"[^>]*>', '', s)
        crumbs = '' if pg == 'index' else '\n  <script type="application/ld+json">' + json.dumps({
            '@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
                {'@type': 'ListItem', 'position': 1, 'name': 'Lcore', 'item': SITE + '/'},
                {'@type': 'ListItem', 'position': 2, 'name': info[pg][0], 'item': f'{SITE}/{pg}.html'}]}) + '</script>'
        s = region(s, 'head', '\n  <meta name="theme-color" content="#23272f">\n  <meta name="color-scheme" content="dark light">\n  ' + THEME_JS + crumbs + '\n  ', where='</head>')
        s = region(s, 'header', HEADER, fallback=r'<header class="site-header">.*?</header>', where='<body')
        s = region(s, 'sidebar', sidebar(info, pg), fallback=r'<aside class="sidebar">.*?</aside>')
        if pg == 'index' and '<!--chrome:sidebar-->' not in s:
            s = s.replace('<main class="content"', f'<!--chrome:sidebar-->{sidebar(info, pg)}<!--/chrome:sidebar-->\n  <main class="content"', 1)
        s = re.sub(r'<main class="content"(?! id)', '<main class="content" id="main"', s)
        s = region(s, 'scripts', '<script src="assets/highlight.min.js"></script>\n  <script src="assets/search-index.js"></script>\n  <script src="assets/site.js"></script>',  # sync: DOMContentLoaded needs these in order
                   fallback=r'<script src="assets/highlight\.min\.js"></script>\s*<script src="assets/script\.js"></script>')
        s = re.sub(r'("version": ")[^"]+', rf'\g<1>{VERSION}', s)
        s = re.sub(r'(<span class="version-badge">v)[^<]+', rf'\g<1>{VERSION}', s)
        f.write_text(s)


if __name__ == '__main__':
    main()
