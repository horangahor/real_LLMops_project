"""Shared, manually editable writing rules for every adaptive paper structure."""

import copy
import json
import math
import re
from pathlib import Path


def load_policy(path=None):
    policy = json.loads(Path(path or Path(__file__).with_name("writing_policy.json")).read_text(encoding="utf-8"))
    if not isinstance(policy.get("version"), str) or not policy["version"]:
        raise ValueError("공통 작성 정책의 버전이 필요합니다.")
    for role in ("planning", "writing", "editing"):
        if not isinstance(policy.get(role), list) or not all(isinstance(r, str) and r.strip() for r in policy[role]):
            raise ValueError(f"공통 작성 정책의 {role} 규칙 목록이 잘못됐습니다.")
    ratio = policy.get("length_tolerance_ratio")
    if type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio < 1:
        raise ValueError("분량 허용 비율은 1 이상의 유한한 수여야 합니다.")
    limit = policy.get("max_paragraph_chars", 800)
    if type(limit) is not int or limit < 1:
        raise ValueError("문단 최대 글자 수는 양의 정수여야 합니다.")
    policy["max_paragraph_chars"] = limit
    for field in ("max_subsection_chars", "max_section_chars"):
        value = policy.get(field, 0)
        if type(value) is not int or value < 0:
            raise ValueError(f"{field}는 0 이상의 정수여야 합니다.")
        policy[field] = value
    return policy


def instructions(policy, role):
    limits = [(label, policy.get(key, 0)) for key, label in (
        ("max_subsection_chars", "소절 전체"), ("max_section_chars", "절 전체"), ("max_paragraph_chars", "한 문단"))]
    bounds = ", ".join(f"{label} {limit}자" for label, limit in limits if limit)
    return "\n공통 논문 구성 규칙:\n" + "\n".join(f"- {rule}" for rule in policy[role]) + (
        f"\n- 공통 분량 상한: {bounds}. 제목·표·인용 표시를 제외하고 공백을 포함한다. 더 작은 writing_budget 목표도 준수한다."
        if role == "writing" and bounds else "")


def attach_policy(contexts, policy):
    contexts["composition_policy"] = copy.deepcopy(policy)
    meta = {key: policy.get(key, 0) for key in ("version", "length_tolerance_ratio", "max_paragraph_chars", "max_subsection_chars", "max_section_chars")}
    for sid, packet in contexts["sections"].items():
        packet["composition_policy"] = copy.deepcopy(meta)
        packet["editorial_guidance"] = instructions(policy, "editing")
        for child in contexts["subsections"][sid].values():
            child["composition_policy"] = copy.deepcopy(meta)
            child["writing_guidance"] = instructions(policy, "writing")


def length_issues(value, packets, level):
    if level != "subsection":
        return []
    from writing_length import narrative_chars
    issues = []
    for sid, packet in packets.items():
        meta = packet.get("composition_policy")
        if not meta:
            continue
        assignments = packet.get("subsection_assignments")
        for part, body in value[sid]["parts"].items():
            scoped = assignments[part] if assignments is not None else packet
            budget = scoped.get("writing_budget")
            if not budget:
                continue
            actual, target = narrative_chars(body), budget["target_chars"]
            maximum = budget.get("max_chars", meta.get("max_subsection_chars", 0))
            permitted = min(target * meta["length_tolerance_ratio"], maximum) if maximum else target * meta["length_tolerance_ratio"]
            if actual <= permitted:
                continue
            heading = scoped.get("heading", packet.get("target_heading", part))
            issues.append({"section_id": sid, "paragraph_id": "none", "part": part,
                "severity": "error", "category": "organization", "evidence_ids": [], "quote": "",
                "validation_code": "composition_length", "review_stage": "composition",
                "failure_owner": "writer" if level == "subsection" else "editor",
                "reason": f"{heading}: 본문 {actual}자 / 목표 {target}자 / 허용 상한 {int(permitted)}자로 허용 범위를 초과했습니다. "
                          "핵심 설명·조건·반례·한계를 남기고 반복·로그·수치 열거를 줄여 목표 분량에 맞추세요. "
                          "소절 삭제나 긴 한 문단으로 합치는 방식은 쓰지 마세요."})
        enabled = packet.get("writing_budget") or any(a.get("writing_budget") for a in (assignments or {}).values())
        section_limit = meta.get("max_section_chars", 0) if enabled else 0
        actual_section = sum(narrative_chars(b) for b in value[sid]["parts"].values())
        if section_limit and actual_section > section_limit:
            issues.append({"section_id": sid, "paragraph_id": "none", "part": next(iter(value[sid]["parts"])),
                "severity": "error", "category": "organization", "evidence_ids": [], "quote": "",
                "validation_code": "composition_length", "review_stage": "composition",
                "failure_owner": "writer" if level == "subsection" else "editor",
                "reason": f"{sid}: 절 전체 본문 {actual_section}자가 공통 상한 {section_limit}자를 넘습니다. "
                          "절 전체에서 중복·실행 이력·표의 수치 재열거를 줄이고 소절·핵심 조건·반례는 보존하세요."})
    return issues


COMPOSITION_CODES = {"composition_length", "composition_layout", "composition_style"}
NARRATOR = re.compile(r"(?:기록자|작성자)(?:는|가|의\s*(?:판단|기록))|연구\s*(?:노트|일지)의\s*저자(?:는|가)|(?:연구\s*노트|연구\s*일지|현재\s*페이지)(?:에는|에서|에)\s*(?:직접\s*)?(?:기록|제시|남|확인|포함)")


def composition_issues(value, packets, level):
    from writing_length import narrative_chars
    from paper_display import PROTECTED
    issues = length_issues(value, packets, level)
    for sid, packet in packets.items():
        meta = packet.get("composition_policy")
        if not meta:
            continue
        for part, body in value[sid]["parts"].items():
            base = {"section_id": sid, "paragraph_id": "none", "part": part, "severity": "error",
                    "evidence_ids": [], "quote": "", "review_stage": "composition",
                    "failure_owner": "writer" if level == "subsection" else "editor"}
            prose = PROTECTED.sub("", body)
            if level == "subsection":
                from publication_tables import _citations
                paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
                for table in packet.get("tables", []):
                    count = sum(bool(_citations(p) & set(table["evidence_ids"])) for p in paragraphs)
                    if count == 0 or count > 2:
                        issues.append({**base, "category": "organization", "validation_code": "composition_layout",
                            "reason": f"{sid}/{part}: 표 {table['id']}에 근거 인용으로 연결된 문단이 {count}개입니다. "
                                      "표 하나마다 핵심 관찰·비교 조건·해석 한계를 독립 문단 1~2개로 구성하세요. "
                                      "근거를 일괄 부착하거나 조건·반례를 삭제하지 마세요."})
            maximum = max((narrative_chars(p) for p in re.split(r"\n\s*\n", prose.strip())), default=0)
            limit = meta.get("max_paragraph_chars", 0) if level == "subsection" else 0
            if limit and maximum > limit:
                issues.append({**base, "category": "flow", "validation_code": "composition_layout",
                    "reason": f"{sid}/{part}: 가장 긴 문단이 {maximum}자로 공통 문단 목표 {limit}자를 넘습니다. "
                              "입력 조건·환경·측정 방식·결과·해석을 설명 단위별 문단 또는 병렬 목록으로 나누세요. "
                              "내용·조건·인용을 보존하고 코드·수식 중간을 자르지 마세요."})
            markers = list(dict.fromkeys(m.group() for m in NARRATOR.finditer(prose)))
            if markers:
                issues.append({**base, "category": "style", "validation_code": "composition_style",
                    "reason": f"{sid}/{part}: 기록자·자료 중심 표현 {markers[:3]}을 객관적인 3인칭 학술 문체로 고치세요. "
                              "관측·시도·제안·미검증 해석의 확실성 수준과 필요한 귀속은 유지하세요."})
    return issues
