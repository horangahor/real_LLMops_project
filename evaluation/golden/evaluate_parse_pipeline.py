"""Offline evaluation of direct Parse/Python outlines, plus an optional identical-Parse replay."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from document_parse import write_json
from golden_evaluation import EVALUATION_VERSION, evaluate_outline, fraction, percent, ratio, select_profile, verify_source
from paper_outline import PIPELINE_VERSION, extract_numbered_outline


def assess(profile, reference_path, source_dir, prediction_path):
    reference_bytes = reference_path.read_bytes()
    reference = json.loads(reference_bytes)
    digest = verify_source(reference, source_dir / reference["source_file"])
    if profile.get("source_sha256") != digest:
        raise ValueError("새 예측의 원본 해시가 평가 PDF와 다릅니다.")
    report = evaluate_outline(profile, reference)
    if profile.get("schema_version") != 2:
        for key in ("role_accuracy_on_matched", "fully_correct_item_recall"):
            report["metrics"][key] = fraction(0, 0)
        for row in report["matches"]:
            row.update(predicted_role=None, role_correct=None, fully_correct=None)
    report.update(evaluation_version=EVALUATION_VERSION, pipeline_version=PIPELINE_VERSION,
                  source_file=reference["source_file"], source_sha256=digest,
                  reference_sha256=hashlib.sha256(reference_bytes).hexdigest(),
                  prediction_path=str(prediction_path),
                  prediction_sha256=hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
                  outline_code_sha256=hashlib.sha256((BASE / "paper_outline.py").read_bytes()).hexdigest(),
                  reference_items=reference["items"], annotation_provenance=reference["annotation_provenance"],
                  prediction_provenance=profile.get("provenance"),
                  hierarchy_policy="Python derives hierarchy and order from explicit source numbers; no invented parents",
                  scope=reference["scope"], matching_policy=reference["matching_policy"],
                  excluded_candidate_count=len(profile["rejected_candidates"]) if "rejected_candidates" in profile else None,
                  unnumbered_sections_assessed=False)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, default=BASE / "golden sample")
    parser.add_argument("--output", type=Path, default=BASE / "evaluation/golden/results/parse-api-v1-validation.md")
    parser.add_argument("--tag", default="parse-api-v1", help="결과 JSON의 이름 접두부")
    parser.add_argument("--studio-rgbd-run", type=Path, default=BASE / "draft_history/rgbd-config4")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9-]+", args.tag):
        parser.error("--tag는 소문자·숫자·하이픈만 사용할 수 있습니다.")
    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    reports = {}
    for name in ("npu", "rgbd"):
        reference_path = BASE / f"evaluation/golden/{name}-reference.json"
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        profile = select_profile(profiles, reference["source_file"])
        report = assess(profile, reference_path, args.source_dir, args.profiles)
        reports[name] = report
        write_json(args.output.parent / f"{name}-{args.tag}.json", report)

    replay = None
    if (args.studio_rgbd_run / "job-response.json").is_file():
        state = json.loads((args.studio_rgbd_run / "state.json").read_text(encoding="utf-8"))
        if state["source_sha256"] != reports["rgbd"]["source_sha256"]:
            raise ValueError("Studio 재생 원본이 RGBD 평가 PDF와 다릅니다.")
        job = json.loads((args.studio_rgbd_run / "job-response.json").read_text(encoding="utf-8"))
        step = next(x for x in job["output"] if x.get("model") == "step_1_parse")
        parsed = json.loads(step["content"][0]["text"])
        # The extractor receives Parse only. Reference data is used exclusively in assess().
        profile = {"file": "research_revies.pdf", "source_sha256": state["source_sha256"],
                   "provenance": "same_studio_parse_python_replay", **extract_numbered_outline(parsed)}
        prediction_path = BASE / f"evaluation/golden/predictions/rgbd-{args.tag}-studio-replay.json"
        write_json(prediction_path, profile)
        replay = assess(profile, BASE / "evaluation/golden/rgbd-reference.json", args.source_dir, prediction_path)
        write_json(args.output.parent / f"rgbd-{args.tag}-studio-replay.json", replay)

    lines = ["# Direct Parse API + Python 목차 평가 v1", "",
             "파싱은 Document Parse API, 목차 선택·페이지 연결·부모 복원은 Python 코드가 담당한다. Studio Agent를 호출하지 않는다.",
             "기존 NPU 14개·RGBD 23개의 원문 기준표와 번역 별칭·제외 제목을 변경하지 않았다. 정답표는 추출 코드의 입력이 아니다.",
             "지원 범위는 참고문헌 이전의 아라비아 숫자 본문 목차다. 무번호·로마 숫자 목차의 정확도는 이 결과로 주장하지 않는다.", "",
             "| PDF | Studio Config 4 구조 F1 | 새 경로 F1 | 정밀도 | 재현율 | 오탐 / 누락 | 부모 | 시작 페이지 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, report in reports.items():
        previous = json.loads((BASE / f"evaluation/golden/results/{name}-studio-config4-structure.json").read_text(encoding="utf-8"))
        metric = report["metrics"]["heading_number_and_identity"]
        lines.append(f"| {name.upper()} | {percent(previous['metrics']['heading_number_and_identity']['f1'])} | {percent(metric['f1'])} | {ratio(metric['precision'])} | {ratio(metric['recall'])} | {metric['false_positive']} / {metric['false_negative']} | {ratio(report['metrics']['parent_accuracy_on_matched'])} | {ratio(report['metrics']['page_accuracy_on_matched'])} |")
    if replay:
        metric = replay["metrics"]["heading_number_and_identity"]
        lines += ["", "## 동일 Parse 결과 재생", "",
                  f"기존 RGBD Studio의 step_1_parse 원본을 그대로 새 코드에 입력했다. 제목+번호 F1 {percent(metric['f1'])}, 정밀도 {ratio(metric['precision'])}, 재현율 {ratio(metric['recall'])}다.",
                  "파싱 모델을 다시 호출하거나 Parse 결과를 수정하지 않고도 목차 선택 정책의 효과를 확인한 비교다. 새 API 실행과의 비교는 OCR 등 모든 숨은 설정이 통제된 모델 실험은 아니다."]
    for name, report in reports.items():
        lines += ["", f"## {name.upper()} 상세", "", "| 원문 번호·제목 | 예측 | 번호 / 부모 / 페이지 |", "|---|---|---|"]
        matches = {row["reference_id"]: row for row in report["matches"]}
        for item in report["reference_items"]:
            row = matches.get(item["id"])
            flags = " / ".join("일치" if row[key] else "불일치" for key in ("number_correct", "parent_correct", "page_correct")) if row else "누락"
            lines.append(f"| {item['id']} {item['title']} | {row['prediction_title'] if row else '누락'} | {flags} |")
        lines += [f"- 오탐: {row['title']} ({row['reason']})" for row in report["unmatched_predictions"]]
        lines += ["", f"역할 라벨 일치율: {ratio(report['metrics']['role_accuracy_on_matched'])}. 역할 기준은 초기 원문 판정이며 전문가 독립 검수 전이다."]
    lines += ["", "## 출력과 검증 범위", "",
              "- 원본 API 응답·설정·원본 및 응답 해시·선택/제외 후보는 ignored draft_history/parse-api-v1/에 보관한다.",
              "- --outline-only는 Solar를 호출하지 않는다. 본문 목차의 role=other는 기술적 자리표시자로 역할 점수에 사용하지 않는다.",
              "- 전체 분석에서는 코드가 정한 제목·번호·페이지를 유지하고, Solar가 원문 element_id에 역할 및 재사용 작성 가이드만 연결한다. JSON Schema와 로컬 ID·형식 검증을 적용한다.",
              "- 원문 전용 영문 식별자는 재사용 지침에서 검사하고, 발견되면 지침 문장만 최대 한 번 수정해 재검사한다. 현재 앱 가이드의 일부 표현은 Codex가 추가 추상화했으며 프로파일의 guidance_review에 전후를 기록했다. 원본 API 응답은 수정하지 않았다.",
              "- 제목·번호가 있는 일반 paragraph를 복원하고 문장·수식·캡션을 목차에서 제외한다. 서로 다른 제목의 동일 절 번호 충돌과 누락 부모는 임의 보완하지 않고 실패시킨다.",
              "- 두 편에서 측정한 결과다. 무번호 절, OCR 오류, 합쳐진 문단, 복잡한 번호 체계, 번호가 붙은 목록은 추가 검증이 필요하다.",
              "- 이 두 문서를 보며 줄바꿈·paragraph 절·반복 머리말 처리 규칙을 개선했다. 개발 샘플이며 독립 보류 평가셋의 점수가 아니다.",
              "- 문체 가이드의 충실도·생성 초안 품질은 이 목차 점수와 별도로 평가해야 한다. 원문 기준표는 전문가 독립 검수 전이다.", "",
              "## 재현", "", "```powershell",
              "python -X utf8 -B paper_structure.py --outline-only --run-dir draft_history/parse-api-v1 --output evaluation/golden/predictions/parse-api-v1-outlines.json",
              "python -X utf8 -B evaluation/golden/evaluate_parse_pipeline.py --profiles evaluation/golden/predictions/parse-api-v1-outlines.json",
              "```", "", "동일 원본·설정의 캐시가 있으면 Parse API를 다시 호출하지 않는다. 새 파싱은 --force-parse 또는 별도 --run-dir를 사용한다.", ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({name: {"f1": r["metrics"]["heading_number_and_identity"]["f1"],
                             "false_positive": r["metrics"]["heading_number_and_identity"]["false_positive"],
                             "missing": len(r["missing"])} for name, r in reports.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
