"""Protect literal prose tildes without altering scientific content or code/math."""

import re

DECORATION = re.compile(r"[\U0001F300-\U0001FAFF✨🌟🎉]|[\ufe0e\ufe0f\u200d]")


def plain_table_text(text):
    """Strip pictorial decoration in display copies, retaining technical text."""
    marks = {"✅": "✓", "☑": "✓", "✔": "✓", "❌": "×", "✖": "×", "⚠": "주의"}
    def clean(value):
        for old, new in marks.items():
            value = value.replace(old, new)
        return DECORATION.sub("", value)
    result, start = [], 0
    for match in PROTECTED.finditer(str(text)):
        result.extend((clean(str(text)[start:match.start()]), match.group()))
        start = match.end()
    result.append(clean(str(text)[start:]))
    return "".join(result).strip()


def readable_prose(text, limit=600):
    """View-only paragraph breaks at sentence boundaries; never cut a sentence."""
    if len(text) <= limit or re.match(r"^\s*(?:[-*+] |\d+[.)] |```|~~~|\|)", text):
        return text
    protected = [(m.start(), m.end()) for m in PROTECTED.finditer(text)]
    boundaries = [m.end() for m in re.finditer(r"[.!?。]\s+", text)
                  if not any(start <= m.start() < end for start, end in protected)]
    chunks, start, last = [], 0, 0
    for end in boundaries + [len(text)]:
        if end - start > limit and last > start:
            chunks.append(text[start:last].strip())
            start = last
        last = end
    if text[start:].strip():
        chunks.append(text[start:].strip())
    return "\n\n".join(chunks)

PROTECTED = re.compile(
    r"(?ms:^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[^\n]*(?:\n|$))"
    r"|`+[^`\n]*`+|\$\$[\s\S]*?\$\$|(?<!\\)\$[^$\n]+(?<!\\)\$"
    r"|\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]"
    r"|!?\[[^\]\n]*\]\([^\)\n]*\)|<https?://[^>\n]+>|https?://[^\s<>]+")


def safe_markdown(text):
    def prose(value):
        out = []
        slashes = 0
        for char in value:
            if char == "~" and slashes % 2 == 0:
                out.append("\\")
            out.append(char)
            slashes = slashes + 1 if char == "\\" else 0
        return "".join(out)
    out, start = [], 0
    for match in PROTECTED.finditer(text):
        token = match.group()
        if re.match(r"!?\[", token):
            label, target = token.split("](", 1)
            token = prose(label) + "](" + target
        out.extend((prose(text[start:match.start()]), token))
        start = match.end()
    out.append(prose(text[start:]))
    return "".join(out)
