import { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { useMahjongWasm } from '../hooks/useMahjongWasm';
import { ActionType, PlayerAction, Suit, Tile, GameState } from '../proto/game';
import { motion } from 'framer-motion';

// Helper to stringify suit/honor tiles nicely
function getTileName(tile: Tile) {
    if (tile.suit === Suit.SUIT_JIHAI) {
        const honors: Record<number, string> = {
            1: 'East', 2: 'South', 3: 'West', 4: 'North',
            5: 'White', 6: 'Green', 7: 'Red'
        };
        return honors[tile.value] || 'Unknown Honor';
    }

    if (tile.suit === Suit.SUIT_UNKNOWN) {
        return `Flower ${tile.value}`;
    }

    const suitNames: Record<number, string> = {
        [Suit.SUIT_SOU]: 'Bamboo',
        [Suit.SUIT_MAN]: 'Characters',
        [Suit.SUIT_PIN]: 'Dots',
    };

    return `${tile.value} ${suitNames[tile.suit]}`;
}

export default function Game() {
    const { matchId } = useParams();
    const navigate = useNavigate();
    const { isConnected, socket, connect } = useSocket();
    const { gameState, mySeatId } = useGameState();
    const { isWasmReady } = useMahjongWasm();

    // Track the last drawn tile so we can delay its sorting animation
    const lastDrawnTileId = useRef<number | null>(null);

    useEffect(() => {
        if (!isConnected || !socket) {
            const storedToken = sessionStorage.getItem('mahjong_token');
            if (storedToken) {
                // Attempt to auto-reconnect instead of booting user
                connect(storedToken);
            } else {
                navigate('/');
            }
        }
    }, [isConnected, socket, navigate, connect]);

    if (!gameState) {
        return (
            <div className="flex h-screen w-full items-center justify-center">
                <h2 className="text-2xl text-green-400 animate-pulse">Waiting for Server to Deal...</h2>
            </div>
        );
    }

    if (mySeatId === null) {
        return (
            <div className="flex h-screen w-full items-center justify-center">
                <h2 className="text-2xl text-blue-400 animate-pulse">Assigning Seat...</h2>
            </div>
        );
    }

    // Identify who we are playing as
    // const me = gameState.players.find(p => p.seat === mySeatId);

    // If Wasm is loaded and it's our turn, fetch valid UI buttons locally!
    let validActions: ActionType[] = [];
    if (isWasmReady && gameState.activePlayer === mySeatId && gameState.phase === 2) {
        // 2 == GamePhase.PHASE_PLAYER_TURN
        const stateBytes = GameState.encode(gameState).finish();
        validActions = window.mahjongGetValidActions(stateBytes, mySeatId);
    }

    const handleAction = (type: ActionType, tile?: Tile) => {
        if (!socket || socket.readyState !== WebSocket.OPEN) return;

        const action: PlayerAction = {
            type: type,
            tile: tile,
            meldTiles: [],
            targetPlayer: 0,
            isRobbingKong: false,
            isBottomTile: false,
            isBloomingKong: false
        };

        const buffer = PlayerAction.encode(action).finish();
        socket.send(buffer);
    };

    // Helper to get SVG filename for a tile
    const getTileSvgName = (tile: Tile) => {
        let suitChar = '';
        switch (tile.suit) {
            case Suit.SUIT_MAN: suitChar = 'm'; break;
            case Suit.SUIT_PIN: suitChar = 'p'; break;
            case Suit.SUIT_SOU: suitChar = 's'; break;
            case Suit.SUIT_JIHAI: suitChar = 'z'; break;
            default: return 'Blank.svg';
        }
        return `${tile.value}${suitChar}.svg`;
    };

    // Helper for sorting tiles: Man -> Pin -> Sou -> Jihai
    const getSuitOrder = (suit: Suit) => {
        switch (suit) {
            case Suit.SUIT_MAN: return 1;
            case Suit.SUIT_PIN: return 2;
            case Suit.SUIT_SOU: return 3;
            case Suit.SUIT_JIHAI: return 4;
            default: return 5;
        }
    };

    // Render helper for tiles
    const TileComponent = ({ tile, isInteractive = false, size = 'normal' }: { tile: Tile, isInteractive?: boolean, size?: 'normal' | 'small' }) => {
        const isWild = gameState.wildTiles.some(w => w.suit === tile.suit && w.value === tile.value);
        const svgName = getTileSvgName(tile);

        return (
            <div
                className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${isInteractive ? 'interactive' : ''} ${size === 'small' ? 'small' : ''}`}
                onClick={() => isInteractive && handleAction(ActionType.ACTION_DISCARD, tile)}
                style={{
                    padding: 0,
                    border: 'none',
                    backgroundColor: 'transparent',
                    boxShadow: isWild ? '0 0 10px rgba(234, 179, 8, 0.8)' : '1px 1px 3px rgba(0,0,0,0.5)'
                }}
            >
                <img
                    src={`/Regular_shortnames/${svgName}`}
                    alt={getTileName(tile)}
                    style={{ width: '100%', height: '100%', display: 'block', borderRadius: '4px' }}
                    draggable="false"
                />
            </div>
        );
    };

    return (
        <div className="mahjong-table">

            {/* Center Info HUD */}
            <div className="center-info text-white text-center">
                <div className="text-2xl font-black text-green-400 mb-2 tracking-widest uppercase">Match {matchId?.substring(0, 5)}</div>
                <div className="text-gray-300 mb-4 text-sm font-mono">
                    Phase: {gameState.phase} | Wall Left: {gameState.wallCount}
                </div>
                {gameState.wildTiles.length > 0 && (
                    <div className="bg-yellow-900 border border-yellow-500 text-yellow-200 px-3 py-1 rounded text-sm mb-4">
                        WILD: {getTileName(gameState.wildTiles[0])}
                    </div>
                )}

                {/* Action Buttons Overlay within HUD Context */}
                {gameState.activePlayer === mySeatId ? (
                    <div className="text-green-400 font-bold animate-pulse mt-4">YOUR TURN</div>
                ) : (
                    <div className="text-gray-400 text-sm mt-4">Waiting for Seat {gameState.activePlayer}...</div>
                )}

                <div className="flex gap-2 mt-4 pointer-events-auto">
                    {validActions.includes(ActionType.ACTION_TSUMO) && (
                        <button onClick={() => handleAction(ActionType.ACTION_TSUMO)} className="bg-yellow-500 hover:bg-yellow-400 text-black font-bold py-2 px-4 rounded shadow">
                            TSUMO
                        </button>
                    )}
                    {validActions.includes(ActionType.ACTION_KAN) && (
                        <button onClick={() => handleAction(ActionType.ACTION_KAN)} className="bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-4 rounded shadow">
                            KONG
                        </button>
                    )}
                </div>
            </div>

            {/* Loop through all 4 players to place their hands and discards */}
            {gameState.players.map((p) => {
                const diff = (p.seat - mySeatId + 4) % 4;
                const positions = ['bottom', 'right', 'top', 'left'];
                const posStr = positions[diff];

                const isMe = diff === 0;
                const canDiscard = isMe && gameState.activePlayer === mySeatId && gameState.phase === 2;

                return (
                    <div key={p.seat} className="contents">

                        {/* Discard Pool Area */}
                        <div className={`discard-pool discard-pool-${posStr}`}>
                            {p.discards.map((t, i) => (
                                <div key={i} className={`pov-${posStr} small`}>
                                    <TileComponent tile={t} size="small" />
                                </div>
                            ))}
                        </div>

                        {/* Hand Area */}
                        <div className={`hand-container-${posStr}`}>
                            <div className={`hand-inner hand-inner-${posStr}`}>
                                {/* Render actual tiles for self, backs for others (unless server sent open hands for replay) */}
                                {isMe || p.closedHand.length > 0 ? (
                                    (() => {
                                        // If hand size modulo 3 is 2 (e.g. 14, 11, 8), the last tile is the active drawn tile
                                        const hasDrawnTile = p.closedHand.length % 3 === 2;
                                        const baseTiles = hasDrawnTile ? p.closedHand.slice(0, -1) : [...p.closedHand];
                                        const drawnTile = hasDrawnTile ? p.closedHand[p.closedHand.length - 1] : null;

                                        // Persist the ID of what was drawn so we know to delay its insertion animation
                                        if (hasDrawnTile && drawnTile && isMe) {
                                            lastDrawnTileId.current = drawnTile.id;
                                        }

                                        const sortedBaseTiles = [...baseTiles].sort((a, b) => {
                                            const suitA = getSuitOrder(a.suit);
                                            const suitB = getSuitOrder(b.suit);
                                            if (suitA !== suitB) return suitA - suitB;
                                            return a.value - b.value;
                                        });

                                        const renderedTiles = [...sortedBaseTiles];
                                        if (drawnTile) {
                                            renderedTiles.push(drawnTile);
                                        }

                                        return (
                                            <>
                                                {renderedTiles.map((t) => {
                                                    // Only apply the delayed insertion animation to our specific player hand
                                                    const isRecentlyDrawn = isMe && lastDrawnTileId.current === t.id && !hasDrawnTile;
                                                    const isCurrentlyDrawnSlot = hasDrawnTile && drawnTile && t.id === drawnTile.id;

                                                    return (
                                                        <motion.div
                                                            layoutId={t.id.toString()}
                                                            initial={false}
                                                            key={t.id}
                                                            style={{ zIndex: isRecentlyDrawn ? 0 : 10 }}
                                                            transition={{
                                                                layout: {
                                                                    duration: isRecentlyDrawn ? 0.15 : 0.25,
                                                                    delay: isRecentlyDrawn ? 0.05 : 0,
                                                                    ease: "easeInOut"
                                                                }
                                                            }}
                                                            className={`pov-${posStr} ${!isMe ? 'small' : ''} ${isCurrentlyDrawnSlot ? 'drawn-tile' : ''}`}
                                                        >
                                                            <TileComponent
                                                                tile={t}
                                                                isInteractive={canDiscard}
                                                                size={isMe ? 'normal' : 'small'}
                                                            />
                                                        </motion.div>
                                                    );
                                                })}
                                            </>
                                        );
                                    })()
                                ) : (
                                    Array(p.handSize).fill(0).map((_, i) => (
                                        <div key={`back-${i}`} className={`pov-${posStr} small`}>
                                            <div className="mahjong-tile-back small" />
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
