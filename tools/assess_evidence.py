"""Assess saved retrieval or a live question with the configured free model."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
from retrieval.assessor import OpenRouterClient, assess_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('retrieval_json', type=Path, nargs='?')
    parser.add_argument('--question', help='Retrieve locally, then assess the returned passages.')
    parser.add_argument('--limit', type=int, choices=range(1, 21), default=5)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--model', default=config.LLM_MODEL)
    args = parser.parse_args()
    if (args.retrieval_json is None) == (args.question is None):
        parser.error('Provide either a saved retrieval JSON file or --question.')
    try:
        client = OpenRouterClient(config.OPENROUTER_API_KEY, args.model)
        if args.retrieval_json is not None:
            retrieval = json.loads(args.retrieval_json.read_text(encoding='utf-8-sig'))
        else:
            from retrieval.search import InvalidInput, Retriever
            retriever = None
            try:
                retriever = Retriever()
                retrieval = retriever.search(args.question, limit=args.limit)
            except InvalidInput:
                retrieval = {'status': 'invalid_input'}
            except Exception:
                retrieval = {'status': 'service_error'}
            finally:
                if retriever is not None:
                    retriever.close()
    except (OSError, ValueError):
        print(json.dumps({'status': 'invalid_input', 'message': 'Read valid retrieval JSON and select an explicit :free model.'}))
        return 2
    result = assess_evidence(retrieval, client)
    result['retrieval'] = retrieval
    text = json.dumps(result, indent=2, ensure_ascii=True)
    if args.report:
        try:
            args.report.write_text(text + '\n', encoding='utf-8')
        except OSError:
            print(json.dumps({'status': 'service_error', 'message': 'Could not write the assessment report.'}))
            return 1
    print(text)
    return 1 if result['status'] == 'service_error' else 2 if result['status'] in ('review_required', 'invalid_input') else 0


if __name__ == '__main__':
    raise SystemExit(main())
