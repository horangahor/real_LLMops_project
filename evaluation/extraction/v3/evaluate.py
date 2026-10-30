"""Recalculate the frozen source-audited development comparison; never call a model."""

import hashlib
import json
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from evaluation.extraction.v2.evaluate import coverage


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    protocol = load(HERE / "protocol.json")
    for name, expected in protocol["bound_files_sha256"].items():
        if digest(BASE / name) != expected:
            raise ValueError(f"평가 입력이 변경됐습니다: {name}")
    for name, expected in protocol["extractor_sha256"].items():
        if digest(BASE / name) != expected and digest(HERE / "code" / name) != expected:
            raise ValueError(f"고정한 추출 코드가 없습니다: {name}")
    reference = load(HERE.parent / "benchmark/reference.json")
    prediction, annotations = load(HERE / "evidence.json"), load(HERE / "annotations.json")
    if not (prediction["source"]["sha256"] == reference["source_sha256"] == annotations["source_sha256"]):
        raise ValueError("다른 연구 원본의 평가를 섞었습니다.")
    if digest(HERE / "evidence.json") != annotations["prediction_sha256"]:
        raise ValueError("판정에 연결된 예측 해시가 다릅니다.")
    old = coverage(load(HERE.parent / "cuda-evidence.json"), reference, load(HERE.parent / "benchmark/annotations.json"))
    previous = coverage(load(HERE.parent / "v2/evidence.json"), reference, load(HERE.parent / "v2/annotations.json"))
    current = coverage(prediction, reference, annotations)
    result = {"v1": old, "v2": previous, "v3": current, "completion": prediction["completion"],
              "diagnostics": prediction["diagnostics"], "overall_precision": None,
              "assessment": "Same 42 development references, single-Codex nonblinded source audit; not overall precision or whole-document semantic recall.",
              "prediction_sha256": digest(HERE / "evidence.json"), "reference_sha256": digest(HERE.parent / "benchmark/reference.json"),
              "api_calls_for_scoring": 0}
    (HERE / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive = load(Path(prediction["source_archive_path"]))
    completion, stats = prediction["completion"], prediction["diagnostics"]
    lines = ["# 연구 근거 추출 v3 개발 평가", "",
             "같은 CUDA 원본과 v1의 42개 평가 전용 참조 사실을 그대로 대조했다. 인용문·지원 판정 설명·원시 보관 파일 안에만 있는 내용은 구조화 보존으로 세지 않는다. statement/limits/conditions/observations/parameters/승인 measurements에 실제 남은 내용과 주장 강도·출처를 확인한다.", "",
             "| 지표 | v1 | v2 | v3 |", "|---|---:|---:|---:|",
             f"| 필수 사실 완전 보존 | {old['full']}/42 | {previous['full']}/42 | {current['full']}/42 |",
             f"| 작성 입력까지 완전 보존 | {old['writing_full_strict']}/42 | {previous['writing_full_strict']}/42 | {current['writing_full_strict']}/42 |",
             f"| 부분 보존 / 누락 | {old['counts'].get('partial', 0)} / {old['counts'].get('missing', 0)} | {previous['counts'].get('partial', 0)} / {previous['counts'].get('missing', 0)} | {current['counts'].get('partial', 0)} / {current['counts'].get('missing', 0)} |", "",
             "작성 입력 보존은 완전 매칭을 구성하는 모든 후보가 작성 입력에 있어야 인정한다. 질문·계획·인용 조언·원문 자체의 미정 기록은 context_only로 보존하며 실험 성과로 쓰지 않는다.", "",
             "Codex 단독 개발 감사이고 예측과 이전 평가를 본 상태다. 새 자료·전문가 독립·맹검 평가가 아니며, 이 수치를 전체 문서의 재현율이나 전체 후보 정확도로 해석하지 않는다. 복합 후보와 참조 단위가 달라 F1은 계산하지 않는다.", "",
             "## 원문 보존과 누락 검사의 범위", "",
             f"- 검토 대장: {completion['pages_reviewed']}/{completion['source_pages']}쪽, {completion['elements_reviewed']}/{completion['source_elements']}개 통합 텍스트 요소.",
             f"- PDF 내장 이미지 {len(archive['pdf_image_inventory'])}개를 실제 배치와 Parse 영역으로 점검하고, 영역이 부족했던 {sum(r['state'] == 'image_reprocessed' for r in archive['pdf_image_inventory'])}개를 별도 이미지로 판독했다. Parse 요소에 아예 등록되지 않은 표·그림도 대상이다. 면적 비교는 OCR 의미 정확성의 보증이 아니다.",
             f"- 원본·재판독 Parse 응답 {len(archive['native_documents'])}개를 HTML/표·좌표·빈 영역까지 원형과 해시로 보관했다. 원본 PDF는 변경하지 않았다.",
             f"- 후보 {stats['candidates']}개, 작성용 {stats['writing_facts']}개, 승인 측정 {stats['measurements']}개, 격리 측정 {stats['rejected_measurements']}개. 개수는 정확도 점수가 아니다.",
             f"- 최종 대장의 미해결 원문 항목: {len(completion['unresolved_source_items'])}개. 본문 생성 게이트: {'통과' if completion['ready_for_drafting'] else '보류'}.", "",
             "원문에 없는 조건을 만들어서 빈칸을 채우지 않는다. source_archive에 전체 원문을 보관하는 것과 구조화된 연구 사실을 완전히 보존하는 것은 구분한다. 모델의 완료 체크 외에도 원문 식별자와 명시된 시간·지연 등 지표 값이 실제 추출 필드에 남았는지 코드로 대조한다. 필요한 검사이지 의미·단위·비교 관계 전체의 독립 증명은 아니다.", "",
             "## 검토와 실행 경로", "",
             "기본 경로는 직접 Document Parse API와 Solar다. 평가 정답·수작업 근거·골든 논문은 연구 사실 추출 입력에 넣지 않는다. 원문 획득 경로(origin)와 연구 내용의 작성자·인용 조언(source_origin)을 구별한다.", "",
             "별도 원문 검토와 누락 복구에는 reasoning_effort=medium을 명시했다. 최종 대장 첫 검사는 기존 medium 완료 캐시를 우선 재사용하고 새 요청은 low로 시작하며, 후속 검사는 medium이다. Solar Pro4는 생략 시 추론이 꺼진다는 [공식 설명](https://console.upstage.ai/docs/capabilities/generate/reasoning)을 확인했다. 개발 사례 3개(정상 1개·조건/귀속 오류 2개)의 제한된 비교에서 추론 검토가 두 오류를 구별했으며 일반화 성능의 독립 검증은 아니다.", "",
             "모델이 설명에서 모순을 지적해도 지원 플래그만으로 승인하지 않는다. 모순·근거 부족·귀속 불일치·수치 검사 실패는 제외한다. 명시적인 AI 인용 도입문은 출처 귀속을 별도로 검사한다. 해석·계획·가설·미정 기록은 문맥 용도로만 작성 입력에 넣는다.", "",
             "공급자가 최종 JSON을 비운 사례가 있었다. 정상 캐시로 저장하지 않고 제한된 재시도, 별도 캐시의 low 설정, 검토 묶음 분할을 사용한다. 여전히 검토 답변이 없으면 보류한다. 개발 중 재시도·재개가 있어 첫 시도 성공률·동일 비용·처리 속도 개선을 측정한 실험은 아니다.", "",
             "기존 7장 초안은 재작성하지 않았다. 이번 평가는 근거 추출 단계다.", "",
             "## 참조별 원문 판정", "", "| 참조 | 원문 쪽 | 판정 | 후보 | 사유 |", "|---|---:|---|---|---|"]
    refs = {r["id"]: r for r in reference["facts"]}
    for row in annotations["reference_matches"]:
        lines.append(f"| {row['reference_id']} | {refs[row['reference_id']]['page']} | {row['verdict']} | {', '.join(row['prediction_ids']) or '없음'} | {row['note'].replace('|', '/')} |")
    lines += ["", "## 미해결 원문 항목", ""]
    lines += ["- " + issue for issue in completion["unresolved_source_items"]] or ["미해결 표시 없음. 모델 보조 대장 검토 결과이며 독립적인 100% 의미 정확도 보증은 아니다."]
    lines += ["", "## 재계산", "", "```powershell", "python -X utf8 -B evaluation/extraction/v3/validate.py",
              "python -X utf8 -B evaluation/extraction/v3/evaluate.py", "```", "",
              "validate는 로컬 원본·응답 캐시를 재생하며 네트워크·수작업/평가 파일·골든 가이드 읽기를 차단한다. evaluate는 고정 원본·예측·판정·참조·코드 해시를 확인하고 API 없이 계산한다.", ""]
    (HERE / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"v1": old, "v2": previous, "v3": current, "unresolved_source_items": len(completion["unresolved_source_items"])}))


if __name__ == "__main__":
    main()
