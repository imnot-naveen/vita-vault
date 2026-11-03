"""Apply supplied evidence reviews to saved retrieval JSON without model calls."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrieval.evidence import decide_evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('retrieval_json', type=Path)
    parser.add_argument('review_json', type=Path)
    args = parser.parse_args()
    try:
        retrieval = json.loads(args.retrieval_json.read_text(encoding='utf-8-sig'))
        review = json.loads(args.review_json.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        print(json.dumps({'status': 'review_required',
                          'message': 'Could not read valid retrieval/review JSON.'}))
        return 2
    decision = decide_evidence(retrieval, review)
    print(json.dumps(decision, indent=2, ensure_ascii=True))
    if decision['status'] == 'service_error':
        return 1
    if decision['status'] in {'review_required', 'invalid_input'}:
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
