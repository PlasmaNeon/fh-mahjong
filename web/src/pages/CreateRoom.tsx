import { useMemo, useState } from 'react';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, ButtonLink, TextLink, Note } from '../theme';

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

    const meta =
        copyState === 'copied' ? <span style={{ color: 'var(--accent)' }}>copied</span>
        : copyState === 'failed' ? <span style={{ color: 'var(--danger)' }}>copy failed</span>
        : undefined;

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Private Room"
                        subtitle="生成房间链接"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/play">Matchmaking →</TextLink>
                        </>}
                    />

                    <Section title="Share link" meta={meta}>
                        <ToolsRow>
                            <Button variant="primary" onClick={handleCreateRoom}>
                                {roomId ? 'Create another link' : 'Generate link'}
                            </Button>
                            {roomUrl && <ButtonLink to={`/room/${roomId}`}>Open Room →</ButtonLink>}
                        </ToolsRow>

                        <div className="ldg-input-row">
                            <input
                                className="ldg-input"
                                readOnly
                                value={roomUrl}
                                placeholder="Generate a room link first, then copy or open it."
                            />
                            <Button onClick={handleCopy} disabled={!roomUrl}>Copy</Button>
                        </div>

                        <Note>
                            Send the link to friends. Everyone opens the same /room/… link and enters a name;
                            the host (first joiner) fills any empty seats with AI and starts when ready.
                        </Note>
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
