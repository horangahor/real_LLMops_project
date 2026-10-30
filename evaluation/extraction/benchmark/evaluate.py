"""Score a frozen extraction using explicit source-audit annotations, without API calls."""

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def rate(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def indexed(items, key, expected, label):
    keys = [item[key] for item in items]
    if len(keys) != len(set(keys)) or set(keys) != set(expected):
        raise ValueError(f"{label}: 누락·중복·알 수 없는 ID가 있습니다.")
    return {item[key]: item for item in items}


def score(prediction, reference, annotations, protocol):
    if not (prediction["source"]["sha256"] == reference["source_sha256"] == annotations["source_sha256"] == protocol["source_sha256"]):
        raise ValueError("평가 대상 원본 해시가 다릅니다.")
    if annotations["prediction_sha256"] != protocol["prediction_sha256"]:
        raise ValueError("평가 대상 예측 해시가 다릅니다.")
    facts = {item["id"]: item for item in prediction["items"]}
    if len(facts) != len(prediction["items"]):
        raise ValueError("예측 연구 사실 ID가 중복됩니다.")
    reviews = indexed(annotations["fact_reviews"], "id", facts, "사실 판정")
    measures = {}
    for fact in facts.values():
        for name, suffix in (("measurements", "a"), ("rejected_measurements", "r")):
            for index, measurement in enumerate(fact.get(name, [])):
                measures[f"{fact['id']}.{suffix}{index}"] = {"fact_id": fact["id"], "state": "accepted" if suffix == "a" else "rejected", **measurement}
    measured = indexed(annotations["measurement_reviews"], "id", measures, "측정 항목 판정")
    for key, review in measured.items():
        if review["fact_id"] != measures[key]["fact_id"] or review["state"] != measures[key]["state"]:
            raise ValueError("측정 판정의 상태·연구 사실 연결이 다릅니다.")
    refs = {item["id"]: item for item in reference["facts"]}
    if len(refs) != len(reference["facts"]) or any(r["page"] not in protocol["sampling"]["pages"] for r in refs.values()):
        raise ValueError("참조 사실 ID가 중복됐거나 표본 밖의 페이지입니다.")
    matches = indexed(annotations["reference_matches"], "reference_id", refs, "참조 매칭")
    for review in reviews.values():
        if review["document_support"] not in ("full", "partial", "unsupported", "unverifiable") or review["linked_support"] not in ("full", "partial", "unsupported", "unverifiable"):
            raise ValueError("알 수 없는 원문 뒷받침 판정입니다.")
    for row in measured.values():
        if any(type(row[key]) is not bool for key in ("pdf_grounded", "measurement_applicable", "value_unit_correct", "condition_correct", "linked_value_supported")):
            raise ValueError("측정 판정은 명시적인 boolean이어야 합니다.")
    questions = (prediction.get("research") or {}).get("open_questions", [])
    for match in matches.values():
        if match["verdict"] not in ("full", "partial", "missing") or match["question_verdict"] not in ("full", "partial", "missing"):
            raise ValueError("알 수 없는 참조 매칭 판정입니다.")
        if not set(match["prediction_ids"]) <= set(facts) or (match["verdict"] != "missing" and not match["prediction_ids"]):
            raise ValueError("참조 매칭에 없는 예측 ID를 사용했습니다.")
        if any(type(i) is not int or not 0 <= i < len(questions) for i in match["question_indices"]):
            raise ValueError("참조 매칭의 질문 ID가 잘못됐습니다.")
        if match["question_verdict"] != "missing" and not match["question_indices"]:
            raise ValueError("질문 매칭 판정에 질문 ID가 없습니다.")
    writing = set(prediction["writing_fact_ids"])
    excluded = set(prediction["diagnostics"]["excluded_selected_ids"])
    if not (writing | excluded) <= set(facts) or writing & excluded:
        raise ValueError("작성·제외 후보 ID가 잘못됐습니다.")
    full = {key for key, r in reviews.items() if r["document_support"] == "full"}
    selected = writing | excluded
    model_supported = {key for key, item in facts.items() if item["support"] == "supported"}
    accepted = [key for key, m in measures.items() if m["state"] == "accepted"]
    rejected = [key for key, m in measures.items() if m["state"] == "rejected"]
    def correct_tuple(key):
        row = measured[key]
        return all(row[name] for name in ("measurement_applicable", "value_unit_correct", "condition_correct"))
    scalar = re.compile(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\Z")
    metrics = {
        "candidate_document_faithfulness": rate(len(full), len(facts)),
        "candidate_linked_source_completeness": rate(sum(r["linked_support"] == "full" for r in reviews.values()), len(facts)),
        "claim_strength_preserved": rate(sum(r["claim_strength_preserved"] for r in reviews.values()), len(facts)),
        "kind_acceptable": rate(sum(facts[k]["kind"] in r["acceptable_kinds"] for k, r in reviews.items()), len(facts)),
        "accepted_measurement_tuple_correct": rate(sum(correct_tuple(k) for k in accepted), len(accepted)),
        "accepted_value_unit_correct": rate(sum(measured[k]["value_unit_correct"] for k in accepted), len(accepted)),
        "accepted_scalar_value_format": rate(sum(bool(scalar.fullmatch(measures[k]["value"].strip())) for k in accepted), len(accepted)),
        "measurement_linked_value_support": rate(sum(r["linked_value_supported"] for r in measured.values()), len(measured)),
        "quarantined_pdf_numeric_content_present": rate(sum(measured[k]["measurement_applicable"] and measured[k]["pdf_grounded"] for k in rejected), len(rejected)),
        "quarantined_correct_measurement_tuples": rate(sum(correct_tuple(k) for k in rejected), len(rejected)),
        "model_supported_document_faithfulness": rate(len(model_supported & full), len(model_supported)),
        "writing_gate_document_faithfulness": rate(len(writing & full), len(writing)),
        "excluded_selected_document_supported": rate(len(excluded & full), len(excluded)),
        "sampled_required_fact_coverage": rate(sum(m["verdict"] == "full" for m in matches.values()), len(refs)),
        "sampled_required_fact_writing_coverage": rate(sum(m["verdict"] == "full" and bool(set(m["prediction_ids"]) & writing) for m in matches.values()), len(refs)),
        "sampled_required_fact_any_text_coverage": rate(sum(m["verdict"] == "full" or m["question_verdict"] == "full" for m in matches.values()), len(refs)),
    }
    by_kind = {}
    for kind in sorted({r["kind"] for r in refs.values()}):
        ids = [key for key, r in refs.items() if r["kind"] == kind]
        by_kind[kind] = rate(sum(matches[key]["verdict"] == "full" for key in ids), len(ids))
    return {"metrics": metrics, "reference_coverage_by_kind": by_kind,
            "candidate_support_counts": dict(Counter(r["document_support"] for r in reviews.values())),
            "reference_match_counts": dict(Counter(r["verdict"] for r in matches.values())),
            "writing_incomplete_ids": sorted(writing - full), "excluded_but_document_supported_ids": sorted(excluded & full),
            "missing_reference_ids": [key for key, m in matches.items() if m["verdict"] == "missing"],
            "assessment": "Single-Codex source audit of development data; not blinded, not expert-independent; sample coverage is not whole-document recall"}


def main():
    load = lambda name: json.loads((HERE / name).read_text(encoding="utf-8"))
    protocol, reference, annotations = load("protocol.json"), load("reference.json"), load("annotations.json")
    pred_path = BASE / protocol["prediction_file"]
    source = BASE / protocol["source_file"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != protocol["source_sha256"] or hashlib.sha256(pred_path.read_bytes()).hexdigest() != protocol["prediction_sha256"]:
        raise ValueError("고정한 PDF 또는 추출 결과가 변경됐습니다. 새 평가 버전을 사용하세요.")
    for name, digest in protocol["frozen_code_sha256"].items():
        current = BASE / name
        archived = HERE / "baseline-code" / name
        if hashlib.sha256(current.read_bytes()).hexdigest() != digest and (not archived.is_file() or hashlib.sha256(archived.read_bytes()).hexdigest() != digest):
            raise ValueError("평가 도중 추출 코드가 변경됐습니다. 새 버전으로 평가하세요.")
    prediction = json.loads(pred_path.read_text(encoding="utf-8"))
    result = score(prediction, reference, annotations, protocol)
    # Raw Parse text consistency is independent from semantic source attribution judgments.
    import sys
    sys.path.insert(0, str(BASE))
    from document_parse import artifact_directory
    from paper_outline import element_key, element_text
    folder = artifact_directory(source, BASE / "draft_history/parse-api-v1")
    raw = folder / "parse-response.json"
    manifest = json.loads((folder / "parse-manifest.json").read_text(encoding="utf-8"))
    if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest["response_sha256"] or manifest["source_sha256"] != protocol["source_sha256"]:
        raise ValueError("원본 Parse 캐시의 해시가 다릅니다.")
    elements = {element_key(e): e for e in json.loads(raw.read_text(encoding="utf-8"))["elements"]}
    links = [s for f in prediction["items"] for s in f["sources"]]
    exact = sum(s["element_id"] in elements and s["page"] == elements[s["element_id"]]["page"] and s["quote"] == element_text(elements[s["element_id"]]) for s in links)
    result["metrics"]["parse_quote_page_integrity"] = rate(exact, len(links))
    result.update(source_sha256=protocol["source_sha256"], prediction_sha256=protocol["prediction_sha256"],
                  annotation_sha256=hashlib.sha256((HERE / "annotations.json").read_bytes()).hexdigest(),
                  reference_sha256=hashlib.sha256((HERE / "reference.json").read_bytes()).hexdigest(),
                  sampled_pages=protocol["sampling"]["pages"], facts_audited=len(prediction["items"]),
                  visual_pages_reviewed=sorted(set(protocol["sampling"]["pages"]) | {s["page"] for f in prediction["items"] for s in f["sources"]} | {25, 28, 42}),
                  measurements_audited=len(annotations["measurement_reviews"]), independently_expert_validated=False,
                  extractor_changed=False, api_calls=0)
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_report(result, prediction, reference, annotations)
    print(json.dumps(result["metrics"], ensure_ascii=False))


def render_report(result, prediction, reference, annotations):
    m = result["metrics"]
    labels = [("후보 진술 전체의 문서 충실도", "candidate_document_faithfulness"),
              ("후보 진술 전체를 선택한 출처가 뒷받침", "candidate_linked_source_completeness"),
              ("인용문·페이지의 Parse 원본 일치", "parse_quote_page_integrity"),
              ("승인 측정의 값·단위·조건 일치", "accepted_measurement_tuple_correct"),
              ("승인 측정의 value/단위 분리 형식", "accepted_scalar_value_format"),
              ("표본 필수 사실 커버리지 (후보 전체)", "sampled_required_fact_coverage"),
              ("표본 필수 사실 커버리지 (질문 목록 포함)", "sampled_required_fact_any_text_coverage"),
              ("작성용 통과 후보의 문서 충실도", "writing_gate_document_faithfulness"),
              ("제외된 요약 후보 중 문서에 충실한 후보", "excluded_selected_document_supported")]
    lines = ["# 연구 근거 추출 1차 원문 대조 평가", "",
        "**실행 검사는 통과했지만, 핵심 내용 누락·출처 연결 누락·정상 항목의 과도한 제외·잘못된 횟수의 통과가 함께 확인됐다.**", "",
        "CUDA 개발 자료 1편의 고정된 추출 결과를 평가했다. 후보 34개와 승인/격리 측정 항목 63개를 원문과 대조했고, 고정 seed로 선택한 21쪽에서 필수 사실 42개를 정했다.",
        "평가자는 Codex 1개이며 이미 예측을 본 상태다. 전문가의 독립 정답·맹검·보류셋 평가가 아니다. 비율은 이 평가 표본에만 적용한다.", "",
        "[판정 기준·고정 입력](protocol.json) · [평가용 참조 사실](reference.json) · [전체 항목별 판정](annotations.json) · [집계 JSON](results.json)", "",
        "## 주요 결과", "", "| 항목 | 분자/분모 | 비율 |", "|---|---:|---:|"]
    for label, key in labels:
        value = m[key]
        percentage = f"{value['value']:.1%}" if value["value"] is not None else "미정의"
        lines.append(f"| {label} | {value['numerator']}/{value['denominator']} | {percentage} |")
    lines += ["", "후보 충실도는 복합 진술 전체가 문서와 일치해야 통과한다. 부분 일치는 정답으로 합산하지 않았다. 출처 완전성은 선택한 요소들만으로 핵심 주장을 모두 뒷받침하는지 별도로 판정했다.",
        "표본 커버리지는 선정한 필수 사실의 재현율이며 PDF 전체 사실의 재현율이 아니다. 후보와 참조 사실의 단위가 달라 두 비율을 섞은 F1은 계산하지 않았다.",
        "승인 측정의 값·단위·조건 판정은 원문의 관측 기록에 대한 충실도다. 독립 실험의 정확성을 의미하지 않는다. 숫자+단위가 value에 함께 들어간 항목은 내용 판정과 별개로 분리 형식에서 탈락한다.", "",
        "## 우선 확인한 오류", "",
        "1. **잘못된 숫자 통과 — F16:** 후보는 memcpy 66→56회라고 쓰지만 원본 36쪽의 효과 목록은 94→54회다. 실제 17.223600ms 로그는 맞아서, 구조화된 측정값만 검사한 게이트가 문장 안의 잘못된 횟수를 놓쳤다. 현재 작성용 11개에도 들어 있다.",
        "2. **검증 강도 과장 — F24:** 시간 분리·20회 측정·warmup 스파이크는 맞지만 CV로 확인했다는 표현은 원문의 계산 예정·정성 관찰보다 강하다.",
        "3. **정상 내용의 격리:** 버전 V13.3.73, epsilon 10^-6/1e-06, 5~10ms 범위, 소수점의 OCR 쉼표, 시간/비율 복합값 등이 수치 한 개 검사에서 탈락했다.",
        f"   격리된 20개 중 {m['quarantined_pdf_numeric_content_present']['numerator']}개는 PDF에 실제 수치·범위가 있는 항목이고, 나머지는 버전·모드·정성 비교다. 형식 오류와 원문 내용 부재를 같은 이유로 표시하면 안 된다.",
        "4. **출처 누락:** F08의115.469900은20쪽, F18의15.751000은42쪽인데 선택한 출처에는 해당 결과가 없다. F09는64ms 변화 후 로그, F11은후속라이브러리 실험, F33은1138s 변경 전 기록의 링크가 빠졌다.",
        "5. **중요 내용 누락:** auto_LiRPA forward114.78s/backward_only55.78s, batch1024, FP32 결과 불일치 주의, 커널 계수에서 복사·동기화·graphLaunch 제외 조건 등이 후보 사실 목록에 없다. 일부 연구 질문은 별도 질문 목록에만 남았다.", "",
        "## 개선 우선순위", "",
        "- 복합 진술을 원자 주장으로 나누고 문장 안의 모든 수치·대상·조건에 출처를 연결한다. 구조화된 measurements만 검사해서는 부족하다.",
        "- 버전·설정·정성 비교·수치·범위를 분리하고, 숫자 형식 정규화 실패를 사실 전체의 불충분 판정과 분리한다. 원문 이미지를 확인할 필요가 있는 OCR 실패도 구분한다.",
        "- 20쪽당8개·요약18개 제한 때문에 빠지는 조건·실패·비교 실험을 별도로 수집한다. 후보 수집 재현율과 작성용 선택 품질을 따로 평가한다.",
        "- 현재 42개 참조 사실과 판정은 개발 평가용으로만 사용한다. 전문가 재검토와 새로운 연구 자료의 보류 평가가 필요하다.", "",
        "## 후보별 판정", "", "| ID | 문서 충실도 | 선택 출처 완전성 | 사유 |", "|---|---|---|---|"]
    for row in annotations["fact_reviews"]:
        lines.append(f"| {row['id']} | {row['document_support']} | {row['linked_support']} | {row['note'].replace('|', '/')} |")
    lines += ["", "## 표본 필수 사실별 커버리지", "", "| ID | 원문 쪽 | 필수 사실 | 후보 매칭 | 판정 |", "|---|---:|---|---|---|"]
    matches = {row["reference_id"]: row for row in annotations["reference_matches"]}
    for row in reference["facts"]:
        match = matches[row["id"]]
        lines.append(f"| {row['id']} | {row['page']} | {row['statement'].replace('|', '/')} | {', '.join(match['prediction_ids']) or '없음'} | {match['verdict']} |")
    lines += ["", "## 재계산", "", "```powershell", "python -X utf8 -B evaluation/extraction/benchmark/evaluate.py", "```", "",
              "원본 PDF, 고정 추출 결과, 로컬 Parse 캐시가 필요하다. 외부 API를 호출하지 않는다. 원본·예측·추출 코드 해시가 다르면 중단한다.",
              "평가용 reference/annotations는 작성 코드에 전달하지 않았다. 추출기·입력·예측·기존 초안은 이번 평가에서 변경하지 않았다.", ""]
    (HERE / "report.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
