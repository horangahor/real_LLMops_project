"""골든 샘플의 형식·자료 분리·실패 시 산출물 보존을 검증한다."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import paper_structure as analysis
import paper_draft_agent as paper
from structure_profiles import (
    PROFILE_EXAMPLE, load_profiles, parse_profile_response, save_profiles, validate_profile, writing_guide,
)


def sample_profile():
    content = copy.deepcopy(PROFILE_EXAMPLE)
    content['observed_outline'][0]['title'] = 'Jetson 장비에서 95.8% 관측'
    content['not_to_transfer'] = ['Jetson', '95.8%']
    content['section_guidelines'].append({
        'role': 'conclusion', 'purpose': 'CONCLUSION_ONLY', 'required_content': ['핵심 발견'],
        'paragraph_flow': ['발견', '한계'], 'figures_tables': [],
    })
    return parse_profile_response(json.dumps(content), 'sample.pdf', 'pdf_analysis')


class StructureProfileTests(unittest.TestCase):
    def test_hierarchy_and_unknown_pages_survive_roundtrip(self):
        profile = sample_profile()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            target = Path(folder) / 'profiles.json'
            save_profiles([profile], target)
            self.assertEqual(load_profiles(target), [profile])
        self.assertIsNone(profile['observed_outline'][0]['source_pages'])
        self.assertEqual(len(profile['observed_outline'][0]['children']), 1)

    def test_invalid_nested_fields_and_versions_are_rejected(self):
        for mutation in (
            lambda p: p.update(schema_version=9),
            lambda p: p['observed_outline'][0].update(children='Markdown string'),
            lambda p: p['observed_outline'][0].update(source_pages=[True]),
            lambda p: p['section_guidelines'][0].update(required_content='long text'),
            lambda p: p['section_guidelines'][0].update(role='invented'),
        ):
            profile = sample_profile()
            mutation(profile)
            with self.assertRaises(ValueError):
                validate_profile(profile)

    def test_generation_overrides_model_paths_and_accepts_json_fences(self):
        content = {**PROFILE_EXAMPLE, 'file': 'model-path', 'provenance': 'invented'}
        result = parse_profile_response('```json\n' + json.dumps(content) + '\n```', 'actual.pdf', 'pdf_analysis')
        self.assertEqual(result['file'], 'actual.pdf')
        self.assertEqual(result['provenance'], 'pdf_analysis')
        with self.assertRaises(ValueError):
            parse_profile_response('not JSON', 'sample.pdf', 'pdf_analysis')

    def test_prompt_selects_chapter_role_and_excludes_reference_facts(self):
        reference = {'profiles': [sample_profile()]}
        methods = writing_guide(reference, '4')
        conclusion = writing_guide(reference, '6')
        self.assertIn('전체 구성', methods)
        self.assertNotIn('CONCLUSION_ONLY', methods)
        self.assertIn('CONCLUSION_ONLY', conclusion)
        self.assertNotIn('전체 구성', conclusion)
        for text in (methods, conclusion, writing_guide(reference)):
            self.assertNotIn('95.8%', text)
            self.assertNotIn('Jetson', text)

    def test_previous_markdown_files_remain_readable(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'old.json'
            path.write_text(json.dumps({'paper_structure_profile': 'STYLE_MARKER'}), encoding='utf-8')
            self.assertIn('STYLE_MARKER', writing_guide({'profiles': load_profiles(path)}, '4'))

    def test_section_writer_receives_selected_guide_instead_of_raw_profile(self):
        with patch.object(paper, 'call_solar', return_value='method body') as call:
            paper.SectionWriter('key').write('4', {}, {'profiles': [sample_profile()]}, {})
        prompt = call.call_args.args[1]
        self.assertIn('전체 구성', prompt)
        self.assertNotIn('CONCLUSION_ONLY', prompt)
        self.assertNotIn('95.8%', prompt)
        self.assertNotIn('Jetson', prompt)

    def test_invalid_result_does_not_replace_existing_profiles(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / 'profiles.json'
            path.write_text('previous file', encoding='utf-8')
            profile = sample_profile()
            del profile['observed_outline']
            with self.assertRaises(ValueError):
                save_profiles([profile], path)
            with self.assertRaises(ValueError):
                save_profiles([], path)
            self.assertEqual(path.read_text(encoding='utf-8'), 'previous file')

    def test_migration_preserves_provenance_without_claiming_pdf_review(self):
        legacy = {'file': 'old.pdf', 'paper_structure_profile':
                  '#### 4. 섹션 계층 및 순서\n1. **방법론**\n  - 1.1 실험 설정\n2. **결론**\n'}
        with patch.object(analysis, 'run_chat') as call, patch.object(analysis, 'parse_pdf') as parse:
            migrated = analysis.migrate_profiles([legacy])
        call.assert_not_called()
        parse.assert_not_called()
        self.assertEqual(migrated[0]['provenance'], 'legacy_analysis')
        self.assertIsNone(migrated[0]['observed_outline'][0]['source_pages'])
        self.assertEqual(migrated[0]['observed_outline'][0]['children'][0]['title'], '1.1 실험 설정')
        self.assertEqual([guide['role'] for guide in migrated[0]['section_guidelines']], ['methods', 'conclusion'])

    def test_batch_failure_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            root = Path(folder)
            for name in ('one.pdf', 'two.pdf'):
                (root / name).write_bytes(b'placeholder')
            output = root / 'profiles.json'
            output.write_text('previous file', encoding='utf-8')
            with patch.object(analysis, 'analyze_paper', side_effect=[sample_profile(), ValueError('bad analysis')]):
                with self.assertRaisesRegex(ValueError, 'bad analysis'):
                    analysis.main([str(root/'one.pdf'), str(root/'two.pdf'), '--output', str(output)])
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous file')

    def test_truncated_generation_is_rejected(self):
        response = Mock(status_code=200)
        response.json.return_value = {'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}
        with patch.object(analysis.requests, 'post', return_value=response):
            with self.assertRaisesRegex(ValueError, '잘렸습니다'):
                analysis.run_chat('system', 'text')


if __name__ == '__main__':
    unittest.main()
