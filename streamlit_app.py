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
from pathlib import Path

import streamlit as st
from paper_draft_agent import PaperDraftOrchestrator
from paper_quality import extraction_fingerprint

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
STRUCTURE_JSON = BASE_DIR / "paper_structure_analysis.json"
DRAFT_MD = BASE_DIR / "paper_draft_full.md"
LEGACY_DRAFT_MD = BASE_DIR / "paper_draft_section4_5.md"
REVIEW_JSON = BASE_DIR / "paper_draft_review.json"

if "full_paper_draft" not in st.session_state:
    # 기존에 작성된 파일이 있으면 초기 로드
    initial_draft = DRAFT_MD if DRAFT_MD.exists() else LEGACY_DRAFT_MD
    if initial_draft.exists():
        with open(initial_draft, "r", encoding="utf-8") as f:
            st.session_state["full_paper_draft"] = f.read()
    else:
        st.session_state["full_paper_draft"] = ""
    st.session_state["is_legacy_draft"] = not DRAFT_MD.exists() and LEGACY_DRAFT_MD.exists()

##################################################
# Sidebar: 간결한 입력 및 제어 패널
##################################################

with st.sidebar:
    st.markdown("### 📄 논문 초안 작성 설정")
    st.caption("비정형 연구 실측 데이터와 레퍼런스 스타일을 결합하여 학술 논문 초안을 작성합니다.")
    st.caption("작성 범위: 1장 서론 · 3장 배경 및 문제 정의 · 4장 방법론 · 5장 결과 · 6장 결론. 2장 관련 연구는 비워둡니다.")
    st.divider()

    st.markdown("#### 1. 연구 원천 데이터")
    data_source_mode = st.radio(
        "데이터 선택",
        ["내장된 CUDA 연구 데이터 사용", "CUDA 연구 PDF 업로드·재추출"],
        label_visibility="collapsed"
    )

    uploaded_pdf = None
    if data_source_mode == "CUDA 연구 PDF 업로드·재추출":
        uploaded_pdf = st.file_uploader("연구 PDF 파일", type=["pdf"])
        st.caption("현재 대상은 CUDA 연구 PDF입니다. 업로드 시 Studio Agent로 데이터를 다시 추출합니다.")
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
    if STRUCTURE_JSON.exists():
        st.info("✅ `paper_structure_analysis.json` 적용 중 (인용 제외, IMRAD 규칙 준수)")
    else:
        st.caption("기본 학술지 가이드라인 적용")

    st.markdown("#### 3. 초안 검토")
    st.caption("장별 작성 후 근거 검토 → 종합 편집 → 재검토를 진행합니다. 주요 오류가 남으면 후보 초안으로 분리합니다.")

    st.divider()
    generate_btn = st.button("🚀 논문 초안 작성 시작", type="primary", use_container_width=True)

##################################################
# Generation Logic
##################################################

if generate_btn:
    temp_pdf_path = None
    try:
        if data_source_mode == "CUDA 연구 PDF 업로드·재추출":
            if not uploaded_pdf:
                st.error("업로드할 연구 PDF 파일을 선택해주세요.")
                st.stop()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fp:
                fp.write(uploaded_pdf.read())
                temp_pdf_path = fp.name

        orchestrator = PaperDraftOrchestrator()

        progress_bar = st.progress(0, text="논문 초안 작성 준비 중...")
        def progress_cb(pct, msg):
            progress_bar.progress(pct, text=msg)

        with st.spinner("장별 초안을 작성하고 전체 논문의 흐름을 종합 편집 중입니다..."):
            pipeline_result = orchestrator.run_pipeline(
                research_pdf_path=temp_pdf_path,
                progress_callback=progress_cb
            )
            st.session_state["full_paper_draft"] = pipeline_result["draft_markdown"]
            st.session_state["is_legacy_draft"] = False
            
            st.toast("✅ 논문 초안 작성이 완료되었습니다!")

    except Exception as e:
        st.error(f"초안 작성 중 오류가 발생했습니다: {e}")
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

##################################################
# Main Paper Viewer Area (순수 논문 리더기 형식)
##################################################

draft_content = st.session_state.get("full_paper_draft", "").strip()

if not draft_content:
    st.info("👈 좌측 사이드바에서 **[🚀 논문 초안 작성 시작]** 버튼을 클릭하면 완성된 학술 논문 초안이 이곳에 표시됩니다.")
else:
    if st.session_state.get("is_legacy_draft"):
        st.info("현재 표시된 내용은 기존 4·5장 초안입니다. [논문 초안 작성 시작]을 누르면 1·3·4·5·6장과 종합 초안을 새로 생성합니다.")
    else:
        st.caption("2장 관련 연구는 저자가 작성할 수 있도록 본문을 비워두었습니다. [확인 필요] 표시는 원자료 확인이 필요한 내용입니다.")
        if REVIEW_JSON.exists():
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
                """
                <div class="paper-canvas">
                    <div class="paper-title">CROWN 신경망 검증을 위한 GPU 가속 및 메모리 계층 최적화 기법 연구</div>
                    <div class="paper-meta">연구 자료를 기반으로 작성한 학술 논문 초안</div>
                    <div class="paper-divider"></div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown(draft_content)
