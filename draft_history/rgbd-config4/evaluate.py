"""Offline evaluation of the saved RGBD Config 4 run; never calls an API."""
import hashlib
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from pypdf import PdfReader
from golden_evaluation import (
    EVALUATION_VERSION, evaluate_outline, fraction, normalize_title,
    percent, ratio, title_parts, verify_source,
)
from studio_json_evaluation import decode_document, explicit_outline

REFERENCE_PATH = BASE / 'evaluation/golden/rgbd-reference.json'
PDF = BASE / 'golden sample/research_revies.pdf'
REFERENCE = json.loads(REFERENCE_PATH.read_text(encoding='utf-8'))
SOURCE_HASH = verify_source(REFERENCE, PDF)
RESULTS = BASE / 'evaluation/golden/results'
PREDICTIONS = BASE / 'evaluation/golden/predictions'
PAGES = [page.extract_text() for page in PdfReader(PDF).pages]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fragment_check(evidence):
    checks = []
    for entry in evidence:
        quote = entry.get('quote')
        page = entry.get('page')
        if not isinstance(quote, str) or not quote.strip():
            continue
        quote = re.sub(r'【†\d+】', '', quote)
        fragments = [normalize_title(x) for x in re.split(r'\.{3}|…+', quote) if normalize_title(x)]
        exists = isinstance(page, int) and 1 <= page <= len(PAGES)
        text = normalize_title(PAGES[page - 1]) if exists else ''
        checks.append({'evidence_id': entry.get('evidence_id'), 'page': page,
                       'normalized_fragments_present': bool(fragments) and all(x in text for x in fragments)})
    return {'score': fraction(sum(x['normalized_fragments_present'] for x in checks), len(checks)),
            'policy': 'NFKC/case/punctuation/whitespace normalization; ellipsis-separated fragments on declared page only; not semantic entailment',
            'checks': checks}


def assess(stage):
    path = RUN / (stage + '.md')
    text = path.read_text(encoding='utf-8')
    try:
        document, syntax = decode_document(text, diagnostic_citations=True, diagnostic_controls=True)
    except json.JSONDecodeError as exc:
        # Read intact root arrays only. Do not strip tokens or repair the invalid object.
        document = {}
        for key in ('sections', 'evidence', 'structure_coverage'):
            match = re.search(r'(?m)^  "' + key + r'"\s*:\s*', text)
            if match is None:
                raise ValueError('Missing independently readable root field: ' + key) from exc
            document[key], _ = json.JSONDecoder().raw_decode(text, match.end())
        if not isinstance(document['sections'], list) or not isinstance(document['evidence'], list):
            raise ValueError('Diagnostic extraction requires unchanged strict JSON arrays.') from exc
        tail = re.search(r'}(\s*(?:【†\d+】\s*)*)$', text)
        syntax = {'strict_valid': False, 'json_object_strict_valid': False,
                  'error': {'message': exc.msg, 'line': exc.lineno, 'column': exc.colno, 'position': exc.pos},
                  'diagnostic_control_characters': False, 'diagnostic_trailing_citations': False,
                  'trailing_citation_count': len(re.findall(r'【†\d+】', tail.group(1))) if tail else 0,
                  'all_citation_marker_count': len(re.findall(r'【†\d+】', text)),
                  'diagnostic_isolated_arrays': True,
                  'array_extraction_policy': 'Strict raw_decode of original sections/evidence root arrays; no response repair; full object remains invalid.'}
    if stage == 'style':
        return {'syntax': syntax, 'keys': list(document), 'raw_file': str(path.relative_to(BASE))}
    derived = explicit_outline(document)
    report = evaluate_outline(derived, REFERENCE)
    for key in ('role_accuracy_on_matched', 'fully_correct_item_recall'):
        report['metrics'][key] = fraction(0, 0)
    for row in report['matches']:
        row.update(predicted_role=None, role_correct=None, fully_correct=None)
    is_sections = 'sections' in document
    items = document['sections' if is_sections else 'headings']
    title_key = 'title' if is_sections else 'heading_text'
    number_key = 'number' if is_sections else 'section_number'
    by_title = {item[title_key]: item for item in items}
    level_checks, number_checks = [], []
    for row in report['matches']:
        item = by_title[row['prediction_title']]
        expected_level = len(row['reference_id'].split('.'))
        level_checks.append({'reference_id': row['reference_id'], 'expected': expected_level,
                             'actual': item.get('level'), 'correct': item.get('level') == expected_level})
        number_checks.append({'reference_id': row['reference_id'], 'actual': item.get(number_key),
                              'correct': item.get(number_key) == row['reference_id']})
    levels = fraction(sum(x['correct'] for x in level_checks), len(level_checks))
    numbers = fraction(sum(x['correct'] for x in number_checks), len(number_checks))
    evidence = document.get('evidence', []) if is_sections else items
    links = [link for item in items for link in item.get('evidence_ids', [])]
    evidence_ids = {item.get('evidence_id') for item in document.get('evidence', [])}
    link_check = fraction(sum(link in evidence_ids for link in links), len(links))
    quote_check = fragment_check(evidence)
    fields = ('id', 'title', 'number', 'level', 'parent_id', 'evidence_ids') if is_sections else (
        'evidence_id', 'heading_text', 'section_number', 'level', 'parent_evidence_id', 'quote', 'page')
    projection = {'document_title': document.get('document_title'),
                  'sections' if is_sections else 'headings': [{k: item[k] for k in fields if k in item} for item in items]}
    if is_sections:
        projection['evidence'] = [{k: item[k] for k in ('evidence_id', 'page') if k in item} for item in evidence]
    projection_path = PREDICTIONS / f'rgbd-studio-config4-{stage}-projection.json'
    save(projection_path, projection)
    report.update(evaluation_version=EVALUATION_VERSION, source_file=REFERENCE['source_file'],
                  source_sha256=SOURCE_HASH, reference_sha256=hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest(),
                  pdf_page_count=len(PAGES), prediction_provenance='studio_agent_config4_' + stage,
                  prediction_path=projection_path.relative_to(BASE).as_posix(),
                  prediction_sha256=hashlib.sha256(projection_path.read_bytes()).hexdigest(),
                  native_text_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  reference_items=REFERENCE['items'], annotation_provenance=REFERENCE['annotation_provenance'],
                  scope=REFERENCE['scope'], matching_policy=REFERENCE['matching_policy'],
                  json_syntax=syntax, native_level_accuracy_on_matched=levels,
                  native_number_field_accuracy_on_matched=numbers,
                  native_level_checks=level_checks, native_number_checks=number_checks,
                  missing_evidence_links=derived['missing_evidence_links'],
                  evidence_link_validity=link_check, quoted_fragment_page_matches=quote_check,
                  role_assessment='N/A: no role labels provided; placeholder other is not scored',
                  self_reported_structure_coverage_not_used_as_score=document.get('structure_coverage'),
                  application_inputs_changed=False)
    save(RESULTS / f'rgbd-studio-config4-{stage}.json', report)
    return {'syntax': syntax, 'report': report}


def assess_parse():
    job = json.loads((RUN / 'job-response.json').read_text(encoding='utf-8'))
    step = next(x for x in job['output'] if x.get('model') == 'step_1_parse')
    parsed = json.loads(step['content'][0]['text'])
    checks = []
    for item in REFERENCE['items']:
        target = normalize_title(item['title'])
        matches = [e for e in parsed['elements'] if e.get('page') == item['page']
                   and target in normalize_title(e.get('content', {}).get('text', ''))]
        checks.append({'reference_id': item['id'], 'page': item['page'],
                       'present_on_start_page': bool(matches),
                       'element_categories': [e.get('category') for e in matches],
                       'heading_category_present': any(str(e.get('category', '')).startswith('heading') for e in matches)})
    return {'model': parsed.get('model'), 'usage': parsed.get('usage'),
            'heading_text_start_page_presence': fraction(sum(x['present_on_start_page'] for x in checks), len(checks)),
            'heading_category_start_page_presence': fraction(sum(x['heading_category_present'] for x in checks), len(checks)),
            'checks': checks,
            'scope': 'Title fragment existence and element category on reference start pages only; not all-page OCR or reading-order accuracy.'}


def main():
    completion = json.loads((RUN / 'completion.json').read_text(encoding='utf-8'))
    state = json.loads((RUN / 'state.json').read_text(encoding='utf-8'))
    if completion['status'] != 'completed':
        raise ValueError('The workflow did not complete; do not score empty responses.')
    outputs = {stage: assess(stage) for stage in ('structure', 'style', 'review')}
    baseline = json.loads((RESULTS / 'rgbd-legacy-baseline.json').read_text(encoding='utf-8'))
    metadata = {**completion, 'source_sha256': SOURCE_HASH,
                'agent_fingerprint_sha256': hashlib.sha256(state['agent_id'].encode()).hexdigest(),
                'agent_matches_user_request': state['agent_id'] == 'agt_ZodDrwGVgFVrFBh6W8UiSY',
                'usage_note': 'Zero token counts are the API-returned values, not a verified cost measurement.',
                'reference_sha256': hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest(),
                'local_raw_response_directory': RUN.relative_to(BASE).as_posix(),
                'json_syntax': {stage: result['syntax'] for stage, result in outputs.items()},
                'raw_document_parse_checks': assess_parse(),
                'application_inputs_changed': False}
    save(RESULTS / 'rgbd-studio-config4-run-metadata.json', metadata)
    structure, review = outputs['structure']['report'], outputs['review']['report']
    lines = ['# RGBD Studio Config 4 구조 추출 평가', '',
             '## 실행 조건', '',
             '- PDF: `research_revies.pdf`, 16페이지. 기존 원문 기준표 23개를 변경하지 않고 사용했다.',
             '- 같은 구조 Agent의 Config 4를 명시했고, 원본 PDF만 전송했다. 평가 기준표는 입력하지 않았다.',
             '- 원본 SHA-256과 기준표를 확인했고, 원본 API 응답은 ignored 실행 폴더에 보관했다.',
             '- 기존 앱 입력 프로파일과 Studio 지침은 변경하지 않았다.', '',
             '## 목차 비교', '', '| 지표 | 기존 legacy 저장 분석 | Config 4 구조 분석 | Config 4 최종 검토 |',
             '|---|---:|---:|---:|']
    def comparison(label, getter):
        lines.append('| ' + label + ' | ' + ' | '.join(getter(x) for x in (baseline, structure, review)) + ' |')
    comparison('범위 내 예측 수', lambda x: str(x['prediction_count']))
    comparison('제목+번호 정밀도', lambda x: ratio(x['metrics']['heading_number_and_identity']['precision']))
    comparison('제목+번호 재현율', lambda x: ratio(x['metrics']['heading_number_and_identity']['recall']))
    comparison('제목+번호 F1', lambda x: percent(x['metrics']['heading_number_and_identity']['f1']))
    comparison('부모 관계 정확도 (대응 항목)', lambda x: ratio(x['metrics']['parent_accuracy_on_matched']))
    comparison('하위 절 재현율', lambda x: ratio(x['metrics']['exact_subsection_recall']))
    comparison('시작 페이지 포함률 (대응 항목)', lambda x: ratio(x['metrics']['page_accuracy_on_matched']))
    lines += ['', '## JSON 및 원본 필드', '', '| 단계 | 응답 전체 strict JSON | 객체 자체 strict JSON | 인용 접미부 수 |', '|---|---|---|---:|']
    for stage, output in outputs.items():
        syntax = output['syntax']
        lines.append(f"| {stage} | {syntax['strict_valid']} | {syntax['json_object_strict_valid']} | {syntax['trailing_citation_count']} |")
    lines += ['',
              "최종 검토는 2행 166열의 document_title 값 바로 뒤에서 `Expecting ',' delimiter`로 실패했다. 인용 표시가 닫힌 문자열 뒤와 쉼표 사이에 들어갔으므로 NPU 실행의 단순 접미부 문제와 다르다.",
              '최종 응답을 수정하거나 인용 표시를 제거하지 않았다. 원문 sections 배열 39개와 evidence 배열 51개를 각각 strict JSONDecoder.raw_decode로 읽어 진단용 투영을 만들었다. 최종 검토의 아래 목차 점수는 이 독립 배열에 한정하며 전체 JSON이 유효하거나 서비스가 바로 읽을 수 있다는 뜻이 아니다.',
              '최종 structure_coverage는 output_section_count=38을 자체 보고했으나 실제 sections 배열 길이는 39다. 자체 보고 개수를 평가 점수로 사용하지 않았다.', '',
              '## Document Parse 단계에서 확인한 원인', '',
              f"- 실제 모델: `{metadata['raw_document_parse_checks']['model']}`. 16페이지 처리.",
              f"- 실제 제목의 시작 페이지 내 텍스트 존재: {ratio(metadata['raw_document_parse_checks']['heading_text_start_page_presence'])}.",
              f"- 같은 제목을 heading 범주로 분류한 비율: {ratio(metadata['raw_document_parse_checks']['heading_category_start_page_presence'])}.",
              '- 2장 Materials and methods와 2.1.1 Preparation of seedling samples는 paragraph로 분류됐지만 후속 구조 분석이 복원했다.',
              '- 반대로 본문 문장, computed as:, 수식, 표 6·8 제목, 결론 앞의 문장 조각이 heading1로 분류됐고 후속 단계가 목차 후보에 그대로 남겼다.',
              '- Data will be made available on request.도 목차에 포함됐다. 데이터 제공 안내는 사전 범위 밖이지만 이 문장은 고정된 excluded_titles의 Data availability와 문자열이 달라 기존 평가기에서 오탐으로 남는다. 결과를 보고 기준표를 변경하지 않았다.',
              '- 이 점검은 지정한 제목의 텍스트·범주 확인이다. 전체 OCR, 읽기 순서, 수식·표 인식 정확도 점수가 아니다.']
    for stage in ('structure', 'review'):
        report = outputs[stage]['report']
        lines += ['', f'### {stage}', '',
                  f"- 원본 level 필드: {ratio(report['native_level_accuracy_on_matched'])}",
                  f"- 원본 번호 필드: {ratio(report['native_number_field_accuracy_on_matched'])}",
                  f"- 근거 ID 연결: {ratio(report['evidence_link_validity'])}",
                  f"- 인용문 조각의 지정 페이지 존재: {ratio(report['quoted_fragment_page_matches']['score'])}",
                  f"- 누락: {len(report['missing'])}개. 오탐: {len(report['unmatched_predictions'])}개. 범위 제외: {len(report['ignored_predictions'])}개."]
        lines += [f"- 누락: {x['id']} {x['title']}" for x in report['missing']]
        lines += [f"- 오탐: {x['title']} ({x['reason']})" for x in report['unmatched_predictions']]
        lines += [f"- 페이지 불일치: {x['reference_id']} {x['reference_title']}: 기대 {x['reference_page']}, 출력 {x['predicted_pages']}" for x in report['matches'] if not x['page_correct']]
    lines += ['', '## 항목별 대조', '', '| 원문 번호·제목 | 원문 시작 페이지 | 구조 분석 | 최종 검토 |', '|---|---:|---|---|']
    maps = [{x['reference_id']: x for x in report['matches']} for report in (structure, review)]
    for item in REFERENCE['items']:
        cells = []
        for mapping in maps:
            row = mapping.get(item['id'])
            if not row:
                cells.append('누락')
            else:
                failures = [label for key,label in (('number_correct','번호'),('parent_correct','부모'),('page_correct','페이지')) if not row[key]]
                cells.append('일치' if not failures else '불일치: ' + ', '.join(failures))
        lines.append(f"| {item['id']} {item['title']} | {item['page']} | {' | '.join(cells)} |")
    lines += ['', '## 해석 한계', '',
              '- 단일 RGBD 논문의 실행 결과다. NPU와 함께 두 편에서 관찰한 결과이며 전체 논문의 일반화 점수가 아니다.',
              '- legacy는 예전 저장본이며 동일 모델·동일 출력 계약의 통제된 전후 실험이 아니다. 엄격한 제목 매칭은 미등록 번역·요약도 불일치로 본다.',
              '- 기준표는 원문 대조로 작성했으나 전문가 독립 검수 전이다. 역할 라벨은 제공되지 않아 N/A이며 추론하지 않았다.',
              '- 인용문 검사는 문자열 조각의 페이지 존재 검사다. 해석의 타당성이나 문체 가이드의 충실도를 증명하지 않는다.',
              '- 페이지 지표는 시작 페이지가 source_pages에 포함되는지 검사하며, 추가 페이지의 정확성을 뜻하지 않는다.',
              '- 자체 보고 coverage나 confidence를 정답 점수로 사용하지 않았다. 진단 파싱은 원본의 strict_valid 상태를 바꾸지 않는다.', '',
              '## 다음 Studio 지침 개선 후보', '',
              '1. Parse의 heading1은 후보로 취급한다. 본문 문장·수식·수식 도입문·표/그림 캡션·문장 조각은 원문 위치와 문맥을 대조해 본문 목차에서 제외하고, 논문 메타데이터·부속 항목은 별도 배열로 분리한다.',
              '2. paragraph로 분류됐어도 실제 번호와 절 제목이 있으면 본문 목차 후보로 복원한다. 이번 2장과 2.1.1의 복원은 유지한다. 무번호라는 이유만으로 실제 절을 일괄 삭제하지 않는다.',
              '3. 최종 응답은 JSON 객체 하나로 제한하고 출처는 evidence_id 배열과 JSON 문자열 안에만 둔다. 값 밖의 인용 토큰을 금지한다. 실제 배열 개수로 coverage를 계산하고 형식 검증 실패는 성공과 구분한다.',
              '4. 이 두 PDF를 고정 회귀 샘플로 재실행해 재현율뿐 아니라 오탐 수와 strict JSON 성공 여부도 함께 비교한다.', '',
              '## 재현', '', '원본 실행과 평가 스크립트는 `draft_history/rgbd-config4/`에 보관했다.',
              '구조·최종 검토의 목차 투영은 `evaluation/golden/predictions/rgbd-studio-config4-*-projection.json`에 있다.',
              '동일 기준표와 `studio_json_evaluation.explicit_outline()` 및 `golden_evaluation.evaluate_outline()`로 재채점할 수 있다.', '']
    (RESULTS / 'rgbd-studio-config4-validation.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'structure': structure['metrics'], 'review': review['metrics'], 'json': metadata['json_syntax']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
