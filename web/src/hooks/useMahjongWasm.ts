// Type declaration to let TypeScript know that the Go ruleset exposes these to window.
declare global {
    interface Window {
        Go: any;
        mahjongInit: (args: any[]) => string;
        mahjongGetValidActions: (stateBytes: Uint8Array, playerSeat: number) => number[];
    }
}

import { useState, useEffect } from 'react';

export function useMahjongWasm() {
    const [isWasmReady, setIsWasmReady] = useState(false);

    useEffect(() => {
        if (typeof window.mahjongGetValidActions === 'function') {
            setIsWasmReady(true);
            return;
        }

        const loadWasm = async () => {
            // The wasm_exec.js file exposes the global `Go` constructor.
            // This file is injected into the public dir during build.
            const go = new window.Go();
            try {
                const result = await WebAssembly.instantiateStreaming(
                    fetch('/mahjong.wasm'),
                    go.importObject
                );
                go.run(result.instance);
                setIsWasmReady(true);
                console.log('WASM Module Loaded System Status:', window.mahjongInit([]));
            } catch (err) {
                console.error('Failed to instantiate WebAssembly engine.', err);
            }
        };

        // Load the wasm_exec.js script dynamically
        if (!window.Go) {
            const script = document.createElement('script');
            script.src = '/wasm_exec.js';
            script.onload = loadWasm;
            document.body.appendChild(script);
        } else {
            loadWasm();
        }
    }, []);

    return { isWasmReady };
}
