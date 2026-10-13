import { fireEvent, render, screen } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { describe, expect, it, vi } from 'vitest';
import messages from '../../../messages/zh.json';
import type { VideoParams } from '@/store/projectStore';
import { getR2vRouteModelId } from '@/lib/modelCatalog';
import VideoSidebar from './VideoSidebar';

vi.mock('./VideoQueue', () => ({ default: () => null }));

const params = {
    generationMode: 'r2v', model: 'happyhorse-1.1-r2v', duration: 5,
    resolution: '1080p', batchSize: 1, promptExtend: true,
    negativePrompt: '', audioUrl: '', generateAudio: false,
} as VideoParams;

function showSidebar(overrides: Partial<VideoParams> = {}) {
    const setParams = vi.fn();
    render(
        <NextIntlClientProvider locale="zh" messages={messages}>
            <VideoSidebar tasks={[]} onRemix={vi.fn()} params={{ ...params, ...overrides }} setParams={setParams} />
        </NextIntlClientProvider>,
    );
    return setParams;
}

describe('Motion model selection', () => {
    it('shows R2V cards and preserves the selected model for request routing', () => {
        const setParams = showSidebar();
        expect(screen.getByText('HappyHorse R2V')).toBeInTheDocument();
        expect(screen.queryByText('HappyHorse I2V')).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole('button', { name: /PixVerse C1 R2V/ }));
        const updated = setParams.mock.calls[0][0];
        expect(updated.model).toBe('pixverse-c1-r2v');
        expect(updated.generationMode).toBe('r2v');
        expect(getR2vRouteModelId(updated.model)).toBe(updated.model);
    });

    it('shows I2V cards when using first-frame mode', () => {
        showSidebar({ generationMode: 'i2v', model: 'happyhorse-1.1-i2v' });
        expect(screen.getByText('HappyHorse I2V')).toBeInTheDocument();
        expect(screen.queryByText('HappyHorse R2V')).not.toBeInTheDocument();
    });

    it('uses R2V duration controls rather than I2V fallback controls', () => {
        showSidebar({ model: 'viduq3-pro-r2v', duration: 5 });
        const duration = screen.getAllByRole('slider').find(input => input.getAttribute('max') === '16');
        expect(duration).toBeDefined();
    });
});
