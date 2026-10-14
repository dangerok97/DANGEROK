"""Bounded MIME text extraction. Never fetch links, images or attachments."""
import base64
from html.parser import HTMLParser

MAX_DETAIL_CHARS = 8000
MAX_DECODE_BYTES = 256_000


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'head', 'template', 'noscript'}:
            self.hidden += 1
        elif not self.hidden and tag in {'br', 'p', 'div', 'td', 'tr', 'li', 'h1', 'h2', 'h3'}:
            self.chunks.append('\n')

    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'head', 'template', 'noscript'}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in {'p', 'div', 'td', 'tr', 'li'}:
            self.chunks.append('\n')

    def handle_data(self, data):
        if not self.hidden:
            self.chunks.append(data)


def message_text(payload, *, max_chars=1200):
    """Prefer an inline plain part; render HTML text only as fallback."""
    limit = max(1, min(int(max_chars), MAX_DETAIL_CHARS))
    pending, candidates, count = [(payload, 0)], [], 0
    while pending and count < 64:
        part, depth = pending.pop(0)
        count += 1
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
                    text = '\n'.join(line.strip() for line in ''.join(parser.chunks).splitlines() if line.strip())
                if text.strip():
                    candidates.append((mime == 'text/html', text.strip()))
            except (ValueError, TypeError):
                pass
        pending.extend((child, depth + 1) for child in (part.get('parts') or [])[:64])
    return min(candidates, key=lambda pair: pair[0])[1][:limit] if candidates else ''
