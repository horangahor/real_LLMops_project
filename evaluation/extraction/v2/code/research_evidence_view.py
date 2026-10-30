"""Read-only inspection of automatically extracted, source-linked research evidence."""

import json
import streamlit as st

from research_extract import KINDS, STATUSES, SUPPORT, render_evidence

ORIGINS = {"research_note": "연구노트", "measurement_log": "실행·측정 로그", "implementation_code": "구현 코드",
           "quoted_instruction": "인용된 안내·요청", "ai_advice": "AI 조언", "unknown": "확인 필요"}


def render_research_evidence(package):
    stats = package["diagnostics"]
    with st.expander("연구 근거 자동 추출 결과", expanded=True):
        st.caption("자동 분류와 원문 대조 결과입니다. 독립적인 사실 검증은 아니며 원문 해석·비교 조건은 저자 확인이 필요합니다.")
        st.write(f"후보 {stats['candidates']}개 · 측정값 {stats['measurements']}개 · 작성용 {stats['writing_facts']}개")
        if stats.get("rejected_measurements"):
            st.warning(f"확인 필요 측정 항목 {stats['rejected_measurements']}개를 별도로 분리했습니다. 연구 사실의 뒷받침은 진술 전체로 검사합니다.")
        if stats["excluded_selected_ids"]:
            st.info("원문 뒷받침 부족·가설·확인 필요로 작성 입력에서 제외: " + ", ".join(stats["excluded_selected_ids"]))
        kind = st.selectbox("근거 유형", ["전체", *KINDS], format_func=lambda key: KINDS.get(key, key))
        status = st.selectbox("주장 강도", ["전체", *STATUSES], format_func=lambda key: STATUSES.get(key, key))
        filtered = [item for item in package["items"] if (kind == "전체" or item["kind"] == kind)
                    and (status == "전체" or item["claim_status"] == status)]
        page = st.selectbox("목록 페이지", range(1, max(1, (len(filtered) + 24) // 25) + 1))
        start = (page - 1) * 25
        st.caption(f"필터 결과 {len(filtered)}개 · 현재 {start + 1 if filtered else 0}~{min(start + 25, len(filtered))}개 표시")
        for item in filtered[start:start + 25]:
            st.markdown(f"**{item['id']} · {KINDS[item['kind']]} · {STATUSES[item['claim_status']]}**")
            st.write(item["statement"])
            st.caption(f"{SUPPORT[item['support']]}: {item['support_note']}")
            if item["conditions"]:
                st.write("조건: " + " / ".join(item["conditions"]))
            if item.get("source_origin"):
                st.caption("자료 성격: " + ORIGINS.get(item["source_origin"], item["source_origin"]))
            for parameter in item.get("parameters", []):
                st.write(f"설정: {parameter['name']} = {parameter['value']} ({parameter['value_kind']})")
            for observation in item.get("observations", []):
                st.write("관찰·비교: " + observation)
            for issue in item.get("numeric_issues", []):
                st.caption("문장 수치 검사: " + issue)
            for measure in item["measurements"]:
                st.write(f"측정: {measure['metric']} = {measure['value']} {measure['unit']} · {measure['condition']}")
                st.caption("측정값 출처: " + ", ".join(measure["element_ids"]))
            for measure in item.get("rejected_measurements", []):
                st.caption(f"확인 필요 수치 (작성 제외): {measure['metric']} = {measure['value']} {measure['unit']}")
            st.caption("해석 한계: " + item["limits"])
            for source in item["sources"]:
                st.caption(f"원문 {source['page']}쪽 · {source['element_id']}")
                st.code(source["quote"], language=None)
        st.download_button("추출 근거 JSON 저장", json.dumps(package, ensure_ascii=False, indent=2),
                           file_name="research_evidence_auto.json", mime="application/json")
        st.download_button("추출 근거 Markdown 저장", render_evidence(package),
                           file_name="research_evidence_auto.md", mime="text/markdown")
