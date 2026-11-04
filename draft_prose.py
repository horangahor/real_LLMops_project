"""Paragraph-level model citations, rendered into the existing reviewed prose format."""

import re

from paper_plan import object_schema

PROTOCOL = """\n출력 형식 규칙: parts의 각 p번호 값은 문자열이 아니라 문단 객체의 배열이다.
각 문단은 text(제목·표·인용 표시 없는 한 문단)와 evidence_ids(그 문단을 직접 뒷받침하는 근거 ID 목록)를 필수로 갖는다.
앞선 [근거:ID] 인용 지시는 evidence_ids 필드로 이행한다. text에 [근거:...]를 직접 쓰지 않는다. 코드가 표시를 조립한다.
각 문단에 배정 범위 안의 실제 근거 ID를 하나 이상 선택한다. 모든 배정 근거를 일괄 연결하지 않는다.
계획의 evidence_ids는 사용 가능한 후보 목록이다. 필수 내용은 충족하되 후보를 전부 사용하거나 인용할 필요는 없다.
필수 비교에서 요구한 대상·조건·결과는 설명하되, 사용하지 않은 후보의 내용을 통과 목적으로 억지로 추가하지 않는다.
쓸 근거가 없는 주장은 삭제하거나 배정된 근거가 뒷받침하는 범위로 고친다. ID를 골랐다고 주장이 검증된 것은 아니다.
revision이 있으면 형식 지적과 함께 review, content_repair_instruction, evidence_link_gaps의 원래 수정 지적도 반영한다.
evidence_link_gaps의 내용이 이미 본문에 있으면 해당 문단에 실제로 맞는 근거 ID를 연결한다. 없는 내용에 ID만 붙이지 않는다.
형식만 고치고 원래 내용·인용 연결 오류를 남기거나 이전 실패 응답을 그대로 반환하지 않는다."""


def allowed_ids(packet, key):
    assignments = packet.get("subsection_assignments")
    return assignments[key]["evidence_ids"] if assignments is not None else packet["section_plan"]["evidence_ids"]


def prose_schema(packet):
    properties = {}
    for index in range(max(1, len(packet["subsection_headings"]))):
        key = f"p{index}"
        ids = list(dict.fromkeys(allowed_ids(packet, key)))
        if not ids:
            raise ValueError(f"{key}에 작성할 근거가 배정되지 않았습니다. 작성 계획의 근거 배정을 확인해주세요.")
        paragraph = object_schema({"text": {"type": "string"},
                                   "evidence_ids": {"type": "array", "minItems": 1,
                                                    "items": {"type": "string", "enum": ids}}})
        properties[key] = {"type": "array", "minItems": 1, "items": paragraph}
    return object_schema({"parts": object_schema(properties)})


def render_part(value, ids, label):
    from planned_paper import validate_body

    packet = {"section_plan": {"evidence_ids": ids}, "subsection_headings": []}
    # Completed responses from the previous output format remain reusable, but
    # a citation-free legacy string is never repaired by guessing its sources.
    if isinstance(value, str):
        return validate_body(value, packet)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label}: 본문은 text와 evidence_ids를 가진 문단 배열이어야 합니다.")
    paragraphs = []
    for index, paragraph in enumerate(value):
        at = f"{label} 문단 {index + 1}"
        if not isinstance(paragraph, dict) or set(paragraph) != {"text", "evidence_ids"}:
            raise ValueError(f"{at}: text와 evidence_ids가 모두 필요합니다.")
        text, selected = paragraph["text"], paragraph["evidence_ids"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{at}: text는 비어 있지 않은 한 문단이어야 합니다.")
        if (not isinstance(selected, list) or not selected
                or any(not isinstance(key, str) or key not in ids for key in selected)):
            raise ValueError(f"{at}: evidence_ids가 비었거나 허용 범위 밖입니다. 허용={ids}")
        selected = list(dict.fromkeys(selected))
        segments = re.split(r"\n\s*\n", text.strip())
        linked = []
        for segment in segments:
            inline = list(dict.fromkeys(identifier for group in re.findall(r"\[근거:\s*([^\]]+)\]", segment)
                                        for identifier in re.split(r"[,，;·\s]+", group.strip()) if identifier))
            linked.append(inline)
        if len(segments) > 1 or "[근거:" in text:
            # Normalize only citations the model stated in BOTH representations.
            # Never spread a paragraph's aggregate IDs over uncited paragraphs.
            if any(not keys for keys in linked) or {key for keys in linked for key in keys} != set(selected):
                raise ValueError(f"{at}: 문단별 본문 인용과 evidence_ids가 일치하지 않아 자동 정리할 수 없습니다.")
            records = [(re.sub(r"\[근거:\s*[^\]]+\]", "", segment).strip(), keys)
                       for segment, keys in zip(segments, linked)]
        else:
            records = [(text.strip(), selected)]
        for segment, keys in records:
            if not segment or "[근거:" in segment:
                raise ValueError(f"{at}: 문단 본문 또는 인용 표시가 잘못됐습니다.")
            if re.search(r"(?m)^\s*\|.*\|\s*$", segment):
                raise ValueError(f"{at}: 모델이 표를 직접 생성했습니다. 표는 코드가 배치해야 합니다.")
            paragraphs.append(validate_body(segment + " [근거:" + ",".join(keys) + "]", packet))
    return "\n\n".join(paragraphs)


def render_parts(value, packet):
    from planned_paper import clean_part

    expected = [f"p{i}" for i in range(max(1, len(packet["subsection_headings"])))]
    if not isinstance(value, dict) or not isinstance(value.get("parts"), dict) or set(value["parts"]) != set(expected):
        raise ValueError("계획의 본문 칸이 누락·추가됐습니다.")
    return {"parts": {key: render_part(clean_part(value["parts"][key], packet, index), allowed_ids(packet, key), key)
                      for index, key in enumerate(expected)}}


def render_generation(value, packets, single):
    if single:
        return render_parts(value, next(iter(packets.values())))
    if not isinstance(value, dict) or not isinstance(value.get("sections"), dict) or set(value["sections"]) != set(packets):
        raise ValueError("편집 결과에 계획의 장이 누락·추가됐습니다.")
    return {"sections": {sid: render_parts(value["sections"][sid], packet) for sid, packet in packets.items()}}
