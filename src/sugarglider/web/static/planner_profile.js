import { PUBLIC_LOCAL_ROUTE_PROFILES } from "./local_routing.js";
import { PWA_STORES } from "./pwa_store.js";

export const DEFAULT_PLANNER_PROFILE = "trail_run";
const PREFERENCE_KEY = "planner-routing-profile";

// A current choice (including an unavailable one) always wins. The product default
// is explicit; metadata/DOM ordering must not choose the default activity.
export function initialLocalPlannerProfile(current, statuses) {
  if (current) return current;
  const available = (id) => statuses.some((status) => status.profile.id === id && status.available);
  if (available(DEFAULT_PLANNER_PROFILE)) return DEFAULT_PLANNER_PROFILE;
  // Stable public supported-profile order; never pick a disabled/unknown activity.
  return PUBLIC_LOCAL_ROUTE_PROFILES.find(available) ?? null;
}

// Only explicit activity changes are persisted, not implicit defaults or imported
// route identities. Use the existing optional storage; no database/schema change.
export function createPlannerProfilePreference(store) {
  let pending = Promise.resolve();
  return {
    async restore() {
      try {
        const value = await store.get(PWA_STORES.publicRuntime, PREFERENCE_KEY);
        return value?.schema_version === 1 && PUBLIC_LOCAL_ROUTE_PROFILES.includes(value.profile)
          ? value.profile : null;
      } catch { return null; }
    },
    remember(profile) {
      if (!PUBLIC_LOCAL_ROUTE_PROFILES.includes(profile)) return Promise.resolve(false);
      // Keep rapid choices ordered even if an earlier write fails.
      pending = pending.then(async () => {
        try {
          await store.put(PWA_STORES.publicRuntime, PREFERENCE_KEY, { schema_version: 1, profile });
          return Boolean(store.durable);
        } catch { return false; }
      });
      return pending;
    },
  };
}
