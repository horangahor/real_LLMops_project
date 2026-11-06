"""Allocate a paper's narrative target to subsections and their source fragments."""

import copy
import os
import re

POLICY = "subsection-length-v2"
DEFAULT_TARGET_CHARS = 30000
ROLE_WEIGHTS = {"introduction": 2, "methods": 4, "results": 4, "evaluation": 4,
                "discussion": 3, "conclusion": 2, "limitations": 2, "related_work": 2}
INSTRUCTION = """\nwriting_budget는 인용 표시·제목·표를 제외한 본문 글자 수(공백 포함)의 목표다.
whole_target_chars는 소절 전체의 예산이고 target_chars는 이번 요청 몫이다. 분할 요청마다 전체 예산을 다시 쓰지 않는다.
max_chars는 소절 전체의 허용 상한이다. 각 분할의 분량을 늘리거나 편집 때 상한을 새로 배정하지 않는다.
필수 내용의 핵심 주장·대표 비교·조건·한계를 우선하고, 후보 근거를 모두 본문으로 열거하지 않는다.
표의 모든 수치나 설정을 문장으로 되풀이하지 않고 핵심 결과와 해석 범위를 간결히 설명한다.
분할 조각은 현재 근거가 담당하는 내용만 쓰고 서론·연구 목표·요약을 반복하지 않는다.
수정 시 기존 문단과 새 내용의 합계가 소절 예산 안에 머물도록 중복을 줄인다.
글자 수를 맞추려고 필수 주장·조건·한계를 없애거나 근거 없는 내용을 추가하지 않는다.
목표가 작아도 문장·JSON·근거 연결은 완결한다. 길이 제한을 이유로 문장이나 JSON을 중간에서 끊지 않는다."""


def resolve_target(value=None):
    if value is None:
        value = os.getenv("PAPER_DRAFT_TARGET_CHARS", str(DEFAULT_TARGET_CHARS))
    if isinstance(value, str):
        value = int(value)
    if type(value) is not int or value < 0:
        raise ValueError("본문 목표 글자 수는 0 이상의 정수여야 합니다.")
    return value


def apportion(total, weights):
    """Deterministic integer shares whose sum is exactly the original budget."""
    if not weights:
        return []
    denominator = sum(weights)
    values = [total * weight // denominator for weight in weights]
    remainder = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % denominator), i))
    for index in remainder[:total - sum(values)]:
        values[index] += 1
    return values


def narrative_chars(body):
    text = re.sub(r"\[근거:\s*[^\]]+\]", "", body)
    lines = [line.rstrip() for line in text.splitlines()
             if not re.match(r"^\s*#{1,6}\s|^\s*\|.*\|\s*$", line)]
    return len("\n".join(lines).strip())


def apply_length_targets(plan, contexts, target):
    if not target:
        return None
    sections = [s for s in plan["sections"] if s["status"] == "write"]
    shares = apportion(target, [ROLE_WEIGHTS.get(s["role"], 2) for s in sections])
    rows = []
    for section, share in zip(sections, shares):
        sid = section["id"]
        meta = contexts.get("composition_policy", {})
        ratio = meta.get("length_tolerance_ratio", 1.25)
        section_max = meta.get("max_section_chars", 0)
        part_max = meta.get("max_subsection_chars", 0)
        if section_max:
            share = min(share, int(section_max / ratio))
        children = contexts["subsections"][sid]
        budgets = apportion(share, [1] * len(children))
        for (key, child), budget in zip(children.items(), budgets):
            if part_max:
                budget = min(budget, int(part_max / ratio))
            value = {"policy": POLICY, "scope": "whole_subsection", "target_chars": budget,
                     "whole_target_chars": budget, "paper_target_chars": target,
                     "counting": "narrative characters including spaces; excluding citation markers, headings and tables"}
            if part_max:
                value["max_chars"] = part_max
            child["writing_budget"] = copy.deepcopy(value)
            contexts["sections"][sid]["subsection_assignments"][key]["writing_budget"] = copy.deepcopy(value)
            rows.append({"section_id": sid, "part": key, "heading": child["target_heading"], "target_chars": budget,
                         **({"max_chars": part_max} if part_max else {})})
    return {"policy": POLICY, "paper_target_chars": target, "allocated_target_chars": sum(r["target_chars"] for r in rows), "subsections": rows}


def allocate_fragment_targets(tasks, packets):
    """Share one part's remaining target across its requests, never per API call."""
    from paper_context import part_context
    grouped = {}
    for index, (sid, part, _, request, schema) in enumerate(tasks):
        grouped.setdefault((sid, part), []).append(index)
    result = list(tasks)
    for (sid, part), indices in grouped.items():
        full = packets[sid]
        scoped = part_context(full, part) if "subsection_assignments" in full else full
        budget = scoped.get("writing_budget")
        if not budget:
            continue
        kept = sum(narrative_chars(tasks[i][3]["passthrough"]) for i in indices if tasks[i][4] is None)
        active = [i for i in indices if tasks[i][4] is not None]
        remaining = max(0, budget["target_chars"] - kept)
        for index, share in zip(active, apportion(remaining, [1] * len(active))):
            sid, key, batch, request, schema = result[index]
            request = {**request, "writing_budget": {**copy.deepcopy(budget), "scope": "fragment",
                "target_chars": share, "whole_target_chars": budget["target_chars"],
                "preserved_chars": kept, "fragment_count": len(active)}}
            result[index] = (sid, key, batch, request, schema)
    return result
