"""Legacy citation-response replay helper; runtime sends fixes directly to the writer."""

import copy
import re

from document_parse import write_json
from drafting_budget import call_bounded, fits_request
from paper_plan import object_schema

INSTRUCTION = """기존 소절 본문의 누락 인용 연결만 확인한다. 본문을 작성하거나 수정하지 않는다.
각 근거의 실제 원문·조건·한계와 candidate_paragraphs를 대조한다.
해당 근거의 내용이 이미 쓰인 문단이 있을 때만 그 paragraph_id와 본문의 연속된 정확한 구절 support_quote를 반환한다.
주제나 단어만 비슷한 문단에 연결하지 않는다. 원문이 뒷받침하지 않는 확대·인과·수치가 있으면 연결하지 않는다.
그 내용이 본문에 없거나 판단할 수 없으면 paragraph_id=none, support_quote=""로 반환한다.
필수 ID를 모두 붙여 통과시키는 것이 목적이 아니다. 사용자 임시 승인 범위도 유지한다.
links의 고정된 근거 ID별 칸만 채운다. 새 본문이나 다른 근거 ID는 반환하지 않는다."""


def link_only_gaps(report):
    """Do not use citation-only revision for any substantive review failure."""
    failed = [c for c in report["checks"] if c["verdict"] in ("missing", "incorrect")]
    if not failed or any(c.get("model_verdict") != "met"
                         or c.get("failure_owner") == "reviewer"
                         or not c.get("missing_body_evidence_ids")
                         or c.get("missing_review_evidence_ids")
                         or not c.get("paragraph_ids") for c in failed):
        return []
    errors = [i for i in report["issues"] if i["severity"] == "error"]
    if (not errors or any(i.get("validation_code") != "required_content" for i in errors)
            or {i.get("item_id") for i in errors} != {c["item_id"] for c in failed}):
        return []
    return failed


def repair_leaf_citations(engine, folder, name, grounding, sections, bodies, packets, report):
    from planned_paper import fingerprint, index_paragraphs

    gaps = link_only_gaps(report)
    if not gaps or len(packets) != 1:
        return None
    sid, packet = next(iter(packets.items()))
    if packet["subsection_headings"] or set(sections[sid]["parts"]) != {"p0"}:
        return None
    paragraphs = index_paragraphs(bodies)
    segments = re.split(r"(\n\s*\n)", sections[sid]["parts"]["p0"])
    positions = [i for i in range(0, len(segments), 2) if segments[i].strip()]
    if [segments[i].strip() for i in positions] != [p["text"] for p in paragraphs.values()]:
        return None
    locations = dict(zip(paragraphs, positions))
    facts = {f["id"]: f for f in packet["facts"]}
    candidates = {}
    for check in gaps:
        for key in check["missing_body_evidence_ids"]:
            if key not in facts:
                return None
            candidates.setdefault(key, {})
            for pid in check["paragraph_ids"]:
                if pid not in paragraphs or paragraphs[pid]["section_id"] != sid:
                    return None
                candidates[key][pid] = paragraphs[pid]
    schema = object_schema({"links": object_schema({key: object_schema({
        "paragraph_id": {"type": "string", "enum": ["none", *rows]},
        "support_quote": {"type": "string"}}) for key, rows in candidates.items()})})
    request = {"workflow_stage": "subsection", "operation": "citation_links_only",
               "facts": [copy.deepcopy(facts[key]) for key in candidates],
               "candidate_paragraphs": candidates,
               "human_guidance": copy.deepcopy(packet.get("human_guidance", []))}
    system = grounding + "\n" + INSTRUCTION
    audit = {"before_sha256": fingerprint(sections), "missing_evidence_ids": list(candidates)}
    audit_path = folder / f"{name}.json"
    if not fits_request(system, request, schema):
        write_json(audit_path, {**audit, "status": "skipped_input_budget"})
        return None
    raw = call_bounded(engine, folder, name, system, request, schema)
    try:
        if not isinstance(raw, dict) or set(raw) != {"links"} or not isinstance(raw["links"], dict) or set(raw["links"]) != set(candidates):
            raise ValueError("누락 근거별 인용 연결 칸이 일치하지 않습니다.")
        additions = {}
        for key, row in raw["links"].items():
            if (not isinstance(row, dict) or set(row) != {"paragraph_id", "support_quote"}
                    or not isinstance(row["paragraph_id"], str) or not isinstance(row["support_quote"], str)):
                raise ValueError("인용 연결 응답 형식이 잘못됐습니다.")
            pid, quote = row["paragraph_id"], row["support_quote"]
            if pid == "none":
                if quote:
                    raise ValueError("연결하지 않은 근거에 본문 구절이 있습니다.")
                continue
            if pid not in candidates[key]:
                raise ValueError("배정 범위 밖 문단에 인용을 연결했습니다.")
            plain = re.sub(r"\[근거:\s*[^\]]+\]", "", paragraphs[pid]["text"])
            if not quote.strip() or quote not in plain:
                raise ValueError("인용 연결의 구절이 실제 본문에 없습니다.")
            additions.setdefault(pid, []).append(key)
        if not additions:
            write_json(audit_path, {**audit, "status": "no_supported_link", "response": raw})
            return None
        result = copy.deepcopy(sections)
        for pid, ids in additions.items():
            index = locations[pid]
            segments[index] += " [근거:" + ",".join(ids) + "]"
        result[sid]["parts"]["p0"] = "".join(segments)
        write_json(audit_path, {**audit, "status": "awaiting_review", "response": raw,
                                "after_sha256": fingerprint(result), "sections": result})
        return result
    except (ValueError, KeyError, TypeError) as error:
        # Keep the original body and fall back to the normal content revision.
        write_json(audit_path, {**audit, "status": "rejected", "response": raw, "reason": str(error)})
        return None
