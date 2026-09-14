import { ref } from "vue";

export type TransientImageLoadPhase = "idle" | "retrying" | "failed";

export interface TransientImageLoadState {
  phase: TransientImageLoadPhase;
  attempts: number;
  nonce: number;
  source: string;
}

const DEFAULT_RETRY_DELAYS_MS = [800, 1500, 2500];

function createIdleState(source = ""): TransientImageLoadState {
  return {
    phase: "idle",
    attempts: 0,
    nonce: 0,
    source,
  };
}

export function appendTransientImageNonce(url: string, nonce: number) {
  if (!url || nonce <= 0 || url.startsWith("data:") || url.startsWith("blob:")) {
    return url;
  }
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}__retry=${nonce}`;
}

export function useTransientImageLoad(delaysMs: number[] = DEFAULT_RETRY_DELAYS_MS) {
  const states = ref<Record<string, TransientImageLoadState>>({});
  const timers = new Map<string, ReturnType<typeof setTimeout>>();

  function clearTimer(key: string) {
    const timer = timers.get(key);
    if (!timer) return;
    clearTimeout(timer);
    timers.delete(key);
  }

  function writeState(key: string, state?: TransientImageLoadState) {
    const next = { ...states.value };
    if (!state) {
      delete next[key];
    } else {
      next[key] = state;
    }
    states.value = next;
  }

  function getState(key: string): TransientImageLoadState {
    return states.value[key] || createIdleState();
  }

  function syncSource(key: string, source: string) {
    const normalizedSource = source || "";
    const current = states.value[key];
    if (!normalizedSource) {
      clearTimer(key);
      writeState(key, undefined);
      return;
    }
    if (!current) {
      writeState(key, createIdleState(normalizedSource));
      return;
    }
    if (current.source === normalizedSource) return;
    clearTimer(key);
    writeState(key, createIdleState(normalizedSource));
  }

  function markLoaded(key: string, source: string) {
    syncSource(key, source);
    const current = states.value[key];
    if (!current || current.phase === "idle") return;
    writeState(key, {
      ...current,
      phase: "idle",
    });
  }

  function scheduleRetry(key: string, source: string) {
    syncSource(key, source);
    const current = states.value[key];
    if (!current) return false;
    if (current.phase === "retrying") return true;
    const delayMs = delaysMs[current.attempts];
    if (typeof delayMs !== "number") {
      writeState(key, {
        ...current,
        phase: "failed",
      });
      return false;
    }

    const attempts = current.attempts + 1;
    writeState(key, {
      ...current,
      phase: "retrying",
      attempts,
    });
    clearTimer(key);
    const timer = setTimeout(() => {
      timers.delete(key);
      const latest = states.value[key];
      if (!latest) return;
      writeState(key, {
        ...latest,
        phase: "idle",
        attempts,
        nonce: latest.nonce + 1,
      });
    }, delayMs);
    timers.set(key, timer);
    return true;
  }

  function reset(key: string) {
    clearTimer(key);
    writeState(key, undefined);
  }

  function clearExcept(keys: Set<string>) {
    for (const key of Object.keys(states.value)) {
      if (keys.has(key)) continue;
      clearTimer(key);
      writeState(key, undefined);
    }
  }

  function dispose() {
    for (const key of timers.keys()) {
      clearTimer(key);
    }
    states.value = {};
  }

  return {
    states,
    getState,
    syncSource,
    markLoaded,
    scheduleRetry,
    reset,
    clearExcept,
    dispose,
  };
}
