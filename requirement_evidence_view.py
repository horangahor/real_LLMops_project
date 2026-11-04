"""Read-only inspection of question-scoped collection; avoids whole-source review mutations."""

import json

import streamlit as st


def render_requirement_evidence(package):
    st.markdown("### 요구사항 기준 연구 근거")
    st.caption("질문별로 수집·검토한 결과입니다. 원문 전체의 모든 연구 내용을 수집했다는 의미는 아닙니다.")
    st.write(f"후보 {len(package['items'])}개 · 작성용 {len(package['writing_fact_ids'])}개")
    quarantined = package["completion"].get("quarantined_fact_ids", [])
    if quarantined:
        st.caption(f"검증 탈락 후보 {len(quarantined)}개는 검토 기록에 보존되며 초안 작성에 사용하지 않습니다.")
    if not package["completion"]["ready_for_drafting"]:
        st.warning("필수 질문의 근거 부족·적용 여부 미확인 또는 원문 검토 보류가 있어 전체 초안 작성을 제한합니다.")
    if package["completion"].get("pending_extraction_pages"):
        st.warning("출처·근거 연결 보정 후에도 보류된 페이지: " +
                   ", ".join(str(p) for p in package["completion"]["pending_extraction_pages"]) +
                   "쪽. 원응답과 검증 사유는 실행 폴더의 pages에 보존했습니다.")
    labels = {"sufficient": "충족", "partial": "일부 부족", "missing": "근거 부족",
              "not_applicable": "해당 없음", "applicability_uncertain": "적용 여부 미확인", "excluded_by_user": "사용자 지시로 제외",
              "accepted_limited": "현재 정보로 임시 승인"}
    for q in package["requirements"]["requirements"]:
        row = package["requirement_coverage"][q["id"]]
        with st.expander(f"{labels[row['status']]} · {q['question']}"):
            st.write(row["reason"])
            if row["status"] == "accepted_limited":
                st.caption("질문별 사용자 임시 승인입니다. 아래 부족 항목과 원래 AI 판정은 충족된 것으로 바꾸지 않았습니다.")
                st.write("원래 AI 판정: " + row["original_assessment"].get("reason", ""))
            decision = package.get("requirement_applicability", {}).get(q["id"])
            if decision:
                st.caption("적용 여부: " + {"applicable": "적용", "not_applicable": "해당 없음", "uncertain": "미확인"}[decision["status"]])
                for source in decision.get("sources", []):
                    st.write(f"판단 출처 · {source['page']}쪽 · {source['element_id']}")
                    st.text(source["quote"])
            if row["missing_fields"]:
                st.write("부족 항목: " + " / ".join(row["missing_fields"]))
            st.write(("작성에 사용할 근거·사용자 설명: " if row["status"] == "accepted_limited" else "충족 근거: ") + (", ".join(row["evidence_ids"]) or "없음"))
    with st.expander("공유 근거·원문 출처"):
        for fact in package["items"]:
            st.markdown(f"**{fact['id']} · {fact['statement']}**")
            st.caption("질문: " + (", ".join(fact["requirement_ids"]) or "질문 밖의 중요 근거"))
            if fact.get("supplemental_reason"):
                st.write("추가 보존 이유: " + fact["supplemental_reason"])
            st.write(fact["limits"])
            st.caption(f"원문 검토: {fact['support']} · {fact['claim_status']} · {fact['source_origin']}")
            for source in fact["sources"]:
                st.write(("사용자 추가 기록" if source.get("origin") == "user_addendum" else f"{source['page']}쪽") + f" · {source['element_id']}")
                st.text(source["quote"])
    st.download_button("요구사항별 근거 JSON 저장", json.dumps(package, ensure_ascii=False, indent=2),
                       file_name="requirement_evidence.json", mime="application/json")
