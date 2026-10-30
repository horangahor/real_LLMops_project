"""Source-bound research records and variable paper plans; no domain-specific chapter rules."""

import copy
import json
import re
from pathlib import Path

from structure_profiles import ROLE_LABELS

BASE = Path(__file__).resolve().parent
VERSION = "evidence-paper-plan-v1"
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,47}\Z")


def project_profile(identifier):
    if identifier not in ("generic", "cuda"):
        raise ValueError("알 수 없는 프로젝트 프로파일입니다.")
    return json.loads((BASE / "projects" / f"{identifier}.json").read_text(encoding="utf-8"))


def normalize_research(data):
    if not isinstance(data, dict):
        raise ValueError("연구 자료는 JSON 객체여야 합니다.")
    facts = data.get("facts", data.get("verified_facts"))
    if not isinstance(facts, list) or not facts:
        raise ValueError("연구 JSON에는 facts 또는 verified_facts 목록이 필요합니다.")
    normalized, seen = [], set()
    for fact in facts:
        identifier = fact.get("id")
        statement = fact.get("statement", fact.get("finding"))
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in seen:
            raise ValueError("연구 근거 ID는 고유한 영문 식별자여야 합니다.")
        if not isinstance(statement, str) or not statement.strip():
            raise ValueError("각 근거에 statement 또는 finding이 필요합니다.")
        normalized.append({"id": identifier, "statement": statement,
                           "limits": fact.get("limits", ""), "sources": fact.get("sources", [])})
        for field in ("kind", "claim_status", "support", "support_note", "conditions", "measurements"):
            if field in fact:
                normalized[-1][field] = copy.deepcopy(fact[field])
        seen.add(identifier)
    title = data.get("title") or data.get("document_title") or data.get("project_name")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("연구 자료의 title이 필요합니다.")
    tables = copy.deepcopy(data.get("tables", data.get("result_tables", [])))
    table_ids = set()
    for table in tables:
        identifier = table.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in table_ids:
            raise ValueError("표 ID가 없거나 중복됩니다.")
        if not table.get("evidence_ids") or not set(table["evidence_ids"]) <= seen:
            raise ValueError("표의 원문 근거가 연결되지 않았습니다.")
        if (not table.get("columns") or not table.get("rows") or
                any(len(row) != len(table["columns"]) for row in table["rows"])):
            raise ValueError("표의 행·열 구성이 잘못됐습니다.")
        table_ids.add(identifier)
    return {"title": title, "facts": normalized, "tables": tables,
            "open_questions": data.get("open_questions", []),
            "provenance": data.get("provenance", data.get("evidence_status", "user_supplied_unreviewed")),
            "source": data.get("source", {})}


def reference_catalog(reference):
    """Only reusable guides enter prompts. Source outlines and research facts never enter this catalog."""
    if not isinstance(reference, dict):
        return {}
    catalog = {}
    for index, profile in enumerate(reference.get("profiles", []), 1):
        for guide in profile.get("section_guidelines", []):
            identifier = f"ref{index}_{guide['role']}"
            catalog[identifier] = {"id": identifier, **copy.deepcopy(guide),
                                   "style_rules": copy.deepcopy(profile.get("style_rules", []))}
    return catalog


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


STRINGS = {"type": "array", "items": {"type": "string"}}


def plan_schema(research=None, catalog=None):
    def choices(values):
        return {"type": "array", "items": {"type": "string", "enum": values}} if values else {"type": "null"}
    evidence = choices([f["id"] for f in research["facts"]]) if research else STRINGS
    references = choices(list(catalog)) if catalog is not None else STRINGS
    tables = choices([t["id"] for t in research["tables"]]) if research else STRINGS
    item = object_schema({"id": {"type": "string"}, "description": {"type": "string"}, "evidence_ids": evidence})
    section = object_schema({"id": {"type": "string"}, "title": {"type": "string"},
        "role": {"type": "string", "enum": list(ROLE_LABELS)}, "purpose": {"type": "string"},
        "status": {"type": "string", "enum": ["write", "placeholder"]},
        "subsections": STRINGS, "evidence_ids": evidence, "reference_ids": references,
        "table_ids": tables, "depends_on": STRINGS, "reference_adaptation": {"type": "string"},
        "required_items": {"type": "array", "items": item}})
    return object_schema({"title": {"type": "string"}, "rationale": {"type": "string"},
                          "sections": {"type": "array", "items": section},
                          "generation_order": STRINGS, "unresolved": STRINGS})


def bind_plan_evidence(plan, research, profile=None):
    """Synchronize section packets with facts explicitly selected by their own requirements/tables."""
    result = copy.deepcopy(plan)
    facts = {fact["id"] for fact in research["facts"]}
    tables = {table["id"]: table for table in research["tables"]}
    omitted = []
    if profile and profile["constraints"]["related_work"] == "omit_without_evidence":
        omitted = [s["id"] for s in result["sections"] if s["role"] == "related_work" and not s["evidence_ids"] and not s["required_items"]]
        result["sections"] = [s for s in result["sections"] if s["id"] not in omitted]
        result["generation_order"] = [key for key in result["generation_order"] if key not in omitted]
        for section in result["sections"]:
            section["depends_on"] = [key for key in section["depends_on"] if key not in omitted]
    bindings = []
    labels = []
    for section in result["sections"]:
        for field in ("table_ids", "reference_ids"):
            if section.get(field) is None:
                section[field] = []
        for field in ("title", "subsections"):
            values = [section[field]] if field == "title" else section[field]
            cleaned = [re.sub(r"^(?:제\s*)?\d+(?:\.\d+)*(?:\s*장|[.)])?\s+", "", value).strip() for value in values]
            if values != cleaned:
                labels.append({"section_id": section["id"], "field": field, "before": values, "after": cleaned})
            section[field] = cleaned[0] if field == "title" else cleaned
        if section["status"] != "write":
            continue
        requested = [key for item in section["required_items"] for key in item["evidence_ids"]]
        requested += [key for table_id in section["table_ids"] if table_id in tables for key in tables[table_id]["evidence_ids"]]
        if not set(requested) <= facts:
            raise ValueError("필수 내용이 연구 자료에 없는 근거를 요청했습니다.")
        additions = list(dict.fromkeys(key for key in requested if key not in section["evidence_ids"]))
        if additions:
            section["evidence_ids"].extend(additions)
            bindings.append({"section_id": section["id"], "added_from_explicit_requirements": additions})
    result["evidence_binding"] = bindings
    result["label_normalizations"] = labels
    result["omitted_empty_related_work"] = omitted
    return result


def validate_plan(plan, research, catalog, profile):
    if not isinstance(plan, dict) or not isinstance(plan.get("title"), str) or not plan["title"].strip() or "\n" in plan["title"]:
        raise ValueError("작성 계획의 제목이 필요합니다.")
    sections = plan.get("sections")
    if not isinstance(sections, list) or not 2 <= len(sections) <= profile["constraints"]["max_sections"]:
        raise ValueError("작성 계획의 장 개수가 허용 범위를 벗어났습니다.")
    facts = {f["id"] for f in research["facts"]}
    tables = {t["id"]: t for t in research["tables"]}
    section_ids, item_ids, used_tables = set(), set(), set()
    for section in sections:
        identifier = section.get("id")
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier) or identifier in section_ids:
            raise ValueError("작성 계획의 장 ID가 잘못됐거나 중복됩니다.")
        section_ids.add(identifier)
        for key in ("title", "purpose"):
            if not isinstance(section.get(key), str) or not section[key].strip() or "\n" in section[key]:
                raise ValueError("장 제목과 목적은 비어 있지 않은 한 줄 문자열이어야 합니다.")
        for key in ("subsections", "evidence_ids", "reference_ids", "table_ids", "depends_on"):
            values = section.get(key)
            if not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values) or len(values) != len(set(values)):
                raise ValueError(f"장 계획의 {key} 목록이 잘못됐습니다.")
        if any("\n" in s or s.startswith("#") for s in section["subsections"]):
            raise ValueError("소절 제목에 Markdown 제목 문법을 넣지 마세요.")
        if len(section["subsections"]) > profile["constraints"].get("max_subsections", 6):
            raise ValueError("한 장의 소절 개수가 프로젝트 허용 범위를 넘었습니다.")
        if section.get("role") not in ROLE_LABELS or section.get("status") not in ("write", "placeholder"):
            raise ValueError("장 역할 또는 작성 상태가 잘못됐습니다.")
        if not set(section["evidence_ids"]) <= facts:
            raise ValueError("계획에 존재하지 않는 연구 근거가 있습니다.")
        if any(key not in catalog or catalog[key]["role"] != section["role"] for key in section["reference_ids"]):
            raise ValueError("참고 가이드의 ID 또는 장 역할이 맞지 않습니다.")
        available = [key for key, guide in catalog.items() if guide["role"] == section["role"]]
        if section["status"] == "write" and available and not section["reference_ids"]:
            raise ValueError("사용 가능한 역할별 골든 가이드가 계획에 연결되지 않았습니다.")
        if section["reference_ids"] and not section.get("reference_adaptation", "").strip():
            raise ValueError("골든 가이드를 어떻게 적용할지 설명이 필요합니다.")
        if any(key not in tables or key in used_tables for key in section["table_ids"]):
            raise ValueError("표가 없거나 여러 장에 중복 배치됐습니다.")
        for key in section["table_ids"]:
            if not set(tables[key]["evidence_ids"]) <= set(section["evidence_ids"]):
                raise ValueError("표의 근거가 해당 장에 없습니다.")
        used_tables.update(section["table_ids"])
        if section["status"] == "placeholder":
            if section["role"] != "related_work" or any(section[key] for key in ("evidence_ids", "table_ids", "required_items", "depends_on", "subsections")):
                raise ValueError("빈 관련 연구 장에 본문 작성 항목을 넣을 수 없습니다.")
        elif not section["evidence_ids"] or not section.get("required_items"):
            raise ValueError("작성할 장에는 근거와 필수 내용이 필요합니다.")
        for item in section.get("required_items", []):
            key = item.get("id")
            if not isinstance(key, str) or not IDENTIFIER.fullmatch(key) or key in item_ids:
                raise ValueError("필수 내용 ID가 없거나 중복됩니다.")
            if (not isinstance(item.get("description"), str) or not item["description"].strip() or
                    not isinstance(item.get("evidence_ids"), list) or
                    any(not isinstance(v, str) for v in item["evidence_ids"]) or
                    not set(item["evidence_ids"]) <= set(section["evidence_ids"])):
                raise ValueError("필수 내용의 근거가 해당 장에 없습니다.")
            item_ids.add(key)
    policy = profile["constraints"]["related_work"]
    if not {"introduction", "conclusion"} <= {s["role"] for s in sections if s["status"] == "write"}:
        raise ValueError("작성 계획에는 서론과 결론의 역할이 필요합니다.")
    related = [s for s in sections if s["role"] == "related_work"]
    if policy == "placeholder" and (len(related) != 1 or related[0]["status"] != "placeholder"):
        raise ValueError("프로젝트 설정에 따라 관련 연구는 빈 장이어야 합니다.")
    order = plan.get("generation_order")
    writable = {s["id"] for s in sections if s["status"] == "write"}
    if not isinstance(order, list) or len(order) != len(set(order)) or set(order) != writable:
        raise ValueError("작성 순서가 작성 대상 장과 일치하지 않습니다.")
    visited = set()
    for identifier in order:
        section = next(s for s in sections if s["id"] == identifier)
        if not set(section["depends_on"]) <= visited:
            raise ValueError("작성 의존 관계가 순환하거나 선행 장이 없습니다.")
        visited.add(identifier)
    return plan
