"""HTTP evidence review with a fake provider and the actual review validator."""
from copy import deepcopy
import unittest
from fastapi.testclient import TestClient
from api.main import create_app
from retrieval.assessor import AssessorUnavailable
import test_assessor as fixtures


class SavedRetriever:
    def __init__(self, result):
        self.result = result
    def search(self, *_args, **_kwargs):
        return deepcopy(self.result)
    def close(self):
        pass


class AssessmentAPITests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AssessorTests()
        fixture.setUp()
        self.fixture = fixture
        self.retrieval = fixture.retrieval | {
            'collection': 'test', 'embedding_model': 'fixture', 'query_prefix': '',
            'ranking': 'fixture', 'query_identifiers': [], 'min_score': None,
            'evidence_assessment': 'not_assessed', 'notice': 'Fixture.',
            'fetched_points': 1, 'skipped': {}}
        self.retrieval['sources'][0]['matching_query_identifiers'] = []

    def app(self, provider):
        return create_app(retriever_factory=lambda: SavedRetriever(self.retrieval),
                          assessor_factory=lambda: provider)

    def test_supported_claim_has_bound_quote_and_source_without_raw_provider_output(self):
        provider = fixtures.FakeClient(self.fixture.response())
        with TestClient(self.app(provider)) as client:
            response = client.post('/assess', json={'question': self.retrieval['question']})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['status'], 'assessed')
        self.assertEqual(result['decision']['status'], 'supported_answer')
        claim = result['decision']['permitted_claims'][0]
        self.assertEqual(claim['url'], self.retrieval['sources'][0]['payload']['url'])
        self.assertIn(claim['evidence_quote'], self.retrieval['sources'][0]['payload']['chunk'])
        self.assertEqual(result['retrieval'], self.retrieval)
        self.assertNotIn('review', result)
        self.assertNotIn('usage', result)

    def test_release_lookup_requires_a_quoted_version_and_exact_error(self):
        self.retrieval['question'] = 'Which installable Adrenaline release fixed error C1-2858-3?'
        self.fixture.output['requested_support'] = 'release_identification'
        claim = 'The release note lists Adrenaline v99.2 as the release that fixes C1-2858-3.'
        cases = (
            ('matching release', 'Adrenaline v99.2 release notes: fixed C1-2858-3.', 'supported_answer'),
            ('different error', 'Adrenaline v99.2 release notes: fixed C1-2758-2.', 'review_required'),
            ('different version', 'Adrenaline v99.1 release notes: fixed C1-2858-3.', 'review_required'),
            ('commit only', 'Commit a1b2c3d fixed Adrenaline error C1-2858-3.', 'review_required'),
        )
        source = self.retrieval['sources'][0]['payload']
        for name, passage, expected in cases:
            with self.subTest(name=name):
                source['chunk'] = passage
                self.fixture.output['assessments'][0].update(
                    support='documented_release', claim=claim, evidence_quote=passage,
                    reason='The release note supplies the version and error.',
                )
                provider = fixtures.FakeClient(self.fixture.response())
                with TestClient(self.app(provider)) as client:
                    response = client.post('/assess', json={'question': self.retrieval['question']})
                self.assertEqual(response.status_code, 200)
                decision = response.json()['decision']
                self.assertEqual(decision['status'], expected)
                if expected == 'supported_answer':
                    self.assertEqual(len(decision['permitted_claims']), 1)
                    release = decision['permitted_claims'][0]
                    self.assertEqual(release['support'], 'documented_release')
                    self.assertEqual(release['claim'], claim)
                    self.assertEqual(release['evidence_quote'], passage)
                    self.assertEqual(release['url'], source['url'])
                else:
                    self.assertEqual(decision['permitted_claims'], [])

    def test_release_lookup_extracts_and_validates_the_span_between_excerpts(self):
        self.retrieval['question'] = 'Which installable Adrenaline release fixed error C1-2858-3?'
        self.fixture.output['requested_support'] = 'release_identification'
        start = 'Firmware 3.65, error C1-2858-3'
        end = 'Fixed in v99.2.'
        span = f'{start}. Several comments discussed the launch failure. {end}'
        passage = f'Adrenaline issue. {span} Thanks for the update.'
        cases = (
            ('matching span', passage, start, end, span),
            ('missing opening', passage, 'Opening from another issue', end, None),
            ('missing ending', passage, start, 'Fixed in v99.1.', None),
            ('reversed excerpts', f'{end} Earlier report: {start}.', start, end, None),
            ('ambiguous opening', f'{start}. Then: {span}', start, end, None),
            ('missing firmware', passage, 'error C1-2858-3', end, None),
        )
        for name, source_text, opening, ending, expected_quote in cases:
            with self.subTest(name=name):
                self.retrieval['sources'][0]['payload']['chunk'] = source_text
                self.fixture.output['assessments'][0].update(
                    support='documented_release',
                    claim='Adrenaline v99.2 fixes C1-2858-3 on firmware 3.65.',
                    evidence_start=opening, evidence_quote=ending,
                    reason='The issue report records the error and the released fix.',
                )
                provider = fixtures.FakeClient(self.fixture.response())
                with TestClient(self.app(provider)) as client:
                    response = client.post('/assess', json={'question': self.retrieval['question']})
                self.assertEqual(response.status_code, 200)
                decision = response.json()['decision']
                if expected_quote is None:
                    self.assertEqual(decision['status'], 'review_required')
                    self.assertEqual(decision['permitted_claims'], [])
                else:
                    self.assertEqual(decision['status'], 'supported_answer')
                    self.assertEqual(decision['permitted_claims'][0]['evidence_quote'], expected_quote)

    def test_commit_mislabeled_as_release_preserves_related_source_without_a_claim(self):
        self.retrieval['question'] = 'Which installable Adrenaline release fixed error C1-2858-3?'
        source = self.retrieval['sources'][0]['payload']
        start = 'Downloading a demo v1.0 asset triggered error C1-2858-3.'
        end = 'Adrenaline commit a1b2c3d fixes the download.'
        source['chunk'] = f'{start} Discussion followed. {end}'
        self.fixture.output['requested_support'] = 'release_identification'
        self.fixture.output['assessments'][0].update(
            support='documented_release', claim='Adrenaline commit a1b2c3d fixes C1-2858-3.',
            evidence_start=start, evidence_quote=end, reason='The source identifies the fixing commit.',
        )
        provider = fixtures.FakeClient(self.fixture.response())
        with TestClient(self.app(provider)) as client:
            response = client.post('/assess', json={'question': self.retrieval['question']})

        self.assertEqual(response.status_code, 200)
        decision = response.json()['decision']
        self.assertEqual(decision['status'], 'related_reports_insufficient_support')
        self.assertEqual(decision['message'], "The retrieved sources don't identify an installable release.")
        self.assertEqual(decision['permitted_claims'], [])
        self.assertEqual(decision['related_sources'][0]['url'], source['url'])
        self.assertEqual(decision['related_sources'][0]['support'], 'none')

    def test_cross_source_release_quote_cannot_discard_an_independent_valid_citation(self):
        self.retrieval['question'] = 'Which installable Adrenaline release fixed error C1-2858-3?'
        first = self.retrieval['sources'][0]
        opening = 'Error C1-2858-3 appears when launching Adrenaline.'
        first['payload']['chunk'] = f'{opening} Retry with v99.2.'
        second = deepcopy(first)
        second['point_id'] = 2
        fixed = 'Adrenaline release v99.2 fixed C1-2858-3.'
        second['payload'].update(url='https://example.com/issue/2', chunk=fixed)
        self.retrieval['sources'].append(second)
        self.fixture.output['requested_support'] = 'release_identification'
        row = self.fixture.output['assessments'][0]
        row.update(support='documented_release', claim='Adrenaline v99.2 fixed C1-2858-3.',
                   evidence_start=opening, evidence_quote=fixed, reason='The release addresses the error.')
        self.fixture.output['assessments'].append(row | {
            'source_index': 1, 'evidence_start': '', 'evidence_quote': fixed,
        })
        provider = fixtures.FakeClient(self.fixture.response())

        with TestClient(self.app(provider)) as client:
            response = client.post('/assess', json={'question': self.retrieval['question']})

        self.assertEqual(response.status_code, 200)
        decision = response.json()['decision']
        self.assertEqual(decision['status'], 'supported_answer')
        self.assertEqual([claim['point_id'] for claim in decision['permitted_claims']], [2])
        self.assertEqual(decision['related_sources'][0]['support'], 'none')

    def test_provider_failure_retains_sources_and_redacts_private_details(self):
        for error in [AssessorUnavailable('secret-provider-body'), RuntimeError('secret-provider-body')]:
            with self.subTest(error=type(error).__name__):
                with TestClient(self.app(fixtures.FakeClient(error))) as client:
                    response = client.post('/assess', json={'question': self.retrieval['question']})
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['decision']['status'], 'service_error')
                self.assertEqual(response.json()['retrieval'], self.retrieval)
                self.assertEqual(response.json()['decision']['permitted_claims'], [])
                self.assertNotIn('secret-provider-body', response.text)

    def test_invalid_model_quote_cannot_become_a_supported_answer(self):
        output = deepcopy(self.fixture.output)
        output['assessments'][0]['evidence_quote'] = 'fabricated remedy'
        with TestClient(self.app(fixtures.FakeClient(self.fixture.response(output)))) as client:
            response = client.post('/assess', json={'question': self.retrieval['question']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'review_required')
        self.assertEqual(response.json()['decision']['permitted_claims'], [])
        self.assertNotIn('fabricated remedy', response.text)

    def test_related_and_irrelevant_reviews_have_distinct_states(self):
        for relevance, expected in [('related', 'related_reports_insufficient_support'), ('irrelevant', 'no_relevant_evidence_retrieved')]:
            output = deepcopy(self.fixture.output)
            output['assessments'][0].update(relevance=relevance,
                applicability='unknown' if relevance == 'related' else 'not_applicable',
                support='symptoms_only' if relevance == 'related' else 'none', claim='', evidence_quote='')
            with TestClient(self.app(fixtures.FakeClient(self.fixture.response(output)))) as client:
                response = client.post('/assess', json={'question': self.retrieval['question']})
            self.assertEqual(response.json()['decision']['status'], expected)
            self.assertEqual(response.json()['decision']['permitted_claims'], [])

    def test_empty_or_invalid_inputs_and_source_search_skip_provider(self):
        calls = []
        def factory():
            calls.append(True)
            raise AssertionError('Must not call provider')
        app = create_app(retriever_factory=lambda: SavedRetriever(self.retrieval), assessor_factory=factory)
        with TestClient(app) as client:
            self.assertEqual(client.post('/search', json={'question': 'test'}).status_code, 200)
            for body in [{'question': ' '}, {'question': 'test', 'limit': True}, {'question': 'test', 'sources': []}]:
                self.assertEqual(client.post('/assess', json=body).status_code, 422)
            self.retrieval.update(status='no_candidates', sources=[])
            response = client.post('/assess', json={'question': 'test'})
        self.assertEqual(response.json()['decision']['status'], 'no_relevant_evidence_retrieved')
        self.assertFalse(response.json()['model_called'])
        self.assertEqual(calls, [])

    def test_busy_assessor_does_not_queue_or_block_local_search(self):
        app = self.app(fixtures.FakeClient(self.fixture.response()))
        with TestClient(app) as client:
            app.state.assessment_lock.acquire()
            try:
                self.assertEqual(client.post('/assess', json={'question': 'test'}).status_code, 503)
                self.assertEqual(client.post('/search', json={'question': 'test'}).status_code, 200)
            finally:
                app.state.assessment_lock.release()
            self.assertEqual(client.post('/assess', json={'question': 'test'}).status_code, 200)

    def test_retrieval_failure_never_calls_provider_or_claims_insufficient_evidence(self):
        class Broken(SavedRetriever):
            def search(self, *_args, **_kwargs):
                raise RuntimeError('secret backend body')
        provider = fixtures.FakeClient(self.fixture.response())
        with TestClient(create_app(retriever_factory=lambda: Broken(None), assessor_factory=lambda: provider)) as client:
            response = client.post('/assess', json={'question': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['status'], 'service_error')
        self.assertEqual(provider.requests, [])
        self.assertNotIn('secret backend body', response.text)
