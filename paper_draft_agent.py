"""Research-source evidence collection and plan-driven paper drafting gateway."""

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from config import UPSTAGE_API_KEY
from structure_profiles import StructureGuide, load_profiles

ProgressCallback = Callable[[int, str], None]


def load_paper_structure(structure_path: Optional[str | Path] = None) -> StructureGuide:
    base_dir = Path(__file__).resolve().parent
    if structure_path is not None:
        target = Path(structure_path)
    else:
        target = next((path for path in [base_dir / "paper_structure.json",
                                        base_dir / "paper_structure_analysis.json"] if path.exists()), None)
    if target is None:
        return ""
    return {"profiles": load_profiles(target)}


class PaperDraftOrchestrator:
    """Collect research evidence and run structure-driven planning and drafting."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or UPSTAGE_API_KEY
        self.base_dir = Path(__file__).resolve().parent

    def run_pipeline(self, research_pdf_path: Optional[str | Path] = None,
                     results_json_path: Optional[str | Path] = None,
                     structure_json_path: Optional[str | Path] = None,
                     progress_callback: Optional[ProgressCallback] = None,
                     planning_mode: str = "adaptive", project_id: str = "generic",
                     plan_only: bool = False, output_dir: Optional[str | Path] = None,
                     extract_only: bool = False, evidence_mode: str = "comprehensive",
                     research_scope: str = "", requirements_only: bool = False,
                     writing_target_chars: Optional[int] = None) -> Dict[str, Any]:
        if planning_mode != "adaptive":
            raise ValueError("기존 CUDA 고정 구성 작성 방식은 제거됐습니다. 연구 자료에 맞춰 계획하는 방식을 사용해주세요.")
        from planned_paper import PlannedPaper
        from paper_plan import project_profile
        engine = PlannedPaper(self.base_dir, api_key=self.api_key)
        engine.evidence_progress = progress_callback
        if evidence_mode not in ("comprehensive", "requirements"):
            raise ValueError("알 수 없는 근거 수집 방식입니다.")
        requirements = None
        reference = None
        if evidence_mode == "requirements" or requirements_only:
            from evidence_requirements import generate_requirements
            reference = load_paper_structure(structure_json_path)
            if progress_callback:
                progress_callback(3, "골든 작성지침에서 근거 요구사항 생성 중")
            requirements = generate_requirements(engine, reference)
            engine.evidence_requirements = requirements
        if requirements_only:
            if progress_callback:
                progress_callback(100, "공통 근거 질문 파일 저장 완료")
            return {"evidence_requirements": requirements, "draft_markdown": "", "run_dir": requirements["run_dir"]}
        if extract_only:
            extraction = engine.load_evidence(project_profile(project_id), results_json_path, research_pdf_path)
            if progress_callback:
                progress_callback(100, "연구 근거 추출·수집 대장 검사 종료")
            return {"evidence_extraction": extraction, "evidence_requirements": requirements,
                    "draft_markdown": "", "run_dir": extraction["run_dir"]}
        research = engine.load_research(project_profile(project_id), results_json_path, research_pdf_path)
        if reference is None:
            reference = load_paper_structure(structure_json_path)
        result = engine.run(research, reference, project_id, output_dir, plan_only, progress_callback,
                            writing_target_chars=writing_target_chars)
        result["evidence_extraction"] = getattr(engine, "last_extraction", None)
        result["evidence_requirements"] = requirements
        return result


if __name__ == "__main__":
    from planned_paper import main
    main()
