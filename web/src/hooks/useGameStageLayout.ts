import { useLayoutEffect, useState } from 'react';
import type { RefCallback } from 'react';

type GameStageLayoutOptions = {
    stageWidth?: number;
    stageHeight?: number;
};

type StageBounds = {
    width: number;
    height: number;
};

export function useGameStageLayout(options: GameStageLayoutOptions = {}) {
    const stageWidth = options.stageWidth ?? 1600;
    const stageHeight = options.stageHeight ?? 900;
    const [containerElement, setContainerElement] = useState<HTMLDivElement | null>(null);
    const [bounds, setBounds] = useState<StageBounds>({
        width: stageWidth,
        height: stageHeight,
    });

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

                return {
                    width: nextWidth,
                    height: nextHeight,
                };
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
    }, [containerElement, stageWidth, stageHeight]);

    const scale = Math.min(bounds.width / stageWidth, bounds.height / stageHeight);
    const scaledWidth = stageWidth * scale;
    const scaledHeight = stageHeight * scale;

    return {
        containerRef: setContainerElement as RefCallback<HTMLDivElement>,
        stageWidth,
        stageHeight,
        availableWidth: bounds.width,
        availableHeight: bounds.height,
        scale,
        scaledWidth,
        scaledHeight,
        offsetX: Math.max((bounds.width - scaledWidth) / 2, 0),
        offsetY: Math.max((bounds.height - scaledHeight) / 2, 0),
    };
}
