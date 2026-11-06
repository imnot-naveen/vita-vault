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
