import { useEffect, useState } from 'react'
import { Page, Shell, Card, PageHeader, Section, ToolsRow, ButtonLink, TextLink, Note } from '../theme'

// Decode the username from the stored JWT, if present, so the account link
// reflects logged-in state without a network call.
function useStoredUsername(): string | null {
    const [username, setUsername] = useState<string | null>(null)
    useEffect(() => {
        const token = localStorage.getItem('fh_token')
        if (!token) {
            setUsername(null)
            return
        }
        const parts = token.split('.')
        if (parts.length !== 3) {
            setUsername(null)
            return
        }
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')))
            setUsername(typeof payload.username === 'string' ? payload.username : null)
        } catch {
            setUsername(null)
        }
    }, [])
    return username
}

export default function Home() {
    const username = useStoredUsername()

    return (
        <Page>
            <Shell>
                <Card>
                    <PageHeader
                        title="Fenghua Mahjong"
                        subtitle="奉化麻将"
                        nav={<TextLink to="/login">{username ? `Signed in · ${username}` : 'Login / Register'}</TextLink>}
                    />

                    <Note style={{ marginTop: '1.25rem' }}>
                        Jump into a live public match, set up a private room for friends, or open the
                        scoring and shanten tools.
                    </Note>

                    <Section title="Play" subtitle="Live hometown-rules matchmaking">
                        <ToolsRow>
                            <ButtonLink to="/play" variant="primary">Find Match →</ButtonLink>
                        </ToolsRow>
                    </Section>

                    <Section title="Private Room" subtitle="Play with friends by link">
                        <ToolsRow>
                            <ButtonLink to="/room/new">Create Private Room →</ButtonLink>
                        </ToolsRow>
                    </Section>

                    <Section title="Tools" subtitle="No login needed">
                        <ToolsRow>
                            <ButtonLink to="/tools/calc">Scoring Calculator</ButtonLink>
                            <ButtonLink to="/tools/shanten">Shanten Calculator</ButtonLink>
                        </ToolsRow>
                    </Section>
                </Card>
            </Shell>
        </Page>
    )
}
