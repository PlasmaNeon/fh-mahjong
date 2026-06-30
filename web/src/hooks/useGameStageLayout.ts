import { useLayoutEffect, useState } from 'react';
import type { RefCallback } from 'react';
import { computeStageLayout, type StageLayoutOptions } from './computeStageLayout';

type StageBounds = {
    width: number;
    height: number;
};

export function useGameStageLayout(options: StageLayoutOptions = {}) {
    const [containerElement, setContainerElement] = useState<HTMLDivElement | null>(null);
    const [bounds, setBounds] = useState<StageBounds>({ width: 1600, height: 900 });

    useLayoutEffect(() => {
        const element = containerElement;
        if (!element) {
            return;
        }

        let frameId = 0;

        const updateBounds = () => {
            const rect = element.getBoundingClientRect();
            const nextWidth = Math.max(Math.floor(rect.width), 1);
            const nextHeight = Math.max(Math.floor(rect.height), 1);

            setBounds((previous) => {
                if (previous.width === nextWidth && previous.height === nextHeight) {
                    return previous;
                }
                return { width: nextWidth, height: nextHeight };
            });
        };

        const scheduleUpdateBounds = () => {
            if (frameId) {
                cancelAnimationFrame(frameId);
            }
            frameId = requestAnimationFrame(() => {
                frameId = 0;
                updateBounds();
            });
        };

        updateBounds();

        const resizeObserver = new ResizeObserver(() => {
            scheduleUpdateBounds();
        });
        resizeObserver.observe(element);
        if (element.parentElement) {
            resizeObserver.observe(element.parentElement);
        }

        const visualViewport = window.visualViewport;
        visualViewport?.addEventListener('resize', scheduleUpdateBounds);
        window.addEventListener('resize', scheduleUpdateBounds);
        window.addEventListener('orientationchange', scheduleUpdateBounds);

        return () => {
            if (frameId) {
                cancelAnimationFrame(frameId);
            }
            resizeObserver.disconnect();
            visualViewport?.removeEventListener('resize', scheduleUpdateBounds);
            window.removeEventListener('resize', scheduleUpdateBounds);
            window.removeEventListener('orientationchange', scheduleUpdateBounds);
        };
    }, [containerElement]);

    const layout = computeStageLayout(bounds.width, bounds.height, options);

    return {
        containerRef: setContainerElement as RefCallback<HTMLDivElement>,
        availableWidth: bounds.width,
        availableHeight: bounds.height,
        ...layout,
    };
}
