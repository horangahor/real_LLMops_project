"""Numeric/identifier normalization and claim-wide source guards; never infer new results."""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

NUMBER = re.compile(r"(?<![A-Za-z_\d.])[+-]?\d+(?:[.,]\d+)*(?:[eE][+-]?\d+)?(?![\d.])")
VERSION = re.compile(r"(?<![A-Za-z_\d.])(?:[vV]\d+(?:[.-]\d+)+|\d+(?:\.\d+){2,})(?![A-Za-z_\d.])")
POWER = re.compile(r"10\s*(?:\^|\*\*)\s*\{?\s*([+-]?\d+)\s*\}?")
SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def canonical(value):
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("유한한 수치만 허용합니다.")
    return str(number.normalize()) if number else "0"


def text_normalize(value):
    value = re.sub(r"10([⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+)", lambda m: "10^" + m[1].translate(SUPERSCRIPT), value)
    return unicodedata.normalize("NFKC", value).replace("−", "-").replace("，", ",")


def numeric_atoms(value):
    text = text_normalize(value)
    versions = [m.group() for m in VERSION.finditer(text)]
    text = VERSION.sub(lambda m: " " * len(m.group()), text)
    atoms = []
    for match in POWER.finditer(text):
        exponent = int(match[1])
        if abs(exponent) > 100:
            raise ValueError("지수 범위가 너무 큽니다.")
        atoms.append((match.group(), {canonical(Decimal(10) ** exponent)}))
    text = POWER.sub(lambda m: " " * len(m.group()), text)
    for match in NUMBER.finditer(text):
        raw = match.group()
        variants = {raw}
        if "," in raw:
            if "." in raw or raw.count(",") > 1:
                variants = {raw.replace(",", "")}
            else:
                left, right = raw.split(",")
                variants = {left + "." + right}
                if len(right) == 3:
                    variants.add(left + right)
        normalized = set()
        for variant in variants:
            try:
                normalized.add(canonical(variant))
            except InvalidOperation:
                pass
        if normalized:
            atoms.append((raw, normalized))
    return atoms, versions


def missing_numbers(claim, source_text):
    atoms, versions = numeric_atoms(claim)
    originals, _ = numeric_atoms(source_text)
    pool = set().union(*(values for _, values in originals)) if originals else set()
    errors = [raw for raw, values in atoms if not values & pool]
    normalized_source = text_normalize(source_text).casefold()
    errors += [version for version in versions if version.casefold() not in normalized_source]
    return list(dict.fromkeys(errors))


def normalize_measurement(measurement, source_text):
    result = dict(measurement)
    atoms, versions = numeric_atoms(result["value"])
    # The model sometimes labels a single literal as a range. Correct only this
    # unambiguous type error; never split compound comparisons or invent endpoints.
    if result.get("value_kind") == "range" and len(atoms) == 1 and not versions:
        result["declared_value_kind"] = "range"
        result["value_kind"] = "scalar"
    expected = 2 if result.get("value_kind", "scalar") == "range" else 1
    if versions or len(atoms) != expected:
        raise ValueError("수치는 scalar/range로 분리하고 버전·정성 문장은 parameters/observations에 넣어야 합니다.")
    if missing_numbers(result["value"], source_text):
        raise ValueError("측정값이 연결 원문에 없습니다.")
    # A comma with three following digits has two possible meanings. Keep its raw spelling for review.
    if any(len(values) != 1 for _, values in atoms):
        result["normalization_status"] = "ambiguous_decimal_separator"
        result["raw_value"] = result["value"]
        return result
    values = [next(iter(variants)) for _, variants in atoms]
    result["raw_value"] = result["value"]
    result["value"] = values[0] if expected == 1 else "~".join(values)
    result["normalization_status"] = "normalized"
    return result
