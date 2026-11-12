'use strict';
(() => {
 const form = document.getElementById('debug-form');
 const question = document.getElementById('question');
 const response = document.getElementById('response');
 const status = document.getElementById('search-status');
 const submit = form.querySelector('[type="submit"]');
 const reviewEvidence = document.getElementById('review-evidence');
 let controller;
 let revision = 0;

 function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
 }
 function busy(value) {
  submit.disabled = value;
  submit.textContent = value ? (reviewEvidence.checked ? 'Reviewing…' : 'Searching…') : (reviewEvidence.checked ? 'Review evidence ↗' : 'Search sources ↗');
  form.setAttribute('aria-busy', String(value));
 }
 function reset() {
  revision++;
  controller?.abort();
  busy(false);
  status.textContent = '';
  response.hidden = true;
  question.setCustomValidity('');
 }
 function show(title, message, state) {
  response.replaceChildren(element('h3', title), element('p', message));
  response.dataset.state = state;
  response.hidden = false;
  status.textContent = title;
 }
 function sourceURL(value) {
  try {
   const url = new URL(value);
   return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url : null;
  } catch { return null; }
 }
 function validResult(data) {
  return data && data.evidence_assessment === 'not_assessed' &&
   ['candidates_require_review', 'no_candidates'].includes(data.status) &&
   Array.isArray(data.sources) &&
   (data.status === 'no_candidates' ? data.sources.length === 0 : data.sources.length > 0) &&
   data.sources.every(source => typeof source.payload?.chunk === 'string' &&
    source.payload.chunk.trim() && sourceURL(source.payload.url) &&
    Array.isArray(source.matching_query_identifiers));
 }
 function render(data, sentQuestion, assessment) {
  if (!data.sources.length) {
   show('No source passages returned', 'This search returned no eligible passages. Try a specific error code or a shorter description. This does not mean a fix does not exist.', 'empty');
   if (assessment) renderAssessment(assessment);
   return;
  }
  const reviewed = assessment?.status === 'assessed';
  show(`${data.sources.length} source ${data.sources.length === 1 ? 'passage' : 'passages'} ${reviewed ? 'reviewed with AI' : 'to review'}`,
   reviewed ? 'Read the evidence review and original passages below. No confirmed fix or diagnosis has been established for your situation.' :
   'These passages have not been assessed for relevance or support. No confirmed fix or diagnosis has been established for your situation.', 'results');
  const context = element('details', undefined, 'query-context');
  context.append(element('summary', 'Your search context'), element('p', sentQuestion));
  response.append(context);
  if (assessment) renderAssessment(assessment);
  const list = element('div', undefined, 'source-list');
  for (const [index, source] of data.sources.entries()) {
   const payload = source.payload;
   const url = sourceURL(payload.url);
   const card = element('article', undefined, 'source-card');
   card.append(element('div', `${String(index + 1).padStart(2, '0')}  /  ${url.hostname}`, 'source-origin'));
   const heading = element('h4');
   const link = element('a', typeof payload.title === 'string' && payload.title.trim() ? payload.title : 'Open original source');
   link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
   heading.append(link); card.append(heading);
   const tags = element('div', undefined, 'source-tags');
   const reviewed = assessment?.status === 'assessed';
   const row = reviewed ? assessment.decision.related_sources.find(item => item.point_id === source.point_id) : null;
   tags.append(element('span', row ? (row.relevance === 'direct' ? 'Addresses the question · AI review' : 'Similar report · AI review') : reviewed ? 'Not relevant · AI review' : 'Not assessed'));
   if (row && row.applicability !== 'matching') tags.append(element('span', row.applicability === 'mismatch' ? 'Different circumstances' : 'Applicability uncertain'));
   if (source.matching_query_identifiers.length) {
    tags.append(element('span', `Mentions: ${source.matching_query_identifiers.join(', ')}`));
   }
   card.append(tags);
   const passage = element('details', undefined, 'source-passage');
   passage.open = index === 0;
   passage.append(element('summary', 'Read retrieved passage'), element('blockquote', payload.chunk));
   card.append(passage);
   const metadata = ['hardware', 'firmware', 'source', 'doc_id', 'chunk_id']
    .filter(key => ['string', 'number'].includes(typeof payload[key]))
    .map(key => `${key.replaceAll('_', ' ')}: ${payload[key]}`);
   if (metadata.length) {
    const provenance = element('details', undefined, 'source-provenance');
    provenance.append(element('summary', 'Source details'), element('p', metadata.join(' · ')));
    card.append(provenance);
   }
   list.append(card);
  }
  response.append(list);
 }
 function validAssessment(data) {
  const decision = data?.decision;
  const states = ['supported_answer', 'related_reports_insufficient_support', 'no_relevant_evidence_retrieved', 'review_required', 'service_error'];
  if (!validResult(data?.retrieval) || !['assessed', 'no_relevant_evidence_retrieved', 'review_required', 'service_error'].includes(data.status) ||
      !decision || !states.includes(decision.status) || typeof decision.message !== 'string' ||
      !Array.isArray(decision.permitted_claims) || !Array.isArray(decision.related_sources)) return false;
  if (data.status === 'assessed' ? !states.slice(0, 3).includes(decision.status) :
      decision.status !== data.status || decision.permitted_claims.length || decision.related_sources.length) return false;
  if (decision.status !== 'supported_answer' && decision.permitted_claims.length) return false;
  return decision.related_sources.every(row => data.retrieval.sources.some(source => source.point_id === row.point_id && source.payload.url === row.url) &&
   ['direct', 'related'].includes(row.relevance) && ['matching', 'mismatch', 'unknown'].includes(row.applicability)) &&
   decision.permitted_claims.every(claim => typeof claim.claim === 'string' && typeof claim.qualification === 'string' &&
    Array.isArray(claim.limitations) && claim.limitations.every(item => typeof item === 'string') &&
    typeof claim.evidence_quote === 'string' && claim.evidence_quote.trim() &&
    data.retrieval.sources.some(source => source.point_id === claim.point_id && source.payload.url === claim.url && source.payload.chunk.includes(claim.evidence_quote)));
 }
 function renderAssessment(assessment) {
  const decision = assessment.decision;
  const titles = {supported_answer: 'Source-supported information', related_reports_insufficient_support: 'Related reports, insufficient support',
   no_relevant_evidence_retrieved: 'No relevant evidence in these results', review_required: 'Evidence review needs another check', service_error: 'Evidence review is unavailable'};
  const panel = element('section', undefined, 'evidence-panel');
  const messages = {supported_answer: 'These passages support the statements below within the circumstances described.',
   related_reports_insufficient_support: decision.message,
   no_relevant_evidence_retrieved: 'No relevant evidence was found in these retrieved passages. This search does not cover every source.',
   review_required: 'We couldn’t validate this review. Read the original passages or try again.',
   service_error: 'We couldn’t complete the evidence review. The retrieved passages are still available to read.'};
  panel.append(element('h4', titles[decision.status]), element('p', messages[decision.status]));
  if (decision.conflicting_evidence) panel.append(element('p', 'The retrieved reports conflict. No supported answer was established.'));
  for (const claim of decision.permitted_claims) {
   const item = element('article', undefined, 'evidence-claim');
   const source = assessment.retrieval.sources.find(source => source.point_id === claim.point_id);
   const link = element('a', source.payload.title || 'Read original source');
   link.href = sourceURL(claim.url).href; link.target = '_blank'; link.rel = 'noopener noreferrer';
   item.append(element('p', claim.claim), element('blockquote', claim.evidence_quote), link,
    element('p', claim.support === 'reported_success' ? 'A self-reported outcome, not a guaranteed repair.' : 'Read this account in the context of the linked source.'));
   for (const limitation of claim.limitations) item.append(element('p', limitation, 'claim-limitation'));
   panel.append(item);
  }
  panel.append(element('p', assessment.model_called ? 'Experimental AI review of this search’s passages. Check the original sources; this is not a verified repair or hardware diagnosis.' :
   'No passages were sent for AI review. This search does not establish that the archive has no relevant evidence.', 'review-note'));
  response.append(panel);
  status.textContent = titles[decision.status];
 }
 [question, document.getElementById('model'), document.getElementById('firmware'), document.getElementById('prior-tests')]
  .forEach(input => input.addEventListener('input', reset));
 document.addEventListener('question-mode-change', reset);
 reviewEvidence.addEventListener('change', reset);
 form.addEventListener('submit', async event => {
  event.preventDefault();
  reset();
  if (!question.value.trim()) {
   question.setCustomValidity('Describe a problem or enter a question.');
   question.reportValidity(); return;
  }
  const parts = [question.value.trim()];
  for (const [id, label] of [['model', 'Model'], ['firmware', 'Firmware'], ['prior-tests', 'Previous tests']]) {
   const value = document.getElementById(id).value.trim();
   if (value) parts.push(`${label}: ${value}`);
  }
  const sentQuestion = parts.join('\n');
  const current = revision;
  controller = new AbortController();
  const requestController = controller;
  const wantsReview = reviewEvidence.checked;
  const timeout = setTimeout(() => requestController.abort(), wantsReview ? 150000 : 90000);
  busy(true);
  status.textContent = wantsReview ? 'Retrieving passages and reviewing their support. This may take a little longer.' : 'Searching source passages. The first search may take longer while the local model loads.';
  try {
   const result = await fetch(wantsReview ? '/assess' : '/search', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: sentQuestion, limit: 5}), signal: requestController.signal
   });
   if (current !== revision) return;
   if (!result.ok && result.status !== 503) throw new Error([400, 422].includes(result.status) ? 'input' : 'service');
   const data = await result.json();
   if (current !== revision) return;
   if (wantsReview && validAssessment(data)) render(data.retrieval, sentQuestion, data);
   else if (result.ok && !wantsReview && validResult(data)) render(data, sentQuestion);
   else throw new Error('contract');
  } catch (error) {
   if (current !== revision) return;
   show(error.message === 'input' ? 'Check your question' : wantsReview ? 'Evidence review is unavailable' : 'Source search is unavailable',
    error.message === 'input' ? 'Please revise your question and try again. Your details are still here.' :
    error.name === 'AbortError' ? `The ${wantsReview ? 'review' : 'search'} took too long. Your details are still in this form; try again.` :
    wantsReview ? 'We couldn’t complete this review. Your details are still here. Try again later, or uncheck AI review to search sources.' :
    'We couldn’t complete this search. Your details are still here. Try again when the service is available.', 'error');
  } finally {
   clearTimeout(timeout);
   if (current === revision) busy(false);
  }
 });
})();
