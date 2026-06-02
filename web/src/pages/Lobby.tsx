import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { Page, Shell, Card, PageHeader, Section, ToolsRow, Button, ButtonLink, TextLink, Note } from '../theme';

export default function Lobby() {
    const [isQueuing, setIsQueuing] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();
    const { isConnected, connect } = useSocket();
    const { gameState } = useGameState();

    useEffect(() => {
        const token = localStorage.getItem('fh_token');
        if (token && !isConnected) {
            connect(token);
        }

        if (gameState && gameState.matchId) {
            navigate(`/match/${gameState.matchId}`);
        }
    }, [isConnected, gameState, navigate, connect]);

    const joinQueue = async (ruleset: 'hometown' | 'chongci-fh' = 'hometown') => {
        const token = localStorage.getItem('fh_token');
        if (!token) return navigate('/login');

        setError('');
        setIsQueuing(true);
        try {
            const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify({ ruleset }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.error || 'Failed to join queue');
            }
        } catch (e: any) {
            setError(e.message || 'Error contacting matchmaker');
            setIsQueuing(false);
        }
    };

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Play"
                        subtitle="实时匹配 · Hometown rules"
                        nav={<>
                            <TextLink to="/">Home</TextLink>
                            <TextLink to="/room/new">Private room →</TextLink>
                        </>}
                    />

                    <Section title="Matchmaking" meta={isConnected ? 'socket ready' : 'socket offline'}>
                        {error && <Note tone="error">{error}</Note>}

                        {isQueuing ? (
                            <Note>
                                Searching for players… stay on this page; you'll jump into the match
                                automatically once the room is ready.
                            </Note>
                        ) : (
                            <ToolsRow>
                                <Button variant="primary" disabled={!isConnected} onClick={() => joinQueue('hometown')}>Find Match</Button>
                                <Button disabled={!isConnected} onClick={() => joinQueue('chongci-fh')}>Quick Match · Chongci</Button>
                                <ButtonLink to="/room/new">Private Room</ButtonLink>
                            </ToolsRow>
                        )}
                    </Section>
                </Card>
            </Shell>
        </Page>
    );
}
