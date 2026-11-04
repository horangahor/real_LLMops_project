"""Recorded wording review of reusable guidance; native API responses stay unchanged."""
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from document_parse import artifact_directory, write_json
from structure_profiles import save_profiles

profiles_path = BASE / "paper_structure_analysis.json"
profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
write_json(BASE / "draft_history/parse-api-v1/profiles-before-manual-abstraction.json", profiles)
changes = [
    ("시료 준비와 스트레스 조건 설계", "평가 대상과 입력 조건의 구성 및 통제 방법"),
    ("촬영·센서·계산 플랫폼 구성", "데이터 수집 환경과 실행 플랫폼의 구성"),
    ("학습 하이퍼파라미터와 검증 전략", "실행·학습 설정과 검증 절차"),
    ("융합 전략별 정량 성능 비교", "제안 설계와 변형 방법별 정량 성능 비교"),
    ("오분류 양상과 혼동 행렬 해석", "오류 양상과 실패 사례의 해석"),
    ("경량 모델과의 비교", "비교 대상 기준 방법과의 비교"),
    ("주요 정량 결과와 실시간성", "주요 정량 결과와 적용 조건"),
    ("추론 외 전처리·후처리·런타임 등 시스템 수준 오버헤드", "전체 처리 과정의 단계별 부가 비용"),
    ("양자화·컴파일러·배포 도구 등 최적화/툴체인 효과", "설계·구현·배포 선택의 성능 영향"),
    ("벤더별 배포 설정과 적용 범위", "환경별 설정과 적용 범위"),
    ("평가 이미지", "평가 입력"),
    ("전용 가속기 수준과 종단 간 성능의 순위 비교", "구성 요소 단위와 전체 처리 성능의 순위 비교"),
    ("전용 가속기 수준 모델 변환과 최종 배포를 구분해야 하는 이유", "구성 요소의 변경 효과와 전체 처리 과정의 변경 효과를 구분해야 하는 이유"),
    ("전력·에너지 효율 평가가 제외된 이유와 그 함의", "평가에서 제외한 지표와 그 이유 및 해석 범위"),
    ("기준선/전용 가속기 수준 구성에서", "기준선과 구성 요소 단위 비교에서"),
    ("종단 간 구성에서", "전체 처리 과정의 비교에서"),
]
for profile in profiles:
    edits = []
    def refine(value, path):
        if isinstance(value, str):
            revised = value
            for before, after in changes:
                revised = revised.replace(before, after)
            if revised != value:
                edits.append({"path": path, "before": value, "after": revised})
            return revised
        if isinstance(value, list):
            return [refine(item, f"{path}[{index}]") for index, item in enumerate(value)]
        if isinstance(value, dict):
            return {key: refine(item, f"{path}.{key}") for key, item in value.items()}
        return value
    original_outline = json.dumps(profile["observed_outline"], ensure_ascii=False, sort_keys=True)
    for field in ("style_rules", "section_guidelines"):
        profile[field] = refine(profile[field], field)
    profile["guidance_review"] = {"reviewer": "Codex", "version": "guide-abstraction-review-v1",
                                  "scope": "Selected reusable wording only; not expert or complete semantic validation",
                                  "edits": edits}
    profile["analysis_notes"].append("재사용 지침에 남은 일부 원문 전용 표현은 Codex가 추상화했다. 수정 전후는 guidance_review에 기록했으며 문체 품질의 독립 검수는 아니다.")
    assert json.dumps(profile["observed_outline"], ensure_ascii=False, sort_keys=True) == original_outline
    settings = profile["parse_settings"]
    folder = artifact_directory(BASE / profile["file"], BASE / "draft_history/parse-api-v1",
                                model=settings["requested_model"], mode=settings["mode"], ocr=settings["ocr"])
    write_json(folder / "profile.json", profile)
    manifest_path = folder / "guidance-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(profile_sha256=hashlib.sha256((folder / "profile.json").read_bytes()).hexdigest(),
                    wording_review="guide-abstraction-review-v1")
    write_json(manifest_path, manifest)
    print(Path(profile["file"]).name, "wording edits", len(edits))
save_profiles(profiles, profiles_path)

