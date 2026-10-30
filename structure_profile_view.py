"""Streamlit에서 골든 샘플 목차와 작성 지침을 읽기 쉽게 표시한다."""

import json
from pathlib import Path

import streamlit as st

from structure_profiles import ROLE_LABELS, outline_markdown, profile_markdown


def render_reference_profiles(profiles):
    labels = [f"샘플 {index} · {Path(profile.get('file', '기존 분석')).stem}"
              for index, profile in enumerate(profiles, 1)]
    for index, (tab, profile) in enumerate(zip(st.tabs(labels), profiles)):
        with tab:
            if "schema_version" not in profile:
                st.caption("이전 형식의 분석입니다. 원래 분석 문서를 표시합니다.")
                st.markdown(profile_markdown(profile))
            else:
                st.markdown(f"#### {profile['title']}")
                if profile["provenance"] == "legacy_analysis":
                    st.caption("기존 분석을 로컬에서 정리한 자료입니다. PDF 원문을 다시 대조한 결과는 아닙니다.")
                elif profile.get("pipeline_version") == "parse-numbered-outline-v1":
                    st.caption("번호가 있는 본문 장·절을 분석한 결과입니다. 무번호 절은 포함하지 않으며, 문체·작성 가이드는 자동 분석 자료입니다.")
                outline_tab, guide_tab, style_tab, json_tab = st.tabs(
                    ["관찰된 목차", "장별 작성 가이드", "문체·적용 주의", "JSON"])
                with outline_tab:
                    st.markdown(outline_markdown(profile["observed_outline"]))
                    st.caption("페이지가 확인된 항목만 페이지 번호를 표시합니다. 원문의 목차 개수는 우리 논문에 강제하지 않습니다.")
                with guide_tab:
                    guides = {guide["role"]: guide for guide in profile["section_guidelines"]}
                    selected = st.selectbox("참고할 역할", options=list(guides),
                                            format_func=lambda role: ROLE_LABELS[role], key=f"reference-role-{index}")
                    guide = guides[selected]
                    st.markdown(f"**역할** · {guide['purpose']}")
                    st.markdown("**포함할 내용**\n\n" + "\n".join(f"- {item}" for item in guide["required_content"]))
                    st.markdown("**문단 흐름** · " + " → ".join(guide["paragraph_flow"]))
                    if guide["figures_tables"]:
                        st.markdown("**표·그림**\n\n" + "\n".join(f"- {item}" for item in guide["figures_tables"]))
                    st.caption("이 가이드는 원문에서 관찰한 구성을 다른 연구에 적용하기 위한 권고입니다.")
                with style_tab:
                    st.markdown("**문체 규칙**\n\n" + "\n".join(f"- {item}" for item in profile["style_rules"]))
                    st.markdown("**옮기면 안 되는 내용**\n\n" + "\n".join(f"- {item}" for item in profile["not_to_transfer"]))
                    if profile["analysis_notes"]:
                        st.markdown("**분석 메모**\n\n" + "\n".join(f"- {item}" for item in profile["analysis_notes"]))
                with json_tab:
                    st.json(profile, expanded=False)
            json_col, markdown_col = st.columns(2)
            with json_col:
                st.download_button("JSON 저장", data=json.dumps(profile, ensure_ascii=False, indent=2),
                                   file_name=f"golden_sample_{index+1}.json", mime="application/json",
                                   key=f"reference-json-{index}")
            with markdown_col:
                st.download_button("읽기용 Markdown 저장", data=profile_markdown(profile),
                                   file_name=f"golden_sample_{index+1}.md", mime="text/markdown",
                                   key=f"reference-markdown-{index}")
