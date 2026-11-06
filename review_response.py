"""Normalize exact review duplicates and repair invalid reports without rewriting prose."""

import copy
from pathlib import Path

from document_parse import write_json
from paper_plan import object_schema
from drafting_budget import (NO_CACHE, SOURCE_PROTOCOL, cached_response, call_bounded, compact_packet,
                             request_bytes, request_limit)


KEYED_REVIEW = """\n출력 형식: checks는 각 필수 item_id를 키로 하는 객체다.
reference_checks는 section_id 아래 reference_id를 키로 하는 객체다. 스키마의 각 고정 칸을 정확히 한 번 채운다.
필수 항목의 evidence_ids는 사용 가능한 후보 목록이며 전부 사용할 필요는 없다.
description의 핵심 내용이 충족됐는지 평가하고, 실제 선택한 문단에서 그 내용을 뒷받침한 evidence_ids만 보고한다.
검토를 통과시키기 위해 본문에 없는 근거 ID를 채우지 않는다. 해당 항목의 근거가 분산돼 있으면 관련 문단 ID를 모두 선택한다."""

CANDIDATE_REVIEW = """\n근거 사용 정책(candidate-pool-v1): required_items.evidence_ids는 후보 목록이며 필수 인용 목록이 아니다.
사용하지 않은 후보가 있다는 이유로 missing/incorrect/error를 만들거나 후보 내용을 모두 추가하라고 요구하지 않는다.
checks는 description과 연결된 작성 기준의 실제 충족 여부를 판정한다. checks.evidence_ids에는 선택한 실제 본문을
뒷받침하는 사용 근거만 넣고, 해당 문단이 실제 인용한 ID와 일치시킨다. 후보를 전부 나열해 충족으로 꾸미지 않는다.
검토 범위 정책(used-evidence-scope-v1): 항목별 후보 목록은 참고용이다. 현재 장·소절에 배정된 승인 근거를
본문에서 실제 사용했다면 항목의 후보 목록 밖이어도 보고할 수 있다. 후보 목록 밖이라는 이유만으로 오류로 만들지 않는다.
다른 장·소절에만 배정된 근거나 본문에서 인용하지 않은 ID를 사용 근거로 채우지 않는다.
필수 비교의 양쪽 결과·조건처럼 description에 명시한 핵심 내용은 계속 검사한다. 인용 하나만 있으면 met인 것은 아니다.
실제로 쓴 주장의 잘못된 출처·수치·조건·과장은 계속 검사하며, 후보의 사용 개수를 충족률로 삼지 않는다."""


def candidate_review_system(system):
    # Preserve completed writer/plan checkpoint identities. Only review request
    # identities change; old responses made under mandatory-all prompts are not reused.
    legacy_rule = "met은 해당 장의 실제 draft_paragraphs에서 선택한 paragraph_ids와 필수 내용의 모든 evidence_ids가 있어야 한다."
    result = system.replace(legacy_rule, "met은 필수 내용이 실제 본문에서 충족되고 사용한 근거 인용이 연결되어야 한다.")
    return result if CANDIDATE_REVIEW in result else result + CANDIDATE_REVIEW


CORRECTION = """검토 응답의 ID·형식·인용 오류를 고쳐 전체 검토 보고서를 다시 반환한다.
본문은 수정하지 않는다. 원래 연구 근거와 draft_paragraphs를 다시 대조한다.
checks는 expected_item_id를 키로 하는 객체다. reference_checks는 section_id 아래 reference_id를 키로 하는 객체다.
스키마의 키를 정확히 한 번씩 채운다. 항목별 행 배열을 반환하지 않는다.
reference_checks의 한 칸은 해당 가이드 전체의 종합판정이다. 같은 가이드 안의 서로 다른 세부 기준을 별도 행으로 나누지 않는다.
활성 기준 중 일부만 반영됐으면 partial, 모두 반영됐으면 applied, 반영이 보이지 않으면 not_visible로 판단하고 reason에 세부 사유를 함께 적는다.
사용자가 제외·임시 승인한 범위와 적용되지 않는 질문은 그 결정에 맞춰 평가하며, 제외한 내용을 쓰지 않았다는 이유로 누락을 요구하지 않는다.
같은 ID에 상충하는 판정·근거가 있으면 임의로 첫 판정을 선택하지 말고 원문과 본문에 맞는 판정을 다시 결정한다.
알 수 없는 항목·문단·근거 ID는 사용하지 않는다. 형식 오류를 해결하려고 무조건 met으로 바꾸지 않는다."""

COVERAGE_CORRECTION = """필수 내용 검토 응답의 ID·형식·본문 인용만 보정해 전체 보고서를 반환한다.
본문은 수정하지 않고 현재 draft_paragraphs, 필수 내용 description, 관련 작성지침·사용자 승인 범위로 판정한다.
checks는 item_id를 키로, reference_checks는 section_id 아래 reference_id를 키로 하는 객체다.
각 고정 칸을 한 번씩 채우고 같은 가이드의 세부 기준은 하나의 종합판정으로 보고한다.
근거 사용 대조는 선행 단계에서 수행했다. facts·원문을 요구하거나 다시 검증하지 않는다.
선행 검토의 오류를 무시하지 않는다. 실제 본문에 있는 문단·인용 ID만 선택하고, 형식 보정을 위해 met으로 바꾸지 않는다.
사용자 제외·임시 승인 범위를 유지한다."""


def correction_schema(schema, plan):
    """Bind one review slot to each expected item and section/guide pair."""
    properties = schema["properties"]
    check_fields = {k: copy.deepcopy(v) for k, v in properties["checks"]["items"]["properties"].items()
                    if k != "item_id"}
    ref_fields = {k: copy.deepcopy(v) for k, v in properties["reference_checks"]["items"]["properties"].items()
                  if k not in ("section_id", "reference_id")}
    return object_schema({
        "checks": object_schema({item["id"]: object_schema(copy.deepcopy(check_fields))
            for section in plan["sections"] for item in section["required_items"]}),
        "reference_checks": object_schema({section["id"]: object_schema({
            key: object_schema(copy.deepcopy(ref_fields)) for key in section["reference_ids"]})
            for section in plan["sections"] if section["status"] == "write" and section["reference_ids"]}),
        "issues": copy.deepcopy(properties["issues"])})


def expand_keyed_review(raw, plan):
    result = copy.deepcopy(raw)
    expected = {item["id"] for s in plan["sections"] for item in s["required_items"]}
    checks = result["checks"]
    if set(checks) != expected:
        raise ValueError("검토 보정 응답에 필수 항목 ID가 누락·추가됐습니다.")
    refs = result.get("reference_checks")
    expected_refs = {s["id"]: set(s["reference_ids"]) for s in plan["sections"]
                     if s["status"] == "write" and s["reference_ids"]}
    if not isinstance(refs, dict) or set(refs) != set(expected_refs):
        raise ValueError("검토 보정 응답에 참고 가이드의 장 ID가 누락·추가됐습니다.")
    result["checks"] = []
    for key, row in checks.items():
        if not isinstance(row, dict) or set(row) != {"verdict", "paragraph_ids", "evidence_ids"}:
            raise ValueError("검토 보정 응답의 필수 항목 판정 형식이 잘못됐습니다.")
        result["checks"].append({"item_id": key, **row})
    result["reference_checks"] = []
    for sid, rows in refs.items():
        if not isinstance(rows, dict) or set(rows) != expected_refs[sid]:
            raise ValueError("검토 보정 응답에 참고 가이드 ID가 누락·추가됐습니다.")
        for key, row in rows.items():
            if not isinstance(row, dict) or set(row) != {"verdict", "paragraph_ids", "reason"}:
                raise ValueError("검토 보정 응답의 참고 가이드 판정 형식이 잘못됐습니다.")
            result["reference_checks"].append({"section_id": sid, "reference_id": key, **row})
    return result


def normalize_review_response(raw):
    if not isinstance(raw, dict):
        raise ValueError("검토 응답은 객체여야 합니다.")
    result = copy.deepcopy(raw)
    removed = []
    for field, key_fields in (("checks", ("item_id",)),
                              ("reference_checks", ("section_id", "reference_id"))):
        rows = result.get(field)
        if not isinstance(rows, list):
            raise ValueError(f"검토 응답의 {field} 목록이 잘못됐습니다.")
        seen, unique = {}, []
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k].strip() for k in key_fields):
                raise ValueError(f"검토 응답의 {field} ID가 잘못됐습니다.")
            key = tuple(row[k] for k in key_fields)
            if key not in seen:
                seen[key] = row
                unique.append(row)
            elif row == seen[key]:
                removed.append({"field": field, **{k: row[k] for k in key_fields}, "removed_index": index})
            else:
                raise ValueError(f"검토 응답의 {field}에 같은 ID의 서로 다른 판정·근거가 있습니다: {key}")
        result[field] = unique
        for row in unique:
            ids = row.get("paragraph_ids")
            if not isinstance(ids, list) or any(not isinstance(key, str) for key in ids):
                continue
            seen_ids, retained_ids = set(), []
            for index, identifier in enumerate(ids):
                if identifier in seen_ids:
                    removed.append({"field": field, **{k: row[k] for k in key_fields},
                                    "removed_paragraph_id": identifier, "removed_index": index})
                else:
                    seen_ids.add(identifier)
                    retained_ids.append(identifier)
            row["paragraph_ids"] = retained_ids
    result["response_normalizations"] = removed
    return result


def checked_review(raw, plan, bodies):
    from planned_paper import index_paragraphs, materialize_review, validate_review
    if isinstance(raw, dict) and isinstance(raw.get("checks"), dict):
        raw = expand_keyed_review(raw, plan)
    normalized = normalize_review_response(raw)
    return validate_review(materialize_review(normalized, plan, index_paragraphs(bodies)), plan, bodies)


def defer_unlinked_references(raw, plan, bodies):
    """After one correction, retain unverified guide judgments as warnings.

    Only empty selections are downgraded. Revalidate the entire report so this
    cannot hide an unknown ID, another section's paragraph, or an invalid issue.
    """
    from planned_paper import fingerprint
    result = expand_keyed_review(raw, plan) if isinstance(raw, dict) and isinstance(raw.get("checks"), dict) else copy.deepcopy(raw)
    result = normalize_review_response(result)
    changes = []
    for check in result["reference_checks"]:
        if check.get("verdict") not in ("applied", "partial") or check.get("paragraph_ids") != []:
            continue
        original = copy.deepcopy(check)
        check.update(verdict="not_visible", model_verdict=original["verdict"], review_status="incomplete",
                     validation_note="가이드 반영 판정의 실제 본문 연결을 보정 후에도 확인하지 못했습니다.")
        result["issues"].append({"section_id": check["section_id"], "paragraph_id": "none", "quote": "",
            "severity": "warning", "original_severity": "error", "deferred": True,
            "evidence_ids": [], "failure_owner": "reviewer", "review_stage": "reference_application",
            "validation_code": "reference_link_incomplete", "reference_id": check["reference_id"],
            "review_status": "incomplete", "repair_attempts": 1,
            "reason": f"참고 가이드 {check['reference_id']}: 원래 판정={original['verdict']}. "
                      f"검토 응답 보정 1회 후에도 관련 문단이 선택되지 않아 반영 확인을 보류합니다. 원래 사유: {check['reason']}"})
        changes.append({"section_id": check["section_id"], "reference_id": check["reference_id"],
                        "original_check": original, "effective_verdict": "not_visible", "review_status": "incomplete"})
    if not changes:
        return None
    report = checked_review(result, plan, bodies)
    diagnostic = {"policy": "reference-link-completion-v1", "repair_attempts": 1,
                  "body_fingerprint": fingerprint(bodies), "body_rewritten": False,
                  "original_response_fingerprint": fingerprint(raw), "normalized_response_fingerprint": fingerprint(result),
                  "changes": changes}
    return result, report, diagnostic


def reference_metrics(checks):
    result = {verdict: sum(c["verdict"] == verdict and c.get("review_status") != "incomplete" for c in checks)
              for verdict in ("applied", "partial", "not_visible")}
    incomplete = sum(c.get("review_status") == "incomplete" for c in checks)
    if incomplete:
        result["incomplete"] = incomplete
    return {**result, "total": len(checks)}


def review_correction_packet(packet, plan, rejected, error):
    return {**packet, "rejected_review": rejected, "validation_error": str(error),
        "expected_item_ids": [item["id"] for s in plan["sections"] for item in s["required_items"]],
        "required_reference_pairs": [{"section_id": s["id"], "reference_id": key}
            for s in plan["sections"] if s["status"] == "write" for key in s["reference_ids"]]}


def review_correction_system(system, packet):
    return system + "\n" + (COVERAGE_CORRECTION if packet.get("coverage_policy") == "content-coverage-v2" else CORRECTION)


def fits_review_request(system, packet, schema, plan):
    """Budget the actual fixed-key schema, including bounded repair metadata."""
    wire = correction_schema(schema, plan)
    repair = review_correction_packet(packet, plan, {"response_preserved_on_disk": True}, "검토 응답의 ID·형식·본문 인용을 보정한다.")
    return (request_bytes(system + KEYED_REVIEW, compact_packet(packet), wire) <= request_limit()
            and request_bytes(review_correction_system(system, packet), compact_packet(repair), wire) <= request_limit())


def review_with_repair(engine, folder, name, system, packet, schema, plan, bodies):
    folder = Path(folder)
    raw = NO_CACHE
    # Existing valid reviews and their bounded corrections remain reusable.
    # New calls bind item/guide IDs from the start instead of permitting rows
    # with duplicate IDs and spending a second call to fix them.
    for old_system, old_packet in ((system, packet), (system + SOURCE_PROTOCOL, compact_packet(packet))):
        raw = cached_response(engine, folder, name, old_system, old_packet, schema)
        if raw is not NO_CACHE:
            break
    if raw is NO_CACHE:
        raw = call_bounded(engine, folder, name, system + KEYED_REVIEW, packet, correction_schema(schema, plan),
                           source_protocol=packet.get("review_policy") != "approved-facts-v1")
    for attempt in range(2):
        try:
            return raw, checked_review(raw, plan, bodies)
        except (ValueError, KeyError, TypeError) as error:
            rejected = {"raw_response": raw, "validation_error": str(error)}
            write_json(folder / f"{name}-validation-{attempt}.json", rejected)
            if attempt:
                try:
                    deferred = defer_unlinked_references(raw, plan, bodies)
                except (ValueError, KeyError, TypeError):
                    deferred = None  # Other invalid fields still block the run.
                if deferred is not None:
                    normalized, report, diagnostic = deferred
                    write_json(folder / f"{name}-reference-link-completion-v1.json", diagnostic)
                    return normalized, report
                raise ValueError(f"{name}: 검토 응답 보정 후에도 ID·근거·본문 인용 검증을 통과하지 못했습니다. "
                                 f"원인: {error} 후보 본문과 검토 응답은 {folder}에 보존했습니다.") from error
            correction_packet = review_correction_packet(packet, plan, raw, error)
            correction_system = review_correction_system(system, packet)
            wire = correction_schema(schema, plan)
            cached = cached_response(engine, folder, name + "-correction-1", correction_system, correction_packet, wire)
            if cached is not NO_CACHE:
                raw = cached
                continue
            original_size = request_bytes(correction_system, compact_packet(correction_packet), wire)
            if original_size > request_limit():
                summary = {"response_preserved_on_disk": True, "response_type": type(raw).__name__}
                if isinstance(raw, dict):
                    summary["field_counts"] = {k: len(v) for k, v in raw.items() if k in ("checks", "reference_checks", "issues") and isinstance(v, (list, dict))}
                correction_packet = review_correction_packet(packet, plan, summary, error)
                correction_packet["repair_input_policy"] = "review-diagnostics-only-v1"
                correction_packet["repair_instruction"] = "실패한 검토 응답 전체는 별도 보존했다. 현재 본문·계획·승인 범위와 validation_error로 전체 고정 칸을 다시 판정한다. 판정을 추측하거나 형식 보정을 위해 met으로 바꾸지 않는다."
                write_json(folder / f"{name}-correction-input.json", {"policy": "review-diagnostics-only-v1",
                    "original_input_bytes": original_size,
                    "input_bytes": request_bytes(correction_system, compact_packet(correction_packet), wire),
                    "limit_bytes": request_limit(), "original_response_path": str(folder / f"{name}-validation-0.json"),
                    "original_packet_preserved": all(correction_packet[k] == v for k, v in packet.items())})
            raw = call_bounded(engine, folder, name + "-correction-1", correction_system,
                              correction_packet, wire,
                              source_protocol=packet.get("review_policy") != "approved-facts-v1")
