import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import messages from '../../../messages/zh.json';
import VideoAssembly from './VideoAssembly';

const mocks = vi.hoisted(() => ({
    project: {} as any,
    mergeVideos: vi.fn(),
    updateProject: vi.fn(),
}));

vi.mock('@/store/projectStore', () => ({
    useProjectStore: (select: any) => select({
        currentProject: mocks.project,
        updateProject: mocks.updateProject,
    }),
}));
vi.mock('@/lib/api', () => ({ api: { mergeVideos: mocks.mergeVideos } }));

function showExport(ready: number, total: number) {
    mocks.project = {
        id: 'test-project',
        frames: Array.from({ length: total }, (_, index) => ({
            id: `frame-${index}`,
            selected_video_id: index < ready ? `video-${index}` : null,
        })),
        video_tasks: [],
    };
    render(
        <NextIntlClientProvider locale="zh" messages={messages}>
            <VideoAssembly />
        </NextIntlClientProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: '导出' }));
    return screen.getByRole('button', { name: '合并并继续' });
}

describe('partial video export', () => {
    beforeEach(() => vi.clearAllMocks());

    it('allows the selected 9 of 54 shots to merge and blocks duplicate submissions', async () => {
        mocks.mergeVideos.mockReturnValue(new Promise(() => {}));
        const merge = showExport(9, 54);
        expect(merge).toBeEnabled();
        expect(screen.getByText(/无需全部生成/)).toBeInTheDocument();
        fireEvent.click(merge);
        expect(mocks.mergeVideos).toHaveBeenCalledWith('test-project');
        await waitFor(() => expect(merge).toBeDisabled());
    });

    it('keeps export disabled when no shots are selected', () => {
        expect(showExport(0, 54)).toBeDisabled();
    });

    it('allows a complete project to merge', () => {
        expect(showExport(2, 2)).toBeEnabled();
    });
});
