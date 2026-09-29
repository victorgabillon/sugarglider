import { routeChoiceMarkup, renderRouteChoices, resultsNotice } from '../../src/sugarglider/web/static/route_results.js';
import { state, invalidateCandidates, currentDisplayedCandidates, selectedCandidate } from '../../src/sugarglider/web/static/state.js';
import { exportCanonicalCandidate } from '../../src/sugarglider/web/static/local_gpx_export.js';
import { initializeAppShell } from '../../src/sugarglider/web/static/app_shell.js';
const assert = (condition, message) => { if (!condition) throw Error(message); };
const same = (a, b, message) => assert(JSON.stringify(a) === JSON.stringify(b), message);
export async function runResultsHarness() {
  const cases = [];
  const empty = { request: { status: 'idle' }, generationResult: null, resultsInvalidated: false };
  for (const [label, value, expected] of [
    ['never', empty, 'Your next route starts in Plan'],
    ['zero', { ...empty, generationResult: { candidates: [] } }, 'No matching route found'],
    ['failed', { ...empty, request: { status: 'error' } }, 'Couldn’t find routes this time'],
    ['cancelled', { ...empty, request: { status: 'cancelled' } }, 'Planning cancelled'],
    ['stale', { ...empty, resultsInvalidated: true }, 'Your plan has changed'],
    ['running', { ...empty, resultsInvalidated: true, request: { status: 'running' } }, 'Finding your routes…'],
  ]) { assert(resultsNotice(value)[0] === expected, label); cases.push(label); }
  const fixture = await (await fetch('/tests/fixtures/pr41_local_gpx.json')).json();
  const first = fixture.candidate;
  // Deliberately sparse native-style analysis: unknown must not become zero.
  first.rank = 1; first.route.analysis = { repetition: { available: false, repeated_distance: { share: 0 } } };
  first.diagnostics = { within_tolerance: true };
  const second = structuredClone(first); second.id = 'alternate'; second.rank = 2;
  second.route.name = 'Alternate route';
  const candidates = [first, second], original = JSON.stringify(candidates), initial = structuredClone(state);
  const container = document.createElement('div'); document.body.append(container);
  try {
    state.generationResult = { candidates }; state.selectedSignature = first.id;
    assert(selectedCandidate() === first, 'authoritative default'); cases.push('default_authority');
    const expectedGpx = await exportCanonicalCandidate(second).blob.text();
    let selectedCalls = 0;
    function select(id) { selectedCalls++; state.selectedSignature = id; renderRouteChoices(container, currentDisplayedCandidates(), state.selectedSignature, select); }
    renderRouteChoices(container, candidates, state.selectedSignature, select);
    same([...container.querySelectorAll('button')].map(b => b.dataset.candidateId), candidates.map(c => c.id), 'returned order'); cases.push('order_ids');
    assert(container.textContent.includes('Repeated travel Unknown') && !container.textContent.includes('Nature score'), 'honest comparison'); cases.push('unknown_not_zero');
    const button = container.querySelectorAll('button')[1]; button.focus(); button.click();
    assert(selectedCandidate() === second && selectedCalls === 1, 'selection changes only existing authority'); cases.push('alternate_selection');
    assert(document.activeElement.dataset.candidateId === second.id, 'keyboard focus survives'); cases.push('focus_preserved');
    assert(document.activeElement.getAttribute('aria-pressed') === 'true' && document.activeElement.textContent.includes('✓ Selected'), 'non-color selection'); cases.push('selected_semantics');
    same(await exportCanonicalCandidate(selectedCandidate()).blob.text(), expectedGpx, 'selected GPX unchanged'); cases.push('selected_gpx');
    assert(JSON.stringify(candidates) === original, 'immutable identity/order/geometry'); cases.push('no_result_mutation');
    renderRouteChoices(container, [first], first.id, select);
    assert(container.querySelectorAll('button').length === 1 && !container.textContent.includes('Recommended'), 'one confident result'); cases.push('one_result');
    invalidateCandidates();
    assert(currentDisplayedCandidates().length === 0 && selectedCandidate() === null && state.resultsInvalidated, 'stale result not exportable'); cases.push('stale_invalidation');
    invalidateCandidates(); assert(state.resultsInvalidated, 'notice survives repeated editing'); cases.push('stale_notice_durable');
  } finally { Object.assign(state, initial); container.remove(); }
  const markup = new DOMParser().parseFromString(await (await fetch('/static/index.html')).text(), 'text/html');
  markup.querySelectorAll('script, link').forEach(n => n.remove());
  for (const [width, height, scale] of [[360,800,1],[390,844,1],[412,915,1],[1280,800,1],[1440,900,1],[390,420,1],[360,640,2]]) {
    const frame = document.createElement('iframe'); frame.style.cssText = `width:${width}px;height:${height}px`;
    const load = new Promise(resolve => frame.onload = resolve); frame.srcdoc = markup.documentElement.outerHTML; document.body.append(frame); await load;
    const doc = frame.contentDocument, link = doc.createElement('link'); link.rel = 'stylesheet'; link.href = '/static/styles.css'; const styled = new Promise(resolve => link.onload = resolve); doc.head.append(link); await styled;
    doc.documentElement.style.fontSize = `${16*scale}px`;
    const shell = initializeAppShell({ document: doc, resizeMap() {} }); shell.show('routes');
    renderRouteChoices(doc.getElementById('candidate-list'), candidates, first.id, () => {});
    doc.getElementById('selected-route-panel').classList.remove('hidden');
    await new Promise(resolve => setTimeout(resolve, 100));
    const exportButton = doc.getElementById('download-gpx'); exportButton.scrollIntoView();
    assert(doc.documentElement.scrollWidth <= width, 'no horizontal overflow');
    assert(doc.getElementById('map').clientHeight > 100, `map remains useful: ${width}x${height} scale ${scale}, actual ${doc.getElementById("map").clientHeight}`);
    assert(exportButton.getBoundingClientRect().height >= 44, 'touch export');
    assert(doc.querySelector('.candidate-select').getBoundingClientRect().height >= 44, 'touch selection');
    assert(exportButton.getBoundingClientRect().bottom <= height, 'export reachable');
    assert(!doc.querySelector('.metrics-disclosure').open, 'details initially calm');
    assert(doc.getElementById('error-code').closest('details'), 'raw error codes are diagnostic only');
    cases.push(`workspace_${width}_${height}_${scale}x`); shell.destroy(); frame.remove();
  }
  return cases;
}
