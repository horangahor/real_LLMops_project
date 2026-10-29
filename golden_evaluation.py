"""원문 대조 기준표로 저장된 골든 목차를 평가한다. 외부 API·서비스 입력 변경 없음."""

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROLES = {"introduction", "related_work", "background", "methods", "evaluation",
         "limitations", "conclusion", "other"}


def normalize_title(value):
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold()
                   if char.isalnum())


def title_parts(title):
    title = unicodedata.normalize("NFKC", title).strip()
    match = re.match(r"^(\d+(?:\.\d+)*)(?:[.)]?\s+)(.+)$", title)
    number, body = (match.group(1), match.group(2)) if match else (None, title)
    alternatives = [body, re.sub(r"\([^()]*\)", "", body)]
    alternatives.extend(re.findall(r"\(([^()]*)\)", body))
    return number, {normalize_title(part) for part in alternatives if normalize_title(part)}


def validate_reference(reference):
    items = reference.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("평가 기준에는 비어 있지 않은 items 배열이 필요합니다.")
    ids, aliases = set(), {}
    for item in items:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"\d+(?:\.\d+)*", identifier) or identifier in ids:
            raise ValueError("평가 기준의 절 번호는 고유한 숫자 목차여야 합니다.")
        if item.get("parent") is not None and item["parent"] not in ids:
            raise ValueError("평가 기준의 부모 절은 앞에 선언되어야 합니다.")
        if item.get("role") not in ROLES or type(item.get("page")) is not int or item["page"] < 1:
            raise ValueError("평가 기준의 역할·페이지가 올바르지 않습니다.")
        names = [item.get("title"), *item.get("aliases", [])]
        if any(not isinstance(name, str) or not normalize_title(name) for name in names):
            raise ValueError("평가 기준의 제목·별칭은 비어 있지 않은 문자열이어야 합니다.")
        for name in names:
            normalized = normalize_title(name)
            if normalized in aliases and aliases[normalized] != identifier:
                raise ValueError("서로 다른 절의 제목·별칭이 충돌합니다.")
            aliases[normalized] = identifier
        ids.add(identifier)
    return aliases


def flatten_outline(nodes, parent=None):
    if not isinstance(nodes, list):
        raise ValueError("observed_outline과 children은 배열이어야 합니다.")
    result = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("title"), str) or not node["title"].strip():
            raise ValueError("예측 목차에 유효한 제목이 필요합니다.")
        if node.get("role") not in ROLES:
            raise ValueError("예측 목차의 role이 올바르지 않습니다.")
        pages = node.get("source_pages")
        if pages is not None and (not isinstance(pages, list) or any(type(p) is not int or p < 1 for p in pages)):
            raise ValueError("예측 목차의 source_pages가 올바르지 않습니다.")
        key = (parent or ()) + (index,)
        number, names = title_parts(node["title"])
        result.append({"key": key, "parent_key": parent, "title": node["title"],
                       "number": number, "names": names, "role": node["role"], "pages": pages})
        result.extend(flatten_outline(node.get("children", []), key))
    return result


def fraction(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def extraction_metrics(correct, predicted, expected):
    precision, recall = fraction(correct, predicted), fraction(correct, expected)
    return {"true_positive": correct, "false_positive": predicted-correct,
            "false_negative": expected-correct, "precision": precision, "recall": recall,
            "f1": 2*correct/(predicted+expected) if predicted+expected else None}


def evaluate_outline(profile, reference):
    aliases = validate_reference(reference)
    expected = {item["id"]: item for item in reference["items"]}
    predicted = flatten_outline(profile.get("observed_outline"))
    assigned, matches, unmatched = set(), [], []
    for item in predicted:
        candidates = {aliases[name] for name in item["names"] if name in aliases}
        if len(candidates) != 1:
            unmatched.append({"title": item["title"], "reason": "ambiguous" if candidates else "unknown_title"})
            continue
        identifier = next(iter(candidates))
        if identifier in assigned:
            unmatched.append({"title": item["title"], "reason": "duplicate"})
            continue
        assigned.add(identifier)
        matches.append((item, expected[identifier]))
    key_to_id = {item["key"]: truth["id"] for item, truth in matches}
    details = []
    for item, truth in matches:
        parent = key_to_id.get(item["parent_key"]) if item["parent_key"] is not None else None
        parent_ok = (item["parent_key"] is None and truth["parent"] is None) or (
            item["parent_key"] is not None and parent is not None and parent == truth["parent"])
        number_ok, role_ok = item["number"] == truth["id"], item["role"] == truth["role"]
        details.append({"reference_id": truth["id"], "reference_title": truth["title"],
                        "prediction_title": item["title"], "predicted_number": item["number"],
                        "expected_parent": truth["parent"], "predicted_parent_identity": parent,
                        "number_correct": number_ok, "parent_correct": parent_ok,
                        "role_correct": role_ok, "expected_role": truth["role"], "predicted_role": item["role"],
                        "reference_page": truth["page"], "predicted_pages": item["pages"],
                        "page_correct": truth["page"] in (item["pages"] or []),
                        "fully_correct": number_ok and parent_ok and role_ok})
    total, found = len(expected), len(details)
    exact = sum(row["number_correct"] for row in details)
    reference_children = sum(item["parent"] is not None for item in expected.values())
    matched_children = [row for row in details if row["expected_parent"] is not None]
    correct_children = sum(row["number_correct"] for row in matched_children)
    metrics = {
        "heading_identity": extraction_metrics(found, len(predicted), total),
        "heading_number_and_identity": extraction_metrics(exact, len(predicted), total),
        "number_accuracy_on_matched": fraction(exact, found),
        "parent_accuracy_on_matched": fraction(sum(row["parent_correct"] for row in details), found),
        "child_parent_accuracy_on_matched_children": fraction(sum(row["parent_correct"] for row in matched_children), len(matched_children)),
        "role_accuracy_on_matched": fraction(sum(row["role_correct"] for row in details), found),
        "exact_subsection_recall": fraction(correct_children, reference_children),
        "fully_correct_item_recall": fraction(sum(row["fully_correct"] for row in details), total),
        "page_accuracy_on_matched": fraction(sum(row["page_correct"] for row in details), found),
    }
    return {"reference_count": total, "prediction_count": len(predicted), "matched_count": found,
            "metrics": metrics, "matches": details,
            "missing": [item for identifier,item in expected.items() if identifier not in assigned],
            "unmatched_predictions": unmatched}


def verify_source(reference, source_path):
    digest = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    if digest != reference["source_sha256"]:
        raise ValueError("평가 기준에 연결된 PDF와 현재 원본의 SHA-256이 다릅니다.")
    return digest


def select_profile(profiles, source_file):
    if isinstance(profiles, dict):
        profiles = [profiles]
    selected = [p for p in profiles if Path(p.get("file", "").replace("\\", "/")).name == source_file]
    if len(selected) != 1:
        raise ValueError("평가 대상 PDF에 대응하는 프로파일이 정확히 하나 필요합니다.")
    return selected[0]


def percent(value):
    return "N/A" if value is None else f"{100*value:.1f}%"


def ratio(metric):
    return f"{metric['numerator']}/{metric['denominator']} ({percent(metric['value'])})"


def report_markdown(report):
    metrics = report["metrics"]
    heading, exact = metrics["heading_identity"], metrics["heading_number_and_identity"]
    lines = ["# 골든 샘플 구조 추출 평가", "",
             f"- 원본: `{report['source_file']}` (PDF {report['pdf_page_count']}쪽)",
             f"- 예측 출처: `{report['prediction_provenance']}` / `{report['prediction_path']}`",
             f"- 평가 항목: 원문 {report['reference_count']}개, 예측 {report['prediction_count']}개, 제목 대응 {report['matched_count']}개", "",
             "## 측정 범위와 한계", "",
             "저장된 분석 파일을 원문 대조 기준표와 비교한 오프라인 평가다. 이 평가 명령은 Document Parse/Solar를 호출하지 않으며 OCR 성능을 측정하지 않는다. 특히 legacy_analysis는 이전 분석의 변환본이므로 현재 분석 모델의 성능으로 해석하면 안 된다.",
             "원문 대조 기준은 Codex가 페이지 이미지와 텍스트를 확인하여 작성했다. 사용자·전문가의 독립 검수 전이며 역할 분류에는 판단이 포함된다.",
             "한 편의 구조 추출 결과이며 초안 반영률·논문 품질·다른 PDF로의 일반화 성능을 뜻하지 않는다.", "",
             "## 결과", "", "| 지표 | 결과 |", "|---|---:|",
             f"| 제목 대응 정밀도 (번호 무관·사전 선언 번역 허용) | {ratio(heading['precision'])} |",
             f"| 제목 대응 재현율 | {ratio(heading['recall'])} |",
             f"| 제목 대응 F1 | {percent(heading['f1'])} |",
             f"| 제목+번호 정밀도 | {ratio(exact['precision'])} |",
             f"| 제목+번호 재현율 | {ratio(exact['recall'])} |",
             f"| 제목+번호 F1 | {percent(exact['f1'])} |",
             f"| 계층 정확도 (대응된 항목 한정·최상위 포함) | {ratio(metrics['parent_accuracy_on_matched'])} |",
             f"| 하위 절 부모 정확도 (대응된 하위 절 한정) | {ratio(metrics['child_parent_accuracy_on_matched_children'])} |",
             f"| 역할 분류 정확도 (대응된 항목 한정) | {ratio(metrics['role_accuracy_on_matched'])} |",
             f"| 번호가 맞는 하위 절 재현율 | {ratio(metrics['exact_subsection_recall'])} |",
             f"| 제목·번호·계층·역할을 모두 맞춘 항목 재현율 | {ratio(metrics['fully_correct_item_recall'])} |",
             f"| 시작 페이지 일치율 (대응된 항목 한정) | {ratio(metrics['page_accuracy_on_matched'])} |", "",
             "조건부 계층·역할 정확도는 찾아낸 제목만 대상으로 한다. 누락은 재현율과 함께 판단해야 하며 이 점수만으로 전체 구조가 정확하다고 해석하면 안 된다.",
             "페이지 일치율은 시작 페이지가 source_pages에 포함되는지 측정한다. legacy 변환 시 null로 남긴 항목의 0점은 페이지 미제공이며 잘못된 페이지를 추측했다는 뜻은 아니다.", "",
             "## 항목별 비교", "", "| 원문 번호·제목 | PDF 쪽 | 예측 | 번호 | 부모 | 역할 |",
             "|---|---:|---|---|---|---|"]
    rows = {row["reference_id"]: row for row in report["matches"]}
    for item in report["reference_items"]:
        row = rows.get(item["id"])
        if row:
            flags = ["일치" if row[key] else "불일치" for key in ("number_correct", "parent_correct", "role_correct")]
            lines.append(f"| {item['id']} {item['title']} | {item['page']} | {row['prediction_title']} | {' | '.join(flags)} |")
        else:
            lines.append(f"| {item['id']} {item['title']} | {item['page']} | 누락 | — | — | — |")
    lines.extend(["", "## 재현 방법", "", "```powershell",
                  ".\\.venv\\Scripts\\python.exe -X utf8 -B golden_evaluation.py --profiles evaluation/golden/predictions/npu-legacy.json --output evaluation/golden/results/npu-legacy-baseline.json", "```", "",
                  "현재 프로파일 평가: --profiles paper_structure_analysis.json 및 별도 --output 경로를 사용한다. 기존 초안·입력 프로파일은 수정하지 않는다.", "",
                  "## 다음 평가", "",
                  "1. 기준표를 원문과 함께 사용자 검수한다.",
                  "2. 새 분석 결과를 별도 파일에 저장하고 같은 기준표로 비교한다. 원본 파서 응답을 보존해야 파싱 누락과 LLM 분석 누락을 구분할 수 있다.",
                  "3. 구조 분석의 개선을 확인한 뒤, 작성 가이드의 근거성과 초안에서의 역할 반영을 별도 평가한다.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=BASE/"evaluation/golden/npu-reference.json")
    parser.add_argument("--profiles", type=Path, default=BASE/"paper_structure_analysis.json")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path, default=BASE/"evaluation/golden/results/npu-current.json")
    args = parser.parse_args(argv)
    if args.output.suffix != ".json":
        raise ValueError("평가 출력 경로는 .json이어야 합니다.")
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    prediction_bytes = args.profiles.read_bytes()
    profile = select_profile(json.loads(prediction_bytes), reference["source_file"])
    digest = verify_source(reference, args.source or BASE.parent/reference["source_file"])
    report = evaluate_outline(profile, reference)
    report.update({"evaluation_version": "golden-outline-v1", "source_file": reference["source_file"],
                   "source_sha256": digest, "pdf_page_count": reference["pdf_page_count"],
                   "reference_sha256": hashlib.sha256(args.reference.read_bytes()).hexdigest(),
                   "prediction_sha256": hashlib.sha256(prediction_bytes).hexdigest(),
                   "prediction_path": args.profiles.as_posix(), "prediction_provenance": profile.get("provenance"),
                   "annotation_provenance": reference["annotation_provenance"],
                   "scope": reference["scope"], "matching_policy": reference["matching_policy"],
                   "reference_items": reference["items"]})
    protected = {args.profiles.resolve(), args.reference.resolve(),
                 (BASE/"paper_structure_analysis.json").resolve()}
    if args.output.resolve() in protected:
        raise ValueError("평가 결과로 입력 프로파일·기준표를 덮어쓸 수 없습니다.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
    print(json.dumps({"reference_items": report["reference_count"], "predicted_items": report["prediction_count"],
                      "title_f1": report["metrics"]["heading_identity"]["f1"],
                      "title_number_f1": report["metrics"]["heading_number_and_identity"]["f1"],
                      "report": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
