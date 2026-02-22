document.addEventListener('DOMContentLoaded', function () {
  // Mobile sidebar toggle
  var toggle = document.querySelector('.menu-toggle');
  var sidebar = document.querySelector('.sidebar');
  if (toggle && sidebar) {
    toggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
    });
    document.addEventListener('click', function (e) {
      if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove('open');
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

  // TOC scroll spy
  if (document.querySelector('.toc')) {
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
      }, { rootMargin: '-80px 0px -60% 0px' });
      headings.forEach(function (h) { observer.observe(h); });
    }
  }

  // Syntax highlighting for Python code blocks
  highlightCode();

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        history.pushState(null, '', this.getAttribute('href'));
      }
    });
  });

  // Copy button for code blocks
  document.querySelectorAll('pre').forEach(function (pre) {
    var btn = document.createElement('button');
    btn.className = 'copy-btn';
    btn.textContent = 'Copy';
    btn.addEventListener('click', function () {
      var code = pre.querySelector('code');
      var text = code ? code.textContent : pre.textContent;
      navigator.clipboard.writeText(text).then(function () {
        btn.textContent = 'Copied!';
        setTimeout(function () { btn.textContent = 'Copy'; }, 2000);
      });
    });
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
});

function highlightCode() {
  document.querySelectorAll('pre code').forEach(function (block) {
    // Get the raw text content (no HTML tags), then work from scratch
    var text = block.textContent;

    // HTML-encode the text first to prevent any injection
    var lines = text.split('\n');
    var highlighted = lines.map(function (line) {
      return highlightLine(line);
    }).join('\n');

    block.innerHTML = highlighted;
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
}

function highlightLine(line) {
  var tokens = [];
  var i = 0;

  while (i < line.length) {
    // Comments (# to end of line, but not inside strings)
    if (line[i] === '#' && !inString(line, i)) {
      tokens.push({ type: 'comment', text: line.slice(i) });
      i = line.length;
      continue;
    }

    // Triple-quoted strings
    if ((line.slice(i, i + 3) === '"""' || line.slice(i, i + 3) === "'''")) {
      var quote = line.slice(i, i + 3);
      var end = line.indexOf(quote, i + 3);
      if (end !== -1) {
        tokens.push({ type: 'string', text: line.slice(i, end + 3) });
        i = end + 3;
      } else {
        tokens.push({ type: 'string', text: line.slice(i) });
        i = line.length;
      }
      continue;
    }

    // Single/double quoted strings
    if (line[i] === '"' || line[i] === "'") {
      var q = line[i];
      var j = i + 1;
      while (j < line.length && line[j] !== q) {
        if (line[j] === '\\') j++;
        j++;
      }
      tokens.push({ type: 'string', text: line.slice(i, j + 1) });
      i = j + 1;
      continue;
    }

    // Decorators
    if (line[i] === '@' && (i === 0 || /\s/.test(line[i - 1]))) {
      var match = line.slice(i).match(/^@[\w.]+/);
      if (match) {
        tokens.push({ type: 'decorator', text: match[0] });
        i += match[0].length;
        continue;
      }
    }

    // Numbers
    if (/\d/.test(line[i]) && (i === 0 || /[\s(=,:\[{+\-*/%<>!&|^~]/.test(line[i - 1]))) {
      var numMatch = line.slice(i).match(/^\d+(\.\d+)?/);
      if (numMatch) {
        tokens.push({ type: 'number', text: numMatch[0] });
        i += numMatch[0].length;
        continue;
      }
    }

    // Words (keywords, builtins, function calls)
    if (/[a-zA-Z_]/.test(line[i])) {
      var wordMatch = line.slice(i).match(/^[a-zA-Z_]\w*/);
      if (wordMatch) {
        var word = wordMatch[0];
        var keywords = ['def', 'class', 'return', 'from', 'import', 'if', 'else', 'elif',
          'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'raise', 'yield',
          'lambda', 'pass', 'break', 'continue', 'and', 'or', 'not', 'in', 'is',
          'True', 'False', 'None', 'async', 'await', 'del', 'global', 'nonlocal', 'assert'];
        var builtins = ['print', 'len', 'range', 'type', 'int', 'str', 'float', 'bool',
          'list', 'dict', 'set', 'tuple', 'isinstance', 'getattr', 'setattr', 'hasattr',
          'super', 'self', 'cls', 'property', 'staticmethod', 'classmethod', 'dataclass',
          'Exception', 'ValueError', 'TypeError', 'KeyError', 'RuntimeError',
          'HTTPError', 'HTTPResponse'];

        if (keywords.indexOf(word) !== -1) {
          tokens.push({ type: 'keyword', text: word });
        } else if (builtins.indexOf(word) !== -1) {
          tokens.push({ type: 'builtin', text: word });
        } else if (i + word.length < line.length && line[i + word.length] === '(') {
          tokens.push({ type: 'function', text: word });
        } else {
          tokens.push({ type: 'plain', text: word });
        }
        i += word.length;
        continue;
      }
    }

    // Everything else
    tokens.push({ type: 'plain', text: line[i] });
    i++;
  }

  return tokens.map(function (t) {
    var escaped = escapeHtml(t.text);
    if (t.type === 'plain') return escaped;
    return '<span class="' + t.type + '">' + escaped + '</span>';
  }).join('');
}

function inString(line, pos) {
  var inSingle = false, inDouble = false;
  for (var i = 0; i < pos; i++) {
    if (line[i] === '\\') { i++; continue; }
    if (line[i] === "'" && !inDouble) inSingle = !inSingle;
    if (line[i] === '"' && !inSingle) inDouble = !inDouble;
  }
  return inSingle || inDouble;
}
