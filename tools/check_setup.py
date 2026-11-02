"""Read-only Vita Vault environment, offline model, and Qdrant checks."""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    sys.path.insert(0, str(args.repo.resolve()))
    import config

    report = {'python': sys.version, 'executable': sys.executable, 'packages': {}}
    for name in ('sentence-transformers', 'transformers', 'torch', 'qdrant-client',
                 'python-dotenv', 'requests', 'loguru', 'tqdm'):
        try:
            report['packages'][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report['packages'][name] = None

    try:
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(4)
        started = time.monotonic()
        model = SentenceTransformer(config.EMBED_MODEL, device='cpu', local_files_only=True)
        vector = model.encode('PS Vita GPU driver crash during native games',
                              normalize_embeddings=True, show_progress_bar=False)
        norm = float((vector @ vector) ** 0.5)
        report['model'] = {
            'id': config.EMBED_MODEL, 'offline_load': True,
            'vector_size': len(vector), 'expected_vector_size': config.VECTOR_SIZE,
            'finite': bool(torch.isfinite(torch.as_tensor(vector)).all()),
            'norm': norm, 'seconds': round(time.monotonic() - started, 2),
            'ok': len(vector) == config.VECTOR_SIZE and abs(norm - 1) < 0.001
                  and bool(torch.isfinite(torch.as_tensor(vector)).all()),
        }
    except Exception as exc:
        report['model'] = {'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}

    client = None
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=config.QDRANT_URL, timeout=5)
        names = [c.name for c in client.get_collections().collections]
        report['qdrant'] = {'reachable': True, 'collections': names,
                            'expected_collection': config.COLLECTION_NAME}
        if config.COLLECTION_NAME in names:
            info = client.get_collection(config.COLLECTION_NAME)
            params = info.config.params.vectors
            count = client.count(config.COLLECTION_NAME, exact=True).count
            report['qdrant'].update({
                'status': str(info.status), 'points': count,
                'vectors': params.model_dump(mode='json') if hasattr(params, 'model_dump')
                else {k: v.model_dump(mode='json') for k, v in params.items()},
                'dimension_matches': getattr(params, 'size', None) == config.VECTOR_SIZE,
            })
            points, _ = client.scroll(config.COLLECTION_NAME, limit=1,
                                       with_payload=True, with_vectors=True)
            report['qdrant']['sample_payload_keys'] = sorted(points[0].payload or {}) if points else []
            report['qdrant']['embedding_model_provenance'] = 'not established by collection dimensions'
            if points and report['model']['ok'] and isinstance(points[0].vector, list):
                import numpy as np
                text = (points[0].payload or {}).get('chunk')
                if text:
                    fresh = model.encode(text, normalize_embeddings=True, show_progress_bar=False)
                    stored = np.asarray(points[0].vector)
                    similarity = float(fresh @ stored / (np.linalg.norm(fresh) * np.linalg.norm(stored)))
                    report['qdrant']['sample_embedding_cosine'] = similarity
                    report['qdrant']['sample_embedding_matches'] = similarity > 0.999
    except Exception as exc:
        report['qdrant'] = {'reachable': False, 'error': type(exc).__name__ + ': ' + str(exc)}
    finally:
        if client is not None:
            client.close()

    output = json.dumps(report, indent=2)
    print(output)
    if args.report:
        args.report.write_text(output + '\n', encoding='utf-8')
    q = report['qdrant']
    return 0 if report['model']['ok'] and q.get('reachable') and q.get('dimension_matches') and q.get('points', 0) > 0 and q.get('sample_embedding_matches') else 1


if __name__ == '__main__':
    raise SystemExit(main())
