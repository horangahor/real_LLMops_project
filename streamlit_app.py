"""
=========================================================
AI 학술 논문 초안 작성기 (Paper Drafting AI)
불필요한 대시보드를 배제하고, 실측 연구 데이터와 레퍼런스 스타일을
결합하여 완성형 학술 논문 초안을 작성하는 전문 도구.
=========================================================
"""

import os
import json
import tempfile
import hashlib
import html
from pathlib import Path

import streamlit as st
from paper_draft_agent import PaperDraftOrchestrator, load_paper_structure
from paper_quality import extraction_fingerprint
from structure_profile_view import render_reference_profiles
from planned_paper import fingerprint as plan_fingerprint
from requirement_intervention import RequirementInterruption
from requirement_intervention_view import render_intervention

##################################################
# Page Configuration
##################################################

st.set_page_config(
    page_title="AI 학술 논문 초안 작성기",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

##################################################
# Academic Paper Custom Typography & Styling
##################################################

st.markdown("""
<style>
    /* 전체 배경 및 폰트 */
    .stApp {
        background-color: #F8FAFC;
    }
    
    /* 학술 논문 용지(Paper Canvas) 스타일 */
    .paper-canvas {
        background-color: #FFFFFF;
        max-width: 900px;
        margin: 0 auto;
        padding: 48px 56px;
        border: 1px solid #E2E8F0;
        border-radius: 4px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
        font-family: 'Times New Roman', 'Nanum Myeongjo', serif;
        line-height: 1.85;
        color: #1A202C;
    }
    
    .paper-title {
        font-size: 1.85rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 12px;
        color: #0F172A;
        line-height: 1.35;
    }
    
    .paper-meta {
        text-align: center;
        font-size: 0.95rem;
        color: #64748B;
        margin-bottom: 28px;
    }
    
    .paper-divider {
        border-top: 1px solid #CBD5E1;
        margin: 20px 0 28px 0;
    }
    
    .paper-body {
        font-size: 1.02rem;
        text-align: justify;
        color: #1E293B;
    }
    
    .paper-body h1, .paper-body h2, .paper-body h3 {
        color: #0F172A;
        font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
        font-weight: 700;
        margin-top: 24px;
        margin-bottom: 12px;
    }
    
    .paper-body table {
        width: 100%;
        border-collapse: collapse;
        margin: 18px 0;
        font-size: 0.92rem;
    }
    
    .paper-body th, .paper-body td {
        border: 1px solid #CBD5E1;
        padding: 8px 12px;
        text-align: center;
    }
    
    .paper-body th {
        background-color: #F1F5F9;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

##################################################
# Data Paths & Session State
##################################################

BASE_DIR = Path(__file__).resolve().parent
RESULTS_JSON = BASE_DIR / "Results & Discussion.json"
DRAFT_MD = BASE_DIR / "paper_draft_full.md"
LEGACY_DRAFT_MD = BASE_DIR / "archive/legacy-drafts/paper_draft_section4_5.md"
REVIEW_JSON = BASE_DIR / "paper_draft_review.json"
INPUT_DIR = BASE_DIR / "input"
local_inputs = sorted(
    (path for path in INPUT_DIR.glob("*")
     if path.is_file() and path.suffix.lower() == ".pdf"
     and path.resolve().is_relative_to(INPUT_DIR.resolve())),
    key=lambda path: path.name.casefold(),
)

structure_reference, structure_error = None, None
try:
    structure_reference = load_paper_structure()
except (OSError, ValueError) as error:
    structure_error = str(error)

if "full_paper_draft" not in st.session_state:
    # 기존에 작성된 파일이 있으면 초기 로드
    initial_draft = DRAFT_MD if DRAFT_MD.exists() else LEGACY_DRAFT_MD
    if initial_draft.exists():
        with open(initial_draft, "r", encoding="utf-8") as f:
            st.session_state["full_paper_draft"] = f.read()
    else:
        st.session_state["full_paper_draft"] = ""
    st.session_state["is_legacy_draft"] = not DRAFT_MD.exists() and LEGACY_DRAFT_MD.exists()
    from planned_paper import load_latest
    try:
        latest = load_latest(BASE_DIR)
        if latest:
            st.session_state["full_paper_draft"] = latest["draft_markdown"]
            st.session_state["paper_plan"] = latest["plan"]
            st.session_state["planned_review"] = latest["review"]
            st.session_state["draft_mode"] = "adaptive"
            st.session_state["draft_plan_fingerprint"] = plan_fingerprint(latest["plan"])
            st.session_state["is_legacy_draft"] = False
    except (OSError, ValueError, KeyError) as error:
        st.warning(f"저장된 연구별 초안을 불러오지 못했습니다: {error}")

##################################################
# Sidebar: 간결한 입력 및 제어 패널
##################################################

with st.sidebar:
    st.markdown("### 📄 논문 초안 작성 설정")
    st.caption("비정형 연구 실측 데이터와 레퍼런스 스타일을 결합하여 학술 논문 초안을 작성합니다.")
    writing_mode = st.radio("작성 방식", ["연구 자료에 맞춰 계획", "기존 CUDA 고정 구성 (비교용)"])
    adaptive = writing_mode == "연구 자료에 맞춰 계획"
    st.caption("장·절과 작성 순서는 연구 근거와 참고 가이드로 계획합니다. 계획만 먼저 확인할 수도 있습니다." if adaptive
               else "기존 1·3·4·5·6장 작성 경로입니다. 2장 관련 연구는 비워둡니다.")
    st.divider()

    st.markdown("#### 1. 연구 원천 데이터")
    data_source_mode = st.radio(
        "데이터 선택",
        (["input 폴더의 연구 자료"] if local_inputs else []) +
        ["연구 PDF 업로드", "CUDA 원본 PDF 자동 분석"] if adaptive
        else ["내장된 CUDA 연구 데이터 사용", "CUDA 연구 PDF 업로드·재추출"],
        label_visibility="collapsed"
    )

    uploaded_pdf = None
    local_input = None
    if data_source_mode == "input 폴더의 연구 자료":
        local_input = st.selectbox("연구 자료 파일", local_inputs, format_func=lambda path: path.name)
        st.caption("원본 PDF에서 연구 근거를 자동 추출합니다. 인용문·페이지를 원문에 연결하고 파일별로 계획과 초안을 저장합니다.")
    elif data_source_mode in ("연구 PDF 업로드", "CUDA 연구 PDF 업로드·재추출"):
        uploaded_pdf = st.file_uploader("연구 PDF 파일", type=["pdf"])
        st.caption("Document Parse API로 읽고 원문 요소에 연결된 연구 근거를 추출합니다. 기계 추출 내용은 저자 검수가 필요합니다." if adaptive
                   else "현재 대상은 CUDA 연구 PDF입니다. 업로드 시 Studio Agent로 데이터를 다시 추출합니다.")
    elif data_source_mode == "CUDA 원본 PDF 자동 분석":
        from paper_plan import project_profile
        cuda_source = BASE_DIR / project_profile("cuda")["research_pdf"]
        if cuda_source.is_file():
            st.success("CUDA 원본 PDF 준비 완료")
            st.caption("원본에서 근거를 자동 추출합니다. 이전 수작업 근거는 사용하지 않습니다.")
        else:
            st.warning("CUDA 연구 원본을 input 폴더에 넣어주세요.")
    else:
        if RESULTS_JSON.exists():
            try:
                with RESULTS_JSON.open(encoding="utf-8") as source:
                    research_data = json.load(source)
                methods = research_data.get("optimization_methods") or research_data.get("methods_and_results") or []
                st.success(f"✅ 저장된 연구 데이터 준비 완료 (최적화 기법 {len(methods)}개)")
            except (OSError, ValueError, AttributeError):
                st.error("연구 JSON을 읽을 수 없습니다. 추출 결과를 확인해주세요.")
        else:
            st.warning("⚠️ `Results & Discussion.json`이 없습니다. method_result.py를 먼저 실행하세요.")

    evidence_mode = "comprehensive"
    if adaptive:
        collection_label = st.radio("근거 수집 방식", ["작성지침 → 요구사항 → 근거", "기존 전체 수집"])
        evidence_mode = "requirements" if collection_label.startswith("작성지침") else "comprehensive"
        if evidence_mode == "requirements":
            st.caption("공통 질문은 연구 주제 입력 없이 만듭니다. 연구 일지를 넣으면 적용 여부를 판단하고 근거를 찾습니다.")
            st.caption("공통 질문 생성에는 골든 작성지침만 Upstage로 전송합니다. 근거 추출 시에는 선택한 연구 일지를 읽습니다.")

    st.markdown("#### 2. 레퍼런스 스타일 프로파일")
    if structure_error:
        st.error(f"골든 샘플 분석을 읽을 수 없습니다: {structure_error}")
    elif structure_reference:
        st.info(f"✅ 골든 샘플 {len(structure_reference['profiles'])}개 준비 완료")
        st.caption("아래 '골든 샘플 구조·작성 가이드'에서 논문별 목차와 작성 지침을 확인할 수 있습니다.")
    else:
        st.caption("기본 학술지 가이드라인 적용")

    st.markdown("#### 3. 초안 검토")
    st.caption("소절은 본문과 사용 근거를 대조하고, 장별·전체 편집은 중복·연결·문체를 검토합니다." if adaptive else
               "장별 작성 후 근거 검토 → 종합 편집 → 재검토를 진행합니다. 주요 오류가 남으면 후보 초안으로 분리합니다.")

    st.divider()
    requirements_btn = st.button("근거 요구사항만 만들기", use_container_width=True,
        disabled=not adaptive or evidence_mode != "requirements" or not structure_reference or bool(structure_error))
    generate_btn = st.button("🚀 논문 초안 작성 시작", type="primary", use_container_width=True,
                             disabled=bool(structure_error))
    plan_btn = st.button("작성 계획만 만들기", use_container_width=True,
                         disabled=not adaptive or bool(structure_error))
    extract_btn = st.button("연구 근거만 추출하기", use_container_width=True, disabled=not adaptive)
    if adaptive and local_input and st.button("저장된 연구 근거 불러오기", use_container_width=True):
        if evidence_mode == "requirements":
            from evidence_requirements import load_requirements
            from requirement_extraction import load_saved_requirement_evidence
            saved_requirements = load_requirements(BASE_DIR, structure_reference) if structure_reference else None
            saved_evidence = load_saved_requirement_evidence(local_input, BASE_DIR, saved_requirements) if saved_requirements else None
            if saved_requirements:
                st.session_state["evidence_requirements"] = saved_requirements
        else:
            from research_extract_v3 import load_saved_evidence
            saved_evidence = load_saved_evidence(local_input, BASE_DIR)
        if saved_evidence:
            st.session_state["research_evidence_extraction"] = saved_evidence
            st.session_state["evidence_preview_only"] = True
        else:
            st.info("현재 수집 방식의 저장 결과가 없습니다. Git에서 복원한 근거는 '기존 전체 수집'을 선택하면 불러올 수 있습니다.")
    recovery_available = evidence_mode == "comprehensive" and bool(
        (st.session_state.get("research_evidence_extraction") or {}).get("version") == "research-evidence-v3" or (adaptive and local_input))
    if st.button("미확인 근거 복구·중복 연결 검토", key="sidebar_recover_pending_evidence",
                 use_container_width=True, disabled=not recovery_available):
        try:
            from research_extract_v3 import load_saved_evidence, run_unconfirmed_recovery
            from planned_paper import PlannedPaper
            evidence = st.session_state.get("research_evidence_extraction")
            if (evidence is None or evidence.get("version") != "research-evidence-v3") and adaptive and local_input:
                evidence = load_saved_evidence(local_input, BASE_DIR)
            if evidence is None:
                st.info("완료된 저장 근거가 없습니다. 먼저 연구 근거를 추출해주세요.")
            else:
                with st.spinner("미확인 근거를 복구하고 중복 관계를 확인 중입니다..."):
                    run_unconfirmed_recovery(evidence, PlannedPaper(base_dir=BASE_DIR))
                st.session_state["research_evidence_extraction"] = evidence
                st.session_state["evidence_preview_only"] = True
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            st.error(f"미확인 근거 재검토 중 오류가 발생했습니다: {error}")

if structure_reference:
    with st.expander("골든 샘플 구조·작성 가이드", expanded=False):
        render_reference_profiles(structure_reference["profiles"])

##################################################
# Generation Logic
##################################################

if adaptive and evidence_mode == "requirements" and "pending_requirement" not in st.session_state:
    selected_source = local_input
    if data_source_mode == "CUDA 원본 PDF 자동 분석":
        selected_source = cuda_source if cuda_source.is_file() else None
    if selected_source and structure_reference:
        from evidence_requirements import load_requirements
        from requirement_intervention import restore_pending
        current_requirements = load_requirements(BASE_DIR, structure_reference)
        if current_requirements:
            restored = restore_pending(BASE_DIR, selected_source, current_requirements)
            if restored:
                st.session_state["pending_requirement"], st.session_state["pending_requirement_request"] = restored
resume_request = render_intervention(BASE_DIR)

if generate_btn or plan_btn or extract_btn or requirements_btn or resume_request:
    temp_pdf_path = None
    pipeline_request = None
    try:
        if resume_request:
            adaptive = True
            plan_btn = resume_request.get("plan_only", False)
            extract_btn = resume_request.get("extract_only", False)
            requirements_btn = False
            temp_pdf_path = resume_request.get("research_pdf_path")
        elif requirements_btn:
            pass
        elif adaptive and data_source_mode == "input 폴더의 연구 자료":
            if local_input is None or not local_input.is_file():
                st.error("input 폴더에서 연구 자료를 찾을 수 없습니다.")
                st.stop()
            temp_pdf_path = str(local_input)
        elif adaptive and data_source_mode == "연구 PDF 업로드":
            if uploaded_pdf is None:
                st.error("연구 자료를 업로드해주세요.")
                st.stop()
            contents = uploaded_pdf.getvalue()
            upload_path = BASE_DIR / "draft_history/uploads" / (hashlib.sha256(contents).hexdigest() + ".pdf")
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            if not upload_path.exists():
                upload_path.write_bytes(contents)
            temp_pdf_path = str(upload_path)
        elif data_source_mode == "CUDA 연구 PDF 업로드·재추출":
            if not uploaded_pdf:
                st.error("업로드할 연구 PDF 파일을 선택해주세요.")
                st.stop()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
                fp.write(uploaded_pdf.read())
                temp_pdf_path = fp.name

        orchestrator = PaperDraftOrchestrator()

        progress_bar = st.progress(0, text="공통 근거 질문 준비 중..." if requirements_btn else "연구 근거 수집 준비 중..." if extract_btn else "논문 초안 작성 준비 중...")
        def progress_cb(pct, msg):
            progress_bar.progress(pct, text=msg)

        with st.spinner("골든 작성지침에서 공통 질문을 만들고 있습니다..." if requirements_btn else "연구 근거를 수집하고 검토 중입니다..." if extract_btn else "소절별 작성·검토와 장별·전체 편집을 진행 중입니다..." if adaptive else "장별 초안을 작성하고 전체 논문의 흐름을 종합 편집 중입니다..."):
            pipeline_request = resume_request or dict(
                research_pdf_path=temp_pdf_path, planning_mode="adaptive" if adaptive else "legacy_cuda",
                project_id="cuda" if data_source_mode in ("CUDA 원본 PDF 자동 분석", "내장된 CUDA 연구 데이터 사용") else "generic",
                plan_only=plan_btn, extract_only=extract_btn, evidence_mode=evidence_mode,
                requirements_only=requirements_btn)
            pipeline_result = orchestrator.run_pipeline(**pipeline_request, progress_callback=progress_cb)
            st.session_state.pop("pending_requirement", None)
            st.session_state.pop("pending_requirement_request", None)
            if pipeline_result.get("evidence_requirements"):
                st.session_state["evidence_requirements"] = pipeline_result["evidence_requirements"]
            if pipeline_result.get("evidence_extraction"):
                st.session_state["research_evidence_extraction"] = pipeline_result["evidence_extraction"]
                st.session_state["evidence_preview_only"] = extract_btn
            if adaptive and "plan" in pipeline_result:
                st.session_state["paper_plan"] = pipeline_result["plan"]
            if pipeline_result["draft_markdown"]:
                st.session_state["full_paper_draft"] = pipeline_result["draft_markdown"]
                st.session_state["is_legacy_draft"] = False
                st.session_state["draft_mode"] = "adaptive" if adaptive else "legacy_cuda"
                st.session_state["planned_review"] = pipeline_result.get("review") if adaptive else None
                st.session_state["draft_plan_fingerprint"] = plan_fingerprint(pipeline_result["plan"]) if adaptive else None
            
            st.toast("✅ 근거 요구사항을 저장했습니다." if requirements_btn else "✅ 연구 근거를 자동 추출했습니다." if extract_btn else
                     "✅ 작성 계획을 저장했습니다." if plan_btn else "✅ 논문 초안 작성이 완료되었습니다!")

    except RequirementInterruption as interruption:
        from document_parse import write_json
        st.session_state["pending_requirement"] = interruption.pending
        st.session_state["pending_requirement_request"] = pipeline_request
        write_json(Path(interruption.pending["run_dir"]) / "interrupted-request.json", pipeline_request)
        render_intervention(BASE_DIR)
    except Exception as e:
        task_label = "근거 요구사항 생성" if requirements_btn else "연구 근거 추출" if extract_btn else "작성 계획 생성" if plan_btn else "초안 작성"
        st.error(f"{task_label} 중 오류가 발생했습니다: {e}")
    finally:
        if not adaptive and temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

##################################################
# Main Paper Viewer Area (순수 논문 리더기 형식)
##################################################

draft_content = st.session_state.get("full_paper_draft", "").strip()

if st.session_state.get("evidence_requirements"):
    from evidence_requirements import render_requirements
    requirements = st.session_state["evidence_requirements"]
    with st.expander("절별 근거 요구사항", expanded=True):
        st.markdown(render_requirements(requirements))
        st.caption("저장 위치: " + requirements["run_dir"])
        st.download_button("근거 요구사항 JSON 저장", json.dumps(requirements, ensure_ascii=False, indent=2),
                           file_name="evidence_requirements.json", mime="application/json")

if st.session_state.get("research_evidence_extraction"):
    extraction = st.session_state["research_evidence_extraction"]
    if extraction.get("version", "").startswith("research-evidence-requirements-"):
        from requirement_evidence_view import render_requirement_evidence
        render_requirement_evidence(extraction)
    else:
        from research_evidence_view import render_research_evidence
        render_research_evidence(extraction)
    if draft_content and st.session_state.get("evidence_preview_only"):
        st.info("연구 근거 추출 결과만 갱신했습니다. 아래에는 이전 초안이 표시되며, 새 근거를 반영하려면 초안을 다시 생성해주세요.")

if st.session_state.get("paper_plan"):
    with st.expander("이번 연구의 작성 계획", expanded=True):
        plan = st.session_state["paper_plan"]
        st.markdown(f"#### {plan['title']}")
        st.write(plan["rationale"])
        for number, section in enumerate(plan["sections"], 1):
            st.markdown(f"**{number}. {section['title']}**")
            st.write(section["purpose"])
            if section["status"] == "placeholder":
                st.caption("본문을 비워두는 장입니다.")
            if section["subsections"]:
                st.caption("소절: " + " · ".join(section["subsections"]))
            if section["reference_adaptation"]:
                st.caption("참고 구성 적용: " + section["reference_adaptation"])
            if section["required_items"]:
                st.markdown("\n".join("- " + item["description"] for item in section["required_items"]))
        if plan["unresolved"]:
            st.warning("확인이 필요한 내용: " + " / ".join(plan["unresolved"]))
        st.download_button("작성 계획 JSON 저장", json.dumps(st.session_state["paper_plan"], ensure_ascii=False, indent=2),
                           file_name="paper_plan.json", mime="application/json")
        if draft_content and st.session_state.get("draft_plan_fingerprint") != plan_fingerprint(plan):
            st.info("새 작성 계획의 미리보기입니다. 아래에는 이전 초안이 표시됩니다.")

if not draft_content:
    st.info("👈 좌측 사이드바에서 **[🚀 논문 초안 작성 시작]** 버튼을 클릭하면 완성된 학술 논문 초안이 이곳에 표시됩니다.")
else:
    if adaptive and st.session_state.get("draft_mode") != "adaptive":
        st.caption("현재 표시된 것은 기존 CUDA 초안입니다. 새 연구 자료로 계획과 초안을 생성할 수 있습니다.")
    if st.session_state.get("is_legacy_draft"):
        st.info("현재 표시된 내용은 기존 4·5장 초안입니다. [논문 초안 작성 시작]을 누르면 1·3·4·5·6장과 종합 초안을 새로 생성합니다.")
    else:
        st.caption("[확인 필요] 표시는 원자료 확인이 필요한 내용입니다.")
        if st.session_state.get("draft_mode") == "adaptive":
            st.caption("연구별 작성 계획을 적용한 초안입니다. 자동 검토는 독립적인 사실 검증이 아니므로 저자의 확인이 필요합니다.")
            with st.expander("계획·근거 검토 결과"):
                st.json(st.session_state.get("planned_review", {}))
        elif REVIEW_JSON.exists():
            try:
                saved_review = json.loads(REVIEW_JSON.read_text(encoding="utf-8"))
                review = saved_review["review"]
                current_fingerprint = extraction_fingerprint({"draft": draft_content})
                if saved_review.get("draft_fingerprint") != current_fingerprint:
                    st.caption("검토 기록과 현재 표시된 초안의 내용이 일치하는지 확인이 필요합니다.")
                elif review.get("approved"):
                    st.caption("자동 검토의 주요 오류 검사를 통과한 초안입니다. 사실성과 연구 주장은 저자의 최종 확인이 필요합니다.")
                with st.expander("근거 검토 결과"):
                    st.json(review)
            except (OSError, ValueError, KeyError):
                st.caption("검토 기록을 읽을 수 없습니다.")
        else:
            st.info("현재 표시된 초안은 새 근거 검토를 아직 거치지 않았습니다. 다시 생성하면 검토 절차를 적용합니다.")
    # 상단 다운로드 및 유틸리티 툴바
    tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
    with tcol1:
        st.markdown("### 📄 논문 초안")
    with tcol2:
        st.download_button(
            label="📥 텍스트 파일 (.txt) 저장",
            data=draft_content,
            file_name="paper_draft_full.txt",
            mime="text/plain",
            use_container_width=True
        )
        st.download_button(
            label="📥 Markdown (.md) 저장",
            data=draft_content,
            file_name="paper_draft_full.md",
            mime="text/markdown",
            use_container_width=True
        )
    with tcol3:
        view_raw = st.toggle("원문 텍스트/복사 모드", value=False)

    if view_raw:
        st.caption("아래 텍스트 상자에서 Ctrl+A, Ctrl+C로 전체 내용을 복사할 수 있습니다.")
        st.text_area("논문 전문 텍스트", value=draft_content, height=600)
    else:
        # 정통 논문 용지 레이아웃으로 렌더링
        with st.container():
            st.markdown(
                f"""
                <div class="paper-canvas">
                    <div class="paper-title">{html.escape(draft_content.splitlines()[0].lstrip('# ').strip())}</div>
                    <div class="paper-meta">연구 자료를 기반으로 작성한 학술 논문 초안</div>
                    <div class="paper-divider"></div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown(draft_content)
