"""Contract checks against Qdrant's real in-memory engine; no model downloads."""

import unittest

from qdrant_client import QdrantClient, models

import config
from retrieval.search import QUERY_PREFIX, Retriever, RetrievalError, public_source_url


class FixedEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, text, **kwargs):
        self.inputs.append((text, kwargs))
        return [1.0] + [0.0] * (config.VECTOR_SIZE - 1)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.client = QdrantClient(':memory:')
        self.client.create_collection(config.COLLECTION_NAME, vectors_config=models.VectorParams(
            size=config.VECTOR_SIZE, distance=models.Distance.COSINE))
        self.encoder = FixedEncoder()
        self.retriever = Retriever(client=self.client, model=self.encoder)

    def tearDown(self):
        self.client.close()

    def add(self, point_id, url, *, text='Original source passage', extra=None, similarity=1.0):
        payload = {'url': url, 'chunk': text, 'title': 'Source', 'doc_id': str(point_id),
                   'chunk_id': f'{point_id}_c0', 'firmware': '3.65', **(extra or {})}
        self.client.upsert(config.COLLECTION_NAME, points=[models.PointStruct(
            id=point_id, vector=[similarity, (1 - similarity ** 2) ** 0.5] + [0.0] * (config.VECTOR_SIZE - 2),
            payload=payload)])

    def test_source_payload_and_query_settings_survive(self):
        self.add(1, 'https://github.com/example/project/issues/1')
        result = self.retriever.search('  GPU crash  ')
        payload = result['sources'][0]['payload']
        self.assertEqual(payload['chunk'], 'Original source passage')
        self.assertEqual(payload['firmware'], '3.65')
        self.assertEqual(result['evidence_assessment'], 'not_assessed')
        self.assertEqual(self.encoder.inputs[0][0], QUERY_PREFIX + 'GPU crash')
        self.assertTrue(self.encoder.inputs[0][1]['normalize_embeddings'])

    def test_invalid_and_duplicate_sources_do_not_fill_the_limit(self):
        self.add(1, 'data/raw/wikis/README.md')
        self.add(2, 'https://github.com/example/project/issues/1')
        self.add(3, 'https://github.com/example/project/issues/1')
        self.add(4, 'https://github.com/example/project/issues/2')
        self.add(5, 'https://github.com/example/project/issues/3', text=' ')
        result = self.retriever.search('GPU crash', limit=5)
        self.assertEqual(len(result['sources']), 2)
        self.assertEqual(result['skipped'], {'missing_passage': 1, 'invalid_source_url': 1, 'duplicate_source': 1})

    def test_empty_collection_and_score_cutoff_return_no_candidates(self):
        self.assertEqual(self.retriever.search('unrelated')['status'], 'no_candidates')
        self.add(1, 'https://github.com/example/project/issues/1', similarity=0.5)
        result = self.retriever.search('unrelated', min_score=0.9)
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['evidence_assessment'], 'not_assessed')

    def test_exact_error_mention_precedes_higher_scoring_other_error(self):
        self.add(1, 'https://example.com/other', text='HTTP error 0x80436007', similarity=0.99)
        self.add(2, 'https://example.com/exact', text='HTTP error 0x80431068', similarity=0.8)
        result = self.retriever.search('Refresh error 0x80431068')
        self.assertEqual(result['sources'][0]['payload']['url'], 'https://example.com/exact')
        self.assertEqual(result['sources'][0]['matching_query_identifiers'], ['0x80431068'])
        self.assertAlmostEqual(result['sources'][0]['score'], 0.8, places=5)
        self.assertEqual(result['evidence_assessment'], 'not_assessed')

    def test_explicit_firmware_mention_is_preferred_without_filtering_other_sources(self):
        self.add(1, 'https://example.com/other', text='Triangle crash firmware 3.74', similarity=0.99)
        self.add(2, 'https://example.com/exact', text='Triangle crash firmware 3.73', similarity=0.8)
        result = self.retriever.search('Triangle crash on firmware 3.73')
        self.assertEqual(result['sources'][0]['matching_query_identifiers'], ['3.73'])
        self.assertEqual(len(result['sources']), 2)

    def test_invalid_inputs_fail_before_embedding(self):
        for kwargs in ({'question': ' '}, {'question': 'test', 'limit': 0},
                       {'question': 'test', 'limit': 21}, {'question': 'test', 'min_score': float('nan')}):
            with self.assertRaises(ValueError):
                self.retriever.search(**kwargs)
        self.assertEqual(self.encoder.inputs, [])

    def test_incompatible_collection_is_rejected(self):
        self.client.delete_collection(config.COLLECTION_NAME)
        self.client.create_collection(config.COLLECTION_NAME, vectors_config=models.VectorParams(
            size=8, distance=models.Distance.COSINE))
        with self.assertRaises(RetrievalError):
            self.retriever.search('test')

    def test_invalid_embedding_is_rejected(self):
        self.encoder.encode = lambda *args, **kwargs: [float('nan')] * config.VECTOR_SIZE
        with self.assertRaises(RetrievalError):
            self.retriever.search('test')

    def test_only_public_url_syntax_is_accepted(self):
        for url in ('file:///C:/wiki.md', 'http://localhost/a', 'http://127.0.0.1/a',
                    'https://user:secret@example.com/a', 'https://example.com/a b',
                    'https://example.com:invalid/a', 'http://localhost./a', 'https://[bad'):
            self.assertFalse(public_source_url(url), url)
        self.assertTrue(public_source_url('https://github.com/TheOfficialFloW/VitaShell/issues/408'))


if __name__ == '__main__':
    unittest.main()
