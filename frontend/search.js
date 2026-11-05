'use strict';
(() => {
 const form = document.getElementById('debug-form');
 const question = document.getElementById('question');
 const response = document.getElementById('response');
 const status = document.getElementById('search-status');
 const submit = form.querySelector('[type="submit"]');
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
  submit.textContent = value ? 'Searching…' : 'Search sources ↗';
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
 function render(data, sentQuestion) {
  if (!data.sources.length) {
   show('No source passages returned', 'This search returned no eligible passages. Try a specific error code or a shorter description. This does not mean a fix does not exist.', 'empty');
   return;
  }
  show(`${data.sources.length} source ${data.sources.length === 1 ? 'passage' : 'passages'} to review`,
   'These passages have not been assessed for relevance or support. No confirmed fix or diagnosis has been established for your situation.', 'results');
  const context = element('details', undefined, 'query-context');
  context.append(element('summary', 'Your search context'), element('p', sentQuestion));
  response.append(context);
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
   tags.append(element('span', 'Not assessed'));
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
 [question, document.getElementById('model'), document.getElementById('firmware'), document.getElementById('prior-tests')]
  .forEach(input => input.addEventListener('input', reset));
 document.addEventListener('question-mode-change', reset);
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
  const timeout = setTimeout(() => requestController.abort(), 90000);
  busy(true);
  status.textContent = 'Searching source passages. The first search may take longer while the local model loads.';
  try {
   const result = await fetch('/search', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question: sentQuestion, limit: 5}), signal: requestController.signal
   });
   if (current !== revision) return;
   if (!result.ok) throw new Error([400, 422].includes(result.status) ? 'input' : 'service');
   const data = await result.json();
   if (current !== revision) return;
   if (!validResult(data)) throw new Error('contract');
   render(data, sentQuestion);
  } catch (error) {
   if (current !== revision) return;
   show(error.message === 'input' ? 'Check your question' : 'Source search is unavailable',
    error.message === 'input' ? 'Please revise your question and try again. Your details are still here.' :
    error.name === 'AbortError' ? 'The search took too long. Your details are saved in this form; try searching again.' :
    'We couldn’t complete this search. Your details are still here. Try again when the service is available.', 'error');
  } finally {
   clearTimeout(timeout);
   if (current === revision) busy(false);
  }
 });
})();
