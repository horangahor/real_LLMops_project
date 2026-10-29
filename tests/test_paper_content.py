"""작성 자료 분리와 재생성 이후 결과표 보존을 검증한다."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_draft_agent as paper
from paper_content import (
    TABLE_SLOT, TABLE_START, attach_result_tables, chapter_context, output_observations, result_tables, writing_packet,
)
from paper_prompts import GENERATION_ORDER, SECTION_SUBSECTIONS


def evidence_fixture():
    return {
        'evidence_status': 'source_reviewed',
        'verified_facts': [{'id': 'E01', 'finding': 'old runtime 9999ms'}],
        'section_briefs': {
            '1': {'main_claim': 'intro claim', 'selected_facts': [{'id': 'E01', 'finding': 'GPU 실행 비용을 검토한다.'}]},
            '6': {'main_claim': 'conclusion claim', 'selected_facts': [{'id': 'E01', 'finding': '서로 다른 실행 비용을 검토할 필요성이 있다.'}]},
        },
        'result_tables': [{'id': 'initial', 'caption': '초기 실행', 'evidence_ids': ['E01'],
                           'columns': ['구현', '시간 (ms)'], 'rows': [['CPU', '10'], ['GPU', '20']],
                           'scope': '초기 관측이며 후기 예열 결과와 직접 비교하지 않는다.'}],
    }


def chapter(section, marker='body'):
    if section == '1':
        return marker + ' introduction'
    if section == '6':
        return '\n\n'.join(f'{marker} paragraph {i}' for i in range(4))
    return '\n\n'.join(f'### {section}.{i} {title}\n\n{marker}'
                         for i, title in enumerate(SECTION_SUBSECTIONS[section], 1))


class PaperContentTests(unittest.TestCase):
    def test_narrative_packet_and_context_exclude_raw_experiment_history(self):
        evidence = evidence_fixture()
        context = {'5': '### 5.2 결과 및 분석\n\nold runtime 9999ms'}
        for section in ('1', '6'):
            with self.subTest(section=section):
                packet = writing_packet(evidence, section)
                self.assertNotIn('9999ms', json.dumps(packet))
                self.assertNotIn('result_tables', packet)
                self.assertNotIn('9999ms', json.dumps(chapter_context(context, evidence, section)))
        self.assertIn('9999ms', json.dumps(writing_packet(evidence, '5')))
        raw = {'optimization_methods': ['raw extraction']}
        self.assertIs(writing_packet(raw, '1'), raw)

    def test_selected_fact_must_reference_existing_reviewed_evidence(self):
        evidence = evidence_fixture()
        evidence['section_briefs']['1']['selected_facts'][0]['id'] = 'E99'
        with self.assertRaisesRegex(ValueError, '선택 근거'):
            writing_packet(evidence, '1')

    def test_result_writer_receives_qualitative_scope_instead_of_table_values(self):
        evidence = evidence_fixture()
        evidence['section_briefs']['5'] = {'selected_facts': [{'id': 'E01', 'finding': '초기 GPU 실행이 더 오래 걸렸다.'}]}
        with patch.object(paper, 'call_solar', return_value=chapter('5')) as call:
            paper.SectionWriter('key').write('5', evidence, '', {})
        prompt = call.call_args.args[1]
        self.assertIn('초기 GPU 실행이 더 오래 걸렸다', prompt)
        self.assertIn('표 5-1. 초기 실행', prompt)
        self.assertNotIn('9999ms', prompt)
        self.assertNotIn('| GPU | 20 |', prompt)

    def test_observations_do_not_count_background_heading_as_a_speedup(self):
        self.assertEqual(output_observations({'3': '### 3.1 배경 개념\n\n설명'})['3']['performance_values'], 0)

    def test_tables_are_restored_after_model_omission_or_changed_values(self):
        evidence = evidence_fixture()
        body = chapter('5').replace('### 5.2 결과 및 분석\n\nbody',
            '### 5.2 결과 및 분석\n\n| 구현 | 시간 |\n| --- | --- |\n| GPU | 9999 |\n\n해석 문단')
        attached = attach_result_tables(body, evidence)
        self.assertNotIn('9999', attached)
        self.assertIn('| GPU | 20 |', attached)
        self.assertIn('해석 문단', attached)
        self.assertEqual(attached.count(TABLE_START), 1)
        self.assertEqual(attach_result_tables(attached, evidence), attached)
        self.assertEqual(attach_result_tables(body.replace('해석 문단', TABLE_SLOT), evidence).count(TABLE_START), 1)

    def test_tables_reject_unknown_sources_and_invalid_row_width(self):
        for mutate in (lambda e: e['result_tables'][0].update(evidence_ids=['E99']),
                       lambda e: e['result_tables'][0].update(rows=[['missing cell']]),
                       lambda e: e.update(evidence_status='unreviewed_extraction')):
            evidence = evidence_fixture()
            mutate(evidence)
            with self.assertRaises(ValueError):
                result_tables(evidence)

    def test_full_workflow_refinishes_narratives_after_macro_edit_and_keeps_tables(self):
        evidence = evidence_fixture()
        evidence['section_briefs']['5'] = {'selected_facts': [{'id': 'E01', 'finding': '초기 GPU 실행이 더 오래 걸렸다.'}]}
        macro = {section: chapter(section, '9999ms macro history') for section in GENERATION_ORDER}
        worker_calls = []

        def fake_solar(system_prompt, user_prompt, api_key, reasoning_effort=None):
            for section in GENERATION_ORDER:
                if system_prompt.startswith(f'당신은 제{section}장'):
                    worker_calls.append(section)
                    if section in ('1', '5', '6'):
                        self.assertNotIn('9999ms', user_prompt)
                    return chapter(section, 'fresh narrative' if section in ('1', '6') else 'worker body')
            raise AssertionError('Unexpected API call')

        review = {'approved': True, 'issues': [], 'evidence_checks': []}
        with patch.object(paper, 'call_solar', side_effect=fake_solar), \
                patch.object(paper.PaperReviewer, 'review', return_value=review), \
                patch.object(paper.PaperSynthesizer, 'synthesize', return_value=copy.deepcopy(macro)):
            result = paper.write_paper(evidence, '', 'key')
        self.assertEqual(worker_calls, ['3', '4', '5', '1', '6', '5', '1', '6'])
        self.assertNotIn('macro history', result['sections']['1'])
        self.assertNotIn('macro history', result['sections']['6'])
        self.assertIn('| GPU | 20 |', result['sections']['5'])
        self.assertEqual(result['sections']['5'].count(TABLE_START), 1)
        self.assertEqual(result['output_observations']['5']['table_rows'], 4)


if __name__ == '__main__':
    unittest.main()
