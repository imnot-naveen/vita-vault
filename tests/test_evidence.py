"""Evidence-boundary tests; entirely offline, independent of Qdrant/model state."""

from copy import deepcopy
import json
from pathlib import Path
import unittest

from retrieval.evidence import decide_evidence, passage_hash


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.source = {'point_id': 1, 'score': 0.999,
                       'payload': {'chunk': 'The display shows used space, not free space.',
                                   'url': 'https://example.com/issue/1', 'title': 'Space display'}}
        self.retrieval = {'status': 'candidates_require_review',
                          'question': 'Why does space differ?', 'sources': [self.source]}
        self.assessment = {'point_id': 1, 'url': self.source['payload']['url'],
                           'passage_sha256': passage_hash(self.source['payload']['chunk']),
                           'relevance': 'direct', 'applicability': 'matching',
                           'support': 'explanation', 'claim': 'This display represents used space.',
                           'evidence_quote': 'shows used space, not free space',
                           'contradicted': False, 'reason': 'Explains the display.', 'limitations': []}
        self.review = {'schema_version': 1, 'question': self.retrieval['question'],
                       'requested_support': 'explanation', 'assessments': [self.assessment]}

    def decide(self):
        return decide_evidence(self.retrieval, self.review)

    def test_scoped_explanation_preserves_provenance_and_does_not_mutate(self):
        before = deepcopy((self.retrieval, self.review))
        result = self.decide()
        self.assertEqual(result['status'], 'supported_answer')
        self.assertEqual(result['permitted_claims'][0]['evidence_quote'], self.assessment['evidence_quote'])
        self.assertEqual(result['permitted_claims'][0]['url'], self.source['payload']['url'])
        self.assertEqual((self.retrieval, self.review), before)

    def test_similarity_cannot_replace_review(self):
        self.review['assessments'] = []
        self.assertEqual(self.decide()['status'], 'review_required')

    def test_unknown_mismatched_or_related_evidence_cannot_authorize_answer(self):
        for field, value in [('applicability', 'unknown'), ('applicability', 'mismatch'),
                             ('relevance', 'related')]:
            with self.subTest(field=field, value=value):
                review = deepcopy(self.review)
                review['assessments'][0][field] = value
                result = decide_evidence(self.retrieval, review)
                self.assertEqual(result['status'], 'related_reports_insufficient_support')
                self.assertEqual(result['permitted_claims'], [])

    def test_symptoms_and_suggestions_do_not_prove_a_remedy(self):
        self.review['requested_support'] = 'reported_remedy'
        for support in ['symptoms_only', 'suggestion_without_outcome', 'none', 'documented_guidance']:
            with self.subTest(support=support):
                self.assessment['support'] = support
                self.assertEqual(self.decide()['status'], 'related_reports_insufficient_support')

    def test_success_is_qualified_and_never_becomes_confirmed_exact_fix(self):
        self.assessment['support'] = 'reported_success'
        self.review['requested_support'] = 'reported_remedy'
        result = self.decide()
        self.assertEqual(result['status'], 'supported_answer')
        self.assertIn('Self-reported', result['permitted_claims'][0]['qualification'])
        self.review['requested_support'] = 'confirmed_fix'
        self.assertEqual(self.decide()['status'], 'related_reports_insufficient_support')

    def test_conflicting_report_blocks_answer_permission(self):
        second = deepcopy(self.source)
        second['point_id'] = 2
        self.retrieval['sources'].append(second)
        assessment = deepcopy(self.assessment)
        assessment.update(point_id=2, contradicted=True)
        self.review['assessments'].append(assessment)
        result = self.decide()
        self.assertEqual(result['status'], 'related_reports_insufficient_support')
        self.assertTrue(result['conflicting_evidence'])
        self.assertEqual(result['permitted_claims'], [])

    def test_all_irrelevant_is_distinct_from_empty_retrieval_and_service_failure(self):
        self.assessment.update(relevance='irrelevant', applicability='not_applicable',
                               support='none', claim='', evidence_quote='')
        result = self.decide()
        self.assertEqual(result['status'], 'no_relevant_evidence_retrieved')
        self.assertEqual(result['basis'], 'all_sources_reviewed_irrelevant')
        self.retrieval.update(status='no_candidates', sources=[])
        self.assertEqual(self.decide()['basis'], 'no_candidates')
        self.retrieval['status'] = 'service_error'
        self.assertEqual(self.decide()['status'], 'service_error')

    def test_invalid_or_stale_reviews_fail_closed(self):
        mutations = [lambda r: r.update(question='A different question'),
                     lambda r: r.update(schema_version=True),
                     lambda r: r.update(requested_support=[]),
                     lambda r: r['assessments'][0].update(point_id=True),
                     lambda r: r['assessments'][0].update(point_id=999),
                     lambda r: r['assessments'][0].update(url='https://other.example/x'),
                     lambda r: r['assessments'][0].update(passage_sha256='stale'),
                     lambda r: r['assessments'][0].update(evidence_quote='Invented text'),
                     lambda r: r['assessments'][0].update(claim=''),
                     lambda r: r['assessments'][0].update(relevance='certain'),
                     lambda r: r['assessments'][0].update(support=[]),
                     lambda r: r['assessments'][0].update(contradicted='false'),
                     lambda r: r['assessments'].append(deepcopy(r['assessments'][0]))]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                review = deepcopy(self.review)
                mutate(review)
                self.assertEqual(decide_evidence(self.retrieval, review)['status'], 'review_required')

    def test_changed_passage_requires_reassessment(self):
        self.source['payload']['chunk'] += ' Later correction: the earlier explanation was wrong.'
        self.assertEqual(self.decide()['status'], 'review_required')

    def test_one_unreviewed_source_prevents_whole_result_decision(self):
        second = deepcopy(self.source)
        second['point_id'] = 2
        self.retrieval['sources'].append(second)
        self.assertEqual(self.decide()['status'], 'review_required')

    def test_malformed_retrieval_and_review_are_not_answers(self):
        for retrieval, review in [(None, None), ({}, {}), (self.retrieval, None),
                                 ({'status': 'no_candidates', 'question': 'x', 'sources': [self.source]}, None)]:
            self.assertEqual(decide_evidence(retrieval, review)['status'], 'review_required')

    def test_saved_development_decisions(self):
        path = Path(__file__).with_name('evidence_development.json')
        cases = json.loads(path.read_text(encoding='utf-8'))['cases']
        for case in cases:
            with self.subTest(case=case['id']):
                decision = decide_evidence(case['retrieval'], case['review'])
                self.assertEqual(decision['status'], case['expected_status'])
                if case['expected_status'] != 'supported_answer':
                    self.assertEqual(decision['permitted_claims'], [])


if __name__ == '__main__':
    unittest.main()
