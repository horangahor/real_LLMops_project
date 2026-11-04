"""Lossless source pooling and conservative byte budgets for drafting requests."""

import copy
import hashlib
import json
import os
from pathlib import Path

from document_parse import write_json

SOURCE_PROTOCOL = """\nsource_elements는 이번 요청의 원문 저장소다. facts.sources의 source_ref를 이 저장소에서 찾아 원문·페이지·출처를 대조한다.
같은 원문을 여러 근거가 공유할 수 있다. source_ref는 연구 사실 ID가 아니며 본문 인용에는 fact.id만 쓴다."""


class DraftingBudgetError(ValueError):
    pass


NO_CACHE = object()


def cached_response(engine, folder, name, system, packet, schema):
    try:
        return engine.call(folder, name, system, packet, schema, cache_only=True)
    except FileNotFoundError:
        return NO_CACHE
    except RuntimeError as error:
        if "완결된 JSON" not in str(error):
            raise
        return NO_CACHE


def request_limit():
    value = int(os.getenv("PAPER_REQUEST_MAX_BYTES", "240000"))
    if value < 4000:
        raise ValueError("PAPER_REQUEST_MAX_BYTES는 4000 이상이어야 합니다.")
    return value


def compact_packet(packet):
    result = copy.deepcopy(packet)
    sources = copy.deepcopy(result.pop("source_elements", {}))
    research = result.get("research")
    if isinstance(research, dict):
        # Writing metadata references the facts already present in research.
        for scoped in result.get("section_packets", {}).values():
            for field in ("facts", "tables", "human_guidance", "reference_guides"):
                scoped.pop(field, None)
            if "plan" in result and "section_plan" in scoped:
                scoped["section_plan"] = {k: v for k, v in scoped["section_plan"].items()
                                           if k in ("id", "title", "role", "purpose", "subsections")}
        allowed = ("title", "facts", "tables", "source", "provenance", "human_guidance",
                   "requirement_coverage", "requirement_applicability")
        research = {k: v for k, v in research.items() if k in allowed}
        result["research"] = research
        if "requirement_coverage" in research:
            research["requirement_coverage"] = {key: {k: v for k, v in row.items()
                if k in ("status", "missing_fields", "decision_id")}
                for key, row in research["requirement_coverage"].items()}
        if "requirement_applicability" in research:
            research["requirement_applicability"] = {key: {"status": row["status"]}
                                                       for key, row in research["requirement_applicability"].items()}
    guidance_owner = research if isinstance(research, dict) else result
    if "human_guidance" in guidance_owner:
        latest = {d["question_id"]: d for d in guidance_owner["human_guidance"]}
        fields = ("id", "question_id", "action", "instruction", "provided_text", "writing_instruction", "acceptance_method")
        guidance_owner["human_guidance"] = [{k: copy.deepcopy(d[k]) for k in fields if k in d}
                                              for d in latest.values()]

    def pool(value):
        if isinstance(value, list):
            return [pool(v) for v in value]
        if not isinstance(value, dict):
            return value
        if "id" in value and "statement" in value and isinstance(value.get("sources"), list):
            fact = {k: pool(v) for k, v in value.items() if k != "sources"}
            fact["sources"] = []
            for source in value["sources"]:
                if set(source) == {"source_ref"}:
                    if source["source_ref"] not in sources:
                        raise ValueError("요청 원문 저장소에 source_ref가 없습니다.")
                    fact["sources"].append(copy.deepcopy(source))
                    continue
                digest = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                key = "src_" + digest[:20]
                if key in sources and sources[key] != source:
                    raise ValueError("요청 원문 식별자가 충돌했습니다.")
                sources[key] = copy.deepcopy(source)
                fact["sources"].append({"source_ref": key})
            return fact
        return {k: pool(v) for k, v in value.items()}

    result = pool(result)
    if sources:
        result["source_elements"] = sources
    return result


def request_bytes(system, packet, schema):
    # This is a conservative byte budget, NOT an exact provider token count.
    content = json.dumps(packet, ensure_ascii=False)
    return len((system + SOURCE_PROTOCOL + content + json.dumps(schema, ensure_ascii=False)).encode("utf-8")) + 2048


def fits_request(system, packet, schema):
    # Leave headroom for correction instructions and a rejected response.
    return request_bytes(system, compact_packet(packet), schema) <= int(request_limit() * .75)


def call_bounded(engine, folder, name, system, packet, schema, *, source_protocol=True):
    # Old completed calls can be reused without sending their oversized inputs.
    cached = cached_response(engine, folder, name, system, packet, schema)
    if cached is not NO_CACHE:
        return cached
    compact = compact_packet(packet)
    size = request_bytes(system, compact, schema)
    digest = hashlib.sha256(json.dumps(compact, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    write_json(Path(folder) / "request-sizes" / f"{name}-{digest}.json", {
        "input_bytes": size, "limit_bytes": request_limit(), "source_elements": len(compact.get("source_elements", {})),
        "within_budget": size <= request_limit(), "estimate": "UTF-8 byte budget including schema and overhead; not exact token count"})
    if size > request_limit():
        raise DraftingBudgetError(f"작성 요청 {name}의 입력 {size}바이트가 예산 {request_limit()}바이트를 넘습니다. 요청을 더 나눠야 합니다.")
    return engine.call(folder, name, system + SOURCE_PROTOCOL if source_protocol else system, compact, schema)
