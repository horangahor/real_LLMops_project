"""Omit only code-derived chapter evidence lists from model plan output."""

import copy

POLICY = "derived-chapter-evidence-v2"
LEGACY_INSTRUCTION = """\n작성 계획 출력 최적화 규칙:
장 객체의 evidence_ids는 출력하지 않는다. 각 required_items.evidence_ids에 해당 주장·비교·조건을 뒷받침하는 실제 근거 ID만 선택한다.
코드가 각 장의 필수 항목과 선택된 표의 근거를 합쳐 장의 evidence_ids를 만든다. 동일 목록을 장 수준에 반복하지 않는다.
이 규칙은 출력 중복만 줄인다. 장·소절의 핵심 내용, 선택 근거의 조건·수치·한계·사용자 승인 범위는 유지한다."""
INSTRUCTION = LEGACY_INSTRUCTION + """
작성 계획 JSON의 계층:
sections에는 작성 순서에 있는 모든 장의 객체를 반환한다. 첫 장만 쓰고 나머지 장을 generation_order에만 적지 않는다.
subsections는 소절 제목 문자열만 담는 배열이다. 소절 객체·purpose·required_items·evidence_ids·JSON 구문을 제목 목록에 넣지 않는다.
required_items는 해당 장 객체의 별도 필드다. 각 항목의 subsection_index로 소절 제목 목록의 위치를 연결한다.
generation_order는 sections에 실제 반환한 write 장 ID를 각각 한 번 포함한다.
입력 프로젝트의 장·소절 개수 범위와 출력 스키마를 따르며, 보정 시 누락된 장·필수 항목까지 완성한다."""


def bounded_plan_schema(schema, profile):
    """Expose the existing validator's ranges and flat wire layout to the model."""
    result = copy.deepcopy(schema)
    sections = result["properties"]["sections"]
    sections.update(minItems=2, maxItems=profile["constraints"]["max_sections"])
    properties = sections["items"]["properties"]
    subsections = copy.deepcopy(properties["subsections"])
    properties["subsections"] = subsections
    subsections["maxItems"] = profile["constraints"].get("max_subsections", 6)
    subsections["items"]["description"] = "소절 제목 한 개. 목적·필수 항목·근거·JSON 구문은 포함하지 않는다."
    return result


def complete_cached_chapters(value, schema):
    """Never replay a partial chapter list as a completed planning response."""
    shape = schema.get("properties", {}).get("sections")
    if shape is None:
        return True
    sections = value.get("sections") if isinstance(value, dict) else None
    if not isinstance(sections, list) or not shape.get("minItems", 2) <= len(sections) <= shape.get("maxItems", float("inf")):
        return False
    if any(not isinstance(s, dict) or not isinstance(s.get("id"), str) for s in sections):
        return False
    order = value.get("generation_order")
    return (isinstance(order, list) and all(isinstance(key, str) for key in order)
            and len(order) == len(set(order))
            and set(order) == {s["id"] for s in sections if s.get("status") == "write"})


def restore_chapter_evidence(value):
    """Preserve explicit legacy lists; let bind_plan_evidence build omitted lists."""
    result = copy.deepcopy(value)
    if isinstance(result, dict) and isinstance(result.get("sections"), list):
        for section in result["sections"]:
            if isinstance(section, dict) and "evidence_ids" not in section:
                section["evidence_ids"] = []
    return result


def call_plan(engine, folder, name, system, packet, schema, legacy_schema):
    # Completed old plans are still useful; failed transports are never success.
    candidates = [(system + INSTRUCTION, schema)]
    if "sections" in legacy_schema.get("properties", {}):
        old_wire = copy.deepcopy(legacy_schema)
        section = old_wire["properties"]["sections"]["items"]
        section["properties"].pop("evidence_ids", None)
        section["required"] = [key for key in section["required"] if key != "evidence_ids"]
        candidates.append((system + LEGACY_INSTRUCTION, old_wire))
    candidates.append((system, legacy_schema))
    for cached_system, cached_schema in candidates:
        try:
            cached = engine.call(folder, name, cached_system, packet, cached_schema, cache_only=True)
        except FileNotFoundError:
            continue
        # Current replies still go through normal validation and its cached
        # correction; do not spend another call regenerating a repaired plan.
        if cached_system == system + INSTRUCTION and cached_schema == schema:
            return cached
        if complete_cached_chapters(cached, schema):
            return cached
    return engine.call(folder, name, system + INSTRUCTION, packet, schema, transport_retries=1)
