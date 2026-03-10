// @ts-nocheck
import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { game } from '../proto/game';
import { motion } from 'framer-motion';

import { getTileSvgName, getSuitOrder, getTileName } from '../utils/tileUtils';
export default function Game() {
    const { matchId } = useParams();
    const navigate = useNavigate();
    const { isConnected, socket, connect } = useSocket();
    const { gameState, mySeatId } = useGameState();

    // Track the last drawn tile so we can delay its sorting animation
    const lastDrawnTileId = useRef<number | null>(null);
    const previousDiscardIdsRef = useRef<Record<number, number[]>>({});
    const autoFlowerRevealKeyRef = useRef<string>('');
    const [isReady, setIsReady] = useState(false);
    const [hasSubmittedInterrupt, setHasSubmittedInterrupt] = useState(false);

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
        if (gameState?.phase !== 3) {
            setHasSubmittedInterrupt(false);
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
    const rawValidActions: any[] = myPlayer?.validActions || [];
    const pendingFlowerReveal = rawValidActions.find((action: any) => action.type === game.ActionType.ACTION_FLOWER_REVEAL) || null;
    const validActions = rawValidActions.filter((action: any) => action.type !== game.ActionType.ACTION_FLOWER_REVEAL);
    const callableActionTypes = new Set([
        game.ActionType.ACTION_CHII,
        game.ActionType.ACTION_PON,
        game.ActionType.ACTION_KAN,
        game.ActionType.ACTION_RON,
    ]);
    const hasCallableInterrupt = gameState.phase === 3 && validActions.some((action: any) => callableActionTypes.has(action.type));
    const newlyDiscardedTileIds = new Set<number>();

    gameState.players.forEach((player: any) => {
        const previousIds = previousDiscardIdsRef.current[player.seat] || [];
        const currentIds = player.discards.map((tile: any) => tile.id);
        if (currentIds.length === 0) {
            return;
        }

        const lastId = currentIds[currentIds.length - 1];
        const previousLastId = previousIds[previousIds.length - 1];
        if (currentIds.length > previousIds.length || lastId !== previousLastId) {
            newlyDiscardedTileIds.add(lastId);
        }
    });

    useEffect(() => {
        previousDiscardIdsRef.current = Object.fromEntries(
            gameState.players.map((player: any) => [
                player.seat,
                player.discards.map((tile: any) => tile.id),
            ])
        );
    }, [gameState.players]);

    useEffect(() => {
        const canAutoReveal =
            pendingFlowerReveal &&
            gameState.phase === 2 &&
            gameState.activePlayer === mySeatId &&
            socket &&
            socket.readyState === WebSocket.OPEN;

        if (!canAutoReveal) {
            autoFlowerRevealKeyRef.current = '';
            return;
        }

        const revealKey = (pendingFlowerReveal.meldTiles || [])
            .map((tile: any) => tile.id)
            .join(',');

        if (!revealKey || autoFlowerRevealKeyRef.current === revealKey) {
            return;
        }

        autoFlowerRevealKeyRef.current = revealKey;
        handleAction(game.ActionType.ACTION_FLOWER_REVEAL, undefined, pendingFlowerReveal.meldTiles || []);
    }, [pendingFlowerReveal, gameState.phase, gameState.activePlayer, mySeatId, socket]);

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

    // Removed duplicated helpers (now imported from tileUtils)

    // Render helper for tiles
    const TileComponent = ({ tile, isInteractive = false, size = 'normal', noGlow = false }: { tile: game.ITile, isInteractive?: boolean, size?: 'normal' | 'small', noGlow?: boolean }) => {
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
                    boxShadow: (isWild && !noGlow) ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
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

    const getActionMeta = (action: any) => {
        if (action.type === game.ActionType.ACTION_CHII) {
            return { label: 'CHII', accent: 'table-action-btn-chii' };
        }
        if (action.type === game.ActionType.ACTION_PON) {
            return { label: 'PON', accent: 'table-action-btn-pon' };
        }
        if (action.type === game.ActionType.ACTION_KAN) {
            return { label: 'KAN', accent: 'table-action-btn-kan' };
        }
        if (action.type === game.ActionType.ACTION_RON) {
            return { label: 'RON', accent: 'table-action-btn-ron' };
        }
        if (action.type === game.ActionType.ACTION_TSUMO) {
            return { label: 'TSUMO', accent: 'table-action-btn-tsumo' };
        }
        if (action.type === game.ActionType.ACTION_ACCEPT_HAITEI) {
            return { label: '海底 ✓', accent: 'table-action-btn-tsumo' };
        }
        if (action.type === game.ActionType.ACTION_REFUSE_HAITEI) {
            return { label: '海底 ✗', accent: 'table-action-btn-skip' };
        }
        return { label: 'ACTION', accent: 'table-action-btn-neutral' };
    };

    const showInterruptActions = gameState.phase === 3 && validActions.length > 0 && !hasSubmittedInterrupt;
    const showTurnActions = gameState.phase === 2 && gameState.activePlayer === mySeatId && validActions.length > 0;
    const getDiscardAnimationOffset = (position: string) => {
        if (position === 'bottom') return { x: 0, y: 32 };
        if (position === 'top') return { x: 0, y: -32 };
        if (position === 'left') return { x: -32, y: 0 };
        return { x: 32, y: 0 };
    };

    return (
        <div className="mahjong-table">
            {gameState.wildTiles && gameState.wildTiles.length > 0 && (
                <div className="wild-tile-corner">
                    <div className="wild-tile-corner-label">Wild Tile</div>
                    <div className="wild-tile-corner-face">
                        <TileComponent tile={gameState.wildTiles[0]} noGlow />
                    </div>
                </div>
            )}

            {/* Center Info HUD */}
            <div className="center-info text-white text-center">
                {/* Wind labels on 4 sides */}
                {(() => {
                    const windNames = ['', 'East', 'South', 'West', 'North'];
                    const windKanji = ['', '東', '南', '西', '北'];
                    const positions = ['bottom', 'right', 'top', 'left'];
                    return positions.map((pos, idx) => {
                        const seat = gameState.players.find((p: any) => {
                            const diff = (p.seat - mySeatId + 4) % 4;
                            return diff === idx;
                        });
                        if (!seat) return null;
                        const wind = seat.seatWind;
                        const isActive = seat.seat === gameState.activePlayer;
                        return (
                            <div key={pos} className={`center-wind center-wind-${pos} ${isActive ? 'center-wind-active' : ''}`}>
                                {windKanji[wind]}
                            </div>
                        );
                    });
                })()}
                <div className="center-info-stats">
                    <span className="center-info-chip">Wall {gameState.wallCount}</span>
                    {(gameState.dice1 > 0 || gameState.dice2 > 0 || gameState.diceSum > 0) && (
                        <span className="center-info-chip">
                            🎲 {gameState.dice1 > 0 && gameState.dice2 > 0 ? `${gameState.dice1}+${gameState.dice2}` : gameState.diceSum}
                        </span>
                    )}
                    {(gameState.wangpaiTilesLeft > 0 || gameState.wangpaiStacks > 0) && (
                        <span className="center-info-chip">
                            王牌 {gameState.wangpaiTilesLeft > 0 ? gameState.wangpaiTilesLeft : (gameState.wangpaiStacks * 2 - 1)}
                        </span>
                    )}
                    {gameState.isHaitei && (
                        <span className="center-info-chip" style={{color: '#ff6b6b'}}>海底</span>
                    )}
                </div>
            </div>

            {(showInterruptActions || showTurnActions) && (
                <div className="table-action-bar">
                    {showInterruptActions && (
                        <>
                            {validActions.map((action: any, i: number) => {
                                const meta = getActionMeta(action);

                                return (
                                    <button key={i} onClick={() => { setHasSubmittedInterrupt(true); handleAction(action.type, undefined, action.meldTiles || []); }} className={`table-action-btn ${meta.accent}`}>
                                        <span className="table-action-btn-label">{meta.label}</span>
                                        {action.meldTiles && action.meldTiles.length > 0 && (
                                            <div className="table-action-preview">
                                                {action.meldTiles.map((mt: any, mtIdx: number) => (
                                                    <TileComponent key={mtIdx} tile={mt} size="small" />
                                                ))}
                                            </div>
                                        )}
                                    </button>
                                );
                            })}
                            <button onClick={() => { setHasSubmittedInterrupt(true); handleAction(game.ActionType.ACTION_PASS); }} className="table-action-btn table-action-btn-skip">
                                SKIP
                            </button>
                        </>
                    )}

                    {showTurnActions && (
                        <>
                            {validActions.map((action: any, i: number) => {
                                if (action.type === game.ActionType.ACTION_TSUMO) {
                                    const meta = getActionMeta(action);
                                    return (
                                        <button key={i} onClick={() => handleAction(game.ActionType.ACTION_TSUMO)} className={`table-action-btn ${meta.accent} table-action-btn-prominent`}>
                                            {meta.label}
                                        </button>
                                    );
                                } else if (action.type === game.ActionType.ACTION_KAN) {
                                    const meta = getActionMeta(action);
                                    return (
                                        <button key={i} onClick={() => handleAction(game.ActionType.ACTION_KAN, undefined, action.meldTiles || [])} className={`table-action-btn ${meta.accent}`}>
                                            {meta.label}
                                        </button>
                                    );
                                }
                                return null;
                            })}
                        </>
                    )}
                </div>
            )}

            {/* Loop through all 4 players to place their hands and discards */}
            {gameState.players.map((p: any) => {
                const diff = (p.seat - mySeatId + 4) % 4;
                const positions = ['bottom', 'right', 'top', 'left'];
                const posStr = positions[diff];

                const isMe = diff === 0;
                const canDiscard = isMe && gameState.activePlayer === mySeatId && gameState.phase === 2
                    && validActions.some((a: any) => a.type === game.ActionType.ACTION_DISCARD);

                return (
                    <div key={p.seat} className="contents">

                        {/* Discard Pool Area */}
                        <div className={`discard-pool discard-pool-${posStr} ${p.discards.length === 0 ? 'discard-pool-empty' : ''}`}>
                            {p.discards.length === 0 ? (
                                <div className="discard-pool-placeholder" aria-hidden="true" />
                            ) : (
                                p.discards.map((t: any, i: number) => {
                                    const isLastDiscard = i === p.discards.length - 1;
                                    const isNewDiscard = newlyDiscardedTileIds.has(t.id);
                                    const isCallableDiscard = hasCallableInterrupt && isLastDiscard && p.seat === gameState.activePlayer;
                                    const discardMotionOffset = getDiscardAnimationOffset(posStr);

                                    return (
                                        <motion.div
                                            key={t.id}
                                            layoutId={t.id.toString()}
                                            initial={isNewDiscard ? { opacity: 0, scale: 0.82, ...discardMotionOffset } : false}
                                            animate={{ opacity: 1, scale: 1, x: 0, y: 0 }}
                                            transition={{
                                                layout: { duration: 0.18, ease: "easeOut" },
                                                opacity: { duration: 0.08, ease: "easeOut" },
                                                scale: { duration: 0.1, ease: "easeOut" },
                                                x: { duration: 0.11, ease: "easeOut" },
                                                y: { duration: 0.11, ease: "easeOut" },
                                            }}
                                            className={`discard-pool-tile ${isCallableDiscard ? 'discard-pool-tile-callable' : ''} pov-${posStr} small`}
                                        >
                                            <TileComponent tile={t} size="small" noGlow={isCallableDiscard} />
                                        </motion.div>
                                    );
                                })
                            )}
                        </div>

                        {/* Combined Hand and Melds Area */}
                        <div className={`hand-container-${posStr} ${isMe ? 'hand-container-self' : ''}`}>
                            <div className={`hand-main-block hand-main-block-${posStr} ${isMe ? 'hand-main-block-self' : ''}`}>
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
                                                            key={t.id}
                                                            initial={isCurrentlyDrawnSlot ? { opacity: 0, y: -30 } : false}
                                                            animate={{ opacity: 1, y: 0 }}
                                                            style={{ zIndex: isRecentlyDrawn ? 0 : 10 }}
                                                            transition={{
                                                                layout: {
                                                                    duration: isRecentlyDrawn ? 0.15 : 0.25,
                                                                    delay: isRecentlyDrawn ? 0.05 : 0,
                                                                    ease: "easeInOut"
                                                                },
                                                                opacity: isCurrentlyDrawnSlot ? { duration: 0.3, ease: "easeOut" } : { duration: 0 },
                                                                y: isCurrentlyDrawnSlot ? { duration: 0.3, ease: "easeOut" } : { duration: 0 },
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

                            {/* Open Melds Area */}
                            <div className={`melds-container-${posStr}`}>
                                <div className={`melds-main melds-main-${posStr}`}>
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
                                {p.flowerMelds && p.flowerMelds.length > 0 && (
                                    <div className={`flowers-container flowers-container-${posStr}`}>
                                        {p.flowerMelds.map((t: any, fi: number) => (
                                            <div key={`f-${fi}`} className={`pov-${posStr} small`}>
                                                <TileComponent tile={t} size="small" />
                                            </div>
                                        ))}
                                    </div>
                                )}
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
                            <div className="round-result-draw">
                                <div className="round-result-badge round-result-badge-draw">Draw</div>
                                <h2 className="round-result-title round-result-title-draw">Exhaustive Draw</h2>
                                <p className="round-result-subtitle">No tiles remaining in the wall.</p>
                            </div>
                        ) : (
                            <>
                                {/* Win Header */}
                                <div className="round-result-header-line">
                                    <div className={`round-result-badge ${gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? 'round-result-badge-tsumo' : 'round-result-badge-ron'}`}>
                                        {gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? 'TSUMO!' : 'RON!'}
                                    </div>
                                    <h2 className={`round-result-title ${gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? 'round-result-title-tsumo' : 'round-result-title-ron'}`}>
                                        Seat {gameState.roundResult.winnerSeat} wins
                                    </h2>
                                </div>
                                {gameState.roundResult.winType === game.ActionType.ACTION_RON && (
                                    <p className="round-result-subtitle">
                                        From Seat {gameState.roundResult.discarderSeat}
                                    </p>
                                )}

                                {/* Winning Hand Display */}
                                <div className="round-result-panel round-result-panel-plain round-result-hand-panel">
                                    <div className="round-result-hand-row">
                                        {/* Closed hand tiles (sorted, no gaps) + win tile at rightmost with gap */}
                                        {(() => {
                                            const closedTiles = [...(gameState.roundResult.winningHand || [])];
                                            const winTile = gameState.roundResult.winTile;
                                            // Remove the win tile from closed hand (shown separately)
                                            if (winTile) {
                                                const idx = closedTiles.findIndex((t: any) => t.id === winTile.id);
                                                if (idx !== -1) closedTiles.splice(idx, 1);
                                            }
                                            closedTiles.sort((a: any, b: any) => {
                                                const sa = getSuitOrder(a.suit), sb = getSuitOrder(b.suit);
                                                if (sa !== sb) return sa - sb;
                                                return a.value - b.value;
                                            });
                                            return (
                                                <div className="round-result-closed-hand">
                                                    {closedTiles.map((t: any, i: number) => (
                                                        <div key={`h-${i}`} className="pov-bottom small">
                                                            <TileComponent tile={t} size="small" />
                                                        </div>
                                                    ))}
                                                    {winTile && (
                                                        <div className="pov-bottom small round-result-win-tile">
                                                            <TileComponent tile={winTile} size="small" />
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })()}
                                        {/* Open melds — same as table: reversed order, meld-group classes, stolen tile directions */}
                                        {(gameState.roundResult.winningMelds || []).length > 0 && (
                                            <div className="round-result-melds-divider">
                                                {[...(gameState.roundResult.winningMelds || [])].reverse().map((m: any, mIdx: number) => {
                                                    let displayTiles = [...m.tiles];
                                                    const stolenIdx = displayTiles.findIndex((t: any) => t.id === m.calledTileId);
                                                    if (stolenIdx !== -1 && m.calledDirection > 0) {
                                                        const stolen = displayTiles.splice(stolenIdx, 1)[0];
                                                        if (m.calledDirection === 3) displayTiles.unshift(stolen);
                                                        else if (m.calledDirection === 1) displayTiles.push(stolen);
                                                        else if (m.calledDirection === 2) displayTiles.splice(1, 0, stolen);
                                                    }
                                                    return (
                                                        <div key={`m-${mIdx}`} className="meld-group meld-group-bottom">
                                                            {displayTiles.map((t: any, tIdx: number) => {
                                                                const isStolen = t.id === m.calledTileId;
                                                                return (
                                                                    <div key={tIdx} className={`pov-bottom small ${isStolen ? 'stolen-tile' : ''}`}>
                                                                        <TileComponent tile={t} size="small" />
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                        {/* Flower Melds */}
                                        {(() => {
                                            const winnerSeat = gameState.roundResult.winnerSeat;
                                            const winnerFlowers = gameState.players.find((p: any) => p.seat === winnerSeat)?.flowerMelds || [];
                                            if (winnerFlowers.length === 0) return null;
                                            return (
                                                <div className="round-result-melds-divider">
                                                    {winnerFlowers.map((t: any, fi: number) => (
                                                        <div key={`fl-${fi}`} className="pov-bottom small">
                                                            <TileComponent tile={t} size="small" />
                                                        </div>
                                                    ))}
                                                </div>
                                            );
                                        })()}
                                    </div>
                                </div>

                                {/* Score Breakdown Table */}
                                <div className="round-result-panel">
                                    <div className="round-result-breakdown-scroll">
                                        <div className="round-result-breakdown-grid">
                                            {(gameState.roundResult.breakdown || []).map((entry: any, i: number) => (
                                                <div key={i} className="round-result-breakdown-item">
                                                    <div className="round-result-breakdown-name">{entry.patternName}</div>
                                                    <div className="round-result-breakdown-points">+{entry.points}</div>
                                                </div>
                                            ))}
                                            <div className="round-result-breakdown-total-row">
                                                <div>Total</div>
                                                <div>{gameState.roundResult.totalScore}</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Payout Summary */}
                                <div className="round-result-panel round-result-panel-plain">
                                <div className="round-result-payout-grid">
                                    {(gameState.roundResult.payouts || []).map((p: any, i: number) => (
                                        <div key={i} className={`round-result-payout-cell ${p.amount > 0 ? 'round-result-payout-positive' : 'round-result-payout-negative'}`}>
                                            <div className="round-result-payout-seat">Seat {p.seat}</div>
                                            <div className="round-result-payout-amount">
                                                {p.amount > 0 ? '+' : ''}{p.amount}
                                            </div>
                                            {gameState.playerReady && gameState.playerReady.length > p.seat && (
                                                <div className={`round-result-payout-ready ${gameState.playerReady[p.seat] ? 'round-result-payout-ready-on' : ''}`}>
                                                    {gameState.playerReady[p.seat] ? 'Ready' : '...'}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                                </div>
                            </>
                        )}

                        {/* Action Buttons */}
                        <div className="round-result-actions">
                            <button
                                onClick={() => { handleAction(game.ActionType.ACTION_READY); setIsReady(true); }}
                                disabled={isReady}
                                className={`round-result-action-btn round-result-action-btn-ready ${isReady ? 'round-result-action-btn-disabled' : ''}`}
                            >
                                {isReady ? 'Waiting...' : 'Ready'}
                            </button>
                            <button
                                onClick={() => { socket?.close(); navigate('/'); }}
                                className="round-result-action-btn round-result-action-btn-exit"
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
