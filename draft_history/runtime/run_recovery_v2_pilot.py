import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from planned_paper import PlannedPaper
from research_recovery import recover_unconfirmed

paths = list(Path('draft_history/parse-api-v1').glob('*/research-evidence-v3/*/evidence.json'))
evidence_path = max(paths, key=lambda path: path.stat().st_mtime)
package = json.loads(evidence_path.read_text(encoding='utf-8'))
old = package['evidence_recovery']
selected = {'P0003F0009', 'P0006F0006', 'P0024F0010'}
empty_response = next(row for row in old['records'] if row['fact_id'].startswith('P0052') and not row.get('proposal'))
selected.add(empty_response['fact_id'])
elements = json.loads(Path(package['source_archive_path']).read_text(encoding='utf-8'))['elements']
folder = (Path(sys.argv[1]) if len(sys.argv) > 1 else
          Path('draft_history/runtime/recovery-v2-pilot') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
previous = folder / 'recovery-report.json'
if previous.is_file():
    (folder / 'report.before-content-feedback.json').write_bytes(previous.read_bytes())
engine = PlannedPaper(base_dir=Path.cwd())
if '--cache-only' in sys.argv:
    engine.evidence_cache_root = Path('draft_history/runtime/recovery-v2-pilot')
    cached_call = engine.call
    def call_from_cache(*args, **kwargs):
        kwargs['cache_only'] = True
        return cached_call(*args, **kwargs)
    engine.call = call_from_cache
engine.evidence_progress = lambda _, message: print(message, flush=True)
print('PILOT_FOLDER', folder, 'SELECTED', sorted(selected), flush=True)
_, report = recover_unconfirmed(engine, folder, package['items'], {row['element_id']: row for row in elements},
    protected_ids={fact['id'] for fact in package['items']} - selected)
print('PILOT_RESULT', json.dumps({'counts': report['counts'], 'errors': report['errors'],
    'records': [{'id': row['fact_id'], 'status': row['status'], 'reason': row.get('reason'),
                 'attempts': len(row.get('attempts', []))} for row in report['records']]}, ensure_ascii=False), flush=True)
