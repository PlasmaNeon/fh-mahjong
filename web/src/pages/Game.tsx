// @ts-nocheck
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { game } from '../proto/game';
import { useGameStageLayout } from '../hooks/useGameStageLayout';
import { getPrivateRoomToken } from './privateRoomSession';
import { preloadAllTileSvgs } from '../utils/tileUtils';
import { TableBoard, TableRoundResultOverlay, TileComponent } from '../table/TableScene';
import MatchEndOverlay from './MatchEndOverlay';

export default function Game() {
    const { matchId } = useParams();
    const navigate = useNavigate();
    const { isConnected, socket, connect } = useSocket();
    const { gameState, mySeatId } = useGameState();

    const previousDiscardIdsRef = useRef<Record<number, number[]>>({});
    const autoFlowerRevealKeyRef = useRef<string>('');
    const [isReady, setIsReady] = useState(false);
    const [hasSubmittedInterrupt, setHasSubmittedInterrupt] = useState(false);
    const stageLayout = useGameStageLayout();

    useEffect(() => {
        if (!isConnected || !socket) {
            const storedToken = getPrivateRoomToken();
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

    // Debug: log discard conditions each state update
    console.log('[Discard Debug]', {
        mySeatId,
        activePlayer: gameState.activePlayer,
        phase: gameState.phase,
        rawActionTypes: rawValidActions.map((a: any) => a.type),
        filteredActionTypes: validActions.map((a: any) => a.type),
        ACTION_DISCARD_VALUE: game.ActionType.ACTION_DISCARD,
        PHASE_PLAYER_TURN_VALUE: game.GamePhase.PHASE_PLAYER_TURN,
        isMyTurn: gameState.activePlayer === mySeatId,
        isCorrectPhase: gameState.phase === 2,
        hasDiscardAction: validActions.some((a: any) => a.type === game.ActionType.ACTION_DISCARD),
    });
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

    // Preload all tile SVGs on first mount so images are instant
    useEffect(() => { preloadAllTileSvgs(); }, []);

    // Stable callback for discarding (passed to memoized TileComponent)
    const onDiscard = useCallback((tile: game.ITile) => {
        console.log('[Discard] Clicked tile:', tile);
        handleAction(game.ActionType.ACTION_DISCARD, tile);
    }, [socket]);

    // Check if a tile is wild (memoized per gameState.wildTiles)
    const wildTileSet = useRef(new Set<string>());
    wildTileSet.current = new Set(
        (gameState.wildTiles || []).map((w: any) => `${w.suit}-${w.value}`)
    );
    const isWildTile = (tile: game.ITile) => wildTileSet.current.has(`${tile.suit}-${tile.value}`);

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
    const stageShellStyle = {
        '--game-stage-scaled-width': `${stageLayout.scaledWidth}px`,
        '--game-stage-scaled-height': `${stageLayout.scaledHeight}px`,
        '--game-stage-available-width': `${stageLayout.availableWidth}px`,
        '--game-stage-available-height': `${stageLayout.availableHeight}px`,
    } as React.CSSProperties;

    const stageStyle = {
        width: `${stageLayout.stageWidth}px`,
        height: `${stageLayout.stageHeight}px`,
        zoom: stageLayout.scale,
    } as React.CSSProperties;
    const stageFrameStyle = {} as React.CSSProperties;

    const activeDiscardTile = gameState.players
        .find((player: any) => player.seat === gameState.activePlayer)
        ?.discards?.slice(-1)[0] ?? null;

    const callableDiscard = hasCallableInterrupt && activeDiscardTile
        ? { seat: gameState.activePlayer, tileId: activeDiscardTile.id }
        : null;

    const hudChips = [
        { label: `Wall ${gameState.wallCount}` },
        ...((gameState.dice1 > 0 || gameState.dice2 > 0 || gameState.diceSum > 0) ? [{
            label: `🎲 ${gameState.dice1 > 0 && gameState.dice2 > 0 ? `${gameState.dice1}+${gameState.dice2}` : gameState.diceSum}`
        }] : []),
        ...((gameState.wangpaiTilesLeft > 0 || gameState.wangpaiStacks > 0) ? [{
            label: `王牌 ${gameState.wangpaiTilesLeft > 0 ? gameState.wangpaiTilesLeft : (gameState.wangpaiStacks * 2 - 1)}`
        }] : []),
        ...(gameState.isHaitei ? [{ label: '海底', tone: 'danger' as const }] : []),
    ];

    const actionBar = (showInterruptActions || showTurnActions) ? (
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
                                        {action.meldTiles.map((meldTile: any, meldTileIndex: number) => (
                                            <TileComponent key={meldTileIndex} tile={meldTile} size="small" isWild={isWildTile(meldTile)} />
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
    ) : null;

    const playerViews = useMemo(() => gameState.players.map((player: any) => ({
        seat: player.seat,
        seatWind: player.seatWind,
        closedHand: player.closedHand || [],
        handBackCount: player.handSize,
        showClosedHand: player.seat === mySeatId || (player.closedHand?.length ?? 0) > 0,
        drawnTileId: player.drawnTileId,
        openMelds: (player.openMelds || []).map((meld: any) => ({
            tiles: meld.tiles || [],
            calledTileId: meld.calledTileId,
            calledDirection: meld.calledDirection,
        })),
        flowerMelds: player.flowerMelds || [],
        discards: player.discards || [],
        shantenLabel: player.seat === mySeatId && gameState.phase === 2
            ? (player.shanten === -1 ? '和了' : player.shanten === 0 ? '听牌' : `向听: ${player.shanten}`)
            : null,
    })), [gameState.players, gameState.phase, mySeatId]);

    const readyActions = (
        <>
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
        </>
    );

    const winnerPlayer = gameState.roundResult
        ? gameState.players.find((player: any) => player.seat === gameState.roundResult.winnerSeat)
        : null;

    const winningHandWithoutWinTile = (() => {
        if (!gameState.roundResult) return [];
        const closedTiles = [...(gameState.roundResult.winningHand || [])];
        const winTile = gameState.roundResult.winTile;
        if (winTile) {
            const winTileIndex = closedTiles.findIndex((tile: any) => tile.id === winTile.id);
            if (winTileIndex !== -1) {
                closedTiles.splice(winTileIndex, 1);
            }
        }
        return closedTiles;
    })();

    const roundResultView = gameState.phase === 4 && gameState.roundResult ? {
        isDraw: !!gameState.roundResult.isDraw,
        winType: gameState.roundResult.winType === game.ActionType.ACTION_TSUMO ? 'tsumo' : 'ron',
        winnerLabel: `Seat ${gameState.roundResult.winnerSeat} wins`,
        discarderLabel: gameState.roundResult.winType === game.ActionType.ACTION_RON ? `From Seat ${gameState.roundResult.discarderSeat}` : null,
        closedHand: winningHandWithoutWinTile,
        winTile: gameState.roundResult.winTile || null,
        winningMelds: (gameState.roundResult.winningMelds || []).map((meld: any) => ({
            tiles: meld.tiles || [],
            calledTileId: meld.calledTileId,
            calledDirection: meld.calledDirection,
        })),
        flowers: winnerPlayer?.flowerMelds || [],
        breakdown: (gameState.roundResult.breakdown || []).map((entry: any) => ({
            name: entry.patternName,
            points: entry.points,
        })),
        totalScore: gameState.roundResult.totalScore,
        payouts: (gameState.roundResult.payouts || []).map((payout: any) => ({
            seat: payout.seat,
            label: `Seat ${payout.seat}`,
            amount: payout.amount,
            readyLabel: gameState.playerReady && gameState.playerReady.length > payout.seat
                ? (gameState.playerReady[payout.seat] ? 'Ready' : '...')
                : null,
            readyActive: !!(gameState.playerReady && gameState.playerReady[payout.seat]),
        })),
        actions: readyActions,
    } : null;

    return (
        <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
            {gameState?.phase === 5 /* PHASE_MATCH_END */ && (
                <MatchEndOverlay
                    state={gameState}
                    seatNames={[null, null, null, null]}
                />
            )}
            {gameState?.matchMode === 2 && gameState.chongciConfig && (
                <div className="mt-1 inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-900/30 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-amber-200">
                    <span>Chongci</span>
                    <span className="text-amber-400/70">·</span>
                    <span>Start {Number(gameState.chongciConfig.startingScore)}</span>
                    <span className="text-amber-400/70">·</span>
                    <span>Bust ≤ {Number(gameState.chongciConfig.bustThreshold)}</span>
                    <span className="text-amber-400/70">·</span>
                    <span>
                        {Number(gameState.chongciConfig.maxHands) === 0
                            ? 'No cap'
                            : `Cap ${Number(gameState.chongciConfig.maxHands)}`}
                    </span>
                </div>
            )}
            <div className="game-stage-frame" style={stageFrameStyle}>
                <div className="game-stage" style={stageStyle}>
                    <TableBoard
                        viewSeat={mySeatId}
                        players={playerViews}
                        activeSeat={gameState.activePlayer}
                        wildTiles={gameState.wildTiles || []}
                        hudChips={hudChips}
                        actionBar={actionBar}
                        canDiscardSeat={gameState.activePlayer === mySeatId && gameState.phase === 2
                            && validActions.some((action: any) => action.type === game.ActionType.ACTION_DISCARD)
                            ? mySeatId
                            : null}
                        onDiscard={onDiscard}
                        isWildTile={isWildTile}
                        animateDiscardTileIds={newlyDiscardedTileIds}
                        callableDiscard={callableDiscard}
                    />
                </div>
            </div>
            <TableRoundResultOverlay result={roundResultView} isWildTile={isWildTile} />
        </div>
    );
}
