"""HTTP contract checks using actual in-memory Qdrant and a fixed encoder."""

import unittest

from fastapi.testclient import TestClient
from qdrant_client import QdrantClient, models

import config
from api.main import INPUT_MESSAGE, SERVICE_MESSAGE, create_app
from retrieval.search import InvalidInput, Retriever


class FixedEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, text, **kwargs):
        self.inputs.append(text)
        return [1.0] + [0.0] * (config.VECTOR_SIZE - 1)


class FailingRetriever:
    def __init__(self, error):
        self.error, self.calls, self.closed = error, 0, 0

    def search(self, *_args, **_kwargs):
        self.calls += 1
        raise self.error

    def close(self):
        self.closed += 1


class APITests(unittest.TestCase):
    def setUp(self):
        self.database = QdrantClient(':memory:')
        self.database.create_collection(config.COLLECTION_NAME,
            vectors_config=models.VectorParams(size=config.VECTOR_SIZE, distance=models.Distance.COSINE))
        self.encoder = FixedEncoder()
        self.factory_calls, self.close_calls = 0, 0
        outer = self

        class OwnedRetriever(Retriever):
            def close(self):
                outer.close_calls += 1
                super().close()

        def factory():
            self.factory_calls += 1
            return OwnedRetriever(client=self.database, model=self.encoder)

        self.app = create_app(retriever_factory=factory)

    def tearDown(self):
        self.database.close()

    def add_source(self):
        self.payload = {'chunk': 'A source passage about GPU crashes on firmware 3.65.',
                        'url': 'https://github.com/example/vita/issues/1', 'title': 'GPU report',
                        'chunk_id': 'test_c0', 'doc_id': 'test', 'firmware': '3.65',
                        'hardware': 'PS Vita 1000', 'custom_metadata': {'preserved': True}}
        self.database.upsert(config.COLLECTION_NAME, points=[models.PointStruct(
            id=1, vector=[1.0] + [0.0] * (config.VECTOR_SIZE - 1), payload=self.payload)])

    def test_http_search_preserves_source_payload_and_unassessed_state(self):
        self.add_source()
        with TestClient(self.app) as client:
            response = client.post('/search', json={'question': '  GPU crash on firmware 3.65  ', 'limit': 3})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['status'], 'candidates_require_review')
        self.assertEqual(result['question'], 'GPU crash on firmware 3.65')
        self.assertEqual(result['evidence_assessment'], 'not_assessed')
        self.assertEqual(result['sources'][0]['payload'], self.payload)
        self.assertEqual(result['sources'][0]['point_id'], 1)
        self.assertEqual(result['sources'][0]['matching_query_identifiers'], ['3.65'])
        self.assertAlmostEqual(result['sources'][0]['score'], 1.0)

    def test_invalid_bodies_are_rejected_before_embedding(self):
        bodies = [{}, {'question': '   '}, {'question': 123}, {'question': 'x' * 8001},
                  {'question': 'test', 'limit': True}, {'question': 'test', 'limit': '3'},
                  {'question': 'test', 'limit': 1.5}, {'question': 'test', 'limit': 0},
                  {'question': 'test', 'limit': 21}, {'question': 'test', 'assess': True}]
        with TestClient(self.app) as client:
            for body in bodies:
                with self.subTest(body_type=list(body)):
                    response = client.post('/search', json=body)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json(), {'status': 'invalid_input', 'message': INPUT_MESSAGE})
        self.assertEqual(self.encoder.inputs, [])

    def test_malformed_json_has_a_stable_input_error(self):
        with TestClient(self.app) as client:
            response = client.post('/search', content='{invalid JSON', headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['status'], 'invalid_input')
        self.assertNotIn('{invalid JSON', response.text)
        self.assertEqual(self.encoder.inputs, [])

    def test_empty_retrieval_is_success_without_an_evidence_verdict(self):
        with TestClient(self.app) as client:
            response = client.post('/search', json={'question': 'test'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'no_candidates')
        self.assertEqual(response.json()['sources'], [])
        self.assertEqual(response.json()['evidence_assessment'], 'not_assessed')

    def test_backend_errors_are_redacted_and_distinct_from_no_candidates(self):
        failing = FailingRetriever(RuntimeError('https://user:private-password@backend.example/private'))
        with TestClient(create_app(retriever_factory=lambda: failing)) as client:
            response = client.post('/search', json={'question': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'service_error', 'message': SERVICE_MESSAGE})
        self.assertNotIn('private-password', response.text)
        self.assertEqual(failing.closed, 1)

    def test_retriever_input_error_is_redacted(self):
        failing = FailingRetriever(InvalidInput('private internal details'))
        with TestClient(create_app(retriever_factory=lambda: failing)) as client:
            response = client.post('/search', json={'question': 'test'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'status': 'invalid_input', 'message': INPUT_MESSAGE})

    def test_invalid_backend_response_cannot_become_an_answer(self):
        backend = FailingRetriever(None)
        backend.search = lambda *_args, **_kwargs: {'status': 'supported_answer', 'answer': 'unreviewed advice'}
        with TestClient(create_app(retriever_factory=lambda: backend)) as client:
            response = client.post('/search', json={'question': 'test'})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('unreviewed advice', response.text)

    def test_health_is_liveness_and_openapi_exposes_the_search_contract(self):
        failing = FailingRetriever(RuntimeError('backend down'))
        with TestClient(create_app(retriever_factory=lambda: failing)) as client:
            response = client.get('/health')
            schema = client.get('/openapi.json').json()
        self.assertEqual(response.json(), {'status': 'ok', 'service': 'vita-vault', 'check': 'process_liveness'})
        self.assertEqual(failing.calls, 0)
        self.assertIn('/search', schema['paths'])
        self.assertIn('503', schema['paths']['/search']['post']['responses'])

    def test_one_retriever_is_reused_and_closed_once(self):
        self.add_source()
        self.assertEqual(self.factory_calls, 0)
        with TestClient(self.app) as client:
            self.assertEqual(client.post('/search', json={'question': 'first'}).status_code, 200)
            self.assertEqual(client.post('/search', json={'question': 'second'}).status_code, 200)
            self.assertEqual(self.factory_calls, 1)
            self.assertEqual(self.close_calls, 0)
        self.assertEqual(self.close_calls, 1)
        self.assertEqual(len(self.encoder.inputs), 2)


if __name__ == '__main__':
    unittest.main()
