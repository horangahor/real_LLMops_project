"""골든 샘플의 관찰 정보와 재사용 작성 지침을 분리한다."""

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2
StructureGuide = str | dict[str, Any]
ROLE_LABELS = {
    "introduction": "서론", "related_work": "관련 연구", "background": "배경",
    "methods": "방법", "evaluation": "실험·결과", "limitations": "한계",
    "conclusion": "결론", "other": "기타",
}
CHAPTER_ROLES = {
    "1": {"introduction"}, "3": {"background"}, "4": {"methods"},
    "5": {"evaluation", "limitations"}, "6": {"conclusion"},
}

# 이 예시는 추출 형식을 정의한다. 실제 논문의 목차·내용으로 채운다.
PROFILE_EXAMPLE = {
    "title": "분석 대상 논문의 실제 제목",
    "observed_outline": [{
        "title": "실제 섹션 제목", "role": "methods", "source_pages": None,
        "children": [{"title": "실제 하위 절 제목", "role": "methods",
                      "source_pages": None, "children": []}],
    }],
    "style_rules": ["문단은 핵심 주장, 근거, 해석 순서로 연결한다."],
    "section_guidelines": [{
        "role": "methods", "purpose": "제안한 방법의 동작과 설계 이유 설명",
        "required_content": ["전체 구성", "구성 요소의 역할"],
        "paragraph_flow": ["문제", "변경 방법", "선택 이유"],
        "figures_tables": ["구성 요소의 관계를 구조도로 설명한다."],
    }],
    "not_to_transfer": ["원 논문의 장비·데이터셋·성능 수치·인용을 연구 사실로 옮기지 않는다."],
    "analysis_notes": [],
}


def _text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"골든 샘플 형식 오류: {name}은 비어 있지 않은 문자열이어야 합니다.")


def _strings(value: Any, name: str, *, required: bool = False) -> None:
    if not isinstance(value, list) or (required and not value):
        raise ValueError(f"골든 샘플 형식 오류: {name}은 문자열 목록이어야 합니다.")
    for item in value:
        _text(item, name)


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict) or profile.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("골든 샘플의 schema_version은 2여야 합니다.")
    for key in ("file", "title"):
        _text(profile.get(key), key)
    if profile.get("provenance") not in ("pdf_analysis", "legacy_analysis"):
        raise ValueError("골든 샘플의 분석 출처가 올바르지 않습니다.")

    def outline(nodes: Any, depth: int = 0) -> None:
        if not isinstance(nodes, list) or depth > 8:
            raise ValueError("골든 샘플 목차의 계층 형식이 올바르지 않습니다.")
        for node in nodes:
            if not isinstance(node, dict):
                raise ValueError("골든 샘플 목차 항목은 객체여야 합니다.")
            _text(node.get("title"), "observed_outline.title")
            if node.get("role") not in ROLE_LABELS:
                raise ValueError("골든 샘플 목차의 role이 올바르지 않습니다.")
            if "source_pages" not in node:
                raise ValueError("확인되지 않은 페이지는 source_pages: null로 표시해야 합니다.")
            pages = node["source_pages"]
            if pages is not None and (not isinstance(pages, list) or not pages or
                                      any(type(page) is not int or page < 1 for page in pages)):
                raise ValueError("source_pages는 양의 페이지 번호 목록 또는 null이어야 합니다.")
            outline(node.get("children"), depth + 1)

    if not profile.get("observed_outline"):
        raise ValueError("골든 샘플의 관찰된 목차가 비어 있습니다.")
    outline(profile["observed_outline"])
    for key in ("style_rules", "not_to_transfer", "analysis_notes"):
        _strings(profile.get(key), key)
    guidelines = profile.get("section_guidelines")
    if not isinstance(guidelines, list) or not guidelines:
        raise ValueError("골든 샘플의 장별 작성 지침이 필요합니다.")
    roles = set()
    for guide in guidelines:
        if not isinstance(guide, dict) or guide.get("role") not in ROLE_LABELS:
            raise ValueError("골든 샘플 작성 지침의 role이 올바르지 않습니다.")
        if guide["role"] in roles:
            raise ValueError("골든 샘플 작성 지침의 role이 중복됩니다.")
        roles.add(guide["role"])
        _text(guide.get("purpose"), "section_guidelines.purpose")
        for key in ("required_content", "paragraph_flow", "figures_tables"):
            _strings(guide.get(key), f"section_guidelines.{key}", required=key == "required_content")
    return profile


def parse_profile_response(raw: str, source_file: str, provenance: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    try:
        content = json.loads(text)
    except ValueError as error:
        raise ValueError("골든 샘플 분석 응답이 올바른 JSON이 아닙니다.") from error
    if not isinstance(content, dict):
        raise ValueError("골든 샘플 분석 응답은 JSON 객체여야 합니다.")
    # 파일 경로와 출처는 호출자가 정한다. 모델의 임의 경로를 신뢰하지 않는다.
    profile = {key: content[key] for key in PROFILE_EXAMPLE if key in content}
    profile.update(schema_version=SCHEMA_VERSION, file=source_file, provenance=provenance)
    validate_profile(profile)
    if provenance == "legacy_analysis":
        def clear_pages(nodes):
            for node in nodes:
                node["source_pages"] = None
                clear_pages(node["children"])
        clear_pages(profile["observed_outline"])
        profile["analysis_notes"].append("기존 분석을 재구조화했으며 PDF 원문을 다시 대조하지 않았습니다.")
    return profile


def load_profiles(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    profiles = data if isinstance(data, list) else [data]
    if not profiles:
        raise ValueError("골든 샘플 분석 목록이 비어 있습니다.")
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("골든 샘플 분석 항목은 JSON 객체여야 합니다.")
        if "schema_version" in profile:
            validate_profile(profile)
        else:
            # 이전 Markdown 프로파일도 열 수 있다. 새 작성에는 변환을 권장한다.
            texts = [profile.get(key, "") for key in ("paper_structure_profile", "paper_style_checklist")]
            if not all(isinstance(text, str) for text in texts) or not any(text.strip() for text in texts):
                raise ValueError("기존 골든 샘플 분석 내용이 올바르지 않습니다.")
    return profiles


def save_profiles(profiles: list[dict[str, Any]], path: str | Path) -> None:
    if not profiles:
        raise ValueError("빈 분석 결과로 기존 골든 샘플 파일을 덮어쓸 수 없습니다.")
    for profile in profiles:
        validate_profile(profile)
    target = Path(path)
    # 모두 검증한 뒤 같은 폴더의 임시 파일을 교체한다.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                                     dir=target.parent, delete=False) as stream:
        temp = Path(stream.name)
        json.dump(profiles, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def outline_markdown(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    lines = []
    for node in nodes:
        pages = node.get("source_pages")
        suffix = f" · p. {', '.join(map(str, pages))}" if pages else ""
        lines.append(f"{'  ' * depth}- {node['title']} ({ROLE_LABELS[node['role']]}{suffix})")
        if node["children"]:
            lines.append(outline_markdown(node["children"], depth + 1))
    return "\n".join(lines)


def profile_markdown(profile: dict[str, Any]) -> str:
    if "schema_version" not in profile:
        return "\n\n".join(profile.get(key, "") for key in ("paper_structure_profile", "paper_style_checklist"))
    validate_profile(profile)
    blocks = [f"# {profile['title']}", "## 원문에서 관찰한 목차", outline_markdown(profile["observed_outline"]),
              "## 문체 규칙", "\n".join(f"- {rule}" for rule in profile["style_rules"]), "## 장별 작성 가이드"]
    for guide in profile["section_guidelines"]:
        blocks.extend([f"### {ROLE_LABELS[guide['role']]}", guide["purpose"],
                       "필수 내용\n" + "\n".join(f"- {item}" for item in guide["required_content"]),
                       "문단 흐름: " + " → ".join(guide["paragraph_flow"]),
                       "표·그림\n" + "\n".join(f"- {item}" for item in guide["figures_tables"])])
    blocks.extend(["## 옮기면 안 되는 내용", "\n".join(f"- {item}" for item in profile["not_to_transfer"]),
                   "## 분석 메모", "\n".join(f"- {item}" for item in profile["analysis_notes"])])
    return "\n\n".join(blocks).strip() + "\n"


def writing_guide(reference: StructureGuide, chapter: str | None = None) -> str:
    """원문 목차·샘플 수치 대신 재사용 지침만 작성 프롬프트로 전달한다."""
    if isinstance(reference, str):
        return reference
    roles = CHAPTER_ROLES.get(chapter, set().union(*CHAPTER_ROLES.values()))
    blocks = []
    for index, profile in enumerate(reference["profiles"], 1):
        if "schema_version" not in profile:
            blocks.append(f"[참고 스타일 {index} · 이전 형식]\n{profile_markdown(profile)}")
            continue
        validate_profile(profile)
        lines = [f"[참고 스타일 {index}]", "문체: " + " / ".join(profile["style_rules"])]
        for guide in profile["section_guidelines"]:
            if guide["role"] not in roles:
                continue
            lines.extend([f"{ROLE_LABELS[guide['role']]}의 역할: {guide['purpose']}",
                          "필수 내용: " + " / ".join(guide["required_content"]),
                          "전개 순서: " + " → ".join(guide["paragraph_flow"]),
                          "표·그림: " + " / ".join(guide["figures_tables"])])
        lines.append("현재 논문의 지정된 장·소절 구성을 우선한다. 참고 논문의 연구 사실·수치·장비·인용은 옮기지 않는다.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
