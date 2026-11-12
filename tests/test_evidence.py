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

    def test_tentative_success_and_unflagged_retractions_require_review(self):
        self.review['requested_support'] = 'reported_remedy'
        self.assessment['support'] = 'reported_success'
        for quote in ['Only updating the CA certificates should work.',
                      'I withdraw my earlier statement that it fixed the issue; the problem persists.',
                      'The menu crashed again after fifteen minutes.']:
            with self.subTest(quote=quote):
                self.source['payload']['chunk'] = quote
                self.assessment.update(evidence_quote=quote, passage_sha256=passage_hash(quote))
                result = self.decide()
                self.assertEqual(result['status'], 'review_required')
                self.assertEqual(result['permitted_claims'], [])

    def test_explicit_observed_success_still_can_be_reported(self):
        quote = 'I tried the change, and it worked for me during the test.'
        self.source['payload']['chunk'] = quote
        self.assessment.update(support='reported_success', evidence_quote=quote,
                               passage_sha256=passage_hash(quote))
        self.review['requested_support'] = 'reported_remedy'
        self.assertEqual(self.decide()['status'], 'supported_answer')

    def test_retry_only_version_does_not_support_a_release_but_an_explicit_fix_does(self):
        retry = 'PSP ISO downloads failed with files in wrong order. Retry with PKGj 0.51.'
        fixed = f'{retry} A later update says fixed in PKGj v0.51.'
        claim = 'PKGj v0.51 fixed the PSP ISO download error.'
        self.review['requested_support'] = 'release_identification'
        self.source['payload']['chunk'] = retry
        self.assessment.update(support='documented_release', claim=claim, evidence_quote=retry,
                               passage_sha256=passage_hash(retry))
        second = deepcopy(self.source)
        second['point_id'] = 2
        second['payload'].update(chunk=fixed, url='https://example.com/issue/2')
        self.retrieval['sources'].append(second)
        self.review['assessments'].append(self.assessment | {
            'point_id': 2, 'url': second['payload']['url'], 'evidence_quote': fixed,
            'passage_sha256': passage_hash(fixed),
        })

        result = self.decide()

        self.assertEqual(result['status'], 'supported_answer')
        self.assertEqual([claim['point_id'] for claim in result['permitted_claims']], [2])
        self.assertEqual(result['related_sources'][0]['support'], 'suggestion_without_outcome')

    def test_future_and_conditional_versions_do_not_establish_a_released_fix(self):
        planned = "The DLC still fails. Fixed in v0.27 if it's that bug. Will be fixed in v0.28."
        released = f'{planned} Update after release: fixed in v0.28.'
        self.review['requested_support'] = 'release_identification'
        for quote, claim, expected in (
            (planned, 'PKGj v0.28 fixed the DLC failure.', 'related_reports_insufficient_support'),
            (planned, 'PKGj v0.27 fixed the DLC failure.', 'related_reports_insufficient_support'),
            (released, 'PKGj v0.28 will fix the DLC failure.', 'related_reports_insufficient_support'),
            (released, 'PKGj v0.28 fixed the DLC failure.', 'supported_answer'),
        ):
            with self.subTest(claim=claim, quote=quote):
                self.source['payload']['chunk'] = quote
                self.assessment.update(support='documented_release', claim=claim, evidence_quote=quote,
                                       passage_sha256=passage_hash(quote))
                result = self.decide()
                self.assertEqual(result['status'], expected)
                if expected != 'supported_answer':
                    self.assertEqual(result['permitted_claims'], [])

    def test_predicted_install_is_guidance_and_cannot_prove_reported_success(self):
        quote = 'Remove work.bin and head.bin from the build, and the VPK will install as normal.'
        self.source['payload']['chunk'] = quote
        self.assessment.update(claim='The report advises omitting work.bin and head.bin from the build.',
                               evidence_quote=quote, passage_sha256=passage_hash(quote))

        self.review['requested_support'] = 'reported_remedy'
        self.assessment['support'] = 'reported_success'
        result = self.decide()
        self.assertEqual(result['status'], 'review_required')
        self.assertEqual(result['permitted_claims'], [])

        self.review['requested_support'] = 'guidance'
        self.assessment['support'] = 'documented_guidance'
        self.assertEqual(self.decide()['status'], 'supported_answer')

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
