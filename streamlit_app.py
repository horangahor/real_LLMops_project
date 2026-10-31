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

    st.markdown("#### 2. 레퍼런스 스타일 프로파일")
    if structure_error:
        st.error(f"골든 샘플 분석을 읽을 수 없습니다: {structure_error}")
    elif structure_reference:
        st.info(f"✅ 골든 샘플 {len(structure_reference['profiles'])}개 준비 완료")
        st.caption("아래 '골든 샘플 구조·작성 가이드'에서 논문별 목차와 작성 지침을 확인할 수 있습니다.")
    else:
        st.caption("기본 학술지 가이드라인 적용")

    st.markdown("#### 3. 초안 검토")
    st.caption("장별 작성 후 근거 검토 → 종합 편집 → 재검토를 진행합니다. 주요 오류가 남으면 후보 초안으로 분리합니다.")

    st.divider()
    generate_btn = st.button("🚀 논문 초안 작성 시작", type="primary", use_container_width=True,
                             disabled=bool(structure_error))
    plan_btn = st.button("작성 계획만 만들기", use_container_width=True,
                         disabled=not adaptive or bool(structure_error))
    extract_btn = st.button("연구 근거만 추출하기", use_container_width=True, disabled=not adaptive)
    if adaptive and local_input and st.button("저장된 연구 근거 불러오기", use_container_width=True):
        from research_extract_v3 import load_saved_evidence
        saved_evidence = load_saved_evidence(local_input, BASE_DIR)
        if saved_evidence:
            st.session_state["research_evidence_extraction"] = saved_evidence
            st.session_state["evidence_preview_only"] = True
        else:
            st.info("이 자료의 완료 결과가 아직 없습니다. 추출이 끝난 뒤 다시 불러와 주세요.")

if structure_reference:
    with st.expander("골든 샘플 구조·작성 가이드", expanded=False):
        render_reference_profiles(structure_reference["profiles"])

##################################################
# Generation Logic
##################################################

if generate_btn or plan_btn or extract_btn:
    temp_pdf_path = None
    try:
        if adaptive and data_source_mode == "input 폴더의 연구 자료":
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

        progress_bar = st.progress(0, text="연구 근거 수집 준비 중..." if extract_btn else "논문 초안 작성 준비 중...")
        def progress_cb(pct, msg):
            progress_bar.progress(pct, text=msg)

        with st.spinner("연구 근거를 수집하고 원문별 누락을 검사 중입니다..." if extract_btn else "장별 초안을 작성하고 전체 논문의 흐름을 종합 편집 중입니다..."):
            pipeline_result = orchestrator.run_pipeline(
                research_pdf_path=temp_pdf_path,
                progress_callback=progress_cb,
                planning_mode="adaptive" if adaptive else "legacy_cuda",
                project_id="cuda" if data_source_mode in ("CUDA 원본 PDF 자동 분석", "내장된 CUDA 연구 데이터 사용") else "generic",
                plan_only=plan_btn,
                extract_only=extract_btn,
            )
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
            
            st.toast("✅ 연구 근거를 자동 추출했습니다." if extract_btn else
                     "✅ 작성 계획을 저장했습니다." if plan_btn else "✅ 논문 초안 작성이 완료되었습니다!")

    except Exception as e:
        task_label = "연구 근거 추출" if extract_btn else "작성 계획 생성" if plan_btn else "초안 작성"
        st.error(f"{task_label} 중 오류가 발생했습니다: {e}")
    finally:
        if not adaptive and temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

##################################################
# Main Paper Viewer Area (순수 논문 리더기 형식)
##################################################

draft_content = st.session_state.get("full_paper_draft", "").strip()

if st.session_state.get("research_evidence_extraction"):
    from research_evidence_view import render_research_evidence
    render_research_evidence(st.session_state["research_evidence_extraction"])
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
