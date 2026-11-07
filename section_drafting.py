"""Run one saved plan section through the existing first editor and its review."""
import json
import re
from pathlib import Path

from document_parse import write_json
from hierarchical_drafting import run_hierarchical
from paper_plan import IDENTIFIER, normalize_research, project_profile, validate_plan


def read(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"저장된 작성 계획의 입력이 없습니다: {path.name}. 작성 계획을 먼저 만들어주세요.")
    return json.loads(path.read_text(encoding="utf-8"))


def contains(stored, expected):
    """Core inputs must match; frozen budget/guidance extensions stay intact."""
    if isinstance(expected, dict):
        return isinstance(stored, dict) and all(key in stored and contains(stored[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(stored, list) and len(stored) == len(expected) and all(contains(a, b) for a, b in zip(stored, expected))
    return stored == expected


def load_section_inputs(folder, section_id):
    folder = Path(folder)
    if not isinstance(section_id, str) or not IDENTIFIER.fullmatch(section_id):
        raise ValueError("절 ID가 잘못됐습니다.")
    plan = read(folder / "plan.json")
    if section_id not in plan["generation_order"]:
        raise ValueError("작성 계획에서 생성 가능한 절을 선택해주세요.")
    section = next(s for s in plan["sections"] if s["id"] == section_id)
    research = normalize_research(read(folder / "research.json"))
    # Use this plan's frozen tables, leaf prompts and budget shares. Parent
    # editors receive current common editing rules in run_hierarchical.
    # No extraction/planning agent is called.
    publication = read(folder / "publication-table-input.json")
    writing_research = {**research, "tables": publication["tables"]}
    packet = read(folder / "contexts/sections" / f"{section_id}.json")
    if packet["section_plan"] != section:
        raise ValueError("저장된 절 입력과 작성 계획이 일치하지 않습니다. 작성 계획을 다시 확인해주세요.")
    catalog = {}
    for path in (folder / "contexts/sections").glob("*.json"):
        for guide in read(path).get("reference_guides", []):
            catalog[guide["id"]] = guide
    manifest = read(folder / "manifest.json")
    validate_plan(plan, writing_research, catalog, project_profile(manifest["project"]))
    from paper_context import build_contexts
    rebuilt = build_contexts(plan, writing_research, catalog)
    if not contains(packet, rebuilt["sections"][section_id]):
        raise ValueError("저장된 절 입력의 근거·가이드가 작성 계획과 일치하지 않습니다.")
    children = {}
    for index in range(max(1, len(section["subsections"]))):
        key = f"p{index}"
        child = read(folder / "contexts/subsections" / f"{section_id}-{key}.json")
        expected = rebuilt["subsections"][section_id][key]
        if not contains(child, expected):
            raise ValueError("저장된 소절 입력과 절 계획이 일치하지 않습니다.")
        children[key] = child
    contexts = {"sections": {section_id: packet}, "subsections": {section_id: children},
                "composition_policy": read(folder / "composition-policy.json")}
    return plan, research, writing_research, contexts, catalog


def run_saved_section(engine, folder, section_id, progress=None):
    """Keep full-paper outputs untouched while sharing validated stage caches."""
    from planned_paper import index_paragraphs, fingerprint
    from publication_tables import render_section_tables
    from paper_display import safe_markdown

    folder = Path(folder)
    plan, research, writing_research, contexts, catalog = load_section_inputs(folder, section_id)
    if progress:
        progress(10, "선택한 절의 저장된 계획·근거·분량을 불러왔습니다.")
    workflow = run_hierarchical(engine, folder, writing_research, plan, contexts, catalog, progress,
                                only_section=section_id)
    section = next(s for s in plan["sections"] if s["id"] == section_id)
    index = next(i for i, s in enumerate(plan["sections"], 1) if s["id"] == section_id)
    body = workflow["sections"][section_id]
    markdown = safe_markdown(f"## 제{index}장 {section['title']}\n\n" + render_section_tables(
        body, section, {t["id"]: t for t in research["tables"]}, index) + "\n")
    # The existing protocol links evidence at paragraph granularity. Expose the
    # exact IDs and source quotes; do not imply a new sentence-level attribution.
    from bounded_drafting import cited_ids
    facts = {f["id"]: f for f in research["facts"]}
    provenance = [dict(paragraph_id=pid, text=re.sub(r"\[근거:[^\]]+\]", "", p["text"]).strip(),
                       evidence=[facts[key] for key in sorted(cited_ids(p["text"]))])
                  for pid, p in index_paragraphs({section_id: body}).items()]
    result = dict(scope="section", section_id=section_id, section_title=section["title"], section_number=index,
                  run_dir=str(folder), source=research.get("source", {}), draft_markdown=markdown, cited_markdown=body,
                  plan_fingerprint=fingerprint(plan), workflow=workflow["workflow"],
                  review=workflow["review"], review_warnings=workflow["review_warnings"],
                  writing_length=workflow["writing_length"], provenance=provenance)
    output = folder / "section-runs" / section_id
    write_json(output / "result.json", result)
    write_json(output / "provenance.json", provenance)
    (output / "draft.md").write_text(markdown, encoding="utf-8")
    if progress:
        progress(100, f"{section['title']} · 소절 작성 및 1차 편집·검토 완료")
    return result
