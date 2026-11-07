"""Deterministic, offline Markdown → Overleaf project export; no model calls."""
import hashlib
import html
import io
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from markdown_it import MarkdownIt

from paper_display import PROTECTED

VERSION = "overleaf-export-v1"
ESCAPES = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "#": r"\#", "$": r"\$",
           "%": r"\%", "&": r"\&", "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}
SYMBOLS = {"→": r"\rightarrow", "←": r"\leftarrow", "↔": r"\leftrightarrow", "⇒": r"\Rightarrow",
           "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx", "±": r"\pm", "×": r"\times",
           "μ": r"\mu", "µ": r"\mu", "α": r"\alpha", "β": r"\beta", "ε": r"\varepsilon",
           "∞": r"\infty", "∈": r"\in", "∑": r"\sum", "✓": r"\checkmark"}
PREAMBLE = r"""% !TeX program = xelatex
% Exported by Research Studio. Compile with XeLaTeX.
\documentclass[11pt,a4paper]{article}
\usepackage[margin=25mm]{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\xeCJKsetup{CJKspace=true}
\IfFontExistsTF{Noto Serif}{\setmainfont{Noto Serif}}{\setmainfont[BoldFont=lmroman10-bold.otf,ItalicFont=lmroman10-italic.otf,BoldItalicFont=lmroman10-bolditalic.otf]{lmroman10-regular.otf}}
\IfFontExistsTF{Noto Serif CJK KR}{\setCJKmainfont{Noto Serif CJK KR}}{\setCJKmainfont{Malgun Gothic}}
\IfFontExistsTF{Noto Sans CJK KR}{\setCJKsansfont{Noto Sans CJK KR}}{\setCJKsansfont{Malgun Gothic}}
\IfFontExistsTF{Noto Sans Mono CJK KR}{\setCJKmonofont{Noto Sans Mono CJK KR}}{\setCJKmonofont{Malgun Gothic}}
\usepackage{amsmath,amssymb}
\usepackage{array,booktabs,longtable}
\usepackage{alltt}
\usepackage{enumitem}
\usepackage{xurl}
\usepackage[unicode,hidelinks]{hyperref}
\setlist{nosep,leftmargin=*}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.6em}
\setlength{\emergencystretch}{3em}
\renewcommand{\arraystretch}{1.2}
"""


def escape(text):
    return "".join(ESCAPES.get(c, "\\ensuremath{" + SYMBOLS[c] + "}" if c in SYMBOLS else c)
                   for c in str(text))


def escaped_url(url):
    # Prevent a URL from closing TeX arguments; preserve existing percent escapes.
    url = str(url).replace("\\", "%5C").replace("{", "%7B").replace("}", "%7D").replace("~", "%7E")
    return "".join("\\" + c if c in "#%&_$" else c for c in url)


class LatexRenderer:
    def __init__(self, markdown):
        self.warnings = []
        self.math = {}
        prefix = "EXPORTMATH" + hashlib.sha256(markdown.encode()).hexdigest()[:12] + "X"
        def protect(match):
            token = match.group()
            if token.startswith(("$", r"\(", r"\[")):
                marker = prefix + str(len(self.math)) + "Z"
                display = token.startswith(("$$", r"\["))
                content = token[2:-2] if display or token.startswith(r"\(") else token[1:-1]
                # Documents are text by default. Exported math cannot include
                # TeX file/process/control primitives from source/model prose.
                unsafe = re.search(r"\\(?:input|include|write|openout|openin|read|catcode|csname|def|gdef|edef|newcommand|usepackage|documentclass)\b", content)
                if unsafe:
                    self.warnings.append("TeX 제어 명령이 포함된 수식을 실행하지 않고 원문 텍스트로 보존했습니다.")
                    self.math[marker] = escape(token)
                else:
                    self.math[marker] = (r"\[" + content + r"\]") if display else (r"\(" + content + r"\)")
                return marker
            return token
        self.markdown = PROTECTED.sub(protect, markdown)
        self.math_pattern = re.compile("(" + "|".join(map(re.escape, self.math)) + ")") if self.math else None
        self.parser = MarkdownIt("commonmark", {"html": True, "breaks": False}).enable("table")

    def text(self, text):
        if not self.math_pattern:
            return escape(text)
        return "".join(self.math.get(p, escape(p)) for p in self.math_pattern.split(text))

    def inline(self, tokens):
        out = []
        links = []
        for token in tokens or []:
            kind = token.type
            if kind == "text":
                out.append(self.text(token.content))
            elif kind == "code_inline":
                out.append(r"\texttt{" + escape(token.content) + "}")
            elif kind in ("softbreak", "hardbreak"):
                out.append("\n" if kind == "softbreak" else r"\newline{}" + "\n")
            elif kind in ("strong_open", "em_open"):
                out.append(r"\textbf{" if kind == "strong_open" else r"\emph{")
            elif kind in ("strong_close", "em_close"):
                out.append("}")
            elif kind == "link_open":
                href = token.attrGet("href") or ""
                linked = bool(re.match(r"^(?:https?://|mailto:)", href, re.I))
                links.append(linked)
                out.append(r"\href{" + escaped_url(href) + "}{" if linked else "{")
            elif kind == "link_close":
                if links:
                    links.pop()
                out.append("}")
            elif kind == "image":
                out.append(r"\textit{" + escape("[그림: " + token.content + "]") + "}")
                self.warnings.append("그림은 원본 파일을 ZIP에 포함하지 않고 대체 설명으로 보존했습니다: " + token.content)
            elif kind == "html_inline":
                value = token.content
                if re.fullmatch(r"<br\s*/?>", value, re.I):
                    out.append(r"\newline{}")
                elif value.lower() in ("<sup>", "<sub>"):
                    out.append(r"\textsuperscript{" if value.lower() == "<sup>" else r"\textsubscript{")
                elif value.lower() in ("</sup>", "</sub>"):
                    out.append("}")
                else:
                    out.append(escape(html.unescape(value)))
            else:
                out.append(escape(token.content))
        return "".join(out)

    def render(self):
        tokens = self.parser.parse(self.markdown)
        out, first_title, title = [], True, "논문 초안"
        i = 0
        while i < len(tokens):
            t = tokens[i]
            kind = t.type
            if kind == "heading_open":
                heading = tokens[i + 1]
                if t.tag == "h1" and first_title:
                    title = self.inline(heading.children)
                    first_title = False
                else:
                    level = int(t.tag[1:])
                    command = {1: "section", 2: "section", 3: "subsection", 4: "subsubsection", 5: "paragraph", 6: "subparagraph"}[level]
                    # Saved draft headings already contain their exact numbers.
                    out.append("\\" + command + "*{" + self.inline(heading.children) + "}\n")
                i += 3
                continue
            if kind == "table_open":
                rows, row, header = [], [], False
                i += 1
                while i < len(tokens) and tokens[i].type != "table_close":
                    cell = tokens[i]
                    if cell.type == "thead_open":
                        header = True
                    elif cell.type == "tbody_open":
                        header = False
                    elif cell.type == "tr_open":
                        row = []
                    elif cell.type == "inline":
                        row.append(self.inline(cell.children))
                    elif cell.type == "tr_close":
                        rows.append((row, header))
                    i += 1
                if rows:
                    n = max(len(row) for row, _ in rows)
                    width = r"\dimexpr(\linewidth-" + str(2 * (n - 1)) + r"\tabcolsep)/" + str(n) + r"\relax"
                    spec = "@{}" + "".join(r">{\raggedright\arraybackslash}p{" + width + "}" for _ in range(n)) + "@{}"
                    out.append("\n{\\small\n\\begin{longtable}{" + spec + "}\n\\toprule\n")
                    for index, (row, is_header) in enumerate(rows):
                        row = row + [""] * (n - len(row))
                        if is_header:
                            row = [r"\textbf{" + c + "}" for c in row]
                        line = " & ".join(row) + r" \\" + "\n"
                        out.append(line)
                        if is_header and (index + 1 == len(rows) or not rows[index + 1][1]):
                            out.append("\\midrule\n\\endfirsthead\n\\toprule\n" + line + "\\midrule\n\\endhead\n")
                    out.append("\\bottomrule\n\\end{longtable}\n}\n")
            elif kind == "inline":
                out.append(self.inline(t.children))
            elif kind == "paragraph_close":
                out.append("\n\n")
            elif kind in ("bullet_list_open", "ordered_list_open"):
                env = "itemize" if kind == "bullet_list_open" else "enumerate"
                start = t.attrGet("start")
                options = f"[start={int(start)}]" if env == "enumerate" and start else ""
                out.append("\\begin{" + env + "}" + options + "\n")
            elif kind in ("bullet_list_close", "ordered_list_close"):
                out.append("\\end{" + ("itemize" if kind == "bullet_list_close" else "enumerate") + "}\n")
            elif kind == "list_item_open":
                out.append(r"\item ")
            elif kind == "blockquote_open":
                out.append("\\begin{quote}\n")
            elif kind == "blockquote_close":
                out.append("\\end{quote}\n")
            elif kind in ("fence", "code_block"):
                out.append("\\begin{alltt}\\small\n" + escape(t.content.expandtabs(4)) + "\n\\end{alltt}\n")
            elif kind == "hr":
                out.append("\n\\medskip\\hrule\\medskip\n")
            elif kind == "html_block":
                out.append(escape(html.unescape(t.content)) + "\n")
                self.warnings.append("원시 HTML 블록은 실행하지 않고 텍스트로 보존했습니다.")
            i += 1
        return title, "".join(out).strip() + "\n"


def project_zip(markdown, *, title=None, provenance=None, metadata=None):
    if not isinstance(markdown, str) or not markdown.strip():
        raise ValueError("완성된 본문이 없습니다. 초안 또는 절을 먼저 생성해주세요.")
    renderer = LatexRenderer(markdown)
    parsed_title, content = renderer.render()
    title_tex = escape(title) if title else parsed_title
    main = PREAMBLE + "\n\\title{\\Large\\bfseries " + title_tex + "}\n\\author{}\n\\date{}\n\\begin{document}\n\\maketitle\n\\input{content.tex}\n\\end{document}\n"
    readme = """# Overleaf로 가져오기

1. Overleaf의 New project → Existing project (.zip) / Upload project에서 이 ZIP을 선택합니다.
2. Compiler를 XeLaTeX, Main document를 main.tex로 설정합니다.
3. Recompile을 누릅니다. 한글은 Overleaf에 제공되는 Noto CJK 글꼴을 사용합니다.

main.tex: 독립 실행 가능한 논문 문서 (XeLaTeX).
content.tex: 본문만 담은 조각. 기존 프로젝트에 삽입하려면 이 파일을 사용하고 main.tex의 패키지를 참고하세요.
original.md: 내보낸 화면의 원본 Markdown.
provenance.json: 문단별 기존 근거·원문 연결. PDF 본문에는 자동 삽입하지 않습니다.
export.json: 실행 범위, 변환 버전, 원본 해시, 변환 주의 사항.

장·소절 번호는 원본 제목을 유지하며 LaTeX가 중복 번호를 붙이지 않습니다.
이 내보내기는 새 내용을 작성·요약하거나 근거를 재검토하지 않습니다.
내부 근거 ID를 학술 참고문헌이나 DOI로 만들지 않습니다.
원본 PDF·API 키·전체 API 응답은 이 ZIP에 포함하지 않습니다.
그림 파일은 자동 다운로드하지 않습니다. 그림이 있었다면 export.json의 warnings를 확인하세요.

공식 안내: https://docs.overleaf.com/managing-projects-and-files/uploading-a-project
한글 설정: https://www.overleaf.com/learn/latex/Korean
"""
    files = {"main.tex": main, "content.tex": content, "original.md": markdown, "README.md": readme,
             "latexmkrc": "$pdf_mode = 5;\n", "provenance.json": json.dumps(provenance or [], ensure_ascii=False, indent=2),
             "export.json": json.dumps({"version": VERSION, "compiler": "XeLaTeX", "main": "main.tex",
                 "markdown_sha256": hashlib.sha256(markdown.encode()).hexdigest(),
                 "warnings": list(dict.fromkeys(renderer.warnings)), **(metadata or {})}, ensure_ascii=False, indent=2)}
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
    return buffer.getvalue()


def paragraph_sources(sections, research):
    from planned_paper import index_paragraphs
    from bounded_drafting import cited_ids
    facts = {f["id"]: f for f in research.get("facts", [])}
    result = []
    for pid, paragraph in index_paragraphs(sections).items():
        ids = sorted(cited_ids(paragraph["text"]))
        result.append(dict(paragraph_id=pid, section_id=paragraph["section_id"],
            text=re.sub(r"\[근거:[^\]]+\]", "", paragraph["text"]).strip(),
            evidence=[facts[key] for key in ids if key in facts],
            unresolved_evidence_ids=[key for key in ids if key not in facts]))
    return result
