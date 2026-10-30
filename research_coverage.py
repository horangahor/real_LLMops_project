"""Necessary literal-conservation checks complementing, never replacing, semantic review."""

import json
import re

from research_values import missing_numbers

ACRONYM = re.compile(r"(?<![A-Za-z0-9_])[A-Z][A-Z0-9_]{1,59}(?![A-Za-z0-9_])")
LABEL_WORDS = {"ON", "OFF", "THE", "AND", "OR", "NOT", "WITH", "TO", "IN", "OF", "FOR", "IS", "AS", "AT", "BY",
               "ONLY", "MODE", "OUTPUT", "INDEX", "DIMENSION", "SUM", "MIN", "MAX", "MEAN", "MEDIAN", "TOTAL", "TRUE", "FALSE", "NULL"}
MEASUREMENT = re.compile(r"(?P<label>[A-Za-z가-힣][A-Za-z0-9가-힣 _()/\-]{0,60}?)\s*[:=]\s*"
                         r"(?P<value>[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?)"
                         r"(?P<unit>[ \t]*(?:samples/sec|ns|us|μs|µs|ms|s|%))?")
METRIC_LABEL = re.compile(r"elapsed|latency|throughput|jitter|overall|sum|mean|median|\bmin\b|\bmax\b|시간|지연|평균", re.I)
DURATION = re.compile(r"(?<![A-Za-z0-9_.])(?P<value>[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?(?:\s*[~～→]\s*\d+(?:[.,]\d+)*)?)\s*(?P<unit>ns|us|μs|µs|ms|s)(?![A-Za-z])")


def structured_text(facts):
    fields = ("statement", "limits", "conditions", "observations", "parameters", "measurements")
    return "\n".join(json.dumps({k: f[k] for k in fields if k in f}, ensure_ascii=False) for f in facts)


def conservation_issues(element, facts, state):
    if state in ("unresolved", "unreadable", "no_research"):
        return []
    text = element["text"]
    preserved = structured_text(facts)
    issues = []
    # Screenshots also contain clipped window titles and UI chrome. Requiring
    # every OCR acronym there fabricates research content from display labels.
    # Labelled numerical summaries remain mandatory for every category below.
    if state in ("represented", "duplicate") and element.get("category", "paragraph") != "figure":
        required = set(ACRONYM.findall(text)) - LABEL_WORDS
        missing = sorted(name for name in required if name.casefold() not in preserved.casefold())
        if missing:
            issues.append("원문 식별자 미보존: " + ", ".join(missing))
    # A raw prediction matrix may remain raw data, but its labelled performance summaries may not disappear.
    for match in MEASUREMENT.finditer(text):
        if METRIC_LABEL.search(match["label"]) and missing_numbers(match["value"], preserved):
            issues.append(f"원문 지표 값 미보존: {match['label'].strip()} = {match['value']}{match['unit'] or ''}")
    for match in DURATION.finditer(text):
        # A spaced leading digit in standard OCR is ambiguous (e.g. '6 4ms').
        # Its independently re-read counterpart is checked in its own ledger row.
        if re.search(r"\d[ \t]+$", text[:match.start()]):
            continue
        if missing_numbers(match["value"], preserved):
            issues.append(f"원문 시간 수치 미보존: {match['value']}{match['unit']}")
    return list(dict.fromkeys(issues))
