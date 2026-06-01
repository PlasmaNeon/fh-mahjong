import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import './ledger-theme.css';

function makeRoomId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID().slice(0, 8);
    }

    return Math.random().toString(36).slice(2, 10);
}

export default function CreateRoom() {
    const [roomId, setRoomId] = useState('');
    const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');

    const roomUrl = useMemo(() => {
        if (!roomId || typeof window === 'undefined') {
            return '';
        }

        return `${window.location.origin}/room/${roomId}`;
    }, [roomId]);

    const handleCreateRoom = () => {
        setRoomId(makeRoomId());
        setCopyState('idle');
    };

    const handleCopy = async () => {
        if (!roomUrl) return;

        try {
            await navigator.clipboard.writeText(roomUrl);
            setCopyState('copied');
        } catch {
            setCopyState('failed');
        }
    };

    return (
        <div className="ledger-page">
            <div className="ledger-shell">
                <article className="ldg-page">
                    <div className="ldg-page-head">
                        <div>
                            <h1 className="ldg-page-head__title">
                                Private Room
                                <small>生成房间链接</small>
                            </h1>
                        </div>
                        <div className="ldg-page-head__nav">
                            <Link to="/" className="ldg-link">Home</Link>
                            <Link to="/play" className="ldg-link">Matchmaking →</Link>
                        </div>
                    </div>

                    <section className="ldg-section">
                        <div className="ldg-section-row">
                            <h2 className="ldg-section-title">Share link</h2>
                            {copyState === 'copied' && <span className="ldg-section-meta" style={{ color: 'var(--accent)' }}>copied</span>}
                            {copyState === 'failed' && <span className="ldg-section-meta" style={{ color: 'var(--danger)' }}>copy failed</span>}
                        </div>

                        <div className="ldg-tools-row">
                            <button className="ldg-btn ldg-btn--primary" onClick={handleCreateRoom}>
                                {roomId ? 'Create another link' : 'Generate link'}
                            </button>
                            {roomUrl && <Link to={`/room/${roomId}`} className="ldg-btn">Open Room →</Link>}
                        </div>

                        <div className="ldg-input-row">
                            <input
                                className="ldg-input"
                                readOnly
                                value={roomUrl}
                                placeholder="Generate a room link first, then copy or open it."
                            />
                            <button className="ldg-btn" onClick={handleCopy} disabled={!roomUrl}>Copy</button>
                        </div>

                        <p className="ldg-note">
                            Send the link to friends. Everyone opens the same /room/… link and enters a name;
                            the host (first joiner) fills any empty seats with AI and starts when ready.
                        </p>
                    </section>
                </article>
            </div>
        </div>
    );
}
