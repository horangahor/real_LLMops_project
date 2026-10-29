"""장별 입력 범위와 검토된 결과표를 관리한다. 논문 문장은 모델이 작성한다."""

import re
from typing import Any

CONTENT_POLICY_VERSION = "chapter-packets-and-source-tables-v2"
TABLE_START = "<!-- verified-results:start -->"
TABLE_END = "<!-- verified-results:end -->"
TABLE_SLOT = "<<RESULT_TABLES>>"


def writing_packet(evidence: dict[str, Any], section: str) -> dict[str, Any]:
    brief = evidence.get("section_briefs", {}).get(section, {})
    selected = brief.get("selected_facts")
    if evidence.get("evidence_status") != "source_reviewed":
        return evidence
    if selected is None:
        return {**evidence, "section_briefs": {section: brief}}
    valid_ids = {fact["id"] for fact in evidence.get("verified_facts", [])}
    if not selected or any(fact.get("id") not in valid_ids or not fact.get("finding") for fact in selected):
        raise ValueError(f"제{section}장의 선택 근거가 원문 검토 근거에 연결되지 않았습니다.")
    # 원문 인용과 다른 장의 세부 수치는 다시 붙이지 않는다.
    return {
        "project_name": evidence.get("project_name", ""),
        "document_title": evidence.get("document_title", ""),
        "evidence_status": evidence["evidence_status"],
        "source": evidence.get("source", {}),
        "verified_facts": selected,
        "section_briefs": {section: {key: value for key, value in brief.items() if key != "selected_facts"}},
    }


def chapter_context(context: dict[str, str], evidence: dict[str, Any], section: str) -> dict:
    selected = evidence.get("section_briefs", {}).get(section, {}).get("selected_facts")
    if evidence.get("evidence_status") != "source_reviewed" or not selected or section not in ("1", "5", "6"):
        return context
    # 앞 장의 실험 이력 대신 그 장의 목적·구성만 연결한다.
    briefs = evidence.get("section_briefs", {})
    return {key: {"main_claim": briefs.get(key, {}).get("main_claim", ""),
                  "subsections": re.findall(r"(?m)^###\s+(.+)$", body)}
            for key, body in context.items() if key in ("3", "4", "5") and key != section}


def has_narrative_packets(evidence: dict[str, Any]) -> bool:
    return (evidence.get("evidence_status") == "source_reviewed" and
            all(evidence.get("section_briefs", {}).get(key, {}).get("selected_facts") for key in ("1", "6")))


def result_tables(evidence: dict[str, Any]) -> str:
    tables = evidence.get("result_tables", [])
    if not tables:
        return ""
    if evidence.get("evidence_status") != "source_reviewed":
        raise ValueError("검토된 연구 근거에만 고정 결과표를 연결할 수 있습니다.")
    valid_ids = {fact["id"] for fact in evidence.get("verified_facts", [])}
    blocks = []
    seen = set()
    for index, table in enumerate(tables, 1):
        identifier = table.get("id")
        columns, rows = table.get("columns"), table.get("rows")
        ids = table.get("evidence_ids")
        if (not isinstance(identifier, str) or not identifier or identifier in seen or
                not isinstance(ids, list) or not ids or any(key not in valid_ids for key in ids) or
                not isinstance(columns, list) or not columns or not isinstance(rows, list) or not rows):
            raise ValueError("결과표의 식별자·열·행·근거 연결이 올바르지 않습니다.")
        seen.add(identifier)

        def cell(value):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("결과표의 셀은 비어 있지 않은 문자열이어야 합니다.")
            return value.replace("|", "\\|").replace("\n", " ")

        lines = [f"**표 5-{index}. {cell(table.get('caption'))}**", "",
                 "| " + " | ".join(map(cell, columns)) + " |",
                 "| " + " | ".join("---" for _ in columns) + " |"]
        for row in rows:
            if not isinstance(row, list) or len(row) != len(columns):
                raise ValueError("결과표의 행 길이가 열 수와 다릅니다.")
            lines.append("| " + " | ".join(map(cell, row)) + " |")
        lines.extend(["", cell(table.get("scope"))])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def strip_result_tables(body: str) -> str:
    return re.sub(re.escape(TABLE_START) + r".*?" + re.escape(TABLE_END), TABLE_SLOT,
                  body, flags=re.S)


def table_context(evidence: dict[str, Any]) -> str:
    """해석 작성자에게는 표의 역할·조건만 주고 셀 값은 코드에서 채운다."""
    result_tables(evidence)
    return "\n".join(f"표 5-{index}. {table['caption']} — {table['scope']}"
                     for index, table in enumerate(evidence.get("result_tables", []), 1))


def attach_result_tables(body: str, evidence: dict[str, Any]) -> str:
    rendered = result_tables(evidence)
    if not rendered:
        return body
    body = strip_result_tables(body)
    match = re.search(r"(?ms)^###\s+5\.2[^\n]*\n(.*?)(?=^###\s+5\.3|\Z)", body)
    if not match:
        raise ValueError("결과표를 배치할 5.2 절이 없습니다.")
    content = match[1].replace(TABLE_SLOT, "")
    # 모델이 따로 만든 표는 이 구간에서 검토된 표로 대체한다.
    content = re.sub(r"(?m)^\s*\|.*\|\s*$\n?", "", content)
    content = re.sub(r"(?m)^\*\*표\s+5-\d+\.[^\n]*\*\*\s*$", "", content)
    block = f"\n{TABLE_START}\n{rendered}\n{TABLE_END}\n\n{content.strip()}\n\n"
    result = body[:match.start(1)] + block + body[match.end(1):]
    return result.replace(TABLE_SLOT, "").strip()


def output_observations(sections: dict[str, str]) -> dict[str, Any]:
    """생성 결과의 비교용이다. 짧다는 이유만으로 품질이나 합격을 판정하지 않는다."""
    performance = r"(?<![\w.])\d+(?:\.\d+)?(?=\s*(?:ms|밀리초|초|분|배|%))"
    return {key: {"characters": len(body),
                  "performance_values": len(set(re.findall(performance, re.sub(r"(?m)^#{1,6}\s.*$", "", body)))),
                  "table_rows": len(re.findall(r"(?m)^\|.*\|$", body))}
            for key, body in sections.items()}
