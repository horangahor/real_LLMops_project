"""Conservative publication views; extracted tables and source identifiers stay intact."""

import copy
import re

POLICY = "publication-table-view-v2"


def trace_columns(columns):
    """Console fields accidentally parsed as headings are not paper tables."""
    fragments = sum(bool(re.search(r"\||(?:^|\s)\w+\s*=\s*[+−-]?\d|^\w+\s*=$", str(c))) for c in columns)
    console_marker = any(re.search(r"\||^\w+\s*=$", str(c)) for c in columns)
    return console_marker and fragments >= max(2, (len(columns) + 1) // 2)


def publication_notes(notes):
    # Untyped source prose is kept in the source/audit, not promoted to a
    # scholarly footnote. Explicit interpretation notes remain verbatim.
    roles = {"unit", "condition", "abbreviation", "uncertainty", "missing_value", "statistical_definition"}
    kept, withheld = [], []
    for note in notes:
        text = note.get("text", "") if isinstance(note, dict) else str(note)
        explicit = (isinstance(note, dict) and note.get("kind") in roles) or re.match(
            r"^\s*(?:단위|측정\s*조건|실험\s*조건|약어|불확실성|결측값|통계\s*정의|Units?|Conditions?|Abbreviations?|Uncertainty|Missing values?)\s*[:：]", text, re.I)
        (kept if explicit and text.strip() else withheld).append(text)
    return kept, withheld


def _same(cells):
    values = [str(c).strip() for c in cells]
    return len(values) > 1 and bool(values[0]) and len(set(values)) == 1


def _header_row(cells):
    values = [str(c).strip() for c in cells]
    # Never promote a numeric measurement row or guess missing labels.
    return (bool(values) and all(values) and len(set(values)) == len(values)
            and all(not re.match(r"^[+−-]?\d", c) for c in values)
            and all(any(ch.isalpha() for ch in c) for c in values))


def prepare_tables(research):
    tables, audit = [], []
    for original in research.get("tables", []):
        table = copy.deepcopy(original)
        columns, rows = table["columns"], table["rows"]
        record = {"table_id": table["id"], "actions": [], "status": "eligible"}
        record.update({key: original[key] for key in ("page", "source_element_id", "origin") if key in original})
        if _same(columns):
            if not rows or not _header_row(rows[0]):
                record.update(status="withheld", reason="반복된 열 제목과 실제 열 제목을 확실히 구분할 수 없습니다.")
                audit.append(record)
                continue
            record["source_preamble"] = str(columns[0])
            table["columns"] = copy.deepcopy(rows[0])
            table["rows"] = copy.deepcopy(rows[1:])
            record["actions"].append("promoted_existing_header_row")
            record["header_source_row"] = 0
            notes, kept = [], []
            for row in table["rows"]:
                text = str(row[0]).strip()
                # A repeated long prose row after a merged-title artifact is a
                # note. Equal numeric values/status cells remain data rows.
                if (_same(row) and any(ch.isalpha() for ch in text) and any(ch.isspace() for ch in text)
                        and (len(text) > 80 or text.endswith((":", "：")))):
                    if text not in notes:
                        notes.append(text)
                else:
                    kept.append(row)
            table["rows"] = kept
            if notes:
                table["notes"] = list(dict.fromkeys(table.get("notes", []) + notes))
                record["actions"].append("collapsed_repeated_full_width_notes")
            if not table.get("caption"):
                table["caption"] = " / ".join(map(str, table["columns"]))
        if trace_columns(table["columns"]):
            record.update(status="withheld", reason="열 제목이 변수 할당·실행 결과 조각인 원시 트레이스 표입니다.")
        elif not table["rows"]:
            record.update(status="withheld", reason="열 제목 외에 출판할 데이터 행이 없습니다.")
        else:
            tables.append(table)
        audit.append(record)
    return {"policy": POLICY, "tables": tables, "audit": audit}
