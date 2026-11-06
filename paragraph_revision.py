"""Replace one identified paragraph; never expand it into a section draft."""

import copy
import math
import re
from pathlib import Path

from document_parse import write_json
from draft_prose import PROTOCOL, JoinedParagraphsError, prose_schema, render_parts, structured_system
from drafting_budget import (DraftingBudgetError, NO_CACHE, SOURCE_PROTOCOL, cached_response,
                             call_bounded, compact_packet)
from writing_length import narrative_chars

POLICY = "paragraph-replacement-v1"
CITATION_POLICY = "paragraph-citations-v2"
LEGACY_INSTRUCTION = """\n문단 교체 정책 paragraph-replacement-v1:
source_body의 지정된 한 문단을 그 자리에 대체한다. 새 절·서론·환경·요약을 추가하지 않는다.
section_context는 읽기 전용 문맥이며 그 필수 항목을 모두 다시 작성할 의무가 아니다.
수정 의무는 revision.review의 현재 문단 지적과 명시적으로 배정된 미충족 항목뿐이다.
출력은 parts.p0의 단일 text/evidence_ids 객체다. 문단 배열·빈 줄로 구분한 여러 문단을 반환하지 않는다.
원문에 필요한 조건·반례·귀속·확실성 수준과 인용을 유지하고 지적된 부분만 고친다.
replacement_max_chars 안에서 중복을 줄인다. 글자 수를 맞추려고 문장·수치·조건을 중간에서 자르지 않는다."""
INSTRUCTION = LEGACY_INSTRUCTION.replace(
    "원문에 필요한 조건·반례·귀속·확실성 수준과 인용을 유지하고 지적된 부분만 고친다.",
    "원문에 필요한 조건·반례·귀속·확실성 수준과 근거 연결을 유지하고 지적된 부분만 고친다.") + """
문단 인용 출력 규칙 paragraph-citations-v2:
source_body는 표시용 인용을 분리한 본문이며 source_evidence_ids가 이전 문단의 근거 연결이다.
이전 인용을 보존하라는 지시는 근거 연결을 보존하라는 뜻이다. 출력 text에는 [근거:...] 표시를 넣지 않는다.
출력의 인용 정보는 evidence_ids 한 곳에만 둔다. 표시는 코드가 조립한다.
evidence_ids에는 수정한 문단을 실제로 뒷받침하는 배정 ID만 선택한다. 후보·비교 묶음 전체를 일괄 연결하지 않는다.
E·H 등 ID 접두사는 입력 그대로 사용한다. 서로 다른 접두사의 ID를 추측해서 대응시키지 않는다.
replacement_validation_error가 있으면 실패 응답의 형식을 바로잡되 원래 검토 지적도 반영한다.
특히 text의 인용 표시와 evidence_ids가 충돌했다면 text에서 표시를 빼고 실제 사용 근거만 evidence_ids로 반환한다."""


def local_issues(report, pid, body, meta):
    from writing_policy import NARRATOR
    result = []
    for issue in report.get("issues", []):
        target = issue.get("paragraph_id")
        if target == pid:
            result.append(copy.deepcopy(issue))
        elif target in (None, "none"):
            code = issue.get("validation_code")
            if code == "composition_style" and NARRATOR.search(body):
                result.append(copy.deepcopy(issue))
            elif code == "composition_layout" and narrative_chars(body) > meta.get("max_paragraph_chars", 600):
                result.append(copy.deepcopy(issue))
            elif code not in ("composition_length", "composition_layout", "composition_style"):
                from bounded_drafting import cited_ids
                if (set(issue.get("evidence_ids", [])) & cited_ids(body)
                        or meta.get("single_paragraph") and not issue.get("evidence_ids")):
                    result.append(copy.deepcopy(issue))
    return result


def scope_request(packet):
    result = copy.deepcopy(packet)
    pid = result["fragment"]["paragraph_id"]
    feedback = result.get("revision", {})
    report = feedback.get("review", {})
    single = result["fragment"].get("whole_part_single_paragraph", False)
    checks = [c for c in report.get("checks", [])
              if (pid in c.get("paragraph_ids", []) or single and not c.get("paragraph_ids")) and c.get("verdict") in ("missing", "incorrect", "needs_check")
              and c.get("model_verdict") != "met"]
    obligations = {c["item_id"] for c in checks}
    plan = result["section_plan"]
    if "section_context" not in result:
        result["section_context"] = {k: copy.deepcopy(plan[k]) for k in ("id", "title", "role", "purpose") if k in plan}
        result["section_context"]["required_content_context"] = [
            {k: copy.deepcopy(item[k]) for k in ("id", "description") if k in item} for item in plan.get("required_items", [])]
    plan["required_items"] = [item for item in plan.get("required_items", []) if item["id"] in obligations]
    issues = local_issues(report, pid, result["source_body"], {**result.get("composition_policy", {}), "single_paragraph": single})
    for issue in issues:
        if issue.get("quote", "").strip() == result["source_body"].strip():
            issue.pop("quote", None)
    feedback["review"] = {"checks": [{**{k: v for k, v in c.items() if k not in ("paragraph_quotes", "quote", "paragraph_ids")},
                                      "paragraph_ids": [pid]} for c in checks],
                          "issues": issues, "approved": report.get("approved", False)}
    feedback["content_repair_instruction"] = "현재 한 문단에 연결된 지적만 수정한다. 절 전체 축약·구성 지적은 읽기 전용이며 이 문단에서 전부 해결하지 않는다."
    feedback["scope"] = {"policy": POLICY, "paragraph_id": pid}
    result["revision"] = feedback
    result["fragment"]["replacement_policy"] = POLICY
    size = narrative_chars(result["source_body"])
    maximum = math.ceil(size * result.get("composition_policy", {}).get("length_tolerance_ratio", 1.25))
    budget = result.get("writing_budget")
    if budget:
        maximum = min(maximum, max(size, budget["target_chars"]))
    maximum = min(maximum, result.get("composition_policy", {}).get("max_paragraph_chars", 600))
    result["replacement_max_chars"] = max(1, maximum)
    return result


def schema_for(packet):
    schema = prose_schema(packet)
    paragraph = schema["properties"]["parts"]["properties"]["p0"]["items"]
    paragraph["properties"]["text"]["maxLength"] = packet["replacement_max_chars"]
    schema["properties"]["parts"]["properties"]["p0"] = paragraph
    return schema


class ParagraphGrowthError(ValueError):
    pass


def render_replacement(raw, packet):
    value = copy.deepcopy(raw)
    part = value.get("parts", {}).get("p0") if isinstance(value, dict) else None
    if isinstance(part, dict):
        value["parts"]["p0"] = [part]
    # Legacy-shaped custom clients remain supported only if the same strict
    # paragraph/citation/length contract passes. Their old cache is not selected.
    try:
        body = render_parts(value, packet)["parts"]["p0"]
    except JoinedParagraphsError as exc:
        raise ParagraphGrowthError("교체 문단의 text에 여러 문단이 합쳐져 있습니다.") from exc
    if len(re.split(r"\n\s*\n", body.strip())) != 1:
        raise ParagraphGrowthError("지정된 한 문단 대신 여러 문단을 반환했습니다.")
    if narrative_chars(body) > packet["replacement_max_chars"]:
        raise ParagraphGrowthError(f"교체 문단이 허용 분량 {packet['replacement_max_chars']}자를 넘었습니다.")
    return body


def replacement_system(system):
    return structured_system(system).replace(PROTOCOL, "") + INSTRUCTION


def replacement_input(request):
    """Separate rendered citations at the model boundary; retain the saved prose."""
    result = copy.deepcopy(request)
    source = result["source_body"]
    result["source_evidence_ids"] = list(dict.fromkeys(
        key for group in re.findall(r"\[근거:\s*([^\]]+)\]", source)
        for key in re.split(r"[,，;·\s]+", group.strip()) if key))
    result["source_body"] = re.sub(r"\[근거:\s*[^\]]+\]", "", source).strip()
    return result


def reusable_legacy_replacement(engine, folder, name, system, request, schema):
    """Reuse only old replies that pass the complete current paragraph contract."""
    old_system = structured_system(system).replace(PROTOCOL, "") + LEGACY_INSTRUCTION
    error = None
    for attempt in range(2):
        body = request if error is None else {**request, "replacement_validation_error": error}
        old_name = name + "-" + POLICY + ("-repair" if attempt else "")
        raw = NO_CACHE
        for cached_system, cached_packet in ((old_system, body),
                (old_system + SOURCE_PROTOCOL, compact_packet(body))):
            raw = cached_response(engine, folder, old_name, cached_system, cached_packet, schema)
            if raw is not NO_CACHE:
                break
        if raw is NO_CACHE:
            break
        try:
            return render_replacement(raw, request)
        except (ValueError, KeyError, TypeError) as exc:
            error = {"reason": str(exc)}
    return NO_CACHE


def deferred_warning(request, reason, repair_attempts=1):
    from bounded_drafting import cited_ids
    fragment = request["fragment"]
    return {"section_id": fragment["section_id"], "part": fragment["part"],
        "paragraph_id": fragment["paragraph_id"], "evidence_ids": sorted(cited_ids(request["source_body"])),
        "severity": "warning", "original_severity": "error", "deferred": True,
        "validation_code": "paragraph_revision_deferred", "review_stage": "generation_completion",
        "failure_owner": "writer", "repair_attempts": repair_attempts, "reason": reason}


def replace_paragraph(engine, folder, name, system, packet):
    request = scope_request(packet)
    schema = schema_for(request)
    cached = reusable_legacy_replacement(engine, folder, name, system, request, schema)
    if cached is not NO_CACHE:
        return cached, None
    system = replacement_system(system)
    wire_request = replacement_input(request)
    request_name = name + "-" + POLICY + "-" + CITATION_POLICY
    error = None
    for attempt in range(2):
        body = wire_request if error is None else {**wire_request, "replacement_validation_error": error}
        try:
            raw = call_bounded(engine, folder, request_name + ("-repair" if attempt else ""),
                               system, body, schema)
        except DraftingBudgetError:
            warning = deferred_warning(request, "한 문단 교체의 원문·비교 근거 입력이 예산을 넘어 기존 문단을 보존했습니다.", 0)
            return request["source_body"], warning
        try:
            text = render_replacement(raw, request)
            write_json(Path(folder) / f"{request_name}-applied.json", {
                "policy": POLICY, "citation_policy": CITATION_POLICY, "paragraph_id": request["fragment"]["paragraph_id"],
                "before_chars": narrative_chars(request["source_body"]), "after_chars": narrative_chars(text),
                "max_chars": request["replacement_max_chars"], "paragraph_count": 1})
            return text, None
        except (ValueError, KeyError, TypeError) as exc:
            error = {"reason": str(exc)}
            write_json(Path(folder) / f"{request_name}-invalid-{attempt}.json", {"response": raw, **error})
            if attempt:
                if isinstance(exc, ParagraphGrowthError):
                    return request["source_body"], deferred_warning(request, "문단 교체 보정 후에도 문단 수·분량이 늘어나 기존 문단을 보존했습니다.")
                raise ValueError(f"{name}: 한 문단 교체의 본문·근거 형식 보정에 실패했습니다. 원인: {exc}") from exc
