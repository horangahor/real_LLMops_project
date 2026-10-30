"""원문 검토 결과와 생성 문장의 품질 검사를 연결한다."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from paper_prompts import (
    SECTION_SUBSECTIONS, CONCLUSION_MAX_CHARACTERS, CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES,
)


def extraction_fingerprint(data: dict[str, Any]) -> str:
    content = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def prepare_research_evidence(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """검토한 추출물·원문과 일치할 때만 해당 근거 프로파일을 사용한다."""
    profile_path = base_dir / "research_evidence.json"
    if not profile_path.exists():
        return {**data, "evidence_status": "unreviewed_extraction"}
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if extraction_fingerprint(data) != profile["extraction_sha256"]:
        return {**data, "evidence_status": "unreviewed_extraction"}
    candidates = [base_dir / "input" / profile["source_file"], base_dir.parent / profile["source_file"]]
    sources = [path for path in candidates if path.is_file()]
    if not sources:
        raise FileNotFoundError("근거 프로파일에 연결된 연구 원본 PDF를 찾을 수 없습니다.")
    if not any(hashlib.sha256(path.read_bytes()).hexdigest() == profile["source_sha256"] for path in sources):
        raise ValueError("연구 원본 PDF가 변경되었습니다. 기존 근거 프로파일을 다시 검토하거나 일반 연구 PDF 입력으로 새로 분석해주세요.")
    methods = data.get("optimization_methods") or data.get("methods_and_results") or []
    # 검토 전 추출값은 작성 프롬프트에서 제외한다. 정정 지시와 함께 보내도 모델이
    # 잘못된 수치를 다시 사용하는 문제가 있으므로 검토된 사실만 전달한다.
    return {
        "project_name": data.get("project_name", ""),
        "document_title": data.get("document_title", ""),
        "evidence_status": "source_reviewed",
        "source": {key: profile[key] for key in ("source_file", "source_sha256")},
        "verified_facts": profile["verified_facts"],
        "research_findings": profile["research_findings"],
        "section_briefs": profile.get("section_briefs", {}),
        "result_tables": profile.get("result_tables", []),
        "open_questions": profile["open_questions"],
        "original_extracted_method_count": len(methods),
    }


def known_quality_issues(sections: dict[str, str]) -> list[dict[str, Any]]:
    """이번에 확인한 오류의 재발을 검사한다. 범용 사실 검증기는 아니다."""
    issues = []

    def add(section, quote, reason, revision, evidence_ids=None, severity="error"):
        issues.append({"section": section, "severity": severity, "quote": quote,
                       "reason": reason, "revision": revision,
                       "evidence_ids": evidence_ids or [], "checker": "local_regression"})

    for section, text in sections.items():
        if section not in SECTION_SUBSECTIONS:
            continue
        headings = re.findall(r"(?m)^#{1,6}\s+(.+)$", text)
        expected = [f"{section}.{index}" for index in range(1, len(SECTION_SUBSECTIONS[section]) + 1)]
        actual = []
        for heading in headings:
            match = re.match(r"(\d+(?:\.\d+)+)\s", heading)
            actual.append(match.group(1) if match else None)
        if actual != expected:
            add(section, "", "소절 구성이 합의한 논문 구조와 다름",
                ("소절 제목을 제거하고 연결된 문단으로 작성한다." if not expected
                 else f"소절을 {', '.join(expected)} 세 개만 순서대로 사용하고 추가 하위 제목을 제거한다."))

    patterns = [
        (r"커널\s*실행\s*횟수\s*감소에\s*대한\s*근거는\s*(?:자료에\s*)?없[^\n。]*",
         "일부 커널 제거 기록과 전체 감소율 미계측의 혼동",
         "일부 커널 제거·호출 통합은 기록되어 있음을 인정하고 전체 감소율의 근거만 구별한다.", ["E05"]),
        (r"Convex\s+Relaxation\s+for\s+ONNX\s+Networks", "근거 없는 CROWN 약어 풀이",
         "원문에서 확인하지 않은 약어 풀이를 삭제하고 CROWN으로만 표기한다.", ["E12"]),
        (r"[^\n。]*커널[^\n。]*40\s*%[^\n。]*", "근거 없는 커널 호출 40% 감소",
         "40%를 삭제하고 원문에서 확인한 변경 내용만 서술한다.", ["E05"]),
        (r"(?:15|17|29)\s*단계(?:의)?\s*(?:점진적\s*)?최적화", "실험 분기를 임의의 누적 단계 수로 표현",
         "고정된 단계 수를 삭제하고 실제 적용한 방법과 실험 분기를 구별한다.", []),
        (r"[^\n。]*모든\s*(?:실험\s*결과|수치)[^\n。]*(?:실제\s*측정값|보정된\s*데이터)[^\n。]*",
         "작성 시스템의 근거 보증을 논문 성과처럼 선언",
         "근거를 보증하는 문장을 삭제하고 실험의 한계와 측정 조건을 명시한다.", []),
    ]
    for section, text in sections.items():
        for pattern in (
            r"약어의\s*풀이는?[^.\n]*(?:확인되지|검증하지)",
            r"문헌\s*검색\s*없이[^.\n]*(?:신규성|최초|유일|최고)[^.\n]*주장하지\s*않",
        ):
            match = re.search(pattern, text)
            if match:
                add(section, match.group(), "연구 설명에 작성 방침이 노출됨",
                    "작성 방침 설명을 제거하고 연구 대상과 확인된 방법·결과를 직접 서술한다.",
                    severity="warning")
        for pattern, reason, revision, evidence_ids in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                add(section, match.group(), reason, revision, evidence_ids)
        for sentence in re.split(r"\n|(?<=[다요])\.\s+|(?<=[。!?])\s*", text):
            if ("13.939" in sentence and re.search(r"(?<!\d)5\.3(?:0|2)?\s*배", sentence)
                    and re.search(r"CPU\s*(?:대비|보다)", sentence, re.IGNORECASE)):
                add(section, sentence, "단일 실행 관측값과 별도 bound 가속비의 혼용",
                    "13.939ms는 E06의 관측값, 5.32/5.30배는 E07의 비교로 분리한다.", ["E06", "E07"])
    conclusion = sections.get("6", "")
    if conclusion:
        result_values = re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?=\s*(?:ms|밀리초|초|분|배|%))", conclusion)
        value_count = len(set(result_values))
        if value_count > CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES:
            add("6", "", f"결론의 성능 수치 개수 권장량 초과 ({value_count}개 / 권장 {CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES}개)",
                f"대표 성과와 비교에 필요한 수치를 우선하여 {CONCLUSION_RECOMMENDED_PERFORMANCE_VALUES}개 이내로 줄이는 것을 권장한다. 저장을 막는 오류는 아니다.",
                severity="warning")
        if len(conclusion) > CONCLUSION_MAX_CHARACTERS:
            add("6", "", f"결론의 분량 초과 ({len(conclusion):,}자 / 최대 {CONCLUSION_MAX_CHARACTERS:,}자)",
                f"결론을 {CONCLUSION_MAX_CHARACTERS:,}자 이내로 편집하고 핵심 발견과 의미를 중심으로 쓴다.")
        if re.search(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s)", conclusion, re.MULTILINE):
            add("6", "", "결론이 소절·목록으로 쪼개져 본문을 반복함",
                "소절 제목·목록을 제거하고 발견→성과→한계와 후속 과제의 3~5개 문단으로 쓴다.")
        paragraphs = [part for part in re.split(r"\n\s*\n", conclusion.strip()) if part.strip()]
        if not 3 <= len(paragraphs) <= 5:
            add("6", "", "결론의 논리적 문단 구성이 부족함",
                "연구의 발견, 비교 조건을 명시한 성과, 한계와 후속 과제를 3~5개 문단으로 구성한다.")
    return issues
