"""Inspect and human-review automatically extracted, source-linked research evidence."""

import json
from pathlib import Path
import streamlit as st

from research_extract import KINDS, SUPPORT, render_evidence
from research_extract_v3 import ORIGINS as ORIGIN_VALUES, STATUSES as V3_STATUSES, writing_eligible
from research_dedup import RELATION_LABELS

ORIGIN_LABELS = {"research_note": "연구노트", "measurement_log": "실행·측정 로그", "implementation_code": "구현 코드",
                 "quoted_instruction": "인용된 안내·요청", "ai_advice": "AI 조언", "unknown": "확인 필요"}
GATE_CATEGORIES = {"missing_content": "내용 누락", "response_failure": "모델 응답 실패", "source_unavailable": "원문 없음",
                   "unreviewed": "미검토", "other": "기타", "non_research": "구분선·제목·연결 문장",
                   "acronym_only": "약어 표기만 다름", "reread_duplicate": "재판독 중복",
                   "unreadable_image": "판독 불가 이미지", "quarantined_fact": "검증 제외 후보",
                   "human_accepted": "사람이 진행 허용"}


@st.cache_data(show_spinner=False)
def _load_source_elements(path, modified_ns):
    del modified_ns
    if not path or not Path(path).is_file():
        return []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload.get("elements", [])
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def _context_for_fact(elements, fact, radius=2):
    source_ids = {source.get("element_id") for source in fact.get("sources", [])}
    roles = {source_id: "현재 연결된 원문" for source_id in source_ids}
    groups = {}
    for element in elements:
        groups.setdefault((element.get("page"), element.get("origin")), []).append(element)
    for group in groups.values():
        positions = {element.get("element_id"): index for index, element in enumerate(group)}
        for source_id in source_ids:
            if source_id not in positions:
                continue
            position = positions[source_id]
            for index in range(max(0, position - radius), position):
                roles.setdefault(group[index].get("element_id"), "앞 문맥")
            for index in range(position + 1, min(len(group), position + radius + 1)):
                roles.setdefault(group[index].get("element_id"), "뒤 문맥")
            headings = [element for element in group[:position]
                        if "heading" in str(element.get("category", "")).lower()]
            if headings:
                heading_id = headings[-1].get("element_id")
                if heading_id not in source_ids:
                    roles[heading_id] = "절 제목"
    return [{"relation": roles[element.get("element_id")], **element}
            for element in elements if element.get("element_id") in roles]


def _context_label(element):
    category = str(element.get("category", "원문")).replace("_", " ")
    excerpt = " ".join(str(element.get("text", "")).split())
    if len(excerpt) > 74:
        excerpt = excerpt[:71] + "…"
    return f"{element.get('page', '?')}쪽 · {category} · {excerpt}"


def _render_source_context(context):
    if not context:
        st.warning("이 사실에 연결된 원문 문맥을 불러오지 못했습니다.")
        return
    for element in context:
        st.markdown(f"**{element['relation']} · {element.get('page', '?')}쪽**")
        st.write(element.get("text", ""))
        st.caption(f"자료: {ORIGIN_LABELS.get(element.get('origin'), element.get('origin', '확인 필요'))}")


def _active_exclusions(package):
    latest = {}
    for record in package.get("human_evidence_exclusions", []):
        if record.get("exclusion_id"):
            latest[record["exclusion_id"]] = record
    return [record for record in latest.values() if record.get("active")]


def _restore_exclusion(package, record, key_suffix):
    from research_extract_v3 import set_human_evidence_exclusion

    label = "작성에 다시 포함" if record["target_type"] == "fact" else "검토 목록에 복원"
    if st.button(label, key=f"restore_exclusion_{record['exclusion_id']}_{key_suffix}"):
        try:
            set_human_evidence_exclusion(package, record["target_type"], record["fact_id"],
                record["target_id"], "복원", original_measurement=record.get("original_measurement"),
                excluded=False)
            st.rerun()
        except (OSError, ValueError, TypeError) as error:
            st.error(f"복원하지 못했습니다: {error}")


def _render_exclusion_control(package, fact, target_type="fact", measure=None, index=None, key_scope=""):
    exclusions = _active_exclusions(package)
    if target_type == "fact":
        active = next((record for record in exclusions
                       if record.get("target_type") == "fact" and record.get("fact_id") == fact["id"]), None)
        duplicate_decision = next((record for record in package.get("human_duplicate_decisions", [])
            if record.get("decision") == "keep_one" and fact["id"] in record.get("excluded_fact_ids", [])), None)
        target_id = fact["id"]
        original_measurement = None
    else:
        from research_extract_v3 import measurement_review_id
        target_id = measurement_review_id(fact["id"], measure, index)
        active = next((record for record in exclusions
                       if record.get("target_type") == "measurement" and record.get("fact_id") == fact["id"]
                       and record.get("target_id") == target_id
                       and record.get("original_measurement") == measure), None)
        original_measurement = measure
    if active:
        kind = "사실 전체" if target_type == "fact" else "이 측정값"
        st.caption(f"사람이 {kind} 작성에서 제외함 · 사유: {active.get('reason', '미기록')}"
                   + (f" ({active['reason_detail']})" if active.get("reason_detail") else ""))
        _restore_exclusion(package, active, key_scope)
        return
    if target_type == "fact" and duplicate_decision:
        st.caption("사람이 의미 중복으로 작성에서 제외함 · 작성용 유지: "
                   + ", ".join(duplicate_decision.get("kept_fact_ids", [])))
        return

    reasons = {"": "이유를 선택하세요", "duplicate": "다른 근거와 중복", "not_research": "연구 내용이 아님",
               "not_reliable": "원문·출처를 신뢰하기 어려움", "not_needed": "이번 글에 사용할 필요 없음",
               "other": "기타"}
    title = "작성에서 제외" if target_type == "fact" else "이 수치는 사용하지 않음"
    form_key = f"exclude_{target_type}_{fact['id']}_{target_id}_{key_scope}"
    with st.expander(title, expanded=False):
        with st.form(form_key):
            reason_code = st.selectbox("제외 이유", list(reasons), format_func=lambda value: reasons[value],
                                       key=f"{form_key}_reason")
            reason_detail = st.text_input("보충 설명 (선택)", key=f"{form_key}_detail")
            submitted = st.form_submit_button("제외 기록 저장")
        if submitted:
            if not reason_code:
                st.warning("제외 이유를 선택해주세요.")
                return
            if reason_code == "other" and not reason_detail.strip():
                st.warning("기타를 선택한 경우 간단한 이유를 적어주세요.")
                return
            from research_extract_v3 import set_human_evidence_exclusion
            try:
                set_human_evidence_exclusion(package, target_type, fact["id"], target_id,
                    reasons[reason_code], reason_detail, original_measurement=original_measurement)
                st.rerun()
            except (OSError, ValueError, TypeError) as error:
                st.error(f"제외 기록을 저장하지 못했습니다: {error}")


def _render_gate_acceptance(package, blocking):
    st.caption("원문을 확인한 뒤, 이 항목이 비어 있어도 초안을 써도 되면 이유와 함께 진행을 허용할 수 있습니다. "
               "허용한 항목은 경고로 남고, 항목 내용이 바뀌면 다시 확인합니다.")
    with st.form("comprehensive_gate_accept"):
        item = st.selectbox("항목", [row["item"] for row in blocking], format_func=lambda value: value[:120])
        reason = st.text_input("허용 이유", placeholder="원문 확인 결과 초안에 필요 없는 전환 문장임")
        submitted = st.form_submit_button("확인 완료: 작성 진행 허용")
    if submitted:
        if not reason.strip():
            st.warning("허용 이유를 적어주세요.")
            return
        from research_extract_v3 import accept_gate_item
        try:
            accept_gate_item(package, item, reason)
            st.rerun()
        except (OSError, ValueError, TypeError) as error:
            st.error(f"허용 기록을 저장하지 못했습니다: {error}")


def _problem_lines(fact, excluded_measurement_indices=None):
    excluded_measurement_indices = excluded_measurement_indices or set()
    lines = []
    if fact.get("support") != "supported":
        lines.append(f"원문 뒷받침: {SUPPORT.get(fact.get('support'), fact.get('support', '확인 필요'))}")
    if fact.get("support_note"):
        lines.append(fact["support_note"])
    lines.extend(f"문장 수치 확인: {issue}" for issue in fact.get("numeric_issues", []))
    lines.extend(f"최종 대조: {issue}" for issue in fact.get("verification_conflicts", []))
    lines.extend(f"원문에서 빠진 내용: {issue}" for issue in fact.get("verification_missing_support", []))
    if fact.get("verification_pending"):
        lines.append("자동 재검토 응답이 없어 판정을 보류했습니다. 원문이 틀렸다는 뜻은 아닙니다.")
    for index, measure in enumerate(fact.get("rejected_measurements", [])):
        if index in excluded_measurement_indices:
            continue
        lines.append(f"측정값 확인 필요: {measure.get('metric') or '지표 미상'} · "
                     f"{measure.get('value') or '값 없음'} {measure.get('unit', '')} · "
                     f"{measure.get('validation_error', '원문 대조 필요')}")
    return list(dict.fromkeys(lines)) or ["자동 판정에서 작성용 근거로 승인되지 않았습니다. 원문과 대조해 주세요."]


def _render_fact_approval(package, fact, context):
    from research_extract_v3 import approve_human_fact, human_fact_review_id

    fact_id = fact["id"]
    review_id = human_fact_review_id(fact)
    options = {element["element_id"]: element for element in context}
    valid_ids = list(options)
    original_ids = [source.get("element_id") for source in fact.get("sources", [])
                    if source.get("element_id") in options]
    if not valid_ids:
        st.warning("검토할 원문 문맥을 찾을 수 없어 승인 양식을 열 수 없습니다.")
        return
    with st.form(f"human_fact_review_{review_id}"):
        statement = st.text_area("사실을 한 문장으로 정리", value=fact.get("statement", ""),
                                 key=f"{review_id}_statement", height=100)
        conditions = st.text_area("확인된 조건 (한 줄에 하나씩)",
            value="\n".join(fact.get("conditions", [])), key=f"{review_id}_conditions", height=80)
        observations = st.text_area("관찰·비교 내용 (한 줄에 하나씩)",
            value="\n".join(fact.get("observations", [])), key=f"{review_id}_observations", height=80)
        limits = st.text_area("해석상 한계 또는 미확인 사항", value=fact.get("limits", ""),
                              key=f"{review_id}_limits", height=80)
        claim_status = st.selectbox("이 문장은 어떤 내용인가요?", list(V3_STATUSES),
            index=list(V3_STATUSES).index(fact.get("claim_status")) if fact.get("claim_status") in V3_STATUSES else 0,
            format_func=lambda value: V3_STATUSES[value], key=f"{review_id}_status")
        source_origin = st.selectbox("원문은 어떤 자료인가요?", list(ORIGIN_VALUES),
            index=list(ORIGIN_VALUES).index(fact.get("source_origin")) if fact.get("source_origin") in ORIGIN_VALUES else 0,
            format_func=lambda value: ORIGIN_LABELS.get(value, value), key=f"{review_id}_origin")
        selected_sources = st.multiselect("이 사실을 뒷받침하는 원문 문장", valid_ids,
            default=original_ids, format_func=lambda source_id: _context_label(options[source_id]),
            key=f"{review_id}_source_ids")
        confirmed = st.checkbox("위 원문 문맥을 확인했고, 수정한 사실 전체가 원문에 의해 뒷받침됨을 승인합니다.",
                                key=f"{review_id}_confirmed")
        submitted = st.form_submit_button("사실 전체 승인·수정 저장")
    if submitted:
        if not confirmed:
            st.warning("원문을 확인하고 승인 체크를 해야 저장할 수 있습니다.")
            return
        try:
            review = approve_human_fact(package, fact_id, review_id, {
                "statement": statement, "conditions": conditions, "observations": observations,
                "limits": limits, "claim_status": claim_status, "source_origin": source_origin,
                "source_ids": selected_sources})
            st.success(f"{fact_id}의 사실 전체 승인 기록을 저장했습니다. 검토 시각: {review['reviewed_at']}")
        except (OSError, ValueError, TypeError) as error:
            st.error(f"사실을 반영하지 못했습니다: {error}")


def _duplicate_decision_is_current(package, group, decision):
    if decision.get("decision") == "keep_both":
        return True
    writing_ids = set(package.get("writing_fact_ids", []))
    return not (set(decision.get("excluded_fact_ids", [])) & writing_ids)


def _render_semantic_duplicate_review(package):
    review = package.get("semantic_duplicate_review") or {}
    if review.get("status") in (None, "not_reviewed"):
        st.info("이 저장된 추출물에는 의미 중복 에이전트 검토가 없습니다. 아래 버튼으로 후보 묶기와 원문 문맥 검토만 실행할 수 있습니다.")
        if not package.get("source_archive_path") or not package.get("run_dir"):
            st.warning("원문 문맥 자료가 없어 중복 후보 검토를 실행할 수 없습니다.")
            return
        if st.button("저장된 근거의 의미 중복 검토 실행", key="run_saved_semantic_dedup"):
            try:
                from planned_paper import PlannedPaper
                from research_extract_v3 import apply_saved_duplicate_decisions, run_semantic_duplicate_review
                engine = PlannedPaper(base_dir=Path(__file__).resolve().parent)
                with st.spinner("코드가 후보를 묶고 에이전트가 원문 문맥을 대조 중입니다..."):
                    run_semantic_duplicate_review(package, engine)
                    apply_saved_duplicate_decisions(package)
                st.rerun()
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                st.error(f"중복 후보를 검토하지 못했습니다: {error}")
        return

    groups = review.get("groups", [])
    if review.get("status") == "needs_refresh":
        st.info("근거 수정으로 일부 중복 묶음의 재검토가 필요합니다.")
        if st.button("변경된 근거의 중복 검토 갱신", key="refresh_semantic_dedup"):
            try:
                from planned_paper import PlannedPaper
                from research_extract_v3 import run_semantic_duplicate_review, apply_saved_duplicate_decisions
                with st.spinner("수정된 근거의 중복 관계를 확인 중입니다..."):
                    run_semantic_duplicate_review(package, PlannedPaper(base_dir=Path(__file__).resolve().parent))
                    apply_saved_duplicate_decisions(package)
                st.rerun()
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                st.error(f"중복 관계를 갱신하지 못했습니다: {error}")
    st.caption(f"코드 후보 {review.get('candidate_pair_count', 0)}쌍 중 "
               f"{review.get('grouped_candidate_pair_count', review.get('candidate_pair_count', 0))}쌍을 "
               f"{len(groups)}개 묶음으로 구성했습니다. "
               f"미배정 또는 재검토가 필요한 후보: {review.get('unassigned_candidate_pair_count', 0)}쌍. "
               f"에이전트 검토 상태: {review.get('status', '확인 필요')}.")
    st.caption("후보 묶기는 중복 가능성을 찾는 단계입니다. 자동으로 근거를 제거하지 않으며, 에이전트 판단도 사람이 선택하기 전에는 작성 입력을 바꾸지 않습니다.")
    for error in review.get("review_errors", []):
        st.warning(error)
    source_path = package.get("source_archive_path", "")
    try:
        modified_ns = Path(source_path).stat().st_mtime_ns
    except (OSError, TypeError):
        modified_ns = 0
    elements = _load_source_elements(source_path, modified_ns)
    facts_by_id = {fact["id"]: fact for fact in package.get("items", [])}
    decisions = {record.get("group_id"): record for record in package.get("human_duplicate_decisions", [])}
    writing_ids = set(package.get("writing_fact_ids", []))
    manually_excluded = {record.get("fact_id") for record in package.get("human_evidence_exclusions", [])
                         if record.get("active") and record.get("target_type") == "fact"}
    with st.expander(f"의미상 중복 후보 검토 ({len(groups)}개 묶음)", expanded=bool(groups)):
        if not groups:
            st.caption("코드 후보 필터가 찾은 항목이 없습니다. 이것만으로 문서 전체에 의미상 중복이 없다고 보장하지는 않습니다.")
        for group in groups:
            fact_ids = group.get("fact_ids", [])
            members = [facts_by_id[fact_id] for fact_id in fact_ids if fact_id in facts_by_id]
            relation = group.get("relation", "uncertain")
            title = f"{RELATION_LABELS.get(relation, '판정 대기')} · {len(members)}개 근거"
            saved = decisions.get(group.get("group_id"))
            resolved = bool(saved and _duplicate_decision_is_current(package, group, saved))
            if resolved:
                title += " · 사람 검토 완료"
            with st.expander(title, expanded=not resolved):
                for edge in group.get("candidate_edges", []):
                    if edge.get("shared_source_ids"):
                        st.caption("같은 원문 요소를 공유합니다.")
                    elif edge.get("exact_normalized_statement"):
                        st.caption("정규화한 문장이 같습니다.")
                if group.get("review_status") == "reviewed":
                    st.write(f"에이전트 판정: **{RELATION_LABELS.get(relation, relation)}** · 신뢰도 {group.get('confidence', '확인 필요')}")
                    st.write(group.get("reason", ""))
                    if group.get("recommended_keep_fact_id"):
                        st.info("에이전트가 대표 후보로 제안: " + group["recommended_keep_fact_id"])
                else:
                    st.warning(group.get("reason", "에이전트 판정을 받지 못했습니다. 둘 다 유지하거나 직접 검토하세요."))

                for start in range(0, len(members), 2):
                    columns = st.columns(2)
                    for column, fact in zip(columns, members[start:start + 2]):
                        with column:
                            status = "현재 작성용" if fact["id"] in writing_ids else "현재 작성 제외"
                            st.markdown(f"**{fact['id']} · {KINDS.get(fact.get('kind'), fact.get('kind'))} · {status}**")
                            st.write(fact.get("statement", ""))
                            if fact.get("limits"):
                                st.caption("한계: " + fact["limits"])
                            for limitation in fact.get("evidence_limitations", []):
                                st.caption("원문에 남은 한계: " + limitation)
                            if fact.get("observations"):
                                st.write("관찰: " + " / ".join(fact["observations"]))
                            if fact.get("parameters"):
                                st.write("설정: " + " / ".join(f"{value.get('name')}={value.get('value')}"
                                                           for value in fact["parameters"]))
                            if fact.get("rejected_measurements"):
                                st.warning("확인되지 않은 측정값이 남아 있습니다. 중복 처리 전에 측정 내용도 확인하세요.")
                            st.caption(f"주장: {V3_STATUSES.get(fact.get('claim_status'), fact.get('claim_status'))} · "
                                       f"뒷받침: {SUPPORT.get(fact.get('support'), fact.get('support'))}")
                            if fact.get("conditions"):
                                st.write("조건: " + " / ".join(fact["conditions"]))
                            if fact.get("measurements"):
                                st.write("측정: " + " / ".join(
                                    f"{m.get('metric')} {m.get('value')} {m.get('unit')} ({m.get('condition')})"
                                    for m in fact["measurements"]))
                            with st.expander(f"{fact['id']}의 원문 문맥", expanded=False):
                                _render_source_context(_context_for_fact(elements, fact))

                if resolved:
                    kept = saved.get("kept_fact_ids", [])
                    if saved.get("decision") == "keep_both":
                        st.success("사람 결정: 두 근거를 모두 유지")
                    else:
                        st.success("사람 결정: " + ", ".join(kept) + "만 작성용으로 유지")
                    revise = st.checkbox("사람 결정을 수정", key=f"{group['group_id']}_revise")
                    if not revise:
                        continue
                eligible = [fact_id for fact_id in fact_ids if fact_id in facts_by_id
                            and writing_eligible(facts_by_id[fact_id]) and fact_id not in manually_excluded]
                decision_options = ["keep_both", "keep_one"] if eligible else ["keep_both"]
                default_decision = saved.get("decision") if saved else None
                if default_decision not in decision_options:
                    default_decision = "keep_one" if group.get("relation") in ("duplicate", "subsumes") and eligible else "keep_both"
                with st.form(f"semantic_duplicate_decision_{group['group_id']}"):
                    decision = st.radio("작성용으로 어떻게 처리할까요?", decision_options,
                        index=decision_options.index(default_decision),
                        format_func=lambda value: "둘 다 유지" if value == "keep_both" else "하나만 유지",
                        key=f"{group['group_id']}_decision")
                    keep_fact_id = None
                    if eligible:
                        suggested = ((saved.get("kept_fact_ids") or [group.get("recommended_keep_fact_id")])[0]
                                     if saved and saved.get("decision") == "keep_one"
                                     else group.get("recommended_keep_fact_id"))
                        default_index = eligible.index(suggested) if suggested in eligible else 0
                        keep_fact_id = st.selectbox("대표로 유지할 작성용 근거", eligible,
                            index=default_index, format_func=lambda value: f"{value} · {facts_by_id[value]['statement'][:70]}",
                            key=f"{group['group_id']}_keep")
                    confirmed = st.checkbox("원문 문맥을 확인했고 이 결정을 적용합니다.",
                                            key=f"{group['group_id']}_confirmed")
                    submitted = st.form_submit_button("사람 결정 저장")
                if submitted:
                    if not confirmed:
                        st.warning("원문 문맥 확인 체크 후 저장할 수 있습니다.")
                        continue
                    try:
                        from research_extract_v3 import resolve_semantic_duplicate_group
                        resolve_semantic_duplicate_group(package, group["group_id"], decision, keep_fact_id)
                        st.rerun()
                    except (OSError, ValueError, TypeError) as error:
                        st.error(f"중복 결정을 저장하지 못했습니다: {error}")


def _render_measurement_approval(package, fact, measure, index, context):
    from research_extract_v3 import approve_rejected_measurement, measurement_review_id

    fact_id = fact["id"]
    review_id = measurement_review_id(fact_id, measure, index)
    sources = {source.get("element_id"): source for source in fact.get("sources", [])
               if source.get("element_id")}
    if fact_id not in package.get("writing_fact_ids", []):
        st.info("이 사실 전체가 아직 작성용으로 승인되지 않았습니다. 위의 ‘사실 전체 승인·수정’에서 원문을 먼저 확인하세요.")
        return
    valid_source_ids = list(sources)
    default_source_ids = [key for key in measure.get("element_ids", []) if key in sources]
    labels = {element.get("element_id"): element for element in context}
    with st.form(f"human_measurement_review_{review_id}"):
        metric = st.text_input("무엇을 측정했나요?", value=str(measure.get("metric", "")), key=f"{review_id}_metric")
        value = st.text_input("원문에 적힌 값", value=str(measure.get("value", "")), key=f"{review_id}_value")
        value_kind = st.selectbox("값 형태", ["scalar", "range"],
            index=1 if measure.get("value_kind") == "range" else 0, key=f"{review_id}_kind",
            format_func=lambda kind: "범위" if kind == "range" else "단일값")
        unit = st.text_input("단위", value=str(measure.get("unit", "")), key=f"{review_id}_unit")
        condition = st.text_input("어떤 조건에서 측정했나요?", value=str(measure.get("condition", "")), key=f"{review_id}_condition")
        element_ids = st.multiselect("이 값을 직접 뒷받침하는 원문", valid_source_ids,
            default=default_source_ids,
            format_func=lambda source_id: _context_label(labels[source_id]) if source_id in labels else
                f"{sources[source_id].get('page', '?')}쪽 · 연결된 원문 문장",
            key=f"{review_id}_sources")
        confirmed = st.checkbox("원문을 직접 확인했고 이 측정값을 승인합니다", key=f"{review_id}_confirmed")
        submitted = st.form_submit_button("측정값 승인·수정")
    if submitted:
        if not confirmed:
            st.warning("원문 확인 체크 후 반영할 수 있습니다.")
            return
        try:
            approve_rejected_measurement(package, fact_id, review_id, {
                "metric": metric, "value": value, "value_kind": value_kind,
                "unit": unit, "condition": condition, "element_ids": element_ids})
            st.success(f"{fact_id} 측정값을 승인 기록에 저장했습니다.")
        except (OSError, ValueError, TypeError) as error:
            st.error(f"측정값을 반영하지 못했습니다: {error}")


def _render_recovery_controls(package):
    report = package.get("evidence_recovery") or {}
    from research_recovery import VERSION as RECOVERY_VERSION
    if report and report.get("version") != RECOVERY_VERSION:
        st.info("아래 결과는 이전 복구 기준으로 검토됐습니다. 복구 버튼을 누르면 개선된 기준으로 미확인 항목을 다시 검토합니다.")
    st.caption("미확인 항목을 승인된 근거와 먼저 비교하고, 나머지는 원문 문맥으로 수정한 뒤 별도 검증합니다.")
    if package.get("run_dir") and package.get("source_archive_path"):
        if st.button("미확인 근거 복구·중복 연결 검토", key="recover_pending_evidence"):
            try:
                from planned_paper import PlannedPaper
                from research_extract_v3 import run_unconfirmed_recovery
                with st.spinner("중복 관계·문제 부분을 검토하고 수정된 페이지의 수집 대장을 재확인 중입니다..."):
                    run_unconfirmed_recovery(package, PlannedPaper(base_dir=Path(__file__).resolve().parent))
                st.rerun()
            except (OSError, RuntimeError, ValueError, TypeError) as error:
                st.error(f"미확인 근거를 재검토하지 못했습니다: {error}")
    if not report:
        return
    counts = report.get("counts", {})
    st.write(f"마지막 자동 검토: 복구 {counts.get('repaired', 0)}개 · 중복 연결 제안 "
             f"{counts.get('duplicate_confirmation', 0)}개 · 미해결 {counts.get('unresolved', 0)}개")
    from research_recovery import unresolved_reason_summary
    reasons = unresolved_reason_summary(report)
    if reasons:
        with st.expander("미해결 항목이 남은 이유", expanded=False):
            for reason, count in reasons:
                st.write(f"{reason}: {count}개")
    for error in report.get("errors", []) + report.get("ledger_recheck_errors", []):
        st.warning(error)
    with st.expander("자동 복구 전후와 검토 이유", expanded=False):
        for record in report.get("records", []):
            if record.get("status") != "repaired":
                continue
            st.markdown(f"**{record['fact_id']}**")
            columns = st.columns(2)
            columns[0].write("수정 전: " + record["original"]["statement"])
            columns[1].write("수정 후: " + record["applied"]["statement"])
            st.caption(record.get("proposal", {}).get("reason", ""))
            for limitation in record["applied"].get("evidence_limitations", []):
                st.write("원문 한계: " + limitation)


def _render_measurement_review(package):
    fact_reviews = package.get("human_fact_reviews", [])
    measurement_reviews = package.get("human_measurement_reviews", [])
    exclusions = _active_exclusions(package)
    if fact_reviews or measurement_reviews or exclusions:
        with st.expander(f"사람 검토 기록 (승인 {len(fact_reviews) + len(measurement_reviews)}건 · 제외 {len(exclusions)}건)", expanded=False):
            for review in fact_reviews:
                st.markdown(f"**사실 전체 승인 · {review['fact_id']}**")
                st.write(review["reviewed_fact"]["statement"])
                st.caption(f"원문 확인 {len(review['reviewed_fact']['source_ids'])}개 · {review['reviewed_at']}")
            for review in measurement_reviews:
                approved = review["approved_measurement"]
                st.markdown(f"**측정값 승인 · {review['fact_id']} · {approved['metric']}**")
                st.write(f"{review['original_measurement'].get('value', '값 없음')} → {approved['value']} {approved['unit']}")
                st.caption(f"검토 시각: {review['reviewed_at']}")
            for record in exclusions:
                if record["target_type"] == "fact":
                    st.markdown(f"**작성에서 제외 · {record['fact_id']}**")
                    fact = next((item for item in package.get("items", []) if item.get("id") == record["fact_id"]), None)
                    if fact:
                        st.write(fact.get("statement", ""))
                else:
                    measure = record.get("original_measurement") or {}
                    st.markdown(f"**측정값 사용 안 함 · {record['fact_id']} · {measure.get('metric', '지표 미상')}**")
                    st.write(f"{measure.get('value') or '값 없음'} {measure.get('unit', '')} · {measure.get('condition', '')}")
                st.caption(f"제외 이유: {record.get('reason', '미기록')}"
                           + (f" · {record['reason_detail']}" if record.get("reason_detail") else ""))
                _restore_exclusion(package, record, "audit")
    for warning in package.get("human_review_warnings", []):
        st.warning(warning)

    from research_extract_v3 import human_excluded_measurement_indices

    excluded_fact_ids = {record["fact_id"] for record in exclusions if record.get("target_type") == "fact"}
    excluded_fact_ids.update(fact_id for record in package.get("human_duplicate_decisions", [])
                             if record.get("decision") == "keep_one"
                             for fact_id in record.get("excluded_fact_ids", []))
    excluded_measurements = human_excluded_measurement_indices(package)
    pending = [item for item in package.get("items", []) if item["id"] not in excluded_fact_ids
               and (len(item.get("rejected_measurements", [])) > len(excluded_measurements.get(item["id"], set()))
                    or item["id"] not in package.get("writing_fact_ids", []))]
    if not pending:
        if fact_reviews or measurement_reviews or exclusions:
            st.caption("확인 대상으로 남은 사실·측정값이 없습니다.")
        return

    source_path = package.get("source_archive_path", "")
    try:
        modified_ns = Path(source_path).stat().st_mtime_ns
    except (OSError, TypeError):
        modified_ns = 0
    elements = _load_source_elements(source_path, modified_ns)
    from research_extract_v3 import writing_eligible
    from research_recovery import current_duplicate_suggestions
    duplicate_suggestions = current_duplicate_suggestions(package)
    recovery_records = {record["fact_id"]: record for record in
                        package.get("evidence_recovery", {}).get("records", [])}

    pending_by_page = {}
    for item in pending:
        pages = [source.get("page") for source in item.get("sources", []) if source.get("page") is not None]
        page = min(pages) if pages else 0
        pending_by_page.setdefault(page, []).append(item)
    page_options = sorted(pending_by_page)
    page = st.selectbox("검토할 원문 페이지", page_options,
        format_func=lambda number: f"{number}쪽 · {len(pending_by_page[number])}개 사실" if number else "페이지 확인 필요",
        key="human_review_page")
    facts = sorted(pending_by_page[page], key=lambda item: item["id"])
    st.caption("이 화면은 자동 판정의 구조화 오류를 사람이 원문으로 바로잡는 곳입니다. 미해결 원문 수집 대장은 별도로 남으며, 사실 승인만으로 본문 생성 보류가 해제되지는 않습니다.")
    page_count = max(1, (len(facts) + 9) // 10)
    batch = st.selectbox("이 페이지의 검토 묶음", range(1, page_count + 1),
        format_func=lambda number: f"{number}/{page_count} · 항목 {((number - 1) * 10) + 1}–{min(number * 10, len(facts))}",
        key=f"human_review_batch_{page}")
    chosen = facts[(batch - 1) * 10:batch * 10]
    st.caption("원문 ID보다 문장의 의미를 먼저 보여줍니다. 각 사실을 열어 앞뒤 문맥을 읽고, 필요한 경우 요약·조건·한계와 연결 원문을 고친 뒤 승인하세요.")
    for item in chosen:
        fact_id = item["id"]
        excluded_indices = excluded_measurements.get(fact_id, set())
        measurements = [(index, measure) for index, measure in enumerate(item.get("rejected_measurements", []))
                        if index not in excluded_indices]
        status = "작성용 승인됨 · 측정값 확인 필요" if writing_eligible(item) else "사실 전체 확인 필요"
        title = f"{item.get('kind', '근거')} · {V3_STATUSES.get(item.get('claim_status'), item.get('claim_status', '상태 확인'))} · {status}"
        with st.expander(title, expanded=False):
            st.markdown("**현재 사실 요약**")
            st.write(item.get("statement", ""))
            duplicate = duplicate_suggestions.get(fact_id)
            if duplicate:
                representative = next(fact for fact in package["items"]
                                      if fact["id"] == duplicate["representative_fact_id"])
                st.info("이미 승인된 대표 근거에 전체 내용이 포함된 것으로 재검토됐습니다.")
                st.write("대표 근거: " + representative["statement"])
                st.caption("대표 근거의 한계: " + representative.get("limits", ""))
                with st.expander("대표 근거의 원문과 문맥", expanded=False):
                    _render_source_context(_context_for_fact(elements, representative))
                st.caption(duplicate.get("verification", {}).get("note", ""))
                confirmed = st.checkbox("두 근거와 원문을 확인했고 대표 근거로 묶습니다.", key=f"{fact_id}_cover_confirmed")
                if st.button("대표 근거에 묶고 중복 항목 제외", key=f"{fact_id}_cover_apply"):
                    if confirmed:
                        try:
                            from research_extract_v3 import confirm_recovered_duplicate
                            from planned_paper import PlannedPaper
                            with st.spinner("중복 결정을 저장하고 해당 원문의 수집 대장을 재확인 중입니다..."):
                                confirm_recovered_duplicate(package, fact_id,
                                    PlannedPaper(base_dir=Path(__file__).resolve().parent))
                            st.rerun()
                        except (OSError, RuntimeError, ValueError, TypeError) as error:
                            st.error(f"중복 결정을 반영하지 못했습니다: {error}")
                    else:
                        st.warning("원문 확인 체크 후 적용할 수 있습니다.")
            elif fact_id in recovery_records:
                record = recovery_records[fact_id]
                st.caption("자동 재검토: " + record.get("reason", record.get("proposal", {}).get("reason", "미해결")))
            for line in _problem_lines(item, excluded_indices):
                st.warning(line)
            context = _context_for_fact(elements, item)
            with st.expander("원문과 앞뒤 문맥 보기", expanded=True):
                _render_source_context(context)
            st.markdown("**사실 전체를 확인·수정**")
            _render_fact_approval(package, item, context)
            _render_exclusion_control(package, item, key_scope="review")
            for index, measure in measurements:
                st.markdown(f"**측정 항목 {index + 1} · {measure.get('metric') or '지표 확인 필요'}**")
                st.write(f"현재 추출: {measure.get('value') or '값 없음'} {measure.get('unit', '')} · "
                         f"조건: {measure.get('condition') or '조건 확인 필요'}")
                st.caption("자동 검사: " + measure.get("validation_error", "원문 대조 필요"))
                _render_measurement_approval(package, item, measure, index, context)
                _render_exclusion_control(package, item, "measurement", measure, index, "review")

def render_research_evidence(package):
    stats = package["diagnostics"]
    with st.expander("연구 근거 자동 추출 결과", expanded=True):
        st.caption("자동 분류와 원문 대조 결과입니다. 독립적인 사실 검증은 아니며 원문 해석·비교 조건은 저자 확인이 필요합니다.")
        st.write(f"후보 {stats['candidates']}개 · 측정값 {stats['measurements']}개 · 작성용 {stats['writing_facts']}개")
        _render_recovery_controls(package)
        _render_measurement_review(package)
        _render_semantic_duplicate_review(package)
        structured_tables = package.get("structured_tables", [])
        if structured_tables:
            st.write(f"표 구조화: {stats.get('complete_structured_tables', 0)}/{stats.get('structured_tables', len(structured_tables))}개 완전 보존")
            st.caption(f"작성 계획에서 선택 가능: {stats.get('research_tables', 0)}개 표")
            with st.expander("원문 표의 행·셀 보존 결과", expanded=False):
                st.caption("표의 셀 문자열을 원문 순서대로 분리한 보존용 데이터입니다. OCR 표기는 원문 이미지와 별도 대조가 필요합니다.")
                for table in structured_tables:
                    status = "완전" if table.get("complete") else "일부 또는 파싱 확인 필요"
                    st.markdown(f"**{table['table_id']} · {status} · {len(table.get('rows', []))}행**")
                    st.caption(f"원문 {table['page']}쪽 · {table['source_element_id']} · {table['origin']}")
                    st.json({"headers": table.get("headers", []), "rows": table.get("rows", []),
                             "parse_errors": table.get("parse_errors", []),
                             "unparsed_lines": table.get("unparsed_lines", [])}, expanded=False)
        if completion := package.get("completion"):
            st.write(f"원문 대조: {completion['pages_reviewed']}/{completion['source_pages']}쪽 · {completion['elements_reviewed']}/{completion['source_elements']}개 요소")
            st.caption("모든 요소를 검토했다는 기록입니다. 문서 전체의 의미가 100% 정확하게 추출됐다는 보증은 아닙니다.")
            gate = completion.get("gate")
            if not completion["ready_for_drafting"]:
                if gate:
                    st.warning(f"작성을 막는 원문 항목 {len(gate['blocking'])}개가 남아 본문 생성을 보류합니다. "
                               f"경고 {len(gate['warnings'])}개는 생성을 막지 않습니다.")
                else:
                    st.warning("누락·판독·원문 뒷받침 미해결 항목이 있어 본문 생성을 보류합니다.")
            elif gate and gate["warnings"]:
                st.info(f"본문 생성 가능. 검토 권장 경고 {len(gate['warnings'])}개가 있습니다.")
            if gate:
                with st.expander(f"작성을 막는 항목 {len(gate['blocking'])}개", expanded=False):
                    for row in gate["blocking"]:
                        st.write(f"[{GATE_CATEGORIES.get(row['category'], row['category'])}] {row['item']}")
                    if gate["blocking"]:
                        _render_gate_acceptance(package, gate["blocking"])
                with st.expander(f"경고 항목 {len(gate['warnings'])}개 (생성을 막지 않음)", expanded=False):
                    for row in gate["warnings"]:
                        reason = f" · 허용 사유: {row['reason']}" if row.get("reason") else ""
                        st.write(f"[{GATE_CATEGORIES.get(row['category'], row['category'])}] {row['item']}{reason}")
            with st.expander("원문별 수집 대장과 미해결 항목", expanded=False):
                for issue in completion["unresolved_source_items"]:
                    st.write(issue)
                st.json(package.get("element_ledger", {}), expanded=False)
            st.download_button("원문 수집 대장 JSON 저장", json.dumps({"completion": completion, "element_ledger": package.get("element_ledger", {}),
                                                                         "structured_tables": structured_tables}, ensure_ascii=False, indent=2),
                               file_name="research_source_coverage.json", mime="application/json")
        if stats.get("rejected_measurements"):
            st.warning(f"확인 필요 측정 항목 {stats['rejected_measurements']}개를 별도로 분리했습니다. 연구 사실의 뒷받침은 진술 전체로 검사합니다.")
        if stats.get("human_excluded_fact_ids") or stats.get("human_excluded_measurements"):
            st.caption(f"사람이 작성에서 제외한 근거 {len(stats.get('human_excluded_fact_ids', []))}개 · "
                       f"측정값 {stats.get('human_excluded_measurements', 0)}개")
        if stats["excluded_selected_ids"]:
            st.info("원문 뒷받침·수치·출처 귀속 등의 확인이 필요해 작성 입력에서 제외: " + ", ".join(stats["excluded_selected_ids"]))
        kind = st.selectbox("근거 유형", ["전체", *KINDS], format_func=lambda key: KINDS.get(key, key))
        status = st.selectbox("주장 강도", ["전체", *V3_STATUSES], format_func=lambda key: V3_STATUSES.get(key, key))
        filtered = [item for item in package["items"] if (kind == "전체" or item["kind"] == kind)
                    and (status == "전체" or item["claim_status"] == status)]
        page = st.selectbox("목록 페이지", range(1, max(1, (len(filtered) + 24) // 25) + 1))
        start = (page - 1) * 25
        st.caption(f"필터 결과 {len(filtered)}개 · 현재 {start + 1 if filtered else 0}~{min(start + 25, len(filtered))}개 표시")
        from research_extract_v3 import human_excluded_measurement_indices
        excluded_measurements_by_fact = human_excluded_measurement_indices(package)
        for item in filtered[start:start + 25]:
            st.markdown(f"**{item['id']} · {KINDS[item['kind']]} · {V3_STATUSES[item['claim_status']]}**")
            st.write(item["statement"])
            _render_exclusion_control(package, item, key_scope="evidence_list")
            if item.get("writing_role") == "context_only":
                st.caption("사용 범위: 질문·계획·해석·인용 조언의 문맥 설명 전용")
            st.caption(f"{SUPPORT[item['support']]}: {item['support_note']}")
            if item.get("verification_pending"):
                st.caption("검토 응답을 받지 못해 보류했습니다. 원문 내용이 틀렸다는 판정은 아닙니다.")
            if item["conditions"]:
                st.write("조건: " + " / ".join(item["conditions"]))
            if item.get("source_origin"):
                st.caption("자료 성격: " + ORIGIN_LABELS.get(item["source_origin"], item["source_origin"]))
            for parameter in item.get("parameters", []):
                st.write(f"설정: {parameter['name']} = {parameter['value']} ({parameter['value_kind']})")
            for observation in item.get("observations", []):
                st.write("관찰·비교: " + observation)
            for issue in item.get("numeric_issues", []):
                st.caption("문장 수치 검사: " + issue)
            for measure in item["measurements"]:
                st.write(f"측정: {measure['metric']} = {measure['value']} {measure['unit']} · {measure['condition']}")
                st.caption("측정값 출처: " + ", ".join(measure["element_ids"]))
                if any(review["fact_id"] == item["id"] and review["approved_measurement"] == measure
                       for review in package.get("human_measurement_reviews", [])):
                    st.caption("사람이 원문을 확인해 승인·수정한 값")
            excluded_indices = excluded_measurements_by_fact.get(item["id"], set())
            for index, measure in enumerate(item.get("rejected_measurements", [])):
                if index in excluded_indices:
                    st.caption(f"사람이 사용하지 않기로 한 측정값: {measure.get('metric', '지표 미상')} = "
                               f"{measure.get('value') or '값 없음'} {measure.get('unit', '')}")
                else:
                    st.caption(f"확인 필요 수치 (작성 제외): {measure.get('metric', '지표 미상')} = "
                               f"{measure.get('value') or '값 없음'} {measure.get('unit', '')}")
            st.caption("해석 한계: " + item["limits"])
            for source in item["sources"]:
                st.caption(f"원문 {source['page']}쪽 · {source['element_id']}")
                st.code(source["quote"], language=None)
        st.download_button("추출 근거 JSON 저장", json.dumps(package, ensure_ascii=False, indent=2),
                           file_name="research_evidence_auto.json", mime="application/json")
        st.download_button("추출 근거 Markdown 저장", render_evidence(package),
                           file_name="research_evidence_auto.md", mime="text/markdown")
