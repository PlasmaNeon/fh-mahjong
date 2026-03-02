// @ts-nocheck
import { useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { game } from '../proto/game';
import { motion } from 'framer-motion';

// Helper to stringify suit/honor tiles nicely
function getTileName(tile: game.ITile) {
    if (tile.suit === game.Suit.SUIT_JIHAI) {
        const honors: Record<number, string> = {
            1: 'East', 2: 'South', 3: 'West', 4: 'North',
            5: 'White', 6: 'Green', 7: 'Red'
        };
        return honors[tile.value] || 'Unknown Honor';
    }

    if (tile.suit === game.Suit.SUIT_UNKNOWN) {
        return `Flower ${tile.value}`;
    }

    const suitNames: Record<number, string> = {
        [game.Suit.SUIT_SOU]: 'Bamboo',
        [game.Suit.SUIT_MAN]: 'Characters',
        [game.Suit.SUIT_PIN]: 'Dots',
    };

    return `${tile.value} ${suitNames[tile.suit]}`;
}

export default function Game() {
    const { matchId } = useParams();
    const navigate = useNavigate();
    const { isConnected, socket, connect } = useSocket();
    const { gameState, mySeatId } = useGameState();

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
    const myPlayer = gameState.players.find((p: any) => p.seat === mySeatId);
    // @ts-ignore: TS doesn't think validActions exists on player, but it does
    const validActions: any[] = myPlayer?.validActions || [];

    const handleAction = (type: game.ActionType, tile?: game.ITile, meldTiles: game.ITile[] = []) => {
        if (!socket || socket.readyState !== WebSocket.OPEN) return;

        const action = game.PlayerAction.create({
            type: type,
            tile: tile,
            meldTiles: meldTiles,
            targetPlayer: 0,
            isRobbingKong: false,
            isBottomTile: false,
            isBloomingKong: false
        });

        const buffer = game.PlayerAction.encode(action).finish();
        socket.send(buffer);
    };

    // Helper to get SVG filename for a tile
    const getTileSvgName = (tile: game.ITile) => {
        let suitChar = '';
        switch (tile.suit) {
            case game.Suit.SUIT_MAN: suitChar = 'm'; break;
            case game.Suit.SUIT_PIN: suitChar = 'p'; break;
            case game.Suit.SUIT_SOU: suitChar = 's'; break;
            case game.Suit.SUIT_JIHAI: suitChar = 'z'; break;
            default: return 'Blank.svg';
        }
        return `${tile.value}${suitChar}.svg`;
    };

    // Helper for sorting tiles: Man -> Pin -> Sou -> Jihai
    const getSuitOrder = (suit: game.Suit) => {
        switch (suit) {
            case game.Suit.SUIT_MAN: return 1;
            case game.Suit.SUIT_PIN: return 2;
            case game.Suit.SUIT_SOU: return 3;
            case game.Suit.SUIT_JIHAI: return 4;
            default: return 5;
        }
    };

    // Render helper for tiles
    const TileComponent = ({ tile, isInteractive = false, size = 'normal' }: { tile: game.ITile, isInteractive?: boolean, size?: 'normal' | 'small' }) => {
        const isWild = gameState.wildTiles.some((w: any) => w.suit === tile.suit && w.value === tile.value);
        const svgName = getTileSvgName(tile);

        return (
            <div
                className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${isInteractive ? 'interactive' : ''} ${size === 'small' ? 'small' : ''}`}
                onClick={() => isInteractive && handleAction(game.ActionType.ACTION_DISCARD, tile)}
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
                {gameState.wildTiles && gameState.wildTiles.length > 0 && (
                    <div className="bg-yellow-900 border border-yellow-500 text-yellow-200 px-3 py-1 rounded text-sm mb-4">
                        WILD: {getTileName(gameState.wildTiles[0])}
                        <br />
                        DEBUG: ID={gameState.players.find((p: any) => p.seat === mySeatId)?.drawnTileId != null ? gameState.players.find((p: any) => p.seat === mySeatId)?.drawnTileId + ' (Len:' + gameState.players.find((p: any) => p.seat === mySeatId)?.closedHand.length + ')' : 'null (Len:' + gameState.players.find((p: any) => p.seat === mySeatId)?.closedHand.length + ')'}
                    </div>
                )}

                {/* Action Buttons Overlay within HUD Context */}
                {gameState.activePlayer === mySeatId ? (
                    <div className="text-green-400 font-bold animate-pulse mt-4">YOUR TURN</div>
                ) : (
                    <div className="text-gray-400 text-sm mt-4">Waiting for Seat {gameState.activePlayer}...</div>
                )}

                {/* Interrupt Window Actions (Chii, Pong, Kang, Ron) */}
                {gameState.phase === 3 && validActions.length > 0 && (
                    <div className="flex gap-4 mt-6 pointer-events-auto justify-center">
                        {validActions.map((action: any, i: number) => {
                            let label = 'Unknown';
                            let color = 'bg-gray-600 hover:bg-gray-500';
                            let textCol = 'text-white';
                            if (action.type === game.ActionType.ACTION_CHII) {
                                label = 'CHOW';
                                color = 'bg-blue-600 hover:bg-blue-500';
                            } else if (action.type === game.ActionType.ACTION_PON) {
                                label = 'PONG';
                                color = 'bg-purple-600 hover:bg-purple-500';
                            } else if (action.type === game.ActionType.ACTION_KAN) {
                                label = 'KONG';
                                color = 'bg-indigo-600 hover:bg-indigo-500';
                            } else if (action.type === game.ActionType.ACTION_RON) {
                                label = 'RON (Win)';
                                color = 'bg-red-600 hover:bg-red-500';
                            }

                            return (
                                <button key={i} onClick={() => handleAction(action.type, undefined, action.meldTiles || [])} className={`${color} ${textCol} font-bold py-3 px-6 rounded-lg shadow-xl outline outline-offset-2 outline-white text-lg tracking-widest transition-transform hover:scale-105 animate-bounce flex items-center gap-3`}>
                                    <span>{label}</span>
                                    {action.meldTiles && action.meldTiles.length > 0 && (
                                        <div className="flex gap-1 bg-black bg-opacity-30 p-1 rounded">
                                            {action.meldTiles.map((mt: any, mtIdx: number) => (
                                                <TileComponent key={mtIdx} tile={mt} size="small" />
                                            ))}
                                        </div>
                                    )}
                                </button>
                            );
                        })}
                        <button onClick={() => handleAction(game.ActionType.ACTION_PASS)} className="bg-gray-700 hover:bg-gray-600 text-gray-200 font-bold py-3 px-6 rounded-lg shadow-lg tracking-widest transition-transform hover:scale-105">
                            SKIP
                        </button>
                    </div>
                )}

                {/* Active Turn Actions (Tsumo, Closed Kan) */}
                {gameState.phase === 2 && gameState.activePlayer === mySeatId && validActions.length > 0 && (
                    <div className="flex gap-4 mt-6 pointer-events-auto justify-center">
                        {validActions.map((action: any, i: number) => {
                            if (action.type === game.ActionType.ACTION_TSUMO) {
                                return (
                                    <button key={i} onClick={() => handleAction(game.ActionType.ACTION_TSUMO)} className="bg-yellow-500 hover:bg-yellow-400 text-black font-extrabold py-3 px-6 rounded-lg shadow-[0_0_15px_rgba(234,179,8,0.8)] text-xl tracking-widest transition-transform hover:scale-110 animate-pulse">
                                        TSUMO
                                    </button>
                                );
                            } else if (action.type === game.ActionType.ACTION_KAN) {
                                return (
                                    <button key={i} onClick={() => handleAction(game.ActionType.ACTION_KAN, undefined, action.meldTiles || [])} className="bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-4 rounded shadow">
                                        KONG
                                    </button>
                                );
                            }
                            return null;
                        })}
                    </div>
                )}
            </div>

            {/* Loop through all 4 players to place their hands and discards */}
            {gameState.players.map((p: any) => {
                const diff = (p.seat - mySeatId + 4) % 4;
                const positions = ['bottom', 'right', 'top', 'left'];
                const posStr = positions[diff];

                const isMe = diff === 0;
                const canDiscard = isMe && gameState.activePlayer === mySeatId && gameState.phase === 2;

                return (
                    <div key={p.seat} className="contents">

                        {/* Discard Pool Area */}
                        <div className={`discard-pool discard-pool-${posStr}`}>
                            {p.discards.map((t: any, i: number) => (
                                <div key={i} className={`pov-${posStr} small`}>
                                    <TileComponent tile={t} size="small" />
                                </div>
                            ))}
                        </div>

                        {/* Combined Hand and Melds Area */}
                        <div className={`hand-container-${posStr}`}>
                            <div className={`hand-inner hand-inner-${posStr}`}>
                                {/* Render actual tiles for self, backs for others (unless server sent open hands for replay) */}
                                {isMe || p.closedHand.length > 0 ? (
                                    (() => {
                                        // A tile is drawn if the backend passed the optional value
                                        const hasDrawnTile = p.drawnTileId != null;
                                        let drawnTile = null;
                                        let baseTiles = [...p.closedHand];

                                        if (hasDrawnTile) {
                                            const dIdx = baseTiles.findIndex((t: any) => t.id == p.drawnTileId);
                                            // Debug print if isMe
                                            if (isMe && dIdx === -1) {
                                                console.error(`Drawn tile ${p.drawnTileId} not found in hand!`);
                                            }
                                            if (dIdx !== -1) {
                                                drawnTile = baseTiles.splice(dIdx, 1)[0];
                                            }
                                        }

                                        // Persist the ID of what was drawn so we know to delay its insertion animation
                                        if (drawnTile && isMe) {
                                            lastDrawnTileId.current = drawnTile.id;
                                        }

                                        const sortedBaseTiles = [...baseTiles].sort((a, b) => {
                                            const suitA = getSuitOrder(a.suit);
                                            const suitB = getSuitOrder(b.suit);
                                            if (suitA !== suitB) return suitA - suitB;
                                            if (a.value !== b.value) return a.value - b.value;
                                            return a.id - b.id;
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

                            {/* Open Melds Area */}
                            <div className={`melds-container-${posStr}`}>
                                {((posStr === 'bottom' || posStr === 'top') ? [...p.openMelds].reverse() : p.openMelds).map((m: any, mIdx: number) => {
                                    // Rearrange tiles based on calledDirection (1=Right, 2=Across, 3=Left)
                                    let displayTiles = [...m.tiles];
                                    const stolenIdx = displayTiles.findIndex(t => t.id === m.calledTileId);
                                    if (stolenIdx !== -1 && m.calledDirection > 0) {
                                        const stolen = displayTiles.splice(stolenIdx, 1)[0];
                                        if (m.calledDirection === 3) {
                                            displayTiles.unshift(stolen); // Stolen from Left -> place on left
                                        } else if (m.calledDirection === 1) {
                                            displayTiles.push(stolen); // Stolen from Right -> place on right
                                        } else if (m.calledDirection === 2) {
                                            displayTiles.splice(1, 0, stolen); // Stolen from Across -> place in middle
                                        }
                                    }

                                    return (
                                        <div key={mIdx} className={`meld-group meld-group-${posStr}`}>
                                            {displayTiles.map((t: any, tIdx: number) => {
                                                const isStolen = t.id === m.calledTileId;
                                                return (
                                                    <div key={tIdx} className={`pov-${posStr} small ${isStolen ? 'stolen-tile' : ''}`}>
                                                        <TileComponent tile={t} size="small" />
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}
