"""Recover an Arabic-numbered body outline from native Parse elements, without a reference table."""

import html
import re
import statistics
import unicodedata
from html.parser import HTMLParser

PIPELINE_VERSION = "parse-numbered-outline-v1"
NUMBERED = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,5})([.)]?)\s+(.+)$")
BIBLIOGRAPHY = {"references", "bibliography", "참고문헌"}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def element_text(element):
    content = element.get("content", {})
    if isinstance(content.get("text"), str) and content["text"].strip():
        return content["text"].strip()
    parser = PlainText()
    parser.feed(content.get("html", ""))
    return html.unescape("".join(parser.parts)).strip()


def element_key(element):
    return f"p{element['page']}:e{element['id']}"


def font_size(element):
    match = re.search(r"font-size\s*:\s*([\d.]+)(?:px|pt)", element.get("content", {}).get("html", ""))
    return float(match[1]) if match else None


def margin_signature(element):
    points = element.get("coordinates") or []
    if not points or not all(isinstance(point.get("y"), (int, float)) for point in points):
        return None
    if max(point["y"] for point in points) > 0.16 and min(point["y"] for point in points) < 0.9:
        return None
    text = unicodedata.normalize("NFKC", element_text(element)).casefold()
    if len(text) > 160:
        return None
    return "".join(char for char in text if char.isalpha()) or None


def numbered_candidate(element, body_font=None):
    category, text = element.get("category", ""), element_text(element)
    if category != "paragraph" and not category.startswith("heading"):
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    first = unicodedata.normalize("NFKC", lines[0]).replace("\u00ad", "")
    match = NUMBERED.fullmatch(first)
    if not match:
        return None
    number, suffix, title = match.groups()
    title = " ".join([title, *lines[1:]])
    # Decimal measurements, list markers, and equation statements are not standalone headings.
    if not title[0].isalpha() or any(token in title for token in ("=", "%", "≤", "≥")):
        return None
    if category == "paragraph":
        if "." not in number and suffix != ".":
            size = font_size(element)
            if size is None or body_font is None or size <= body_font:
                return None
        if len(title.split()) > 18 or len(title) > 220 or "@" in title:
            return None
        if title.endswith((".", ";", ":")):
            return None
    return {"element_id": element_key(element), "number": number, "title": f"{number} {title}",
            "page": element["page"], "category": category,
            "coordinates": element.get("coordinates", [])}


def extract_numbered_outline(document):
    candidates, rejected, in_bibliography = [], [], False
    margin_pages = {}
    body_sizes = []
    for element in document["elements"]:
        signature = margin_signature(element)
        if signature:
            margin_pages.setdefault(signature, set()).add(element["page"])
        size = font_size(element)
        if element.get("category") == "paragraph" and len(element_text(element).split()) > 25 and size:
            body_sizes.append(size)
    body_font = statistics.median(body_sizes) if body_sizes else None
    for element in document["elements"]:
        text = element_text(element)
        signature = margin_signature(element)
        if signature and len(margin_pages[signature]) >= 2:
            rejected.append({"element_id": element_key(element), "page": element["page"], "text": text,
                             "reason": "repeated_margin_text"})
            continue
        normalized = "".join(unicodedata.normalize("NFKC", text).casefold().split()).rstrip(":.")
        if normalized in BIBLIOGRAPHY:
            in_bibliography = True
        candidate = None if in_bibliography else numbered_candidate(element, body_font)
        if candidate:
            candidates.append(candidate)
        elif element.get("category", "").startswith("heading"):
            rejected.append({"element_id": element_key(element), "page": element["page"], "text": text,
                             "reason": "bibliography_boundary" if in_bibliography else "outside_numbered_body_policy"})
    by_number = {}
    for candidate in candidates:
        number = candidate["number"]
        previous = by_number.get(number)
        if previous:
            normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
            if normalize(previous["title"]) == normalize(candidate["title"]):
                rejected.append({**candidate, "reason": "duplicate_number_and_title"})
                continue
            heading_priority = [item for item in (previous, candidate) if item["category"].startswith("heading")]
            if len(heading_priority) != 1:
                raise ValueError(f"절 번호 {number}의 서로 다른 목차 후보가 충돌합니다. Parse 원본을 확인하세요.")
            chosen = heading_priority[0]
            rejected.append({**(candidate if chosen is previous else previous), "reason": "number_conflict_with_heading_candidate"})
            by_number[number] = chosen
        else:
            by_number[number] = candidate
    if not by_number:
        raise ValueError("아라비아 숫자 번호가 있는 본문 목차를 찾지 못했습니다. 무번호·로마 숫자 목차는 현재 자동 분석 범위 밖입니다.")
    chosen = sorted(by_number.values(), key=lambda item: tuple(map(int, item["number"].split("."))))
    nodes = {item["number"]: {"title": item["title"], "role": "other", "source_pages": [item["page"]],
                              "source_element_id": item["element_id"], "children": []} for item in chosen}
    roots = []
    for item in chosen:
        parent = item["number"].rpartition(".")[0]
        if parent and parent not in nodes:
            raise ValueError(f"절 {item['number']}의 실제 부모 {parent}가 없습니다. 누락 부모를 만들어 넣지 않습니다.")
        (nodes[parent]["children"] if parent else roots).append(nodes[item["number"]])
    root_numbers = [int(item["number"]) for item in chosen if "." not in item["number"]]
    warnings = []
    if root_numbers and root_numbers != list(range(root_numbers[0], root_numbers[-1] + 1)):
        warnings.append("상위 절 번호에 공백이 있습니다. 추출 누락 또는 원문 번호 체계를 확인하세요.")
    return {"pipeline_version": PIPELINE_VERSION, "observed_outline": roots,
            "selected_headings": chosen, "rejected_candidates": rejected, "warnings": warnings,
            "scope": "Arabic-numbered body sections before bibliography; unnumbered/roman sections are not automatically selected.",
            "hierarchy_policy": "Parents and order derive only from observed section numbers; missing parents cause failure.",
            "role_assessment": "other is a placeholder until an explicit guidance model labels source element IDs"}
