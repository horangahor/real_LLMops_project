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
from typing import Dict, Any, Optional

import streamlit as st
from config import UPSTAGE_API_KEY
from paper_draft_agent import PaperDraftOrchestrator

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
DRAFT_TXT = BASE_DIR / "paper_draft_full.txt"
DRAFT_MD = BASE_DIR / "paper_draft_section4_5.md"

if "current_draft" not in st.session_state:
    # 기존에 작성된 파일이 있으면 초기 로드
    if DRAFT_MD.exists():
        with open(DRAFT_MD, "r", encoding="utf-8") as f:
            st.session_state["current_draft"] = f.read()
    else:
        st.session_state["current_draft"] = ""

##################################################
# Sidebar: 간결한 입력 및 제어 패널
##################################################

with st.sidebar:
    st.markdown("### 📄 논문 초안 작성 설정")
    st.caption("비정형 연구 실측 데이터와 레퍼런스 스타일을 결합하여 학술 논문 초안을 작성합니다.")
    st.divider()

    st.markdown("#### 1. 연구 원천 데이터")
    data_source_mode = st.radio(
        "데이터 선택",
        ["내장된 실측 연구 데이터 사용", "새로운 연구 PDF 업로드"],
        label_visibility="collapsed"
    )

    uploaded_pdf = None
    if data_source_mode == "새로운 연구 PDF 업로드":
        uploaded_pdf = st.file_uploader("연구 PDF 파일", type=["pdf"])
    else:
        if RESULTS_JSON.exists():
            st.success("✅ `Results & Discussion.json` 로드 완료 (29대 최적화 기법)")
        else:
            st.warning("⚠️ `Results & Discussion.json`이 없습니다. method_result.py를 먼저 실행하세요.")

    st.markdown("#### 2. 레퍼런스 스타일 프로파일")
    if STRUCTURE_JSON.exists():
        st.info("✅ `paper_structure_analysis.json` 적용 중 (인용 제외, IMRAD 규칙 준수)")
    else:
        st.caption("기본 학술지 가이드라인 적용")

    st.divider()
    generate_btn = st.button("🚀 논문 초안 작성 시작", type="primary", use_container_width=True)

##################################################
# Generation Logic
##################################################

if generate_btn:
    temp_pdf_path = None
    try:
        if data_source_mode == "새로운 연구 PDF 업로드":
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

        with st.spinner("Solar LLM이 29대 최적화 기법의 구현 디테일과 실측 벤치마크를 정밀 서술 중입니다..."):
            pipeline_result = orchestrator.run_pipeline(
                research_pdf_path=temp_pdf_path,
                progress_callback=progress_cb
            )
            st.session_state["current_draft"] = pipeline_result["draft_markdown"]
            
            # 전문 텍스트 파일(.txt)도 함께 저장
            with open(DRAFT_TXT, "w", encoding="utf-8") as f:
                f.write(st.session_state["current_draft"])
            
            st.toast("✅ 논문 초안 작성이 완료되었습니다!")

    except Exception as e:
        st.error(f"초안 작성 중 오류가 발생했습니다: {e}")
    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

##################################################
# Main Paper Viewer Area (순수 논문 리더기 형식)
##################################################

draft_content = st.session_state.get("current_draft", "").strip()

if not draft_content:
    st.info("👈 좌측 사이드바에서 **[🚀 논문 초안 작성 시작]** 버튼을 클릭하면 완성된 학술 논문 초안이 이곳에 표시됩니다.")
else:
    # 상단 다운로드 및 유틸리티 툴바
    tcol1, tcol2, tcol3 = st.columns([2, 1, 1])
    with tcol1:
        st.markdown("### 📄 작성된 논문 초안 전문 (Section 4 & Section 5)")
    with tcol2:
        st.download_button(
            label="📥 텍스트 파일 (.txt) 저장",
            data=draft_content,
            file_name="paper_draft_full.txt",
            mime="text/plain",
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
                    <div class="paper-meta">연구 논문 초안 | 제4장 연구 방법론 & 제5장 실증 평가 및 고찰 전문</div>
                    <div class="paper-divider"></div>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown(draft_content)
