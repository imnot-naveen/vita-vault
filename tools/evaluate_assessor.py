"""Bounded live development checks of model reviews, not a held-out benchmark."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from retrieval.assessor import OpenRouterClient, SYSTEM_PROMPT, assess_evidence


class RecordedClient:
    """Keep completion data for local evaluation review, never HTTP headers/key."""
    def __init__(self, client):
        self.client, self.model, self.last_response = client, client.model, None

    def complete(self, request):
        self.last_response = self.client.complete(request)
        return self.last_response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=Path('tests/evidence_development.json'))
    parser.add_argument('--case-id', action='append', required=True,
                        help='Explicit case IDs to send; maximum 12 requests, no automatic retries.')
    parser.add_argument('--max-sources', type=int, choices=range(1, 21), default=20)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        fixture = json.loads(args.cases.read_text(encoding='utf-8'))
        requested = set(args.case_id)
        cases = [c for c in fixture['cases'] if c['id'] in requested]
        if len(args.case_id) != len(requested) or not 1 <= len(cases) <= 12 or {c['id'] for c in cases} != requested:
            raise ValueError('Unknown, duplicate or excessive case IDs.')
        client = RecordedClient(OpenRouterClient(config.OPENROUTER_API_KEY, config.LLM_MODEL))
    except (OSError, ValueError, KeyError, TypeError):
        print('Invalid cases or model configuration.', file=sys.stderr)
        return 2
    rows = []
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'model_requested': config.LLM_MODEL, 'max_sources_per_case': args.max_sources,
              'fixture_sha256': hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest(),
              'limitations': ['Assistant-labeled development cases, not held out.',
                              'A source cap creates a selected-passage scenario, not a full retrieval judgment.',
                              'Decision agreement alone does not establish semantic accuracy; inspect label disagreements.',
                              'No answer generation, new retrieval or index writes.'], 'cases': rows}
    for case in cases:
        retrieval = {**case['retrieval'], 'sources': case['retrieval']['sources'][:args.max_sources]}
        client.last_response = None
        started = time.monotonic()
        result = assess_evidence(retrieval, client)
        actual_status = result['decision']['status']
        expected_rows = {str(a['point_id']): a for a in case['review']['assessments']}
        differences = []
        if result['review'] is not None:
            if result['review']['requested_support'] != case['review']['requested_support']:
                differences.append({'field': 'requested_support', 'expected': case['review']['requested_support'],
                                    'actual': result['review']['requested_support']})
            for assessment in result['review']['assessments']:
                expected = expected_rows[str(assessment['point_id'])]
                for field in ('relevance', 'applicability', 'support', 'contradicted'):
                    if assessment[field] != expected[field]:
                        differences.append({'point_id': assessment['point_id'], 'field': field,
                                            'expected': expected[field], 'actual': assessment[field]})
        row = {'id': case['id'], 'split': case.get('split', 'development'),
               'question': retrieval['question'],
               'source_point_ids': [s['point_id'] for s in retrieval['sources']],
               'seconds': round(time.monotonic() - started, 3),
               'expected_status': case['expected_status'], 'actual_status': actual_status,
               'decision_agrees': actual_status == case['expected_status'],
               'label_disagreements': differences, 'result': result}
        if isinstance(client.last_response, dict):
            row['completion_for_review'] = {k: client.last_response[k] for k in ('model', 'choices', 'usage')
                                            if k in client.last_response}
        rows.append(row)
        report['completed_cases'] = len(rows)
        report['decision_agreements'] = sum(x['decision_agrees'] for x in rows)
        report['incorrect_answer_permissions'] = sum(x['actual_status'] == 'supported_answer' and
                                                    x['expected_status'] != 'supported_answer' for x in rows)
        report['label_disagreements'] = sum(len(x['label_disagreements']) for x in rows)
        report['missing_expected_answers'] = sum(x['expected_status'] == 'supported_answer' and
                                                 x['actual_status'] != 'supported_answer' for x in rows)
        report['validation_failures'] = sum(x['actual_status'] == 'review_required' for x in rows)
        args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
        print(json.dumps({k: row[k] for k in ('id', 'seconds', 'actual_status', 'decision_agrees', 'label_disagreements')},
                         ensure_ascii=True), flush=True)
        if result['status'] == 'service_error':
            report['stopped_after_provider_failure'] = True
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
            return 1
    return 0 if all(x['decision_agrees'] for x in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
