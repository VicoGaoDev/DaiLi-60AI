import { ref, onUnmounted } from "vue";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  options: {
    interval?: number;
    shouldStop: (data: T) => boolean;
    onResult: (data: T) => void;
  }
) {
  const { interval = 3000, shouldStop, onResult } = options;
  const active = ref(false);
  let timer: ReturnType<typeof setInterval> | null = null;

  function start() {
    stop();
    active.value = true;
    timer = setInterval(async () => {
      try {
        const data = await fetcher();
        onResult(data);
        if (shouldStop(data)) stop();
      } catch {
        stop();
      }
    }, interval);
  }

  function stop() {
    active.value = false;
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  onUnmounted(stop);

  return { start, stop, active };
}
