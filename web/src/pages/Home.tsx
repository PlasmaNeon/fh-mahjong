import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PageShell from '../components/PageShell'
import GlassCard from '../components/GlassCard'
import Eyebrow from '../components/Eyebrow'
import PageHeading from '../components/PageHeading'
import { ButtonLink } from '../components/Button'

// Decode the username from the stored JWT, if present, so the account button
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
        <PageShell maxWidth="max-w-6xl">
            <header className="flex items-center justify-between">
                <span className="text-xs font-black uppercase tracking-[0.3em] text-emerald-300/85">Fenghua Mahjong</span>
                <Link
                    to="/login"
                    className="rounded-[18px] border border-white/14 bg-white/5 px-5 py-2.5 text-[11px] font-black uppercase tracking-[0.16em] text-slate-100 transition hover:bg-white/10"
                >
                    {username ? `Signed in · ${username}` : 'Login / Register'}
                </Link>
            </header>

            <div className="mt-10">
                <Eyebrow>Welcome</Eyebrow>
                <PageHeading className="mt-3">Fenghua Mahjong</PageHeading>
                <p className="mt-5 max-w-2xl text-sm leading-8 text-slate-300">
                    Jump into a live public match, spin up a private room for friends, or open the
                    scoring and shanten tools. Everything below is one click away.
                </p>
            </div>

            <div className="mt-10 grid gap-5 sm:grid-cols-2">
                <GlassCard className="flex flex-col">
                    <Eyebrow>Play</Eyebrow>
                    <p className="mt-3 mb-6 flex-1 text-sm leading-7 text-slate-300">
                        Queue into the live hometown-rules pool and drop straight into a match when four players are ready.
                    </p>
                    <ButtonLink to="/play" variant="primary" className="self-start">Find Match →</ButtonLink>
                </GlassCard>

                <GlassCard className="flex flex-col">
                    <Eyebrow className="text-cyan-200/85">Private Room</Eyebrow>
                    <p className="mt-3 mb-6 flex-1 text-sm leading-7 text-slate-300">
                        Generate a shareable room link, send it to friends, fill empty seats with AI, and start when ready.
                    </p>
                    <ButtonLink to="/room/new" variant="secondary" className="self-start">Create Private Room →</ButtonLink>
                </GlassCard>

                <GlassCard className="flex flex-col">
                    <Eyebrow className="text-amber-200/85">Tools</Eyebrow>
                    <p className="mt-3 mb-6 flex-1 text-sm leading-7 text-slate-300">
                        Standalone calculators — no login needed.
                    </p>
                    <div className="flex flex-wrap gap-3">
                        <ButtonLink to="/tools/calc" variant="ghost">Scoring Calculator</ButtonLink>
                        <ButtonLink to="/tools/shanten" variant="ghost">Shanten Calculator</ButtonLink>
                    </div>
                </GlassCard>

                <GlassCard className="flex flex-col">
                    <Eyebrow>Account</Eyebrow>
                    <p className="mt-3 mb-6 flex-1 text-sm leading-7 text-slate-300">
                        Login to keep your matchmaking profile, or play instantly as a guest from any private room link.
                    </p>
                    <ButtonLink to="/login" variant="ghost" className="self-start">
                        {username ? 'Account →' : 'Login / Register →'}
                    </ButtonLink>
                </GlassCard>
            </div>
        </PageShell>
    )
}
