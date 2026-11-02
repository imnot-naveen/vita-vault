"""Run the small, manually reviewable retrieval smoke fixture, without index writes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrieval.search import Retriever


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, default=Path(__file__).resolve().parents[1] / 'tests/retrieval_questions.json')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    cases = json.loads(args.fixture.read_text(encoding='utf-8'))
    retriever = Retriever()
    results = []
    try:
        for case in cases:
            started = time.monotonic()
            result = retriever.search(case['question'])
            expected = case['expected_any_urls']
            urls = [s['payload']['url'] for s in result['sources']]
            found = any(url in urls for url in expected) if expected else None
            results.append({**case, 'seconds': round(time.monotonic() - started, 3),
                            'expected_source_in_top5': found, 'result': result})
            print(json.dumps({'id': case['id'], 'expected_source_in_top5': found,
                              'top_sources': [(round(s['score'], 4), s['payload'].get('title'))
                                              for s in result['sources']]}, ensure_ascii=True))
    finally:
        retriever.close()
    known = [r for r in results if r['expected_any_urls']]
    report = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
              'known_source_cases': len(known),
              'known_source_hits_at5': sum(r['expected_source_in_top5'] for r in known),
              'limitations': 'Small development smoke fixture, including a title lookup; not a held-out quality estimate. Review negative relevance and unsupported-fix cases manually. No relevance cutoff has been calibrated.',
              'cases': results}
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    return 0 if all(r['expected_source_in_top5'] for r in known) else 1


if __name__ == '__main__':
    raise SystemExit(main())
