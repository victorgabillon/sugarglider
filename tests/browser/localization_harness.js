import { getLanguage, initializeLocalization, setLanguage, t, tr, setLocalizedText, speechDefaultLanguage } from '../../src/sugarglider/web/static/i18n.js';
import { FRENCH } from '../../src/sugarglider/web/static/translations.js';
import { openPwaStore, PWA_STORES, readLanguagePreference, writeLanguagePreference, readSpeechProviderPreference, writeSpeechProviderPreference } from '../../src/sugarglider/web/static/pwa_store.js';

const equal = (actual, expected, label) => { if (JSON.stringify(actual) !== JSON.stringify(expected)) throw Error(`${label}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`); };
export async function runLocalizationHarness() {
  const cases = [];
  const store = await openPwaStore();
  await store.remove(PWA_STORES.publicRuntime, 'application-language');
  await initializeLocalization(document);
  equal(getLanguage(), 'fr', 'No saved preference always defaults to French');
  equal(document.documentElement.lang, 'fr', 'Document declares French');
  equal(document.querySelector('#loop').textContent, 'Boucle', 'Static French message');
  equal(document.querySelector('#ai').getAttribute('aria-label'), 'Planifier une aventure avec ChatGPT', 'French accessible name');
  const original = [...document.querySelectorAll('#user-text,#place-name,#anecdote')].map(node => node.value ?? node.textContent);
  const dynamic = document.querySelector('#dynamic');
  setLocalizedText(dynamic, () => tr`Stop ${2}: ${'Start'}`);
  equal(dynamic.textContent, 'Étape 2 : Start', 'Parameters preserve original geographical names');
  await writeSpeechProviderPreference('platform');
  const calls = [], oldFetch = globalThis.fetch;
  globalThis.fetch = (...args) => { calls.push(args); throw Error('Localization must not use the network'); };
  try {
    await setLanguage('en');
    equal(document.documentElement.lang, 'en', 'English selected promptly');
    equal(dynamic.textContent, 'Stop 2: Start', 'Parameterized English binding');
    equal(document.querySelector('#ai').getAttribute('aria-label'), 'Plan an adventure with ChatGPT', 'English accessible name');
    equal(speechDefaultLanguage(), 'en-GB', 'English suggested speech language');
    equal(await readLanguagePreference(), 'en', 'English preference persisted in existing runtime store');
    equal(await readSpeechProviderPreference(), 'platform', 'Provider preference unchanged');
    await setLanguage('fr', { persist: false });
    await initializeLocalization(document);
    equal(getLanguage(), 'en', 'Reinitialization restores explicit English');
    equal([...document.querySelectorAll('#user-text,#place-name,#anecdote')].map(node => node.value ?? node.textContent), original, 'User text, place names and model prose preserved');
    for (const invalid of [null, {}, [], 'en', { schema_version: 1, value: 'de' }, { schema_version: 1, value: true }, { schema_version: 2, value: 'en' }]) {
      await store.put(PWA_STORES.publicRuntime, 'application-language', invalid);
      await initializeLocalization(document);
      equal(getLanguage(), 'fr', 'Malformed stored preference falls back to French');
    }
    equal(await writeLanguagePreference('de'), false, 'Unsupported preference is rejected');
    await Promise.all([setLanguage('fr'), setLanguage('en'), setLanguage('fr')]);
    equal(await readLanguagePreference(), 'fr', 'Rapid changes persist in choice order');
    equal(calls, [], 'No network request on language changes');
  } finally { globalThis.fetch = oldFetch; }
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'indexedDB');
  Object.defineProperty(globalThis, 'indexedDB', { configurable: true, get() { throw Error('Storage blocked'); } });
  try {
    equal(await readLanguagePreference(), 'fr', 'Unreadable preferences fall back to French');
    equal(await setLanguage('en'), false, 'Unavailable durable storage reported explicitly');
    equal(getLanguage(), 'en', 'Session language remains usable without storage');
    equal(document.querySelector('#language-storage-status').hidden, false, 'Persistence failure disclosed');
  } finally { if (descriptor) Object.defineProperty(globalThis, 'indexedDB', descriptor); else delete globalThis.indexedDB; }
  // Every translated interpolation uses source-defined parameter names only.
  for (const [key, value] of Object.entries(FRENCH)) {
    const sourceParameters = new Set([...key.matchAll(/\{(\w+)\}/g)].map(match => match[1]));
    for (const match of value.matchAll(/\{(\w+)\}/g)) if (!sourceParameters.has(match[1])) throw Error('Unknown translated parameter: ' + key);
  }
  equal(t('Licence Ouverte 2.0'), 'Licence Ouverte 2.0', 'Official licence names remain unchanged');
  await setLanguage('fr');
  store.close();
  cases.push('french_default_independent_of_device','explicit_english_persisted','invalid_and_unreadable_fallback','optional_storage_failure','parameterized_accessibility','original_user_place_and_story_text','speech_provider_unchanged','serialized_preference_writes','no_localization_network_requests');
  return cases;
}
