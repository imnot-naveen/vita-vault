"""Frozen manual hard-case labels must be internally consistent with policy."""

import json
from copy import deepcopy
from pathlib import Path
import unittest

from retrieval.evidence import decide_evidence


class HardCaseContractTests(unittest.TestCase):
    def test_frozen_manual_expectations_and_source_quotes(self):
        fixture = json.loads(Path(__file__).with_name('evidence_hard_cases.json').read_text(encoding='utf-8'))
        self.assertEqual(len(fixture['cases']), 12)
        self.assertEqual(sum(c['split'] == 'reserved' for c in fixture['cases']), 4)
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                decision = decide_evidence(case['retrieval'], case['review'])
                self.assertEqual(decision['status'], case['expected_status'])

    def test_recorded_suggestion_false_positive_is_rejected(self):
        fixture = json.loads(Path(__file__).with_name('evidence_hard_cases.json').read_text(encoding='utf-8'))
        case = next(c for c in fixture['cases'] if c['id'] == 'dev-untested-suggestion')
        bad_review = deepcopy(case['review'])
        bad_review['assessments'][0].update(
            support='reported_success',
            claim='Updating only CA certificates was reported to resolve the timeout.',
            evidence_quote='Try to no use the full plugin of iTLS, only updating the CA certificates should work.')
        decision = decide_evidence(case['retrieval'], bad_review)
        self.assertEqual(decision['status'], 'review_required')
        self.assertEqual(decision['permitted_claims'], [])


if __name__ == '__main__':
    unittest.main()
