import { useEffect } from 'react';
import { playgroundApi } from '@/lib/api';
import { usePlaygroundStore, type PlaygroundGeneration } from './usePlaygroundStore';

/** Poll all unfinished history, including restored and retried generations. */
export function useGenerationPolling() {
  useEffect(() => {
    let disposed = false;
    const inFlight = new Set<string>();

    const poll = () => {
      const { history } = usePlaygroundStore.getState();
      for (const generation of history) {
        if (!['pending', 'processing'].includes(generation.status) || inFlight.has(generation.id)) continue;
        inFlight.add(generation.id);
        void playgroundApi.getGenerationStatus(generation.id).then((result) => {
          if (disposed) return;
          const current = usePlaygroundStore.getState().history.find((item) => item.id === generation.id);
          if (!current) return;
          usePlaygroundStore.getState().updateGeneration({
            ...current,
            status: result.status as PlaygroundGeneration['status'],
            error: result.error,
            outputs: result.outputs as PlaygroundGeneration['outputs'],
          });
        }).catch((error) => {
          // A transient network failure must not leave a permanent spinner.
          if (!disposed) console.error('[Playground] Status poll failed:', generation.id, error);
        }).finally(() => inFlight.delete(generation.id));
      }
    };

    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);
}
