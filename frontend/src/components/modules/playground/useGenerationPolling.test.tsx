import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { playgroundApi } from '@/lib/api';
import { useGenerationPolling } from './useGenerationPolling';
import { usePlaygroundStore, type PlaygroundGeneration } from './usePlaygroundStore';

vi.mock('@/lib/api', () => ({ playgroundApi: { getGenerationStatus: vi.fn() } }));

const generation: PlaygroundGeneration = {
  id: 'restored', mode: 't2i', model_id: 'gpt-image-2', prompt: 'test',
  input_media: [], parameters: {}, batch_size: 1, outputs: [],
  status: 'processing', created_at: '2026-10-20T08:00:00Z',
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(playgroundApi.getGenerationStatus).mockReset();
  usePlaygroundStore.setState({ history: [], activeGenerationIds: [], isGenerating: false });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('resumes polling history loaded after mount and surfaces credential failures', async () => {
  vi.mocked(playgroundApi.getGenerationStatus).mockResolvedValue({
    id: generation.id, status: 'failed', outputs: [], error: 'MULEROUTER_API_KEY missing',
  });
  const { unmount } = renderHook(useGenerationPolling);
  usePlaygroundStore.getState().setHistory([generation]);
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(usePlaygroundStore.getState().history[0]).toMatchObject({
    status: 'failed', error: 'MULEROUTER_API_KEY missing',
  });
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(playgroundApi.getGenerationStatus).toHaveBeenCalledTimes(1);
  unmount();
});

it('recovers from a transient poll failure and releases the active queue slot', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.mocked(playgroundApi.getGenerationStatus)
    .mockRejectedValueOnce(new Error('network interrupted'))
    .mockResolvedValue({ id: generation.id, status: 'completed', outputs: [] });
  usePlaygroundStore.getState().startGeneration(generation);
  const { unmount } = renderHook(useGenerationPolling);
  await act(() => vi.advanceTimersByTimeAsync(2000));
  expect(playgroundApi.getGenerationStatus).toHaveBeenCalledTimes(2);
  expect(usePlaygroundStore.getState().history[0].status).toBe('completed');
  expect(usePlaygroundStore.getState().activeGenerationIds).toEqual([]);
  expect(usePlaygroundStore.getState().isGenerating).toBe(false);
  unmount();
});

it('does not overlap requests or update state after unmount', async () => {
  let resolve!: (value: { id: string; status: string; outputs: [] }) => void;
  vi.mocked(playgroundApi.getGenerationStatus).mockReturnValue(new Promise((done) => { resolve = done; }));
  usePlaygroundStore.getState().startGeneration(generation);
  const { unmount } = renderHook(useGenerationPolling);
  await act(() => vi.advanceTimersByTimeAsync(6000));
  expect(playgroundApi.getGenerationStatus).toHaveBeenCalledTimes(1);
  unmount();
  await act(async () => { resolve({ id: generation.id, status: 'completed', outputs: [] }); });
  expect(usePlaygroundStore.getState().history[0].status).toBe('processing');
  expect(vi.getTimerCount()).toBe(0);
});
