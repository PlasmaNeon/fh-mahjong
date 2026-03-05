// @ts-nocheck
import React, { useState, useEffect } from 'react';
import { getTileSvgName, getTileName } from '../utils/tileUtils';

// Enum definitions
enum Suit {
    SUIT_MAN = 0,
    SUIT_PIN = 1,
    SUIT_SOU = 2,
    SUIT_JIHAI = 3
}
enum ActionType {
    ACTION_UNKNOWN = 0,
    ACTION_CHII = 1,
    ACTION_PON = 2,
    ACTION_KAN = 3,
    ACTION_TSUMO = 4,
    ACTION_RON = 5
}

interface Tile {
    suit: Suit;
    value: number;
    id: number;
    hash: number;
}

interface Meld {
    type: ActionType;
    tiles: number[]; // Hashes
    calledTileIndex: number;
    calledDirection: number;
}

// Generate all 34 tiles (1 of each for the picker)
const allTiles: Tile[] = [];
[Suit.SUIT_MAN, Suit.SUIT_PIN, Suit.SUIT_SOU].forEach(s => {
    for (let v = 1; v <= 9; v++) {
        allTiles.push({ suit: s, value: v, id: 0, hash: s * 100 + v });
    }
});
for (let v = 1; v <= 7; v++) { // Jihai
    allTiles.push({ suit: Suit.SUIT_JIHAI, value: v, id: 0, hash: Suit.SUIT_JIHAI * 100 + v });
}

// Shared Tile Component
const CalcTile = ({ tile, isWild, onClick, size = 'normal', selected = false }: { tile: Tile, isWild?: boolean, onClick?: () => void, size?: 'normal' | 'small', selected?: boolean }) => {
    const svgName = getTileSvgName(tile);
    return (
        <div
            className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${selected ? 'border-2 border-green-500 box-content -m-0.5' : ''} ${size === 'small' ? 'small' : ''}`}
            onClick={onClick}
            style={{
                padding: 0, border: selected ? '2px solid #22c55e' : 'none', backgroundColor: '#ebe7d9',
                boxShadow: isWild ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)', cursor: 'pointer', position: 'relative'
            }}
        >
            <img src={`/Regular_shortnames/Front.svg`} style={{ width: '100%', height: '100%', display: 'block', borderRadius: '4px', position: 'absolute', top: 0, left: 0, zIndex: 1 }} draggable="false" />
            <img src={`/Regular_shortnames/${svgName}`} alt={getTileName(tile)} style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }} draggable="false" />
        </div>
    );
};

export default function Calc() {
    const [closedHand, setClosedHand] = useState<number[]>([]);
    const [openMelds, setOpenMelds] = useState<Meld[]>([]);
    const [winTile, setWinTile] = useState<number | null>(null);
    const [wildTiles, setWildTiles] = useState<number[]>([]);

    const [isTsumo, setIsTsumo] = useState<boolean>(true);
    const [seatWind, setSeatWind] = useState<number>(1);
    const [prevailingWind, setPrevailingWind] = useState<number>(1);

    // Score State
    const [scoreData, setScoreData] = useState<{ canWin: boolean, score: number, entries: any[] } | null>(null);

    const calculateScore = () => {
        if (!winTile) {
            setScoreData(null);
            return;
        }

        const payload = {
            closedHand,
            openMelds,
            winTile,
            isTsumo,
            wildTiles,
            seatWind,
            prevailingWind
        };

        fetch('/api/v1/calc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(res => res.json()).then(data => {
            setScoreData(data);
        }).catch(err => {
            console.error("Calc API Error:", err);
            setScoreData(null);
        });
    };

    const handleTileClick = (t: Tile) => {
        if (closedHand.length < 13) {
            setClosedHand([...closedHand, t.hash]);
        }
    };

    const handleRemoveClosed = (idx: number) => {
        const h = [...closedHand];
        h.splice(idx, 1);
        setClosedHand(h);
    };

    const addMeld = (type: ActionType) => {
        if (closedHand.length >= 3) {
            const h = [...closedHand];
            const tiles = h.splice(-3); // pop last 3
            setClosedHand(h);
            setOpenMelds([...openMelds, {
                type,
                tiles,
                calledTileIndex: 0,
                calledDirection: 3 // from left
            }]);
        }
    };

    const removeMeld = (idx: number) => {
        const m = [...openMelds];
        const removed = m.splice(idx, 1)[0];
        setOpenMelds(m);
        // Put tiles back to hand safely
        setClosedHand([...closedHand, ...removed.tiles]);
    };

    const toggleWild = (hash: number) => {
        if (wildTiles.includes(hash)) {
            setWildTiles(wildTiles.filter(w => w !== hash));
        } else {
            setWildTiles([...wildTiles, hash]);
        }
    };

    const getLogString = () => {
        let str = "";
        const sortedHand = [...closedHand].sort((a, b) => {
            const ta = allTiles.find(x => x.hash === a);
            const tb = allTiles.find(x => x.hash === b);
            if (!ta || !tb) return 0;
            if (ta.suit !== tb.suit) return ta.suit - tb.suit;
            return ta.value - tb.value;
        });

        sortedHand.forEach(hash => {
            const t = allTiles.find(x => x.hash === hash);
            if (t) {
                let suitChar = '';
                switch (t.suit) {
                    case 0: suitChar = 'm'; break;
                    case 1: suitChar = 'p'; break;
                    case 2: suitChar = 's'; break;
                    case 3: suitChar = 'z'; break;
                }
                str += `${t.value}${suitChar}`;
            }
        });

        if (winTile) {
            const t = allTiles.find(x => x.hash === winTile);
            if (t) {
                let suitChar = '';
                switch (t.suit) {
                    case 0: suitChar = 'm'; break;
                    case 1: suitChar = 'p'; break;
                    case 2: suitChar = 's'; break;
                    case 3: suitChar = 'z'; break;
                }
                str += ` + ${t.value}${suitChar}`;
            }
        }
        return str;
    };



    return (
        <div className="container mx-auto p-4 flex flex-col gap-6">
            <h1 className="text-3xl font-bold">Fenghua Mahjong Scoring Calculator</h1>

            {/* Tile Picker */}
            <div className="bg-gray-800 p-4 rounded-xl border border-gray-700">
                <h2 className="text-xl font-semibold mb-2">Tile Library (Click to add to closed hand, drag to Win Tile)</h2>
                <div className="flex flex-wrap gap-2">
                    {allTiles.map(t => (
                        <div
                            key={t.hash}
                            onClick={() => handleTileClick(t)}
                            draggable
                            onDragStart={(e) => {
                                e.dataTransfer.setData('tileHash', t.hash.toString());
                                e.dataTransfer.effectAllowed = 'copy';
                            }}
                        >
                            <CalcTile tile={t} />
                        </div>
                    ))}
                </div>
            </div>

            {/* Hand Composer */}
            <div className="bg-gray-800 p-4 rounded-xl border border-gray-700">
                <h2 className="text-xl font-semibold mb-4">Your Hand Component</h2>

                {/* Closed Hand */}
                <div className="mb-4">
                    <div className="flex gap-2 items-center mb-2">
                        <span className="font-semibold text-gray-300">Closed Hand (Click to remove):</span>
                        <span className="text-sm bg-gray-700 px-2 rounded">{closedHand.length} tiles</span>
                    </div>
                    <div className="flex gap-1 h-16 bg-gray-900 p-2 rounded">
                        {closedHand.map((h, i) => {
                            const t = allTiles.find(x => x.hash === h);
                            return t && <CalcTile key={i} tile={t} onClick={() => handleRemoveClosed(i)} isWild={wildTiles.includes(h)} />;
                        })}
                    </div>
                </div>

                {/* Win Tile */}
                <div className="mb-4">
                    <div className="flex gap-2 items-center mb-2">
                        <span className="font-semibold text-gray-300">Win Tile (Tsumo/Ron):</span>
                        {winTile && <button onClick={() => setWinTile(null)} className="text-xs text-red-400 border border-red-500 rounded px-2 hover:bg-red-900">Clear Win Tile</button>}
                    </div>
                    <div
                        className={`flex items-center justify-center rounded transition-colors ${!winTile ? 'border-2 border-dashed border-gray-500 bg-gray-900/50 hover:bg-gray-800' : ''}`}
                        style={{ width: '4vw', height: '5.6vw', minWidth: '36px', minHeight: '52px' }}
                        onDragOver={(e) => {
                            e.preventDefault();
                            e.dataTransfer.dropEffect = 'copy';
                        }}
                        onDrop={(e) => {
                            e.preventDefault();
                            const hash = Number(e.dataTransfer.getData('tileHash'));
                            if (!isNaN(hash) && hash > 0) {
                                setWinTile(hash);
                            }
                        }}
                    >
                        {winTile ? (
                            <CalcTile tile={allTiles.find(x => x.hash === winTile)!} onClick={() => setWinTile(null)} />
                        ) : (
                            <div className="text-xs text-gray-500 text-center pointer-events-none p-1">Drop<br />Here</div>
                        )}
                    </div>
                </div>

                {/* Open Melds */}
                <div className="mb-4">
                    <div className="flex gap-2 items-center mb-2">
                        <span className="font-semibold text-gray-300">Open Melds:</span>
                        <button className="bg-gray-600 hover:bg-gray-500 px-2 py-1 rounded text-xs transition" onClick={() => addMeld(ActionType.ACTION_PON)}>
                            Take last 3 for Pon
                        </button>
                        <button className="bg-gray-600 hover:bg-gray-500 px-2 py-1 rounded text-xs transition" onClick={() => addMeld(ActionType.ACTION_CHII)}>
                            Take last 3 for Chii
                        </button>
                    </div>
                    <div className="flex gap-4 min-h-[4rem] bg-gray-900 p-2 rounded">
                        {openMelds.map((m, i) => (
                            <div key={i} className="flex gap-0.5 bg-gray-800 p-1 rounded cursor-pointer hover:bg-red-900/50" onClick={() => removeMeld(i)}>
                                {m.tiles.map((th, tidx) => {
                                    const t = allTiles.find(x => x.hash === th);
                                    return t && <div key={tidx} className={tidx === 0 ? "rotate-90 origin-bottom scale-y-110 ml-2 mr-1" : ""}><CalcTile tile={t} size="small" /></div>;
                                })}
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Game Context Settings */}
            <div className="bg-gray-800 p-4 rounded-xl border border-gray-700 flex gap-10">
                <div>
                    <h2 className="text-xl font-semibold mb-2">Win Condition</h2>
                    <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" className="w-5 h-5" checked={isTsumo} onChange={e => setIsTsumo(e.target.checked)} />
                        <span>Self Draw (Tsumo / 自摸)</span>
                    </label>
                    {!isTsumo && <div className="text-sm text-orange-400 mt-1">If unchecked, it's a Ron (Discard)</div>}
                </div>

                <div>
                    <h2 className="text-xl font-semibold mb-2">Winds</h2>
                    <div className="flex gap-4">
                        <label className="flex flex-col text-sm">Prevailing Wind
                            <select className="text-black p-1 rounded mt-1" value={prevailingWind} onChange={e => setPrevailingWind(Number(e.target.value))}>
                                <option value="1">East</option>
                                <option value="2">South</option>
                                <option value="3">West</option>
                                <option value="4">North</option>
                            </select>
                        </label>
                        <label className="flex flex-col text-sm">Seat Wind
                            <select className="text-black p-1 rounded mt-1" value={seatWind} onChange={e => setSeatWind(Number(e.target.value))}>
                                <option value="1">East</option>
                                <option value="2">South</option>
                                <option value="3">West</option>
                                <option value="4">North</option>
                            </select>
                        </label>
                    </div>
                </div>

                <div>
                    <h2 className="text-xl font-semibold mb-2">Wild Tiles (Baidacao)</h2>
                    <div className="flex flex-wrap gap-1 max-w-[200px]">
                        {wildTiles.length === 0 ? <span className="text-gray-400 text-sm">None selected. Click tiles below to toggle.</span> :
                            wildTiles.map(w => {
                                const t = allTiles.find(x => x.hash === w);
                                return t && <div key={w} onClick={() => toggleWild(w)}><CalcTile tile={t} size="small" isWild /></div>;
                            })
                        }
                    </div>
                    <div className="text-xs text-gray-500 mt-2">Click any tile in the Library to toggle it as a Wild Tile.</div>
                </div>
            </div>

            {/* Action Bar */}
            <div className="flex flex-col justify-center items-center mt-4">
                <button
                    className="bg-green-600 hover:bg-green-500 active:bg-green-700 text-white font-bold py-3 px-8 rounded-full shadow-lg transition transform hover:scale-105"
                    onClick={calculateScore}
                    disabled={!winTile}
                >
                    {winTile ? "Calculate Points" : "Missing Win Tile"}
                </button>
                <div className="mt-4 text-gray-400 font-mono text-sm bg-gray-800 px-4 py-2 rounded-lg border border-gray-700">
                    Submission string: <span className="text-white font-bold tracking-widest">{getLogString()}</span>
                </div>
            </div>

            {/* Score Result View */}
            <div className={`p-6 flex flex-col gap-4 rounded-xl border-2 transition-colors ${scoreData?.canWin ? 'bg-gray-900 border-green-500 shadow-[0_0_20px_rgba(34,197,94,0.3)]' : 'bg-gray-900 border-red-900'}`}>
                <h2 className="text-3xl font-extrabold text-center">
                    {scoreData?.canWin ? "Valid Hand!" : "Invalid Hand"}
                </h2>

                {scoreData?.canWin && scoreData.entries && (
                    <div className="max-w-md mx-auto w-full bg-[#111827] rounded shadow-lg p-4 border border-[#374151]">
                        {scoreData.entries.map((entry, idx) => (
                            <div key={idx} className="flex justify-between items-center py-2 border-b border-[#374151] last:border-0 hover:bg-[#1E293B] px-2 rounded">
                                <span className="text-gray-200 font-medium">{entry.PatternName}</span>
                                <span className="text-[#22C55E] font-bold">+{entry.Points}</span>
                            </div>
                        ))}
                        <div className="mt-4 pt-4 border-t-2 border-[#1E293B] font-bold text-xl flex justify-between">
                            <span className="text-gray-400">Total Score:</span>
                            <span className="text-[#22C55E] text-2xl">{scoreData.score}</span>
                        </div>
                    </div>
                )}
            </div>

        </div>
    );
}
