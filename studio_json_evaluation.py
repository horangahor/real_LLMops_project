"""Studio의 명시적 sections/headings JSON을 참조표 보완 없이 평가용 트리로 변환한다."""

import json
import re


def decode_document(text, *, diagnostic_controls=False, diagnostic_citations=False):
    error = None
    used_controls = False
    citation_count = 0
    value = text
    for _ in range(3):
        if isinstance(value, dict):
            return value, {"strict_valid": error is None, "error": error,
                           "diagnostic_control_characters": used_controls,
                           "diagnostic_trailing_citations": citation_count > 0,
                           "trailing_citation_count": citation_count,
                           "json_object_strict_valid": not used_controls}
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            if diagnostic_citations and exc.msg == "Extra data":
                original = value.lstrip()
                body, end = json.JSONDecoder().raw_decode(original)
                trailing = original[end:].strip()
                if isinstance(body, dict) and re.fullmatch(r"(?:【†[1-9]\d*】\s*)+", trailing):
                    error = {"message": exc.msg, "line": exc.lineno, "column": exc.colno, "position": exc.pos}
                    citation_count = len(re.findall(r"【†[1-9]\d*】", trailing))
                    value = body
                    continue
                raise
            if not diagnostic_controls:
                raise
            error = {"message": exc.msg, "line": exc.lineno, "column": exc.colno, "position": exc.pos}
            # Inspection only. Never rewrite or mark the raw response valid.
            value = json.loads(value, strict=False)
            used_controls = True
    raise ValueError("Studio 응답에서 JSON 객체를 읽을 수 없습니다.")


def explicit_outline(document):
    is_sections = "sections" in document
    items = document.get("sections" if is_sections else "headings")
    if not isinstance(items, list) or not items:
        raise ValueError("Studio JSON에 sections 또는 headings 배열이 필요합니다.")
    evidence = document.get("evidence", [])
    evidence_by_id = {}
    for entry in evidence:
        key = entry.get("evidence_id")
        if not isinstance(key, str) or key in evidence_by_id:
            raise ValueError("근거 ID가 없거나 중복됩니다.")
        evidence_by_id[key] = entry
    nodes, parents, missing_links = {}, {}, []
    for item in items:
        identifier = item.get("id" if is_sections else "evidence_id")
        title = item.get("title" if is_sections else "heading_text")
        parent = item.get("parent_id" if is_sections else "parent_evidence_id")
        if not isinstance(identifier, str) or identifier in nodes or not isinstance(title, str) or not title.strip():
            raise ValueError("목차 ID·제목이 없거나 중복됩니다.")
        pages = []
        if type(item.get("page")) is int and item["page"] > 0:
            pages.append(item["page"])
        for key in item.get("evidence_ids", []):
            if key not in evidence_by_id:
                missing_links.append({"section_id": identifier, "evidence_id": key})
            else:
                page = evidence_by_id[key].get("page")
                if type(page) is int and page > 0:
                    pages.append(page)
        nodes[identifier] = {"title": title, "role": "other", "source_pages": sorted(set(pages)) or None, "children": []}
        parents[identifier] = parent
    for identifier in nodes:
        seen, current = set(), identifier
        while current is not None:
            if current not in nodes:
                raise ValueError("원본 JSON에 없는 부모 ID입니다.")
            if current in seen:
                raise ValueError("목차 부모 관계에 순환이 있습니다.")
            seen.add(current)
            current = parents[current]
    roots = []
    for identifier, node in nodes.items():
        parent = parents[identifier]
        (roots if parent is None else nodes[parent]["children"]).append(node)
    return {"observed_outline": roots,
            "role_placeholder": "other is technical only; no role is inferred",
            "hierarchy_policy": "native parent IDs, not reconstructed from numbering",
            "missing_evidence_links": missing_links}
