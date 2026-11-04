"""Defer unresolved content judgments after bounded writer revisions."""

import copy

POLICY = "content-warning-v1"
MAX_REVISIONS = 2


def reconcile_generation_warnings(warnings, sections, packets):
    """Retain only source-bound gaps still absent from the latest complete part."""
    from bounded_drafting import cited_ids
    from draft_prose import allowed_ids
    result = {}
    for warning in warnings:
        sid, part = warning["section_id"], warning["part"]
        if (warning.get("validation_code") != "fragment_missing_evidence"
                or warning.get("repair_attempts") != 1 or sid not in packets
                or part not in sections[sid]["parts"]
                or not set(warning["evidence_ids"]) <= set(allowed_ids(packets[sid], part))):
            raise ValueError("분할 보완 경고의 장·소절·근거 범위가 잘못됐습니다.")
        missing = sorted(set(warning["evidence_ids"]) - cited_ids(sections[sid]["parts"][part]))
        if not missing:
            continue
        row = {**copy.deepcopy(warning), "evidence_ids": missing,
               "reason": f"분할 누락 보완 {sid}/{part}/{warning['fragment_batch']}: 보정 1회 후에도 "
                         f"본문에 연결되지 않은 요청 근거가 남았습니다: {', '.join(missing)}. "
                         "인용을 임의로 추가하지 않고 확인 필요로 남겼습니다."}
        result[sid, part, tuple(missing)] = row
    return list(result.values())


def finish_content_review(report, stage, completion=None):
    """Allow progression without claiming the remaining findings were resolved.

    Call only after checked_review: malformed IDs/reports never reach this policy.
    Keep initial failed reports unchanged to preserve cached revision requests.
    """
    if completion is None and not report["approved"]:
        return report
    report = copy.deepcopy(report)
    if completion is not None:
        if (completion.get("policy") != POLICY or completion.get("status") != "needs_attention"
                or type(completion.get("revisions")) is not int
                or completion["revisions"] < MAX_REVISIONS):
            raise ValueError("내용 검토 보완 완료 기록이 잘못됐습니다.")
        if any(i["severity"] == "error" and i.get("failure_owner") == "reviewer" for i in report["issues"]):
            raise ValueError("검토 응답의 형식·연결 오류는 내용 경고로 전환할 수 없습니다.")
        for issue in report["issues"]:
            if issue["severity"] == "error":
                issue.update(severity="warning", original_severity="error", deferred=True)
        report["content_completion"] = copy.deepcopy(completion)
        report["approved"] = True  # Workflow may proceed; not a content endorsement.
    report["content_warnings"] = [{**copy.deepcopy(i), "stage": stage}
                                  for i in report["issues"] if i["severity"] == "warning"]
    report["content_status"] = "needs_attention" if report["content_warnings"] else "reviewed"
    report["content_approved"] = not bool(completion or report["content_warnings"])
    return report
