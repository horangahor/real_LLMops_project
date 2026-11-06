"""Render only selected tables at their planned subsection, preserving source data."""

import re
from publication_table_views import prepare_tables, publication_notes

LAYOUT_POLICY = "table-explanation-units-v4"


def _caption(section, table):
    candidates = [p.get("caption", "") for p in section.get("table_placements", []) if p["table_id"] == table["id"]]
    candidates += [table.get("caption", ""), " / ".join(map(str, table["columns"]))]
    for value in candidates:
        value = str(value).strip()
        if (value and value != table["id"] and not re.search(r"\bsource[_ -]?table(?:[_ -]|\b)|^(?:table|tbl|T)[_ -]?\d+$", value, re.I)):
            return value
    return ""


def table_anchors(section, tables):
    explicit = {p["table_id"]: p["subsection_index"] for p in section.get("table_placements", [])}
    anchors = {}
    for key in section["table_ids"]:
        if key in explicit:
            anchors[key] = explicit[key]
            continue
        # Compatibility for saved plans: infer from existing item bindings,
        # never from a particular chapter name or research domain.
        candidates = [(len(set(item["evidence_ids"]) & set(tables[key]["evidence_ids"])),
                       item.get("subsection_index") or 0) for item in section["required_items"]]
        best = max(candidates, key=lambda p: (p[0], -p[1])) if candidates else (0, 0)
        anchors[key] = best[1] if best[0] else 0
    return anchors


def _citations(text):
    return {key for group in re.findall(r"\[근거:\s*([^\]]+)\]", text)
            for key in re.split(r"[,，;·\s]+", group.strip()) if key}


def _layout(body, section, tables):
    chunks = [part.strip() for part in re.split(r"(?m)(?=^###\s)", body) if part.strip()] or [body]
    parts = []
    for chunk in chunks:
        first, separator, rest = chunk.partition("\n")
        heading = first if first.startswith("### ") else ""
        content = rest if heading else chunk
        paragraphs = [p for p in re.split(r"\n\s*\n", content.strip()) if p.strip()]
        parts.append((heading, paragraphs))
    selected = {**section, "table_ids": [key for key in section["table_ids"] if key in tables]}
    anchors = table_anchors(selected, tables)
    positions, matches = {}, {}
    for key, index in anchors.items():
        if index >= len(parts):
            raise ValueError("표를 배치할 소절이 최종 본문에 없습니다.")
        paragraphs = parts[index][1]
        overlap = [len(_citations(p) & set(tables[key]["evidence_ids"])) for p in paragraphs]
        matches[key] = [i for i, count in enumerate(overlap) if count]
        positions[key] = {"subsection_index": index, "paragraph_index": 0,
                          "linked": bool(matches[key]), "published": False}
    used = set()
    # Allocate scarce explanation paragraphs first. Never insert an unrelated
    # paragraph or move prose just to make space between two tables.
    for key in sorted(matches, key=lambda k: len(matches[k])):
        place = positions[key]
        index = place["subsection_index"]
        best = next((i for i in matches[key] if (index, i) not in used), None)
        reason = ("missing_academic_caption" if not _caption(section, tables[key]) else
                  "no_cited_explanation" if not matches[key] else
                  "shared_explanation_without_distinct_paragraph" if best is None else "")
        if reason:
            place.update(withheld_reason=reason, placement_basis="withheld")
            continue
        used.add((index, best))
        place.update(paragraph_index=best, published=True, explanation_paragraphs=[best],
                     placement_basis="first_available_cited_explanation")
    return parts, positions


def render_section_tables(body, section, tables, chapter):
    def cell(value):
        from paper_display import plain_table_text
        return plain_table_text(value).replace("|", "\\|").replace("\n", " ")
    views = {t["id"]: t for t in prepare_tables({"tables": list(tables.values())})["tables"]}
    parts, positions = _layout(body, section, views)
    rendered = {}
    ordered = sorted((key for key in positions if positions[key]["published"]),
                     key=lambda key: (positions[key]["subsection_index"], positions[key]["paragraph_index"]))
    for number, key in enumerate(ordered, 1):
        table = views[key]
        caption = _caption(section, table)
        lines = [f"**표 {chapter}-{number}. {cell(caption)}**", "",
                 "| " + " | ".join(map(cell, table["columns"])) + " |",
                 "| " + " | ".join("---" for _ in table["columns"]) + " |"]
        lines += ["| " + " | ".join(map(cell, row)) + " |" for row in table["rows"]]
        lines += ["", cell(table.get("scope", ""))]
        for note in publication_notes(table.get("notes", []))[0]:
            lines += ["", "주: " + cell(note)]
        place = positions[key]
        rendered.setdefault((place["subsection_index"], place["paragraph_index"]), []).append("\n".join(lines))
    result = []
    for index, (heading, paragraphs) in enumerate(parts):
        if heading:
            result.append(heading)
        for number, paragraph in enumerate(paragraphs):
            result.extend(rendered.get((index, number), []))
            from paper_display import readable_prose
            result.append(readable_prose(re.sub(r"\[근거:[^\]]+\]", "", paragraph).strip()))
        if not paragraphs:
            result.extend(rendered.get((index, 0), []))
    return "\n\n".join(result)


def selection_report(plan, research, sections=None):
    prepared = prepare_tables(research)
    tables = {t["id"]: t for t in prepared["tables"]}
    raw_ids = {t["id"] for t in research["tables"]}
    selected = {}
    for section in plan["sections"]:
        if set(section["table_ids"]) - raw_ids:
            raise ValueError("본문 표 선택에 존재하지 않는 원자료 ID가 있습니다.")
        scoped = {**section, "table_ids": [key for key in section["table_ids"] if key in tables]}
        positions = _layout(sections[section["id"]], scoped, tables)[1] if sections and section["status"] == "write" else {}
        for key, index in table_anchors(scoped, tables).items():
            reason = next((p["reason"] for p in section.get("table_placements", []) if p["table_id"] == key),
                          "기존 계획의 필수 항목·근거 연결로 배치")
            selected[key] = {"table_id": key, "section_id": section["id"], "subsection_index": index, "reason": reason}
            if key in positions:
                selected[key].update(positions[key])
    published = {key for key, place in selected.items() if place.get("published", True)}
    notes_audit = [{"table_id": key, "published": publication_notes(table.get("notes", []))[0],
                    "withheld": publication_notes(table.get("notes", []))[1]} for key, table in tables.items() if table.get("notes")]
    return {"layout_policy": LAYOUT_POLICY,
            "available": len(raw_ids), "eligible": len(tables), "planned": sum(len(s["table_ids"]) for s in plan["sections"]),
            "selected": len(published), "archived": len(raw_ids) - len(published),
            "placements": list(selected.values()), "archived_table_ids": [t["id"] for t in research["tables"] if t["id"] not in published],
            "withheld_tables": [p for p in selected.values() if not p.get("published", True)] +
                [{**p, "withheld_reason": p["reason"]} for p in prepared["audit"] if p["status"] == "withheld"
                 and any(p["table_id"] in s["table_ids"] for s in plan["sections"])],
            "notes": notes_audit, "preparation": prepared["audit"], "unlinked_tables": sum(not p.get("linked", True) for p in selected.values())}
