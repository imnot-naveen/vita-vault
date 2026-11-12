"""Read-only embedding search returning source-bearing candidate passages."""

import argparse
import ipaddress
import json
import math
import os
import re
import sys
from urllib.parse import urlsplit

from qdrant_client import QdrantClient, models

import config
from retrieval.identifiers import error_codes

# BAAI's short-query-to-passage instruction; passages remain unprefixed.
QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '


def query_identifiers(question):
    codes = error_codes(question)
    firmware = set(re.findall(r'\b(?:firmware|fw)\s*(?:version\s*)?[:=]?\s*(3\.\d{2})\b', question, re.IGNORECASE))
    return sorted(codes | firmware)


def matching_identifiers(payload, identifiers):
    text = str(payload.get('title', '')) + '\n' + str(payload.get('chunk', ''))
    return [value for value in identifiers
            if re.search(r'(?<![\w.])' + re.escape(value) + r'(?!\w|\.\d)', text, re.IGNORECASE)]


class RetrievalError(RuntimeError):
    """The model or collection cannot satisfy the retrieval contract."""


class InvalidInput(ValueError):
    """A question or search option is invalid."""


def public_source_url(value):
    """Check URL syntax; this does not verify remote reachability."""
    if not isinstance(value, str) or any(c.isspace() for c in value):
        return False
    try:
        url = urlsplit(value)
        host = url.hostname.rstrip('.') if url.hostname else None
        url.port  # Validate any explicit port as well as the hostname.
        if (url.scheme not in {'http', 'https'} or not host or url.username
                or url.password or host == 'localhost' or host.endswith(('.localhost', '.local'))):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            return '.' in host
    except ValueError:
        return False


class Retriever:
    def __init__(self, *, client=None, model=None):
        self._owns_client = client is None
        self.client = client if client is not None else QdrantClient(url=config.QDRANT_URL, timeout=10)
        self.model = model

    def close(self):
        if self._owns_client:
            self.client.close()

    def _embed(self, question):
        if self.model is None:
            # All embedding work stays local; missing cache files are an error.
            os.environ['HF_HUB_OFFLINE'] = '1'
            os.environ['TRANSFORMERS_OFFLINE'] = '1'
            os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
            import torch
            from sentence_transformers import SentenceTransformer
            torch.set_num_threads(4)
            self.model = SentenceTransformer(config.EMBED_MODEL, device='cpu', local_files_only=True)
        vector = self.model.encode(QUERY_PREFIX + question, normalize_embeddings=True,
                                   show_progress_bar=False)
        values = vector.tolist() if hasattr(vector, 'tolist') else list(vector)
        if len(values) != config.VECTOR_SIZE or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise RetrievalError('Query embedding must be a finite vector matching VECTOR_SIZE.')
        norm = math.sqrt(sum(v * v for v in values))
        if abs(norm - 1) > 0.001:
            raise RetrievalError('Query embedding must have unit length.')
        return values

    def search(self, question, *, limit=5, min_score=None):
        if not isinstance(question, str) or not question.strip():
            raise InvalidInput('Enter a nonempty question.')
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise InvalidInput('limit must be an integer from 1 to 20.')
        if min_score is not None and (not math.isfinite(min_score) or not -1 <= min_score <= 1):
            raise InvalidInput('min_score must be finite and between -1 and 1.')
        question = question.strip()
        info = self.client.get_collection(config.COLLECTION_NAME)
        vectors = info.config.params.vectors
        if (not isinstance(vectors, models.VectorParams) or vectors.size != config.VECTOR_SIZE
                or vectors.distance != models.Distance.COSINE):
            raise RetrievalError('Expected one unnamed cosine vector matching VECTOR_SIZE; check collection configuration.')
        hits = self.client.query_points(
            collection_name=config.COLLECTION_NAME,
            query=self._embed(question), limit=limit * 4,
            with_payload=True, with_vectors=False, score_threshold=min_score,
        ).points
        identifiers = query_identifiers(question)
        hits.sort(key=lambda hit: (len(matching_identifiers(hit.payload or {}, identifiers)), hit.score), reverse=True)
        sources = []
        seen_urls = set()
        skipped = {'missing_passage': 0, 'invalid_source_url': 0, 'duplicate_source': 0}
        for hit in hits:
            payload = hit.payload or {}
            text, url = payload.get('chunk'), payload.get('url')
            if not isinstance(text, str) or not text.strip():
                skipped['missing_passage'] += 1
                continue
            if not public_source_url(url):
                skipped['invalid_source_url'] += 1
                continue
            if url in seen_urls:
                skipped['duplicate_source'] += 1
                continue
            seen_urls.add(url)
            sources.append({'point_id': hit.id, 'score': hit.score,
                            'matching_query_identifiers': matching_identifiers(payload, identifiers),
                            'payload': payload})
            if len(sources) == limit:
                break
        return {
            'status': 'candidates_require_review' if sources else 'no_candidates',
            'question': question, 'collection': config.COLLECTION_NAME,
            'embedding_model': config.EMBED_MODEL, 'query_prefix': QUERY_PREFIX,
            'ranking': 'identifier_mentions_then_cosine', 'query_identifiers': identifiers,
            'min_score': min_score, 'evidence_assessment': 'not_assessed',
            'notice': 'Similarity ranks passages; it is not confidence, proof of a fix, or an evidence assessment.',
            'sources': sources, 'fetched_points': len(hits), 'skipped': skipped,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question')
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--min-score', type=float, help='Optional cosine cutoff; not calibrated as a relevance threshold.')
    args = parser.parse_args()
    retriever = None
    try:
        retriever = Retriever()
        result = retriever.search(args.question, limit=args.limit, min_score=args.min_score)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except InvalidInput as exc:
        print(json.dumps({'status': 'invalid_input', 'message': str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        # Backend exception strings may include credential-bearing URLs.
        print(json.dumps({'status': 'service_error', 'message': 'Retrieval unavailable. Run tools/check_setup.py and check the model cache and Qdrant collection.'}), file=sys.stderr)
        return 1
    finally:
        if retriever is not None:
            retriever.close()


if __name__ == '__main__':
    raise SystemExit(main())
