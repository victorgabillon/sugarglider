import { t, tr, getLanguage, speechDefaultLanguage, onLanguageChange, setLocalizedText } from "./i18n.js";
import { createAdventureController } from "./adventure_controller.js";
import { createAdventureModel, AdventureModelError } from "./adventure_model.js";
import { createAdventureSpeech } from "./adventure_speech.js";
import { createAdventureElevationSampler } from "./adventure_elevation.js";
import { readSpeechProviderPreference, writeSpeechProviderPreference, readUiPreference, writeUiPreference } from "./pwa_store.js";
import { PUBLIC_PROFILE_METADATA } from "./public_profile_metadata.js";
import { adventureEndpointFailure } from "./adventure_grounding.js";

const progressText = { understanding: "Understanding your wishes and proposing places…", checking_places: "Checking locations on this device…",
  reviewing: "Review the required places below.", routing: "Calculating actual offline routes…", comparing: "Comparing routes and measuring terrain…",
  researching_stories: "Researching stories for the places actually reached…", improving: "Improving suggestions using the measured results…", ready: "Your adventure is ready." };
const speechText = { completed: "Transcription added. Check it before Generate; tap Speak to add more.", partial: "Recording ended before final recognition. Check this draft carefully; tap Speak to add more.", cancelled: "Microphone cancelled.",
  unavailable: "Speech recognition is unavailable. You can type your adventure.", permission_denied: "Microphone permission was not granted. Typing still works.",
  language_unavailable: "This language is unavailable for on-device recognition. Try another speech language or type your request.",
  no_match: "No speech was recognized. Try again or type your request.", timeout: "Speech recognition timed out. You can try again.", busy: "The previous speech request is still finishing." };

export function initializeAdventureDialog({ root, launcher, launchers = [launcher], planner, getContext, canOpen = () => true,
  onBusy = () => {}, onResult, onChooseStart, onChooseEnd, onRegions = null, searchLocations = null, geocoding = () => null,
  model = createAdventureModel(), speech = createAdventureSpeech(), elevation = createAdventureElevationSampler() }) {
  const element = id => root.querySelector(`#adventure-${id}`);
  // Only an explicit choice is persisted. Restoring it never records audio;
  // the native provider disclosure still asks for consent on every use.
  let providerChoiceVersion = 0, providerWrite = Promise.resolve();
  void readSpeechProviderPreference().then(mode => {
    if (providerChoiceVersion === 0 && mode === "platform") element("speech-service").value = "platform";
  });
  element("speech-service").addEventListener("change", () => {
    providerChoiceVersion++;
    const mode = element("speech-service").value === "platform" ? "platform" : "device";
    providerWrite = providerWrite.then(() => writeSpeechProviderPreference(mode));
  });
  let voiceMode = null, voiceFinishing = false;
  let epoch = 0, accountBusy = false, aiBusy = false, voiceBusy = false, accountAbort = null, speechAbort = null, planningAbort = null;
  let accountState = { accounts: [], selected_account: null, models: [] }, review = null, successfulClose = false;
  let contextReady = false, displayedContext = null, planningFinished = Promise.resolve(), finishPlanning = null;
  const controller = createAdventureController({ model, planner, measureElevations: elevation.measure, reviewEndpoint: locateEndpoint,
    onProgress: stage => { setLocalizedText(element("progress"), () => t(progressText[stage] ?? "Planning…")); },
    confirmProposal: confirm, lifecycleTarget: null });
  const connected = () => accountState.accounts.find(account => account.id === accountState.selected_account);
  const message = text => { setLocalizedText(element("error"), () => t(text)); };
  function render() {
    const account = connected(), eligible = Boolean(account?.connected && account.plan_usage);
    for (const id of ["connect", "add-account", "account", "refresh-models", "model", "research", "structured", "refine", "language", "speech-service", "keep-start", "keep-end"]) {
      element(id).disabled = accountBusy || aiBusy || voiceBusy;
    }
    for (const id of ["choose-start", "choose-end"]) element(id).disabled = accountBusy || voiceBusy;
    element("text").disabled = aiBusy;
    element("generate").disabled = !contextReady || accountBusy || aiBusy || voiceBusy || !eligible || !element("model").value || element("text").value.length > 8000 || element("text").value.trim().length < 3;
    element("microphone").disabled = aiBusy || voiceBusy || accountBusy || element("text").value.length >= 8000;
    element("microphone").setAttribute("aria-pressed", String(voiceBusy));
    element("stop-speech").hidden = !voiceBusy;
    element("finish-speech").hidden = !voiceBusy || voiceMode !== "on_device";
    element("finish-speech").disabled = voiceFinishing;
    element("cancel").hidden = !aiBusy;
    element("sign-out").hidden = !account;
    element("sign-out").disabled = accountBusy;
    element("add-account").hidden = !accountState.accounts.length;
    element("add-account").disabled ||= accountState.accounts.length >= 4;
    setLocalizedText(element("connect"), () => account ? t("Reconnect this account") : t("Sign in with ChatGPT"));
    // Reconnection remains available without making account management the
    // first task for an already connected user.
    const settings = element("account-settings");
    if (eligible) settings.append(element("connect"));
    else settings.before(element("connect"));
    setLocalizedText(element("account-status"), () => accountBusy ? t("Connecting to ChatGPT…") : eligible ? t("ChatGPT connected. Routing stays on this device.")
        : account?.connected ? t("This account has not granted ChatGPT plan usage. Reconnect with an eligible account.") : t("Connect your ChatGPT account to begin."));
    root.setAttribute("aria-busy", String(aiBusy || accountBusy));
  }
  function endpointContext(context) {
    return { ...context, start: element("keep-start").checked ? context.start : null,
      end: element("keep-end").checked ? context.end : null,
      endpointSnapPolicy: { start: element("keep-start").checked ? context.endpointSnapPolicy?.start ?? "near" : "near",
        end: element("keep-end").checked ? context.endpointSnapPolicy?.end ?? "near" : "near" } };
  }
  function renderEndpoints() {
    if (!displayedContext) return;
    const context = endpointContext(displayedContext);
    const label = (kind, point) => point ? `${kind}: ${point.name || t("chosen map point")} · ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}` : tr`${kind}: from your description, or choose on map`;
    setLocalizedText(element("start"), () => tr`${label(t("Start"), context.start)} · ${label(t("End"), context.end)}. Loops return to Start.`);
  }
  function setAccounts(value) {
    if (!Array.isArray(value.accounts) || value.accounts.length > 4 || !Array.isArray(value.models) || value.models.length > 100) throw new AdventureModelError("invalid_response");
    accountState = value;
    const select = element("account"); select.replaceChildren();
    for (const account of value.accounts) select.append(new Option(account.label, account.id));
    if (!value.accounts.length) select.append(new Option(t("No account connected"), ""));
    select.value = value.selected_account ?? "";
    const models = element("model"), prior = models.value; models.replaceChildren();
    for (const item of value.models) models.append(new Option(item.label, item.id));
    if (!value.models.length) models.append(new Option(t("No available model loaded"), ""));
    if (value.models.some(item => item.id === prior)) models.value = prior;
  }
  async function accountOperation(action, discover = true) {
    if (accountBusy) return;
    stopSpeech(); controller.cancel();
    accountAbort?.abort(); const abort = new AbortController(), owned = epoch;
    accountAbort = abort; accountBusy = true; message(""); render();
    try {
      let value = await action(abort.signal);
      if (owned !== epoch || !root.open || abort.signal.aborted) return;
      setAccounts(value);
      if (discover && connected()?.connected && connected()?.plan_usage) {
        value = await model.models(abort.signal);
        if (owned !== epoch || !root.open || abort.signal.aborted) return;
        setAccounts(value);
      }
      if (Object.hasOwn(value, "remote_revocation_confirmed") && !value.remote_revocation_confirmed) message(t("Signed out on this device. Remote revocation could not be confirmed; review this connection in your ChatGPT account settings."));
    } catch (error) { if (owned === epoch && root.open && !abort.signal.aborted) message(error.message); }
    finally { if (accountAbort === abort) { accountBusy = false; accountAbort = null; render(); } }
  }
  let returnFocus = launcher;
  async function open(source = returnFocus) {
    if (!canOpen() || aiBusy || accountBusy) return false;
    returnFocus = source;
    epoch++; successfulClose = false; contextReady = false; displayedContext = null; message(""); element("progress").textContent = "";
    element("regions").hidden = true; element("endpoint-search").hidden = true;
    element("region-status").hidden = true;
    setLocalizedText(element("start"), () => t("Describe where to start and finish, or choose on the map. Loops return to Start."));
    for (const kind of ["start", "end"]) { element(`keep-${kind}`).checked = true; element(`keep-${kind}`).parentElement.hidden = true; }
    element("review").hidden = true; element("input").hidden = false;
    // Leave the keyboard closed until the user chooses typing. Speech remains
    // visible on a phone, and opening never activates the microphone.
    root.showModal(); element("close").focus({ preventScroll: true }); root.querySelector(".adventure-body").scrollTop = 0; render();
    const owned = epoch;
    try {
      const context = await getContext();
      if (owned === epoch && root.open) {
        displayedContext = context; contextReady = true;
        for (const kind of ["start", "end"]) element(`keep-${kind}`).parentElement.hidden = !context[kind];
        renderEndpoints(); render();
      }
    } catch { if (owned === epoch && root.open) {
      setLocalizedText(element("start"), () => t("Choose an available installed region before generating. Your current route is kept."));
      element("region-status").textContent = element("start").textContent;
      element("region-status").hidden = false;
    } }
    void accountOperation(() => model.status());
    return true;
  }
  function stopSpeech() {
    speechAbort?.abort(); speechAbort = null; speech.cancel();
    voiceBusy = false; voiceMode = null; voiceFinishing = false; render();
  }
  function cancel() {
    planningAbort?.abort(); controller.cancel(); accountAbort?.abort(); stopSpeech();
    review?.resolve(null); review = null;
  }
  function close() { cancel(); if (root.open) root.close(); }
  for (const action of launchers) action.addEventListener("click", () => { void open(action); });
  element("close").addEventListener("click", close);
  element("regions").addEventListener("click", async () => {
    const finishing = planningFinished; close(); await finishing; onRegions?.();
  });
  root.addEventListener("cancel", cancel);
  root.addEventListener("close", () => {
    epoch++; cancel();
    if (!successfulClose) (returnFocus.getClientRects().length ? returnFocus : launchers.find(action => action.getClientRects().length))?.focus({ preventScroll: true });
  });
  element("cancel").addEventListener("click", cancel);
  element("text").addEventListener("input", render);
  element("connect").addEventListener("click", () => { void accountOperation(signal => model.signIn(connected()?.id ?? null, signal)); });
  element("add-account").addEventListener("click", () => { void accountOperation(signal => model.signIn(null, signal)); });
  element("sign-out").addEventListener("click", () => { cancel(); void accountOperation(() => model.signOut(), false); });
  element("account").addEventListener("change", () => { const id = element("account").value; void accountOperation(() => model.select(id)); });
  element("refresh-models").addEventListener("click", () => { void accountOperation(signal => model.models(signal), false); });
  for (const kind of ["start", "end"]) {
    element(`keep-${kind}`).addEventListener("change", renderEndpoints);
    element(`choose-${kind}`).addEventListener("click", async () => {
      const finishing = planningFinished; close(); await finishing;
      if (kind === "start") onChooseStart(); else onChooseEnd();
    });
  }
  element("stop-speech").addEventListener("click", stopSpeech);
  element("finish-speech").addEventListener("click", () => {
    if (!voiceBusy || voiceFinishing || voiceMode !== "on_device") return;
    const owned = speechAbort;
    voiceFinishing = true; setLocalizedText(element("speech-status"), () => t("Finishing transcription…")); render();
    void speech.stop().catch(() => { if (speechAbort === owned && voiceBusy) setLocalizedText(element("speech-status"), () => t("Unable to finish recognition. Cancel and try again.")); });
  });
  let speechLanguageVersion = 0;
  const refreshSpeechDefault = () => { setLocalizedText(element("language").options[0], () => tr`Suggested language (${speechDefaultLanguage()})`); };
  refreshSpeechDefault();
  void readUiPreference("adventure-speech-language", ["fr-FR", "en-GB", "en-US"], "").then(value => {
    if (speechLanguageVersion === 0 && value) element("language").value = value;
  });
  element("language").addEventListener("change", () => {
    speechLanguageVersion++;
    void writeUiPreference("adventure-speech-language", element("language").value, ["", "fr-FR", "en-GB", "en-US"]);
  });
  onLanguageChange(() => { refreshSpeechDefault(); render(); renderEndpoints(); });
  element("microphone").addEventListener("click", async () => {
    if (voiceBusy || aiBusy) return;
    providerChoiceVersion++;
    const abort = new AbortController(), owned = epoch; speechAbort = abort; voiceBusy = true; render();
    try {
      const available = await speech.status();
      if (abort.signal.aborted || owned !== epoch || !root.open) return;
      voiceMode = element("speech-service").value === "platform" ? "platform" : available.mode;
      render();
      if (!["on_device", "platform"].includes(voiceMode)) { setLocalizedText(element("speech-status"), () => t(speechText.unavailable)); return; }
      const language = element("language").value || speechDefaultLanguage();
      setLocalizedText(element("speech-status"), () => voiceMode === "on_device" ? tr`Listening in ${language} on this device. Tap Done speaking when finished.` : t("Android will ask before using your configured speech service. It may send audio to its provider."));
      const result = await speech.start(language, voiceMode, abort.signal);
      if (abort.signal.aborted || owned !== epoch || !root.open) return;
      setLocalizedText(element("speech-status"), () => t(speechText[result.status] ?? speechText.unavailable));
      if (["completed", "partial"].includes(result.status)) {
        // Append to the current editor, including edits made while listening.
        // Keep all text if the combined draft exceeds the sending limit; the
        // user can shorten it rather than silently losing either contribution.
        const text = element("text");
        text.value = [text.value.trimEnd(), result.text].filter(Boolean).join("\n");
        if (text.value.length > 8000) setLocalizedText(element("speech-status"), () => t("Transcription added. Shorten the text to 8,000 characters before Generate or more recording."));
        text.focus();
      }
    } catch (error) { if (speechAbort === abort && owned === epoch && root.open) setLocalizedText(element("speech-status"), () => error.name === "AbortError" ? t(speechText.cancelled) : t(speechText.unavailable)); }
    finally { if (speechAbort === abort) { speechAbort = null; voiceBusy = false; voiceMode = null; voiceFinishing = false; render(); } }
  });
  element("generate").addEventListener("click", async () => {
    if (aiBusy || accountBusy || voiceBusy || element("generate").disabled) return;
    const owned = epoch, abort = new AbortController(); planningAbort = abort;
    planningFinished = new Promise(resolve => { finishPlanning = resolve; });
    aiBusy = true; message(""); element("regions").hidden = true; render(); onBusy(true);
    try {
      const contextStarted = performance.now();
      const context = endpointContext(await getContext({ includePlaces: true, useStart: element("keep-start").checked, useEnd: element("keep-end").checked, signal: abort.signal }));
      if (owned !== epoch || !root.open || abort.signal.aborted) return;
      const output = await controller.run({ prompt: element("text").value, modelId: element("model").value, context,
        responseLanguage: getLanguage(), contextPreparationMs: performance.now() - contextStarted, research: element("research").checked, structured: element("structured").checked, refine: element("refine").checked }, abort.signal);
      if (owned !== epoch || !root.open) return;
      await onResult(output);
      successfulClose = true; root.close();
    } catch (error) {
      if (owned === epoch && root.open) {
        const code = error.code;
        message(error.name === "AbortError" ? t("Planning cancelled. Your previous route is kept.")
          : ["loop_requires_waypoint", "invalid_endpoints"].includes(code) ? t("Choose the missing endpoint or describe some places that can be checked in this region. Your previous route is kept.")
          : typeof error.message === "string" && !/^[a-z_]+$/.test(error.message) ? error.message : t("No valid adventure could be calculated. Your previous route is kept."));
        if (error.parameters) setLocalizedText(element("error"), () => t(error.message, { ...error.parameters,
          endpoint: t(error.parameters.endpoint === "end" ? "End" : "Start") }));
        element("regions").hidden = !onRegions || !["adventure_endpoint_outside_coverage", "no_covering_routing_pack"].includes(code);
      }
    } finally {
      aiBusy = false; review = null; element("review").hidden = true; element("endpoint-search").hidden = true; element("input").hidden = false;
      if (planningAbort === abort) planningAbort = null;
      render(); onBusy(false);
      finishPlanning?.(); finishPlanning = null;
    }
  });
  function locateEndpoint({ kind, resolution }, signal) {
    const failure = adventureEndpointFailure(resolution, kind), query = resolution.proposed_coordinate.name;
    element("input").hidden = true; element("review").hidden = true; element("endpoint-search").hidden = false;
    setLocalizedText(element("endpoint-title"), () => t("Find {place}", { place: query }));
    setLocalizedText(element("endpoint-explanation"), () => t(failure.message, failure.parameters));
    element("endpoint-status").textContent = "";
    element("endpoint-attribution").textContent = geocoding()?.attribution ?? "";
    const searchButton = element("search-ign"); searchButton.disabled = !searchLocations || !geocoding()?.available;
    if (searchButton.disabled) setLocalizedText(element("endpoint-status"), () => t("Online address search is unavailable. You can still choose a point on the map."));
    const results = element("endpoint-results"); results.replaceChildren();
    return new Promise(resolve => {
      const finish = value => {
        signal.removeEventListener("abort", abort); searchButton.onclick = null;
        element("endpoint-search").hidden = true; review = null; resolve(value);
      };
      const abort = () => finish(null);
      const receipt = { resolve: finish }; review = receipt;
      const current = () => review === receipt && root.open && !signal.aborted;
      function rows(locations) {
        results.replaceChildren();
        for (const location of locations) {
          const button = document.createElement("button"); button.type = "button"; button.className = "button secondary";
          setLocalizedText(button, () => `${t(location.source === "online" ? "Online results" : "On this device")} · ${location.name} · ${location.secondaryLabel ?? ""} · ${location.lat.toFixed(5)}, ${location.lon.toFixed(5)}`);
          button.addEventListener("click", () => { if (current()) finish(location); }); results.append(button);
        }
      }
      rows(resolution.matches.map(row => ({ ...row, source: "local" })));
      searchButton.onclick = async () => {
        if (!current() || searchButton.disabled) return;
        searchButton.disabled = true; setLocalizedText(element("endpoint-status"), () => t("Searching online…"));
        try {
          const response = await searchLocations(query, { signal });
          if (!current()) return;
          rows([...response.local, ...response.remote]);
          setLocalizedText(element("endpoint-status"), () => [t(response.localMessage), t(response.remoteMessage)].filter(Boolean).join(" "));
        } catch (error) { if (current()) setLocalizedText(element("endpoint-status"), () => t(error.message)); }
        finally { if (current()) searchButton.disabled = false; }
      };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) abort(); else (results.querySelector("button") ?? searchButton).focus();
    });
  }
  function confirm({ proposal, grounding, unsupportedHard, startResolution, endResolution }, signal) {
    const mandatory = proposal.places.filter(place => place.importance === "mandatory");
    if (!mandatory.length && !unsupportedHard.length && !startResolution && !endResolution) return Promise.resolve({ confirmedMandatoryIds: [] });
    setLocalizedText(element("review-title"), () => startResolution || endResolution ? t("Review Start and End") : t("Confirm required places"));
    element("input").hidden = true; element("review").hidden = false;
    setLocalizedText(element("interpretation"), () => `${proposal.interpretation} · ${t(PUBLIC_PROFILE_METADATA[proposal.intent.activity].display_name)} · ${(proposal.intent.target_distance_m / 1000).toFixed(1)} km`);
    const required = element("required"); required.replaceChildren();
    for (const [kind, resolution] of [[t("Start"), startResolution], [t("End"), endResolution]]) {
      if (!resolution) continue;
      const point = resolution.coordinate, description = document.createElement("p");
      setLocalizedText(description, () => resolution.evidence === "unique_exact_local_name"
        ? tr`${kind} found on this device: ${point.name} · ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}. Use it only if it is the place you intended.`
        : ["selected_ign_result", "selected_local_result"].includes(resolution.evidence)
          ? tr`${kind} selected from place search: ${point.name} · ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}. Routing availability and access still need checking.`
        : tr`Proposed ${kind}: ${point.name} · ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}. This AI coordinate has no matching local place record. Check the location before continuing; its name and access are unverified.`);
      required.append(description);
    }
    const checks = mandatory.map(place => {
      const local = grounding.places.find(item => item.id === place.id), label = document.createElement("label"), checkbox = document.createElement("input");
      checkbox.type = "checkbox"; checkbox.dataset.placeId = place.id; checkbox.disabled = local?.status !== "grounded";
      label.className = "adventure-check"; label.append(checkbox, document.createTextNode(tr`Keep ${local?.local_name ?? place.location.name} required${checkbox.disabled ? t(" — no usable location found; edit your request") : ""}`));
      if (local?.local_name && local.local_name !== place.location.name) label.append(document.createTextNode(tr` (AI suggestion: ${place.location.name})`));
      required.append(label); return checkbox;
    });
    const limitations = element("limitations"); limitations.replaceChildren();
    let acknowledge = null;
    if (unsupportedHard.length) {
      const label = document.createElement("label"); acknowledge = document.createElement("input"); acknowledge.type = "checkbox"; label.className = "adventure-check";
      label.append(acknowledge, document.createTextNode(tr`Continue knowing these required preferences remain unknown: ${unsupportedHard.map(wish => wish.metric.replaceAll("_", " ")).join(", ")}.`)); limitations.append(label);
    }
    const refresh = () => { element("confirm").disabled = checks.some(check => !check.checked) || Boolean(acknowledge && !acknowledge.checked); };
    [...checks, acknowledge].filter(Boolean).forEach(check => check.addEventListener("change", refresh)); refresh();
    return new Promise(resolve => {
      const finish = value => { signal.removeEventListener("abort", abort); review = null; resolve(value); };
      const abort = () => finish(null);
      review = { resolve: finish, checks, acknowledge };
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) abort(); else element("confirm").focus();
    });
  }
  element("confirm").addEventListener("click", () => {
    if (!review || element("confirm").disabled) return;
    review.resolve({ confirmedMandatoryIds: review.checks.map(check => check.dataset.placeId), acceptUnknownHardPreferences: review.acknowledge?.checked ?? false });
  });
  render();
  return Object.freeze({ open, cancel, clear: () => { cancel(); elevation.clear(); }, busy: () => aiBusy });
}
