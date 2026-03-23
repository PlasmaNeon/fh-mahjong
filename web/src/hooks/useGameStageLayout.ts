import { useLayoutEffect, useRef, useState } from 'react';

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
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [bounds, setBounds] = useState<StageBounds>({
        width: stageWidth,
        height: stageHeight,
    });

    useLayoutEffect(() => {
        const element = containerRef.current;
        if (!element) {
            return;
        }

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

        updateBounds();

        const resizeObserver = new ResizeObserver(() => {
            updateBounds();
        });
        resizeObserver.observe(element);

        const visualViewport = window.visualViewport;
        visualViewport?.addEventListener('resize', updateBounds);
        window.addEventListener('orientationchange', updateBounds);

        return () => {
            resizeObserver.disconnect();
            visualViewport?.removeEventListener('resize', updateBounds);
            window.removeEventListener('orientationchange', updateBounds);
        };
    }, [stageWidth, stageHeight]);

    const scale = Math.min(bounds.width / stageWidth, bounds.height / stageHeight);
    const scaledWidth = stageWidth * scale;
    const scaledHeight = stageHeight * scale;

    return {
        containerRef,
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
