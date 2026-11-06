"""Bound editorial rechecks by current text and pending findings, preserving history."""

import copy
import json
from pathlib import Path

from document_parse import write_json
from drafting_budget import (DraftingBudgetError, NO_CACHE, cached_response, call_bounded,
                             compact_packet, fits_request, request_bytes, request_limit)
from editorial_review import INSTRUCTION, POLICY as REVIEW_POLICY, checked_editorial_review, editorial_schema
from paper_plan import object_schema

POLICY = "editorial-recheck-v3"
LEGACY_POLICY = "editorial-recheck-v2"


def recheck_packet(level, outline, paragraphs, findings, policy=POLICY):
    from planned_paper import fingerprint
    rows, quotes = [], {}
    for index, issue in findings:
        row = {key: copy.deepcopy(issue[key]) for key in ("section_id", "paragraph_id", "category", "severity", "reason")}
        quote = issue["quote"]
        reference = "none"
        if quote:
            origin = {"section_id": issue["section_id"], "paragraph_id": issue["paragraph_id"], "text": quote}
            reference = "old_" + fingerprint(origin)
            quotes[reference] = origin
        rows.append({**row, "finding_id": f"finding-{index}", "quote_ref": reference})
    return {"operation": "editorial_review", "workflow_stage": level, "outline": outline,
            "draft_paragraphs": paragraphs, "review_scope": "previous_findings_only", "recheck_policy": policy,
            "previous_findings": rows, "previous_paragraphs": quotes}


def review_editorial_recheck(engine, folder, name, level, plan, bodies, children, pending):
    if pending:
        try:
            return _review_recheck(engine, folder, name, level, plan, bodies, children, pending, LEGACY_POLICY, cache_only=True)
        except (FileNotFoundError, ValueError):
            pass
    return _review_recheck(engine, folder, name, level, plan, bodies, children, pending, POLICY)


def finding_schema(paragraphs, selected):
    return object_schema({"findings": object_schema({f"finding-{index}": object_schema({
        "status": {"type": "string", "enum": ["resolved", "unresolved", "not_assessable"]},
        "paragraph_id": {"type": "string", "enum": ["none", *[pid for pid, row in paragraphs.items()
            if row["section_id"] == issue["section_id"]]]}}) for index, issue in selected})})


def checked_finding_statuses(response, paragraphs, selected):
    expected = {f"finding-{index}": issue for index, issue in selected}
    if not isinstance(response, dict) or set(response) != {"findings"}:
        raise ValueError("편집 재검토는 findings의 고정 칸에 지적별 상태를 반환해야 합니다.")
    rows = response["findings"]
    if not isinstance(rows, dict) or set(rows) != set(expected):
        raise ValueError("편집 재검토의 기존 지적 ID가 누락·추가됐습니다.")
    for key, row in rows.items():
        if (not isinstance(row, dict) or set(row) != {"status", "paragraph_id"}
                or row["status"] not in ("resolved", "unresolved", "not_assessable")
                or not isinstance(row["paragraph_id"], str)):
            raise ValueError(f"편집 재검토 {key}의 상태·문단 형식이 잘못됐습니다.")
        pid = row["paragraph_id"]
        if pid != "none" and (pid not in paragraphs or paragraphs[pid]["section_id"] != expected[key]["section_id"]):
            raise ValueError(f"편집 재검토 {key}가 현재 입력 또는 해당 장에 없는 문단을 선택했습니다.")
        if row["status"] != "unresolved" and pid != "none":
            raise ValueError(f"편집 재검토 {key}: 해결·확인 불가 상태의 paragraph_id는 none이어야 합니다.")
    return copy.deepcopy(rows)


def _review_recheck(engine, folder, name, level, plan, bodies, children, pending, policy, cache_only=False):
    from planned_paper import fingerprint, index_paragraphs
    folder = Path(folder)
    paragraphs = index_paragraphs(bodies)
    original = copy.deepcopy(pending)
    sections = {s["id"] for s in plan["sections"] if s["status"] == "write"}
    outline = [{key: copy.deepcopy(s[key]) for key in ("id", "title", "purpose", "subsections")} for s in plan["sections"]]
    findings = list(enumerate(pending))
    if any(i["section_id"] not in sections for i in pending):
        raise ValueError("편집 재검토 지적의 장이 현재 계획에 없습니다.")
    system = INSTRUCTION + ("\n소절들을 엮은 현재 절의 편집 품질을 검토한다." if level == "section" else "\n전체 논문의 절 간 연결과 일관성을 검토한다.")
    system += "\nprevious_findings에 배정한 기존 지적의 해결 여부만 확인한다. 새로운 지적을 추가하지 않는다. " \
        "각 quote_ref의 이전 본문은 previous_paragraphs에 한 번 저장되어 있다. none은 이전 인용문이 없다는 뜻이다. " \
        "이전 paragraph_id는 삭제·통합·재번호화될 수 있으므로 ID 일치가 아니라 이전 인용문·사유와 현재 본문을 대조한다. " \
        "해결한 지적은 반환하지 않고 미해결 지적만 현재 draft_paragraphs의 문단 ID로 반환한다."
    if policy == POLICY:
        system = system.replace("실제 글에서 확인되는 편집 문제만 issues에 반환한다.", "기존 편집 지적의 해결 여부만 반환한다.")
        system = system.replace(" 글의 흐름을 방해하는 문제는 error,\n선택적인 문체 개선은 warning이다.", "")
        system = system.replace("해결한 지적은 반환하지 않고 미해결 지적만 현재 draft_paragraphs의 문단 ID로 반환한다.",
            "findings의 각 finding_id 고정 칸을 한 번씩 채운다. status와 paragraph_id만 반환한다. "
            "기존 지적이 해결됐으면 resolved, 남아 있으면 unresolved, 현재 문맥으로 확인할 수 없으면 not_assessable이다. "
            "resolved와 not_assessable의 paragraph_id는 none이다. unresolved는 해당 장의 실제 문단 ID를 선택하며 "
            "장 전체 문제이면 none으로 둔다. 사유·유형·심각도·본문을 다시 쓰지 않는다. 코드는 원래 지적을 보존한다.")

    def packet_for(rows, selected):
        return recheck_packet(level, outline, rows, selected, policy)

    def schema_for(rows, selected):
        return finding_schema(rows, selected) if policy == POLICY else editorial_schema(plan, rows)
    # Retain all original findings (including warnings and quotes) locally.
    audit_path = folder / f"{name}-{policy}-input.json"
    audit = {"policy": policy, "original_findings": original, "draft_paragraphs": paragraphs, "batches": []}
    if not cache_only:
        write_json(audit_path, audit)
    if not findings:
        audit["coverage"] = {"findings": 0, "total_findings": 0, "context_paragraphs": 0}
        if not cache_only:
            write_json(audit_path, audit)
        raw = {"review_policy": REVIEW_POLICY, "issues": []}
        return raw, checked_editorial_review(raw, plan, bodies, children)

    def eligible(rows):
        # Do not filter by old paragraph IDs: those may have been renumbered.
        # A section's findings remain available in every relevant text window.
        sids = {row["section_id"] for row in rows.values()}
        return [pair for pair in findings if pair[1]["section_id"] in sids]

    costs = {index: len(json.dumps(packet_for({}, [(index, issue)]), ensure_ascii=False).encode())
             for index, issue in findings}

    def fits(rows, selected):
        return fits_request(system, packet_for(rows, selected), schema_for(rows, selected))

    def fits_one(rows):
        relevant = eligible(rows)
        worst = [max(relevant, key=lambda pair: costs[pair[0]] + len(json.dumps(
            schema_for(rows, [pair]), ensure_ascii=False).encode()))] if relevant else []
        return fits(rows, worst)

    def over_budget(label, rows, selected):
        packet = packet_for(rows, selected)
        schema = schema_for(rows, selected)
        size = request_bytes(system, compact_packet(packet), schema)
        diagnostic = folder / f"{name}-{policy}-budget-failure.json"
        if cache_only:
            raise FileNotFoundError("기존 편집 재검토 입력이 현재 예산을 넘습니다.")
        write_json(diagnostic, {"label": label, "input_bytes": size,
            "packing_budget_bytes": int(request_limit() * .75),
            "paragraph_bytes": sum(len(r["text"].encode()) for r in rows.values()),
            "finding_ids": [f"finding-{index}" for index, _ in selected],
            "history_bytes": len(json.dumps({key: packet[key] for key in ("previous_findings", "previous_paragraphs")}, ensure_ascii=False).encode())})
        raise DraftingBudgetError(f"편집 재검토의 {label} 입력 예산 초과: {size}바이트. 본문·지적은 보존했습니다. 상세: {diagnostic}")

    windows, current = [], {}
    for pid, paragraph in paragraphs.items():
        proposed = {**current, pid: paragraph}
        if fits_one(proposed):
            current = proposed
            continue
        if not current:
            over_budget(f"문단 {pid}와 이전 지적", proposed, eligible(proposed))
        windows.append(current)
        last = next(reversed(current))
        current = {last: current[last], pid: paragraph}
        if not fits_one(current):
            over_budget(f"인접 문단 {last}/{pid}와 이전 지적", current, eligible(current))
    if current:
        windows.append(current)
    tasks = []
    for rows in windows:
        selected = []
        for pair in eligible(rows):
            if fits(rows, selected + [pair]):
                selected.append(pair)
                continue
            if selected:
                tasks.append((rows, selected))
            selected = [pair]
            if not fits(rows, selected):
                over_budget("본문과 단일 지적", rows, selected)
        if selected:
            tasks.append((rows, selected))
    covered = {index for _, selected in tasks for index, _ in selected}
    if covered != {index for index, _ in findings}:
        raise ValueError("편집 재검토 입력에 이전 지적이 누락됐습니다.")
    for index, (rows, selected) in enumerate(tasks):
        packet = packet_for(rows, selected)
        audit["batches"].append({"index": index, "paragraph_ids": list(rows),
            "finding_ids": [row["finding_id"] for row in packet["previous_findings"]],
            "quote_refs": list(packet["previous_paragraphs"]),
            "input_bytes": request_bytes(system, compact_packet(packet), schema_for(rows, selected))})
    audit["coverage"] = {"findings": len(covered), "total_findings": len(findings),
                         "context_paragraphs": len({pid for rows, _ in tasks for pid in rows})}
    if not cache_only:
        write_json(audit_path, audit)
    combined = {"review_policy": REVIEW_POLICY, "issues": []}
    statuses = {}
    for index, (rows, selected) in enumerate(tasks):
        request = packet_for(rows, selected)
        schema = schema_for(rows, selected)
        error = None
        for repair in range(2):
            body = request if error is None else {**request, "invalid_review": error,
                "repair_instruction": ("본문과 이전 지적은 유지하고 배정된 finding_id 고정 칸의 상태·문단 ID만 보정한다. 사유나 본문은 출력하지 않는다."
                    if policy == POLICY else "본문과 이전 지적은 유지하고 현재 묶음의 장·문단 ID와 편집 문제 유형만 보정한다.")}
            call_name = f"{name}-{policy}-{index}" + ("-format-repair" if repair else "")
            if cache_only:
                response = cached_response(engine, folder, call_name, system, compact_packet(body), schema)
                if response is NO_CACHE:
                    raise FileNotFoundError("완료한 기존 편집 재검토 응답이 없습니다.")
            else:
                response = call_bounded(engine, folder, call_name, system, body, schema, source_protocol=False)
            try:
                if policy == POLICY:
                    result = checked_finding_statuses(response, rows, selected)
                    for key, row in result.items():
                        statuses.setdefault(key, []).append(row)
                    break
                for issue in response.get("issues", []):
                    if issue.get("paragraph_id") != "none" and issue.get("paragraph_id") not in rows:
                        raise ValueError("편집 재검토가 현재 입력에 없는 문단을 인용했습니다.")
                    if not any(issue.get("section_id") == old["section_id"] and issue.get("category") == old["category"]
                               for _, old in selected):
                        raise ValueError("편집 재검토가 현재 묶음의 기존 지적 밖의 장·문제 유형을 추가했습니다.")
                checked_editorial_review(response, plan, bodies, children)
                combined["issues"].extend(response["issues"])
                break
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                error = {"response": response, "reason": str(exc)}
                if not cache_only:
                    write_json(folder / f"{name}-{policy}-{index}-invalid-{repair}.json", error)
        else:
            raise ValueError(f"편집 재검토 {name} 묶음 {index}의 JSON·문단 ID 보정에 실패했습니다.")
    if policy == POLICY:
        for index, issue in findings:
            key = f"finding-{index}"
            results = statuses[key]
            unresolved = next((r for r in results if r["status"] == "unresolved"), None)
            if unresolved is None and any(r["status"] == "resolved" for r in results):
                continue
            combined["issues"].append({**{k: copy.deepcopy(issue[k]) for k in ("section_id", "category", "severity", "reason")},
                "paragraph_id": unresolved["paragraph_id"] if unresolved else "none",
                "reason": issue["reason"] if unresolved else "편집 재검토에서 해결 여부를 확인하지 못했습니다. 기존 지적: " + issue["reason"]})
        write_json(folder / f"{name}-{policy}-results.json", {"policy": policy, "finding_statuses": statuses,
                   "unresolved_finding_count": len(combined["issues"]), "total_findings": len(findings),
                   "body_fingerprint": fingerprint(bodies), "body_rewritten": False})
    combined["issues"] = list({str(sorted(i.items())): i for i in combined["issues"]}.values())
    return combined, checked_editorial_review(combined, plan, bodies, children)
