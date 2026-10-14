"""Bounded MIME decoding shared by every mail use; no remote-resource fetches."""
from __future__ import annotations
import base64
from collections import deque
from html.parser import HTMLParser

MAX_DETAIL_CHARS = 8000
MAX_DECODE_BYTES = 256_000


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'head', 'template', 'noscript'}:
            self.hidden.append(tag)
        elif not self.hidden and tag in {'br', 'p', 'div', 'td', 'tr', 'li', 'h1', 'h2', 'h3'}:
            self.chunks.append('\n')

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in {'p', 'div', 'td', 'tr', 'li'}:
            self.chunks.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def bounded_limit(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('invalid_content_limit')
    return max(1, min(value, MAX_DETAIL_CHARS))


def message_text(payload, *, max_chars=1200):
    """Prefer inline plain text; fall back to rendered HTML, not a subject preview."""
    limit = bounded_limit(max_chars)
    pending, candidates, visited = deque([(payload, 0)]), [], 0
    while pending and visited < 64:
        part, depth = pending.popleft()
        visited += 1
        if not isinstance(part, dict) or depth > 12 or part.get('filename'):
            continue
        mime = str(part.get('mimeType') or '').lower()
        raw = (part.get('body') or {}).get('data')
        if mime in {'text/plain', 'text/html'} and isinstance(raw, str) and len(raw) <= MAX_DECODE_BYTES * 2:
            try:
                text = base64.urlsafe_b64decode(raw + '===').decode('utf-8', 'replace')[:MAX_DECODE_BYTES]
                if mime == 'text/html':
                    parser = _VisibleText()
                    parser.feed(text)
                    text = '\n'.join(s.strip() for s in ''.join(parser.chunks).splitlines() if s.strip())
                if text.strip():
                    candidates.append((mime == 'text/html', text.strip()))
            except (ValueError, TypeError):
                pass
        if mime != 'message/rfc822':
            pending.extend((child, depth + 1) for child in (part.get('parts') or [])[:64])
    return min(candidates, key=lambda item: item[0])[1][:limit] if candidates else ''
