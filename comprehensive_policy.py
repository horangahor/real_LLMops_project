"""Comprehensive-collection-only policy: decimal-comma consistency and a blocking/warning gate.

The question-based path (requirement_extraction.py) shares extraction helpers with the
comprehensive path but never calls this module, so its gate and facts are unchanged.
"""

import copy
import re
from difflib import SequenceMatcher

from research_coverage import conservation_issues
from research_values import missing_numbers

NUMERIC_CHECK = "comprehensive-decimal-comma-v1"
GATE_VERSION = "comprehensive-gate-v1"

COMMA_TIME = re.compile(r"(?<![\d.,])(\d{1,3}),(\d{3})(?![\d,])\s*(ms|s)(?![A-Za-z])")
TOTAL_TIME = re.compile(r"total\s+elapsed\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(ms|s)(?![A-Za-z])", re.I)
SEPARATOR = re.compile(r"^[\s=\-_*~#|.·…:]+$")
# Korean particles often follow a unit ("1560s도"), so only a following Latin letter ends the match.
MEASURED = re.compile(r"\d+(?:[.,]\d+)?\s*(?:ms|μs|µs|us|ns|s|%|배|초|분|x|KB|MB|GB)(?![A-Za-z])|\d+[.,]\d+|[:=]\s*\d", re.I)
LIST_NUMBER = re.compile(r"^\s*(?:\d+[.)]|[●•\-*])\s*")
PRIMARY_ELEMENT = re.compile(r"^p\d+:e\d+$")
ACRONYM_ISSUE = "원문 식별자 미보존"
RESPONSE_FAILURE = re.compile(r"응답 미완료|완결된 JSON|검증 실패|재검토를 완료하지 못했습니다")
UNREADABLE_IMAGE = re.compile(r"^p\d+: 이미지\d+ 판독 불가$")


def _seconds(value, unit):
    return float(value) / 1000 if unit == "ms" else float(value)


def _percent_after(text, end):
    match = re.match(r"\s*[(/]?\s*(\d+(?:\.\d+)?)\s*%", text[end:end + 24])
    return float(match[1]) if match else None


def decimal_comma_suspects(text):
    """Comma tokens whose thousands reading contradicts the element's own total or share."""
    totals = [_seconds(m[1].replace(",", "."), m[2]) for m in TOTAL_TIME.finditer(text)]
    suspects = []
    for match in COMMA_TIME.finditer(text):
        whole, fraction, unit = match.groups()
        thousands = _seconds(whole + fraction, unit)
        decimal = _seconds(f"{whole}.{fraction}", unit)
        share = _percent_after(text, match.end())
        reasons = []
        for total in totals:
            if thousands > total:
                reasons.append(f"천 단위로 읽으면 {whole}{fraction}{unit}가 total elapsed {total:g}s보다 큼")
            if share is not None and total and abs(100 * decimal / total - share) <= max(1.5, share * 0.15):
                reasons.append(f"소수로 읽은 {whole}.{fraction}{unit}가 total 대비 {share:g}%와 일치")
        if reasons:
            suspects.append({"raw": match.group(0).strip(), "thousands": whole + fraction,
                             "decimal": f"{whole}.{fraction}", "unit": unit, "reasons": reasons})
    return suspects


def _human_reviewed_fact_ids(extraction):
    return {record.get("fact_id") for record in extraction.get("human_fact_reviews", [])}


def numeric_issues_for(fact, elements):
    issues = []
    for measurement in fact.get("measurements", []):
        texts = [elements[key]["text"] for key in measurement.get("element_ids", []) if key in elements]
        for text in texts:
            for suspect in decimal_comma_suspects(text):
                if measurement.get("value") == suspect["thousands"] and measurement.get("unit") == suspect["unit"]:
                    issues.append(f"소수 쉼표 의심({NUMERIC_CHECK}): 원문 '{suspect['raw']}'를 "
                                  f"{suspect['thousands']}{suspect['unit']}로 정규화함. "
                                  f"{suspect['decimal']}{suspect['unit']}일 가능성. 근거: " + "; ".join(suspect["reasons"]))
    return list(dict.fromkeys(issues))


def apply_numeric_policy(extraction, elements):
    """Add review-required numeric issues; never rewrite the value itself."""
    reviewed = _human_reviewed_fact_ids(extraction)
    flags = []
    for fact in extraction.get("items", []):
        if fact.get("id") in reviewed:
            continue
        new = [issue for issue in numeric_issues_for(fact, elements) if issue not in fact.get("numeric_issues", [])]
        if new:
            fact["numeric_issues"] = list(fact.get("numeric_issues", [])) + new
            flags.append({"fact_id": fact["id"], "issues": new})
    return flags


def _compact(text):
    return re.sub(r"\s+", "", text or "").casefold()


def _structured(facts):
    fields = ("statement", "limits", "conditions", "observations", "parameters", "measurements")
    return "\n".join(str({key: fact.get(key) for key in fields}) for fact in facts)


def is_non_research(element):
    """Separators, short headings and connective phrases without any measurement."""
    text = element.get("text", "")
    if SEPARATOR.match(text):
        return True
    if MEASURED.search(text):
        return False
    compact = _compact(LIST_NUMBER.sub("", text))
    heading = str(element.get("category", "")).startswith("heading")
    return len(compact) <= (60 if heading else 20)


def _covered_twin(key, elements, ledger, writing_sources, settled):
    """A primary element on the same page with the same text that is preserved or itself settled as a warning."""
    element = elements[key]
    text = _compact(element["text"])
    if not text:
        return None
    for other_key, other in elements.items():
        if other_key == key or other["page"] != element["page"] or not PRIMARY_ELEMENT.match(other_key):
            continue
        row = ledger.get(other_key, {})
        if other_key not in writing_sources and other_key not in settled and not (
                row.get("state") in ("represented", "duplicate", "raw_data") and row.get("fact_ids")):
            continue
        other_text = _compact(other["text"])
        if text in other_text or SequenceMatcher(None, text[:2000], other_text[:2000]).ratio() >= 0.85:
            return other_key
    return None


def classify_open_items(extraction, elements):
    """Split unresolved source items into blocking omissions and warnings that need no drafting stop."""
    completion = extraction.get("completion", {})
    ledger = extraction.get("element_ledger", {})
    writing_ids = set(extraction.get("writing_fact_ids", []))
    writing = [fact for fact in extraction.get("items", []) if fact["id"] in writing_ids]
    writing_sources = {source["element_id"] for fact in writing for source in fact.get("sources", [])}
    blocking, warnings, settled = [], [], set()
    keyed = []
    for item in completion.get("unresolved_source_items", []):
        key = next((candidate for candidate in ledger if item.startswith(candidate + ":")), None)
        if key is None:
            target = warnings if UNREADABLE_IMAGE.match(item) else blocking
            target.append({"item": item, "category": "unreadable_image" if target is warnings else "other"})
        else:
            keyed.append((key, item))
    # Primary parses first, so a re-read copy can follow its primary's settled warning.
    keyed.sort(key=lambda pair: not PRIMARY_ELEMENT.match(pair[0]))
    for key, item in keyed:
        row = ledger[key]
        note = row.get("note", "")
        element = (elements or {}).get(key)
        if element is None:
            blocking.append({"item": item, "category": "source_unavailable"})
            continue
        text = element.get("text", "")
        linked = [fact for fact in writing if fact["id"] in row.get("fact_ids", [])
                  or any(source["element_id"] == key for source in fact.get("sources", []))]
        if RESPONSE_FAILURE.search(note):
            blocking.append({"item": item, "category": "response_failure"})
            continue
        if is_non_research(element):
            warning = {"item": item, "category": "non_research"}
        elif note.startswith(ACRONYM_ISSUE) and linked and all(
                issue.startswith(ACRONYM_ISSUE) for issue in conservation_issues(element, linked, "represented")):
            warning = {"item": item, "category": "acronym_only"}
        elif not PRIMARY_ELEMENT.match(key) and \
                (twin := _covered_twin(key, elements, ledger, writing_sources, settled)) and \
                not missing_numbers(text, elements[twin]["text"] + "\n" + _structured(writing)):
            warning = {"item": item, "category": "reread_duplicate", "covered_by": twin}
        else:
            blocking.append({"item": item, "category": "missing_content"})
            continue
        warnings.append(warning)
        settled.add(key)
    if completion.get("unreviewed_elements"):
        blocking.append({"item": f"미검토 원문 요소 {len(completion['unreviewed_elements'])}개", "category": "unreviewed"})
    for fact_id in completion.get("quarantined_fact_ids", []):
        warnings.append({"item": f"{fact_id}: 검증에서 작성 입력 제외", "category": "quarantined_fact"})
    # A person may let drafting proceed past a reviewed item. The decision binds to the exact item text,
    # so a re-extraction that changes the item asks again.
    accepted = {record["item"]: record for record in extraction.get("human_gate_decisions", [])
                if record.get("decision") == "accept"}
    for row in [row for row in blocking if row["item"] in accepted]:
        blocking.remove(row)
        warnings.append({**row, "category": "human_accepted", "original_category": row["category"],
                         "reason": accepted[row["item"]]["reason"]})
    return blocking, warnings


def apply_comprehensive_policy(extraction, elements, refresh=None):
    """Run the numeric check, refresh writing inputs, then recompute the drafting gate. Returns True if changed."""
    before = copy.deepcopy((extraction.get("items"), extraction.get("completion"), extraction.get("comprehensive_policy")))
    flags = apply_numeric_policy(extraction, elements) if elements else []
    if flags and refresh:
        refresh(extraction)
    blocking, warnings = classify_open_items(extraction, elements)
    completion = extraction.setdefault("completion", {})
    complete_scan = completion.get("pages_reviewed") == completion.get("source_pages")
    completion["gate"] = {"version": GATE_VERSION, "blocking": blocking, "warnings": warnings,
                          "source_elements_available": bool(elements)}
    completion["blocking_source_items"] = [row["item"] for row in blocking]
    completion["warning_source_items"] = [row["item"] for row in warnings]
    completion["ready_for_drafting"] = bool(extraction.get("research")) and complete_scan and not blocking
    policy = extraction.setdefault("comprehensive_policy", {"numeric_check": NUMERIC_CHECK, "numeric_flags": []})
    known = {(row["fact_id"], issue) for row in policy["numeric_flags"] for issue in row["issues"]}
    policy["numeric_flags"] += [row for row in flags if any((row["fact_id"], issue) not in known for issue in row["issues"])]
    return before != (extraction.get("items"), extraction.get("completion"), extraction.get("comprehensive_policy"))
