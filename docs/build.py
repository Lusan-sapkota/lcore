#!/usr/bin/env python3
"""Regenerate the shared header, sidebar, head/script chrome and search index. Usage: python3 docs/build.py [page.html ...]"""
import html, json, re, subprocess, sys
from html.parser import HTMLParser
from pathlib import Path

DOCS = Path(__file__).parent
VERSION = re.search(r"__version__ = '([^']+)'", (DOCS.parent / 'lcore.py').read_text()).group(1)
PAGES = ['index', 'getting-started', 'tutorial', 'routing', 'request-response', 'middleware', 'plugins', 'advanced', 'api-reference', 'changelog']
GROUPS = [('Getting Started', ['getting-started', 'tutorial']), ('Core', ['routing', 'request-response', 'middleware', 'plugins']),
          ('Advanced', ['advanced']), ('Reference', ['api-reference', 'changelog'])]
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
        <a href="index.html" class="logo"><img src="lcore-256.png" alt="" class="logo-icon" width="30" height="30">Lcore</a>
        <span class="version-badge">v{VERSION}</span>
      </div>
      <button class="search-btn" type="button" aria-label="Search docs"><svg {SVG}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><span>Search</span><kbd>Ctrl K</kbd></button>
      <div class="header-side header-end">
        <nav class="header-nav" aria-label="Primary">
          <a href="getting-started.html">Guide</a>
          <a href="middleware.html">Middleware</a>
          <a href="api-reference.html">API</a>
          <a href="changelog.html">Changelog</a>
        </nav>
        <div class="header-right">
          <button class="icon-btn theme-toggle" type="button" aria-label="Toggle light/dark theme"><svg class="moon" {SVG}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg><svg class="sun" {SVG}><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
          <a href="{GH}" class="github-link" aria-label="GitHub">{GH_ICON}<span class="gh-label">GitHub</span></a>
        </div>
      </div>
    </div>
  </header>"""

# Phone drawer only (hidden above 900px): title, close button and the top-nav links
DRAWER_HEAD = f"""<div class="drawer-head"><span class="drawer-title">Menu</span><button class="icon-btn drawer-close" type="button" aria-label="Close menu"><svg {SVG}><path d="M6 6l12 12M18 6L6 18"/></svg></button></div>
      <nav class="drawer-nav" aria-label="Site">
        <a href="getting-started.html">Guide</a>
        <a href="middleware.html">Middleware</a>
        <a href="api-reference.html">API</a>
        <a href="changelog.html">Changelog</a>
      </nav>"""


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
    out = ['<aside class="sidebar" id="sidebar" aria-label="Documentation">', DRAWER_HEAD, '      <nav aria-label="Docs">']
    for title, pages in GROUPS:
        out.append(f'      <details class="sidebar-section" open>\n        <summary class="sidebar-title">{title}</summary>')
        for pg in pages:
            h = info[pg]
            on = pg == cur  # active state is baked in so nothing shifts after load
            link = f'<a href="{pg}.html" class="sidebar-link{" active" if on else ""}">{html.escape(h[0])}</a>'
            if h[1]:  # phone drawer: the chevron button expands the sub-links
                link = (f'<div class="sidebar-row">{link}<button class="sub-toggle" type="button" aria-expanded="false" '
                        f'aria-controls="subs-{pg}" aria-label="Sections of {html.escape(h[0])}"></button></div>')
            out.append('        ' + link)
            out.append(f'        <div class="sidebar-subs{" open" if on else ""}" id="subs-{pg}" data-page="{pg}.html">')
            out += [f'          <a href="{pg}.html#{i}" class="sidebar-link sub">{html.escape(x)}</a>' for i, x in h[1]]
            out.append('        </div>')
        out.append('      </details>')
    out.append(f'      <details class="sidebar-section" open>\n        <summary class="sidebar-title">Project</summary>\n'
                              f'        <a href="{GH}" class="sidebar-link">GitHub</a>\n      </details>')
    out.append('      </nav>\n    </aside>')
    return '\n'.join(out)


def md(text):
    """Tiny markdown subset for CHANGELOG.md: headings, flat lists, one table, paragraphs, bold, code, links."""
    def inline(t):
        t = html.escape(t.replace(' — ', ' - '), quote=False)  # no em dashes on the page
        t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
        t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
        return re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2">\1</a>', t)
    out, lst, tbl, ver = [], False, [], ''
    def close():
        nonlocal lst, tbl
        if lst: out.append('</ul>'); lst = False
        if tbl:
            rows = [[c.strip() for c in r.strip().strip('|').split('|')] for r in tbl if not re.match(r'^\|[-| ]+\|$', r.strip())]
            out.append('<table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in rows[0]) + '</tr></thead><tbody>' +
                       ''.join('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>' for r in rows[1:]) + '</tbody></table>')
            tbl = []
    for line in text.splitlines()[1:]:  # first line is the page h1
        if line.startswith('|'): tbl.append(line); continue
        close()
        if m := re.match(r'^(##|###) (.*)', line):
            plain = re.sub(r'[\[\]`*]', '', m.group(2))
            if m.group(1) == '##':
                ver = slug(plain.split('—')[0].replace('.', '-'))
                out.append(f'<h2 id="v{ver}">{inline(re.sub(r" — (\d{4}-\d\d-\d\d)", r" (\1)", re.sub(r"^\[([^]]+)\]", r"\1", m.group(2))))}</h2>')
            else:
                out.append(f'<h3 id="v{ver}-{slug(plain)}">{inline(m.group(2))}</h3>')
        elif line.startswith('- '):
            if not lst: out.append('<ul>'); lst = True
            out.append(f'<li>{inline(line[2:])}</li>')
        elif line.strip() and line.strip() != '---':
            out.append(f'<p>{inline(line)}</p>')
    close()
    return '\n'.join(out)


def region(src, name, new, fallback=None, where=None):
    """Replace <!--chrome:name-->...<!--/chrome:name-->; on first run swap `fallback` or insert at `where`."""
    block = f'<!--chrome:{name}-->{new}<!--/chrome:{name}-->'
    pat = re.compile(rf'<!--chrome:{name}-->.*?<!--/chrome:{name}-->', re.S)
    if pat.search(src): return pat.sub(lambda m: block, src)
    if fallback and re.search(fallback, src, re.S): return re.sub(fallback, lambda m: block, src, count=1, flags=re.S)
    return src.replace(where, block + where, 1) if where else src


class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.kids = tag, dict(attrs), []


class Tree(HTMLParser):
    VOID = {'br', 'hr', 'img', 'input', 'meta', 'link'}

    def __init__(self):
        super().__init__()
        self.root = Node('root'); self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if self.stack[-1].tag == 'p' and tag in ('p', 'pre', 'ul', 'ol', 'table', 'div', 'h1', 'h2', 'h3', 'h4'):
            self.stack.pop()  # browsers auto-close <p> before block elements
        n = Node(tag, attrs); self.stack[-1].kids.append(n)
        if tag not in self.VOID: self.stack.append(n)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag: del self.stack[i:]; return

    def handle_data(self, d):
        self.stack[-1].kids.append(d)


def _text(n):
    return n if isinstance(n, str) else ''.join(_text(k) for k in n.kids)


def _inline(n):
    if isinstance(n, str): return re.sub(r'\s+', ' ', n)
    t, k = n.tag, ''.join(_inline(x) for x in n.kids)
    if t in ('script', 'style', 'button', 'svg', 'img'): return ''
    if t == 'code': return '`' + _text(n).strip() + '`'
    if t in ('strong', 'b'): return f'**{k.strip()}**' if k.strip() else ''
    if t in ('em', 'i'): return f'*{k.strip()}*' if k.strip() else ''
    if t == 'br': return '  \n'
    if t == 'a' and n.attrs.get('href'):
        href = n.attrs['href']
        if not href.startswith(('http', 'mailto:')): href = SITE + '/' + href.lstrip('/')
        return f'[{k.strip()}]({href})'
    return k


BLOCKS = {'h1', 'h2', 'h3', 'h4', 'p', 'pre', 'ul', 'ol', 'table', 'div', 'section', 'main', 'footer', 'blockquote'}


def _lang(n, src):
    m = re.search(r'language-([\w-]+)', ' '.join(k.attrs.get('class', '') for k in n.kids if not isinstance(k, str)))
    if m: return m.group(1)
    first = src.lstrip().split(None, 1)[0] if src.strip() else ''
    return 'bash' if first in ('pip', 'uv', 'curl', 'python', 'python3', 'gunicorn', 'lcore', 'git', '$') else 'python'


def _blocks(kids):
    """Render children to markdown blocks; runs of inline nodes become one paragraph."""
    out, run = [], []

    def flush():
        s = ''.join(run).strip()
        if s: out.append(s)
        run.clear()
    for n in kids:
        if isinstance(n, str) or n.tag not in BLOCKS: run.append(_inline(n)); continue
        flush(); out.extend(_block(n))
    flush()
    return out


def _block(n):
    t, cls = n.tag, n.attrs.get('class', '')
    if t in ('h1', 'h2', 'h3', 'h4'): return ['#' * int(t[1]) + ' ' + _inline(n).strip()]
    if t == 'p': return [_inline(n).strip()] if _inline(n).strip() else []
    if t == 'pre':
        src = _text(n).strip('\n')
        return [f'```{_lang(n.kids[0] if n.kids and not isinstance(n.kids[0], str) else n, src)}\n{src}\n```']
    if t in ('ul', 'ol'):
        items = []
        for i, li in enumerate(k for k in n.kids if not isinstance(k, str) and k.tag == 'li'):
            mark = f'{i + 1}.' if t == 'ol' else '-'
            head = ''.join(_inline(x) for x in li.kids if isinstance(x, str) or x.tag not in ('ul', 'ol')).strip()
            sub = [l for x in li.kids if not isinstance(x, str) and x.tag in ('ul', 'ol') for l in _block(x)[0].splitlines()]
            items.append(f'{mark} {head}' + ''.join('\n   ' + l for l in sub))
        return ['\n'.join(items)]
    if t == 'table':
        rows = [[re.sub(r'\s+', ' ', _inline(c)).strip().replace('|', '\\|') for c in r.kids if not isinstance(c, str) and c.tag in ('td', 'th')]
                for r in _find(n, 'tr')]
        if not rows: return []
        return ['\n'.join(['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * len(rows[0])] + ['| ' + ' | '.join(r) + ' |' for r in rows[1:]])]
    if 'perf-bars' in cls or 'hero-buttons' in cls or 'pager' in cls or t in ('script', 'style'): return []
    if 'install-term' in cls:
        return ['```bash\n' + '\n'.join(_text(c).strip() for c in _find(n, 'code')) + '\n```']
    if 'info-box' in cls:
        return ['\n'.join('> ' + l if l else '>' for b in _blocks(n.kids) for l in (b + '\n').splitlines())]
    if 'api-item' in cls:
        hdr = next((k for k in n.kids if not isinstance(k, str) and 'api-header' in k.attrs.get('class', '')), None)
        body = next((k for k in n.kids if not isinstance(k, str) and 'api-body' in k.attrs.get('class', '')), None)
        name = ''.join(_text(s) for s in (hdr.kids if hdr else []) if not isinstance(s, str) and 'api-name' in s.attrs.get('class', ''))
        sig = ''.join(_text(s) for s in (hdr.kids if hdr else []) if not isinstance(s, str) and 'api-sig' in s.attrs.get('class', ''))
        return [f'### `{name}{sig}`'] + (_blocks(body.kids) if body else [])
    return _blocks(n.kids)


def _find(n, tag):
    return [x for k in n.kids if not isinstance(k, str) for x in ([k] if k.tag == tag else []) + _find(k, tag)]


def to_markdown(page_html, url):
    tree = Tree(); tree.feed(re.search(r'<main[^>]*>(.*)</main>', page_html, re.S).group(1))
    return f'Source: {url}\n\n' + '\n\n'.join(_blocks(tree.root.kids)) + '\n'


def markdown_files():
    """Write <page>.md next to each page (the Copy page button fetches it) and an llms.txt index."""
    lines = ['# Lcore', '', '> A fast, single-file Python WSGI framework with zero dependencies.', '', '## Docs', '']
    for pg in PAGES:
        page = (DOCS / f'{pg}.html').read_text()
        url = f'{SITE}/{"" if pg == "index" else pg + ".html"}'
        md = (DOCS.parent / 'CHANGELOG.md').read_text() if pg == 'changelog' else to_markdown(page, url)
        (DOCS / f'{pg}.md').write_text(md)
        desc = html.unescape(re.search(r'name="description" content="([^"]*)"', page).group(1))
        title = re.search(r'<title>(.*?)</title>', page, re.S).group(1).replace(' - Lcore Documentation', '')
        lines.append(f'- [{title}]({SITE}/{pg}.md): {desc}')
    (DOCS / 'llms.txt').write_text('\n'.join(lines) + '\n')


def lastmod(pg):
    try:
        return subprocess.check_output(['git', 'log', '-1', '--format=%cs', '--', f'docs/{pg}.html'], cwd=DOCS.parent, text=True).strip() or None
    except Exception:
        return None


def sitemap():
    prio = {'index': '1.0', 'getting-started': '0.9', 'tutorial': '0.9', 'api-reference': '0.8', 'changelog': '0.6'}
    rows = []
    for pg in PAGES:
        loc = SITE + '/' + ('' if pg == 'index' else f'{pg}.html')
        lm = lastmod(pg)
        rows.append(f'  <url>\n    <loc>{loc}</loc>\n' + (f'    <lastmod>{lm}</lastmod>\n' if lm else '') + f'    <priority>{prio.get(pg, "0.7")}</priority>\n  </url>')
    (DOCS / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(rows) + '\n</urlset>\n')


def main():
    (DOCS / 'assets' / 'pyodide' / 'lcore.py').write_bytes((DOCS.parent / 'lcore.py').read_bytes())  # playground runs the real file
    cl = DOCS / 'changelog.html'  # regenerate first so the sidebar and search index see the new headings
    cl.write_text(region(cl.read_text(), 'content', md((DOCS.parent / 'CHANGELOG.md').read_text())))
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
        # social card, icons and robots hints (idempotent rewrites of the static head tags)
        s = re.sub(r'(property="og:image" content=")[^"]*', rf'\g<1>{SITE}/og-image.png', s)
        s = re.sub(r'(name="twitter:image" content=")[^"]*', rf'\g<1>{SITE}/og-image.png', s)
        s = s.replace('<meta name="twitter:card" content="summary">', '<meta name="twitter:card" content="summary_large_image">')
        s = s.replace('<meta name="robots" content="index, follow">', '<meta name="robots" content="index, follow, max-image-preview:large">')
        s = re.sub(r'<link rel="shortcut icon"[^>]*>', '<link rel="icon" type="image/png" sizes="64x64" href="favicon.png">\n  <link rel="apple-touch-icon" href="apple-touch-icon.png">', s)
        desc = re.search(r'name="description" content="([^"]*)"', s).group(1)
        graph = ''
        if pg != 'index':
            graph = '\n  <script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@graph': [
                {'@type': 'BreadcrumbList', 'itemListElement': [
                    {'@type': 'ListItem', 'position': 1, 'name': 'Lcore', 'item': SITE + '/'},
                    {'@type': 'ListItem', 'position': 2, 'name': info[pg][0], 'item': f'{SITE}/{pg}.html'}]},
                {'@type': 'TechArticle', 'headline': info[pg][0], 'description': html.unescape(desc), 'url': f'{SITE}/{pg}.html',
                 'inLanguage': 'en', 'dateModified': lastmod(pg), 'image': SITE + '/og-image.png',
                 'author': {'@type': 'Person', 'name': 'Lusan Sapkota', 'url': 'https://lusansapkota.com.np'},
                 'publisher': {'@type': 'Person', 'name': 'Lusan Sapkota'}}]}) + '</script>'
        alt = f'\n  <link rel="alternate" type="text/markdown" href="{pg}.md">'
        social = ('\n  <meta property="og:image:width" content="1200">\n  <meta property="og:image:height" content="630">'
                  '\n  <meta property="og:image:alt" content="Lcore: fast, single-file Python WSGI framework">'
                  '\n  <meta property="og:locale" content="en_US">\n  <meta name="twitter:image:alt" content="Lcore: fast, single-file Python WSGI framework">')
        s = region(s, 'head', '\n  <meta name="theme-color" content="#23272f">\n  <meta name="color-scheme" content="dark light">' + alt + social + '\n  ' + THEME_JS + graph + '\n  ', where='</head>')
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
    sitemap()
    markdown_files()
