"""Conservative decisions over supplied passage reviews; no semantic assessor."""

import hashlib
import re

from retrieval.identifiers import RELEASE_VERSION, error_codes, release_versions


ALLOWED_SUPPORT = {
    'explanation': {'explanation'},
    'guidance': {'documented_guidance', 'reported_success'},
    'reported_remedy': {'reported_success'},
    'release_identification': {'documented_release'},
    # Community passages and reviewer labels do not independently confirm a fix.
    'confirmed_fix': set(),
}
SUPPORT = {'explanation', 'documented_guidance', 'documented_release', 'reported_success',
           'suggestion_without_outcome', 'symptoms_only', 'none'}
NOTICE = ('This decision enforces supplied reviews. It does not independently '
          'verify their meaning, source reliability, or a repair outcome.')
# Narrow English-language checks for observed failure modes, not an entailment
# classifier. Mixed quotes may require a narrower outcome quote or manual review.
TENTATIVE_OUTCOME = re.compile(
    r'\b(?:should|might|may|could|would|will)\s+(?:\w+\s+){0,2}'
    r'(?:work|help|fix|solve|resolve|install|download|launch)\b', re.I,
)
UNCONFIRMED_RELEASE = re.compile(
    r'\b(?:(?:try|retry)\s+(?:[\w-]+\s+){0,5}'
    r'|(?:will|should|might|may|could|would)\s+be\s+(?:fixed|resolved|addressed)\s+in\s+)'
    + RELEASE_VERSION.pattern, re.I,
)
CONDITIONAL_RELEASE = re.compile(
    r'\b(?:fixed|resolved|addressed)\s+in\s+' + RELEASE_VERSION.pattern
    + r"(?=\s+if\s+(?:it's|it is|that's|that is)\s+(?:that|the same)\s+(?:bug|issue|problem)\b)",
    re.I,
)
WITHDRAWN_OUTCOME = re.compile(r'\b(?:withdraw|withdrawn|retract|retracted)\b|\bproblem\s+persists\b|\b(?:crashed|failed)\s+again\b', re.I)


def passage_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _source_key(value):
    if type(value) is int and value >= 0:
        return ('int', value)
    if isinstance(value, str) and value.strip():
        return ('str', value)
    raise ValueError('Each source must have a nonempty string or nonnegative integer point_id.')


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def decide_evidence(retrieval, review):
    """Bind reviews to one question and every returned passage, then decide.

    supported_answer permits only the returned scoped claims with their evidence
    kinds and limitations. It never authorizes an unconditional fix or free-form
    advice. Review inputs remain assertions by their author/semantic assessor.
    """
    def result(status, message, **extra):
        return {'status': status, 'message': message, 'notice': NOTICE,
                'permitted_claims': [], 'related_sources': [], **extra}

    try:
        if not isinstance(retrieval, dict):
            raise ValueError('Retrieval must be an object.')
        state = retrieval.get('status')
        if state == 'service_error':
            return result('service_error', 'Retrieval is unavailable; evidence was not assessed.')
        if state == 'invalid_input':
            return result('invalid_input', 'Enter a valid retrieval question.')
        if state not in {'candidates_require_review', 'no_candidates'}:
            raise ValueError('Unsupported retrieval status.')
        question, sources = retrieval.get('question'), retrieval.get('sources')
        if not _text(question) or not isinstance(sources, list):
            raise ValueError('Retrieval must contain a question and a source list.')
        if state == 'no_candidates':
            if sources:
                raise ValueError('no_candidates cannot contain sources.')
            return result('no_relevant_evidence_retrieved',
                          'No eligible source passages remained in the retrieved results. '
                          'This does not establish that the archive has no relevant evidence.',
                          basis='no_candidates')
        if not sources:
            raise ValueError('Candidate retrieval must contain sources.')
        if not isinstance(review, dict) or type(review.get('schema_version')) is not int or review['schema_version'] != 1:
            raise ValueError('A schema_version 1 review is required.')
        if review.get('question') != question:
            raise ValueError('Review question does not match the retrieval question.')
        requested = review.get('requested_support')
        if not isinstance(requested, str) or requested not in ALLOWED_SUPPORT:
            raise ValueError('Review must specify a supported requested_support kind.')
        requested_codes = error_codes(question) if requested == 'release_identification' else set()
        rows = review.get('assessments')
        if not isinstance(rows, list):
            raise ValueError('Review assessments must be a list.')

        by_id = {}
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError('Every source must be an object.')
            key = _source_key(source.get('point_id'))
            payload = source.get('payload')
            if key in by_id or not isinstance(payload, dict):
                raise ValueError('Source IDs must be unique and payloads must be objects.')
            if not _text(payload.get('chunk')) or not _text(payload.get('url')):
                raise ValueError('Every source needs its original passage and URL.')
            by_id[key] = source

        reviewed = set()
        related, permitted = [], []
        conflict = False
        for assessment in rows:
            if not isinstance(assessment, dict):
                raise ValueError('Every assessment must be an object.')
            key = _source_key(assessment.get('point_id'))
            if key in reviewed or key not in by_id:
                raise ValueError('Review contains a duplicate or unknown source ID.')
            reviewed.add(key)
            source = by_id[key]
            payload = source['payload']
            if (assessment.get('url') != payload['url'] or
                    assessment.get('passage_sha256') != passage_hash(payload['chunk'])):
                raise ValueError('Review provenance does not match the returned passage.')
            relevance = assessment.get('relevance')
            applicability = assessment.get('applicability')
            support = assessment.get('support')
            if relevance not in ('direct', 'related', 'irrelevant'):
                raise ValueError('Invalid relevance label.')
            if applicability not in ('matching', 'mismatch', 'unknown', 'not_applicable'):
                raise ValueError('Invalid applicability label.')
            if not isinstance(support, str) or support not in SUPPORT:
                raise ValueError('Invalid support label.')
            limitations = assessment.get('limitations')
            reason = assessment.get('reason')
            if (not isinstance(limitations, list) or not all(_text(x) for x in limitations)
                    or not _text(reason)
                    or type(assessment.get('contradicted')) is not bool):
                raise ValueError('Each review needs a reason, limitations list and Boolean contradicted field.')
            quote = assessment.get('evidence_quote', '')
            claim = assessment.get('claim', '')
            if not isinstance(quote, str) or not isinstance(claim, str):
                raise ValueError('Claim and evidence_quote must be strings.')
            if support in {'explanation', 'documented_guidance', 'documented_release', 'reported_success'}:
                if not _text(claim) or not _text(quote) or quote not in payload['chunk']:
                    raise ValueError('Positive support needs a scoped claim and a verbatim passage quote.')
            if support == 'documented_release':
                claimed_versions = release_versions(claim)
                release_quote = CONDITIONAL_RELEASE.sub(' ', UNCONFIRMED_RELEASE.sub(' ', quote))
                if not claimed_versions:
                    support = 'none'
                    reason = 'The review did not establish an installable release version.'
                elif (not claimed_versions <= release_versions(quote)
                      or not (requested_codes | error_codes(claim)) <= error_codes(quote)):
                    raise ValueError('A release claim needs its version and exact error in the evidence quote.')
                elif TENTATIVE_OUTCOME.search(claim) or not claimed_versions <= release_versions(release_quote):
                    support = 'suggestion_without_outcome'
                    reason = 'The review offers a suggested or planned fix without documenting a released fix.'
            if support == 'reported_success':
                if TENTATIVE_OUTCOME.search(quote):
                    raise ValueError('A tentative prediction in a success quote requires review; it is not an observed outcome.')
                if not assessment['contradicted'] and WITHDRAWN_OUTCOME.search(quote):
                    raise ValueError('A withdrawn or recurring outcome cannot be labeled uncontradicted success.')
            if relevance == 'irrelevant':
                if support != 'none' or applicability != 'not_applicable' or claim.strip():
                    raise ValueError('Irrelevant passages cannot carry a supported claim.')
                continue
            if applicability == 'not_applicable':
                raise ValueError('Relevant passages need an applicability assessment.')
            item = {'point_id': source['point_id'], 'url': payload['url'],
                    'title': payload.get('title', ''), 'relevance': relevance,
                    'applicability': applicability, 'support': support,
                    'reason': reason, 'limitations': list(limitations)}
            related.append(item)
            conflict = conflict or assessment['contradicted']
            if (relevance == 'direct' and applicability == 'matching'
                    and support in ALLOWED_SUPPORT[requested]
                    and not assessment['contradicted']):
                permitted.append({**item, 'claim': claim, 'evidence_quote': quote,
                                  'qualification': ('Self-reported outcome; not a guaranteed repair.'
                                                    if support == 'reported_success' else
                                                    'Use only within the reviewed claim and circumstances.')})
        if reviewed != set(by_id):
            raise ValueError('Every returned source requires an assessment before a decision.')
        if permitted and not conflict:
            return result('supported_answer', 'Only the listed scoped claims are permitted.',
                          permitted_claims=permitted, related_sources=related)
        if related:
            if requested == 'release_identification':
                message = "The retrieved sources don't identify an installable release."
            elif requested == 'confirmed_fix':
                message = "I couldn't find a confirmed fix for your exact situation in the sources retrieved."
            else:
                message = ('Related reports were retrieved, but they do not sufficiently support '
                           'the requested answer under the supplied reviews.')
            return result('related_reports_insufficient_support', message,
                          related_sources=related, conflicting_evidence=conflict)
        return result('no_relevant_evidence_retrieved',
                      'No relevant evidence was found in the retrieved sources under the supplied reviews.',
                      basis='all_sources_reviewed_irrelevant')
    except (ValueError, TypeError, KeyError) as exc:
        return result('review_required', str(exc))
