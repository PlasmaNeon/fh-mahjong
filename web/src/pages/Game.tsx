// @ts-nocheck
import { useEffect, useRef, useState } from 'react';
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
    const [isReady, setIsReady] = useState(false);

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

    // Reset ready state when a new round starts
    useEffect(() => {
        if (gameState?.phase !== 4) {
            setIsReady(false);
        }
    }, [gameState?.phase]);

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
                    boxShadow: isWild ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
                    position: 'relative'
                }}
            >
                <img
                    src={`/Regular_shortnames/Front.svg`}
                    style={{ width: '100%', height: '100%', display: 'block', borderRadius: '4px', position: 'absolute', top: 0, left: 0, zIndex: 1 }}
                    draggable="false"
                />
                <img
                    src={`/Regular_shortnames/${svgName}`}
                    alt={getTileName(tile)}
                    style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
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
                        <div className={`hand-container-${posStr}`} style={isMe ? { position: 'relative' } : {}}>

                            {/* Action Buttons Overlay for Bottom Player */}
                            {isMe && (
                                <div className="absolute right-0 bottom-full mb-8 flex gap-4 pointer-events-auto items-end justify-end" style={{ zIndex: 100 }}>
                                    {/* Interrupt Window Actions */}
                                    {gameState.phase === 3 && validActions.length > 0 && (
                                        <>
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
                                                    <button key={i} onClick={() => handleAction(action.type, undefined, action.meldTiles || [])} className={`${color} ${textCol} font-bold py-3 px-6 rounded-lg shadow-xl outline outline-offset-2 outline-white text-lg tracking-widest transition-transform hover:scale-105 flex items-center gap-3`}>
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
                                        </>
                                    )}

                                    {/* Active Turn Actions */}
                                    {gameState.phase === 2 && gameState.activePlayer === mySeatId && validActions.length > 0 && (
                                        <>
                                            {validActions.map((action: any, i: number) => {
                                                if (action.type === game.ActionType.ACTION_TSUMO) {
                                                    return (
                                                        <button key={i} onClick={() => handleAction(game.ActionType.ACTION_TSUMO)} className="bg-yellow-500 hover:bg-yellow-400 text-black font-extrabold py-3 px-6 rounded-lg shadow-[0_0_15px_rgba(234,179,8,0.8)] text-xl tracking-widest transition-transform hover:scale-110">
                                                            TSUMO
                                                        </button>
                                                    );
                                                } else if (action.type === game.ActionType.ACTION_KAN) {
                                                    return (
                                                        <button key={i} onClick={() => handleAction(game.ActionType.ACTION_KAN, undefined, action.meldTiles || [])} className="bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-6 rounded shadow-lg text-lg tracking-widest transition-transform hover:scale-105">
                                                            KONG
                                                        </button>
                                                    );
                                                }
                                                return null;
                                            })}
                                        </>
                                    )}
                                </div>
                            )}

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

            {/* Round Result Modal */}
            {gameState.phase === 4 && gameState.roundResult && (
                <div className="round-result-overlay">
                    <div className="round-result-modal">
                        {gameState.roundResult.isDraw ? (
                            <div className="text-center">
                                <h2 className="text-3xl font-bold text-gray-400 mb-4">Exhaustive Draw</h2>
                                <p className="text-gray-500">No tiles remaining in the wall.</p>
                            </div>
                        ) : (
                            <>
                                {/* Win Header */}
                                <h2 className="text-3xl font-extrabold text-center mb-4" style={{
                                    color: gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? '#EAB308' : '#EF4444'
                                }}>
                                    {gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? 'TSUMO!' : 'RON!'}
                                </h2>
                                <p className="text-center text-gray-400 text-sm mb-4">
                                    Seat {gameState.roundResult.winnerSeat} wins
                                    {gameState.roundResult.winType === game.ActionType.ACTION_RON &&
                                        ` from Seat ${gameState.roundResult.discarderSeat}`}
                                </p>

                                {/* Winning Hand Display */}
                                <div className="mb-4">
                                    <div className="flex flex-wrap gap-1 justify-center items-end">
                                        {/* Closed hand tiles */}
                                        {[...(gameState.roundResult.winningHand || [])].sort((a, b) => {
                                            const sa = getSuitOrder(a.suit), sb = getSuitOrder(b.suit);
                                            if (sa !== sb) return sa - sb;
                                            return a.value - b.value;
                                        }).map((t: any, i: number) => (
                                            <div key={`h-${i}`}>
                                                <TileComponent tile={t} size="small" />
                                            </div>
                                        ))}
                                        {/* Open melds */}
                                        {(gameState.roundResult.winningMelds || []).map((m: any, mIdx: number) => (
                                            <div key={`m-${mIdx}`} className="flex gap-0.5 ml-2 pl-2 border-l border-gray-600">
                                                {m.tiles.map((t: any, tIdx: number) => (
                                                    <div key={tIdx}>
                                                        <TileComponent tile={t} size="small" />
                                                    </div>
                                                ))}
                                            </div>
                                        ))}
                                        {/* Win tile highlighted */}
                                        {gameState.roundResult.winTile && (
                                            <div className="ml-3 pl-3 border-l-2 border-yellow-500">
                                                <TileComponent tile={gameState.roundResult.winTile} size="small" />
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Score Breakdown Table */}
                                <div className="bg-black/30 rounded-lg p-3 mb-4 max-h-48 overflow-y-auto">
                                    <table className="w-full text-sm">
                                        <tbody>
                                            {(gameState.roundResult.breakdown || []).map((entry: any, i: number) => (
                                                <tr key={i} className="border-b border-gray-700/50">
                                                    <td className="py-1 text-gray-300">{entry.patternName}</td>
                                                    <td className="py-1 text-right text-green-400 font-mono">+{entry.points}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>

                                {/* Total Score */}
                                <div className="text-center mb-4 py-2 bg-green-900/40 rounded-lg border border-green-600/50">
                                    <span className="text-gray-400 text-sm">Total Score: </span>
                                    <span className="text-2xl font-bold text-green-400">{gameState.roundResult.totalScore}</span>
                                </div>

                                {/* Payout Summary */}
                                <div className="grid grid-cols-4 gap-2 mb-4 text-center text-sm">
                                    {(gameState.roundResult.payouts || []).map((p: any, i: number) => (
                                        <div key={i} className={`rounded-lg py-2 px-1 ${p.amount > 0 ? 'bg-green-900/40 border border-green-600/30' : 'bg-red-900/40 border border-red-600/30'}`}>
                                            <div className="text-gray-400 text-xs">Seat {p.seat}</div>
                                            <div className={`font-bold ${p.amount > 0 ? 'text-green-400' : 'text-red-400'}`}>
                                                {p.amount > 0 ? '+' : ''}{p.amount}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}

                        {/* Ready Indicators */}
                        {gameState.playerReady && gameState.playerReady.length > 0 && (
                            <div className="flex justify-center gap-3 mb-4 text-xs">
                                {gameState.playerReady.map((ready: boolean, i: number) => (
                                    <span key={i} className={`px-2 py-1 rounded ${ready ? 'bg-green-800 text-green-300' : 'bg-gray-800 text-gray-500'}`}>
                                        Seat {i} {ready ? 'Ready' : '...'}
                                    </span>
                                ))}
                            </div>
                        )}

                        {/* Action Buttons */}
                        <div className="flex gap-4 justify-center">
                            <button
                                onClick={() => { handleAction(game.ActionType.ACTION_READY); setIsReady(true); }}
                                disabled={isReady}
                                className={`font-bold py-3 px-8 rounded-lg text-lg transition-transform hover:scale-105 ${isReady ? 'bg-gray-600 text-gray-400 cursor-not-allowed' : 'bg-green-600 hover:bg-green-500 text-white shadow-lg'}`}
                            >
                                {isReady ? 'Waiting...' : 'Ready'}
                            </button>
                            <button
                                onClick={() => { socket?.close(); navigate('/'); }}
                                className="bg-red-800 hover:bg-red-700 text-white font-bold py-3 px-8 rounded-lg text-lg transition-transform hover:scale-105"
                            >
                                Exit
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
