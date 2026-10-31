"""Build source-preserving section/part inputs from explicit plan bindings only."""

import copy
import json

VERSION = "paper-context-v1"


def _select(records, identifiers, label):
    indexed = {record["id"]: record for record in records}
    if len(indexed) != len(records) or not set(identifiers) <= set(indexed):
        raise ValueError(f"{label}에 없거나 중복된 ID가 있습니다.")
    return [copy.deepcopy(indexed[key]) for key in dict.fromkeys(identifiers)]


def _guides(guides, identifiers):
    selected = copy.deepcopy(guides)
    # Unbound research-specific requirements retain the whole selected guide.
    if not identifiers:
        return selected
    available = {c["id"] for guide in selected for c in guide.get("criteria", [])}
    if not set(identifiers) <= available:
        raise ValueError("소절의 작성 기준이 선택된 골든 가이드에 없습니다.")
    for guide in selected:
        criteria = [c for c in guide.get("criteria", []) if c["id"] in identifiers]
        guide["criteria"] = criteria
        guide["required_content"] = [c["description"] for c in criteria]
    # Purpose, paragraph flow, style and non-transfer rules remain intact.
    return selected


def part_context(packet, key):
    assignment = packet["subsection_assignments"][key]
    section = copy.deepcopy(packet["section_plan"])
    section["required_items"] = _select(section["required_items"], assignment["required_item_ids"], "필수 항목")
    section["evidence_ids"] = assignment["evidence_ids"][:]
    section["subsections"] = []
    facts = _select(packet["facts"], assignment["evidence_ids"], "소절 근거")
    linked = assignment["guideline_ids"]
    if any(not item.get("guideline_ids") for item in section["required_items"]):
        linked = []
    tables = [copy.deepcopy(t) for t in packet.get("tables", [])
              if set(t["evidence_ids"]) <= set(assignment["evidence_ids"])]
    section["table_ids"] = [t["id"] for t in tables]
    return {"paper_title": packet["paper_title"], "section_plan": section,
            "target_part": key, "target_heading": assignment["heading"], "subsection_headings": [],
            "facts": facts, "tables": tables,
            "reference_guides": _guides(packet["reference_guides"], linked),
            "context": copy.deepcopy(packet["context"]), "allocation": assignment["allocation"]}


def build_contexts(plan, research, catalog):
    by_id = {section["id"]: section for section in plan["sections"]}
    if len(by_id) != len(plan["sections"]):
        raise ValueError("장 ID가 중복됩니다.")
    sections, parts, report = {}, {}, []
    for position, original in enumerate(plan["sections"], 1):
        if original["status"] != "write":
            continue
        section = copy.deepcopy(original)
        facts = _select(research["facts"], section["evidence_ids"], "장 근거")
        guides = _select(list(catalog.values()), section["reference_ids"], "장 지침")
        tables = _select(research.get("tables", []), section["table_ids"], "장 표")
        if any(not set(t["evidence_ids"]) <= set(section["evidence_ids"]) for t in tables):
            raise ValueError("표의 비교 근거가 장에 모두 배정되지 않았습니다.")
        headings = [f"### {position}.{i} {title}" for i, title in enumerate(section["subsections"], 1)]
        count = max(1, len(headings))
        items = section["required_items"]
        explicit = [item.get("subsection_index") is not None for item in items]
        if any(explicit) and not all(explicit):
            raise ValueError("일부 필수 항목만 소절에 배정됐습니다. 전체 배정 또는 장 단위 유지가 필요합니다.")
        mapped = bool(items) and all(explicit)
        if mapped and (any(type(item["subsection_index"]) is not int or not 0 <= item["subsection_index"] < count for item in items)
                       or {item["subsection_index"] for item in items} != set(range(count))):
            raise ValueError("필수 항목의 소절 인덱스가 잘못됐거나 비어 있는 소절이 있습니다.")
        required_facts = {key for item in items for key in item["evidence_ids"]}
        if not required_facts <= set(section["evidence_ids"]):
            raise ValueError("필수 항목의 근거가 장 배정을 벗어났습니다.")
        shared = [key for key in section["evidence_ids"] if key not in required_facts]
        assignments = {}
        for i in range(count):
            chosen = [item for item in items if not mapped or item["subsection_index"] == i]
            ids = set(shared) | {key for item in chosen for key in item["evidence_ids"]}
            if not mapped:
                ids = set(section["evidence_ids"])
            # A table comparison must retain both sides, not only the matched cell.
            changed = True
            while changed:
                previous = len(ids)
                for table in tables:
                    if ids & set(table["evidence_ids"]):
                        ids.update(table["evidence_ids"])
                changed = len(ids) != previous
            assignments[f"p{i}"] = {
                "heading": headings[i] if headings else section["title"],
                "required_item_ids": [item["id"] for item in chosen],
                "evidence_ids": [key for key in section["evidence_ids"] if key in ids],
                "guideline_ids": list(dict.fromkeys(key for item in chosen for key in item.get("guideline_ids", []))),
                "shared_evidence_ids": shared[:],
                "allocation": "explicit" if mapped else "section_fallback"}
        packet = {"paper_title": plan["title"], "section_plan": section, "subsection_headings": headings,
                  "facts": facts, "tables": tables, "reference_guides": guides,
                  "subsection_assignments": assignments,
                  "context": {key: {field: copy.deepcopy(by_id[key][field])
                                    for field in ("title", "purpose", "role", "subsections")}
                              for key in section["depends_on"]}}
        sections[section["id"]] = packet
        parts[section["id"]] = {key: part_context(packet, key) for key in assignments}
        report.append({"section_id": section["id"], "evidence_ids": section["evidence_ids"],
                       "reference_ids": section["reference_ids"], "parts": assignments,
                       "section_input_characters": len(json.dumps(packet, ensure_ascii=False)),
                       "part_input_characters": {key: len(json.dumps(value, ensure_ascii=False))
                                                 for key, value in parts[section["id"]].items()}})
    return {"version": VERSION, "sections": sections, "subsections": parts, "allocation_report": report}
