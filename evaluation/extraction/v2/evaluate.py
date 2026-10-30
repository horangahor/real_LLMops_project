"""Recalculate the source-audited 42-reference comparison. No model/API calls."""

import hashlib
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def coverage(prediction, reference, annotations):
    refs = {r["id"] for r in reference["facts"]}
    if not refs or len(refs) != len(reference["facts"]):
        raise ValueError("Reference IDs must be unique and nonempty")
    matches = annotations["reference_matches"]
    keys = [r["reference_id"] for r in matches]
    if len(keys) != len(set(keys)) or set(keys) != refs:
        raise ValueError("Reference matches must cover every frozen reference exactly once")
    facts = {f["id"] for f in prediction["items"]}
    if len(facts) != len(prediction["items"]):
        raise ValueError("Duplicate fact IDs")
    writing = set(prediction["writing_fact_ids"])
    if not writing <= facts:
        raise ValueError("Unknown writing fact")
    for row in matches:
        ids = row["prediction_ids"]
        if row["verdict"] not in ("full", "partial", "missing") or len(ids) != len(set(ids)) or not set(ids) <= facts:
            raise ValueError("Invalid match verdict or prediction IDs")
        if row["verdict"] != "missing" and not ids:
            raise ValueError("Nonmissing match needs evidence IDs")
    full = [r for r in matches if r["verdict"] == "full"]
    return {"counts": dict(Counter(r["verdict"] for r in matches)), "denominator": len(refs),
            "full": len(full), "value": len(full) / len(refs),
            "writing_full_strict": sum(set(r["prediction_ids"]) <= writing for r in full)}


def main():
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    protocol = load(HERE / "protocol.json")
    for name, value in protocol["bound_files_sha256"].items():
        if digest(BASE / name) != value:
            raise ValueError(f"Bound evaluation input changed: {name}")
    for name, value in protocol["extractor_sha256"].items():
        if digest(BASE / name) != value and digest(HERE / "code" / name) != value:
            raise ValueError(f"Frozen extractor unavailable: {name}")
    prediction, annotations = load(HERE / "evidence.json"), load(HERE / "annotations.json")
    reference = load(HERE.parent / "benchmark/reference.json")
    if not (prediction["source"]["sha256"] == annotations["source_sha256"] == reference["source_sha256"]):
        raise ValueError("Source identities differ")
    if digest(HERE / "evidence.json") != annotations["prediction_sha256"]:
        raise ValueError("Annotations refer to another prediction")
    old = coverage(load(HERE.parent / "cuda-evidence.json"), reference, load(HERE.parent / "benchmark/annotations.json"))
    new = coverage(prediction, reference, annotations)
    result = {"v1": old, "v2": new, "percentage_point_change": (new["value"] - old["value"]) * 100,
              "assessment": "Same 42 development references; Codex single source audit, not blinded, not expert-independent. Not whole-document recall or overall precision.",
              "overall_v2_precision": None, "api_calls_for_scoring": 0,
              "prediction_sha256": digest(HERE / "evidence.json"), "reference_sha256": digest(HERE.parent / "benchmark/reference.json"),
              "diagnostics": prediction["diagnostics"]}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# 연구 근거 추출 v2 개발 비교", "",
             "원본 CUDA 연구노트와 v1의 평가 전용 참조 사실 42개를 그대로 사용했다. 예측을 본 Codex 단독 원문 감사이며 전문가 독립·맹검·새 자료 보류 평가가 아니다. 표본 21쪽의 일부 필수 사실 커버리지로, 전체 문서 재현율·전체 후보 정확도·F1이 아니다.", "",
             "| 지표 | v1 | v2 |", "|---|---:|---:|",
             f"| 필수 사실 완전 보존 | {old['full']}/42 ({old['value']:.1%}) | {new['full']}/42 ({new['value']:.1%}) |",
             f"| 부분 보존 / 누락 | {old['counts'].get('partial', 0)} / {old['counts'].get('missing', 0)} | {new['counts'].get('partial', 0)} / {new['counts'].get('missing', 0)} |",
             f"| 작성 입력의 완전 보존¹ | {old['writing_full_strict']}/42 | {new['writing_full_strict']}/42 |", "",
             "¹ 완전 매칭을 구성하는 후보가 모두 작성 입력에 남아 있어야 계산한다. 가설·질문은 수집돼도 작성에서 제외될 수 있다. v1 보고서의 any-ID 방식과 달리 양쪽을 같은 all-ID 규칙으로 재계산했다.", "",
             "`statement/limits/conditions/observations/parameters/승인 measurements`에 실제 보존된 내용만 매칭했다. 인용문·support_note·격리된 측정값 안에만 있는 값은 추출 성공으로 세지 않았다. 복수 후보가 한 참조 사실을 함께 충족할 수 있다. 항목별 원문 해석·매칭 판정은 annotations.json에 남겼다.", "",
             "## 변경과 실행", "",
             "- 기본 경로는 직접 Document Parse API → Solar이며 Studio·수작업 research_evidence·골든 논문·평가 정답을 추출 입력으로 사용하지 않는다.",
             "- 4쪽씩 인접 문맥을 포함해 수집한다. 기존 20쪽당8개·요약18개 제한을 제거하고 후보·측정·설정·계획·추정을 분리한다. 여러 관찰이 한 후보에 남는 경우도 있어 완전한 원자화는 아니다.",
             "- 내용이 빈 원문 영역이 있는 13쪽을 enhanced Parse로 다시 읽고 원래 응답과 별도 출처 ID·이미지 해시·응답을 보존했다. 원본 PDF나 원래 Parse 응답은 고치지 않았다.",
             "- 진술·조건·관찰·설정 안의 수치까지 검사한다. 과학 표기·소수 쉼표·범위·버전을 구분하고 raw_value와 정규화 기록을 남긴다. 잘못된 부가 측정값은 주진술과 분리한다.",
             "- 별도 Solar 원문 검토 후 작성 게이트를 적용한다. LLM supported는 독립적 사실 검증 점수가 아니다.",
             f"- 실제 결과: 후보 {len(prediction['items'])}개, 작성용 {len(prediction['writing_fact_ids'])}개, 승인 측정 {prediction['diagnostics']['measurements']}개, 격리 측정 {prediction['diagnostics']['rejected_measurements']}개, 수치 검사 보류 후보 {prediction['diagnostics']['numeric_claim_failures']}개. 개수 증가는 품질 점수가 아니다.",
             "- 실개발 과정에 시간 초과·형식 수정·재시도가 있었다. 완료 단계 캐시를 재사용했다. 첫 시도 성공률·동일 비용·속도 개선을 측정한 실험은 아니다.", "",
             "## 확인된 개선과 남은 문제", "",
             "- batch1024, auto_LiRPA forward114.78s/backward_only55.78s, 세 방법의 bound 커널 계수와 복사·동기화 제외 조건이 새로 보존됐다.",
             "- v1 F16의 잘못된 memcpy66→56 대신 v2 F0192는 원문36쪽94→54와 D2H44→20에 연결된다. 문장 안의 잘못된 횟수가 별도의 올바른 시간 측정값 때문에 통과하는 문제를 회귀 테스트로 막았다.",
             "- R14의 정확한21.3753ms, R18의FP32 정확성 불일치 주의, R20의Codex 조언 출처, R23의전체 변동 범위, R41의비용 차이 해석은 여전히 부분 보존이다. R22의1634.61s, R32의복사시간 표, R38의689.64us는 누락이다.",
             "- v 1-1-2/v1-1-2, 7 87/787 같은 OCR 표기와 불필요한 날짜·번호 조건 때문에 정상 핵심 내용이 작성에서 보류되는 사례가 남았다. 반복 EPS 행·유사 사실도 많다. 자동 승인399개 전체의 정밀도는 이번에 전수 평가하지 않았다.",
             "- AI 조언의 자료 성격 판정도 완전하지 않다. F0267은 Codex 조언을 작성자 추정으로 분류했다. 실제 실험 결과와 인용된 조언의 구분은 추가 보완이 필요하다.",
             "- 기존 7장 초안은 그대로다. 새 근거의 본문 반영·본문 품질은 이번 검증 범위가 아니다.", "",
             "## 참조별 판정", "", "| 참조 | 쪽 | 판정 | 후보 | 사유 |", "|---|---:|---|---|---|"]
    refs = {r["id"]: r for r in reference["facts"]}
    for row in annotations["reference_matches"]:
        lines.append(f"| {row['reference_id']} | {refs[row['reference_id']]['page']} | {row['verdict']} | {', '.join(row['prediction_ids']) or '없음'} | {row['note'].replace('|', '/')} |")
    lines += ["", "## 재계산", "", "```powershell", "python -X utf8 -B evaluation/extraction/v2/validate.py", "python -X utf8 -B evaluation/extraction/v2/evaluate.py", "```", "",
              "validate는 로컬 원본·API 응답 캐시가 필요하며 네트워크와 수작업/평가 파일/골든 가이드 읽기를 차단한다. evaluate는 고정 PDF·예측·참조·판정·코드 해시를 확인하고 API 없이 재계산한다. 평가용 reference/annotations는 추출·검토·작성 프롬프트에 넣지 않았다.", ""]
    (HERE / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"v1": old, "v2": new, "percentage_point_change": result["percentage_point_change"]}))


if __name__ == "__main__":
    main()
