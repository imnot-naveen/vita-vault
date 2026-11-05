"""Frontend routing preserves the API and does not expose repository files."""
import unittest
from fastapi.testclient import TestClient
from api.main import create_app

class NoSearch:
    def search(self, *_args, **_kwargs):
        raise AssertionError('Static requests must not search')
    def close(self):
        pass

class FrontendTests(unittest.TestCase):
    def test_ui_assets_and_existing_routes_share_one_origin(self):
        with TestClient(create_app(retriever_factory=NoSearch)) as client:
            self.assertIn('Search sources', client.get('/').text)
            self.assertIn("fetch('/search'", client.get('/search.js').text)
            self.assertEqual(client.get('/style.css').status_code, 200)
            self.assertEqual(client.get('/health').status_code, 200)
            self.assertIn('/search', client.get('/openapi.json').json()['paths'])
            self.assertEqual(client.post('/search', json={'question': ' '}).status_code, 422)

    def test_repository_files_are_not_public(self):
        with TestClient(create_app(retriever_factory=NoSearch)) as client:
            for path in ['/.env', '/config.py', '/api/main.py', '/%2e%2e/.env', '/.git/config']:
                self.assertEqual(client.get(path).status_code, 404, path)
