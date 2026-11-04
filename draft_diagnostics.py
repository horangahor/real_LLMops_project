"""Trace failed reviews to planned items, actual citations, evidence and source locations."""

import copy
from pathlib import Path

from bounded_drafting import cited_ids
from document_parse import write_json


def review_diagnostics(stage, plan, research, bodies, report):
    from planned_paper import index_paragraphs
    facts = {f["id"]: f for f in research["facts"]}
    items = {i["id"]: (s, i) for s in plan["sections"] for i in s["required_items"]}
    paragraphs = index_paragraphs(bodies)
    if report.get("review_kind") == "editorial":
        return {"stage": stage, "approved": report["approved"], "review_kind": "editorial", "items": [],
                "paragraphs": paragraphs, "issues": copy.deepcopy(report["issues"]),
                "inherited_content_coverage": copy.deepcopy(report["required_content_coverage"])}
    rows = []
    for check in report.get("checks", []):
        section, item = items[check["item_id"]]
        selected = set().union(*(cited_ids(paragraphs[pid]["text"])
            for pid in check.get("paragraph_ids", []) if pid in paragraphs))
        all_cited = cited_ids(bodies[section["id"]])
        missing_body = set(check.get("missing_body_evidence_ids", []))
        missing_review = set(check.get("missing_review_evidence_ids", []))
        evidence = []
        for key in item["evidence_ids"]:
            fact = facts[key]
            evidence.append({"id": key, "statement": fact["statement"], "limits": fact.get("limits", ""),
                "support": fact.get("support"), "writing_role": fact.get("writing_role"),
                "claim_status": fact.get("claim_status"), "source_origin": fact.get("source_origin"),
                "user_accepted": fact.get("support") == "user_accepted",
                "provisional_decision_id": fact.get("provisional_decision_id"),
                "sources": [{k: s[k] for k in ("page", "element_id", "origin") if k in s}
                            for s in fact.get("sources", [])],
                "cited_in_selected_paragraphs": key in selected, "cited_anywhere_in_section": key in all_cited,
                "listed_by_reviewer": key in check["evidence_ids"],
                "unused_candidate": key not in all_cited,
                "missing_body": key in missing_body, "missing_review": key in missing_review})
        rows.append({"item_id": check["item_id"], "description": item["description"], "section_id": section["id"],
            "verdict": check["verdict"], "model_verdict": check.get("model_verdict", check["verdict"]),
            "planned_evidence_count": len(evidence), "missing_body_count": len(missing_body),
            "missing_section_count": len(check.get("missing_section_evidence_ids", [])),
            "unused_candidate_count": sum(f["unused_candidate"] for f in evidence),
            "unselected_cited_count": sum(f["missing_body"] and f["cited_anywhere_in_section"] for f in evidence),
            "failure_owner": check.get("failure_owner"),
            "missing_review_count": len(missing_review), "paragraph_ids": check.get("paragraph_ids", []),
            "evidence": evidence})
    return {"stage": stage, "approved": report["approved"], "items": rows,
            "paragraphs": paragraphs, "issues": copy.deepcopy(report.get("issues", []))}


def save_review_diagnostics(folder, name, stage, plan, research, bodies, report):
    folder = Path(folder)
    details = review_diagnostics(stage, plan, research, bodies, report)
    path = folder / f"{name}-diagnostics.json"
    write_json(path, details)
    if report["approved"]:
        return path
    write_json(folder / "failure-details.json", details)
    lines = [f"# 작성 검토 실패: {stage}", "", "## 검토 지적", ""]
    for issue in details["issues"]:
        if issue["severity"] != "error":
            continue
        phase = issue.get("review_stage", "원문·내용 검토")
        if issue.get("validation_code") == "required_content" or issue["reason"].startswith("필수 내용 "):
            phase = "코드의 필수 내용·근거 연결 검사"
        lines += [f"- [{phase}; 처리 책임: {issue.get('failure_owner', '미분류')}] {issue['reason']}",
                  f"  - 문단: {issue.get('paragraph_id', '미지정')}; 근거: {', '.join(issue['evidence_ids']) or '미지정'}"]
        if issue.get("quote"):
            lines += [f"  - 실제 본문: {issue['quote']}"]
        if issue.get("adjudication"):
            proof = issue["adjudication"]
            lines += [f"  - 지적 확인: {proof['decision']}",
                      f"  - 대조한 본문 구절: {proof.get('matched_draft_quote', proof.get('draft_quote', ''))}",
                      f"  - 대조한 원문 구절: {proof.get('matched_source_quote', proof.get('source_quote', ''))}",
                      f"  - 원래 지적: {proof['original_issue']['reason']}"]
    for item in details["items"]:
        if item["verdict"] not in ("missing", "incorrect"):
            continue
        lines += ["", f"## {item['item_id']}: {item['description']}", "",
            f"- 검토자 판정: {item['model_verdict']}; 코드 검증 후: {item['verdict']}",
            f"- 배정 근거: {item['planned_evidence_count']}개; 본문 전체 인용 누락: {item['missing_section_count']}개; 검토 문단 선택 누락: {item['unselected_cited_count']}개; 검토 목록 누락: {item['missing_review_count']}개", ""]
        for fact in item["evidence"]:
            if not fact["missing_body"] and not fact["missing_review"]:
                continue
            locations = ", ".join(f"{s.get('page', '?')}쪽/{s.get('element_id', '?')}" for s in fact["sources"])
            lines += [f"### {fact['id']}", "", fact["statement"], "",
                f"- 임시 승인: {'예' if fact['user_accepted'] else '아니오'}; 성격: {fact['writing_role']}; 출처: {fact['source_origin']}",
                f"- 원문 위치: {locations or '원문 위치 없음'}",
                f"- 선택 문단 인용: {fact['cited_in_selected_paragraphs']}; 장 전체 인용: {fact['cited_anywhere_in_section']}; 검토 목록: {fact['listed_by_reviewer']}",
                f"- 해석 한계: {fact['limits']}", ""]
    (folder / "failure-details.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
