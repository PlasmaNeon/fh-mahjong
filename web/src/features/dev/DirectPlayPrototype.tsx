import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './directPlayPrototype.css'

type Page = 'play' | 'room' | 'search' | 'match' | 'replays' | 'tools'
type Seat = 'human' | 'bot' | 'empty'
const pages: Page[] = ['play', 'room', 'search', 'match', 'replays', 'tools']
const readPage = (): Page => pages.includes(location.hash.slice(1) as Page) ? location.hash.slice(1) as Page : 'play'

function Prototype() {
  const [page, setPage] = useState<Page>(readPage)
  const [zh, setZh] = useState(false)
  const [seats, setSeats] = useState<Seat[]>(['human', 'empty', 'empty', 'empty'])
  const [host, setHost] = useState(true)
  const [room, setRoom] = useState(false)
  const [started, setStarted] = useState(false)
  const [link, setLink] = useState('')
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [rules, setRules] = useState('classic')
  const [signedIn, setSignedIn] = useState(false)
  const [intent, setIntent] = useState<'create' | 'find' | 'join' | null>(null)
  const [phone, setPhone] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const main = useRef<HTMLElement>(null)
  const loginDialog = useRef<HTMLDialogElement>(null)
  const loginOpener = useRef<HTMLElement | null>(null)
  const t = (en: string, cn: string) => zh ? cn : en
  const filled = seats.filter(s => s !== 'empty').length
  const navigate = (next: Page) => { location.hash = next; setPage(next); setError('') }
  useEffect(() => {
    const changed = () => { setPage(readPage()); setError('') }
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  useEffect(() => { document.documentElement.lang = zh ? 'zh-CN' : 'en' }, [zh])
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      (heading.current ?? main.current)?.focus({ preventScroll: true })
      window.scrollTo({ top: 0, behavior: 'auto' })
    })
    return () => cancelAnimationFrame(frame)
  }, [page])
  useEffect(() => {
    if (intent) loginDialog.current?.showModal()
    else if (loginDialog.current?.open) loginDialog.current.close()
  }, [intent])
  function perform(action: 'create' | 'find' | 'join') {
    if (action === 'find') { navigate('search'); return }
    setHost(action === 'create'); setRoom(true); setStarted(false)
    setSeats(action === 'create' ? ['human', 'empty', 'empty', 'empty'] : ['human', 'human', 'empty', 'empty'])
    navigate('room')
  }
  function request(action: 'create' | 'find' | 'join') {
    if (signedIn) perform(action)
    else { loginOpener.current = document.activeElement as HTMLElement; setIntent(action) }
  }
  function openInvitation(event: React.FormEvent) {
    event.preventDefault()
    try {
      const url = new URL(link.trim(), location.origin)
      if (url.origin === location.origin && url.pathname === '/ui-prototype.html' && url.search === '?invite=demo' && url.hash === '#room') { setError(''); request('join'); return }
      if (url.origin !== location.origin || !/^\/room\/[a-zA-Z0-9_-]+$/.test(url.pathname) || url.search || url.hash) throw new Error()
      if (url.pathname !== '/room/demo') { setError(t('This demo room is unavailable. Try /room/demo.', '此演示房间不可用，请试用 /room/demo。')); return }
      setError(''); request('join')
    } catch { setError(t('Paste a room invitation from this site, such as /room/demo.', '请粘贴本站房间邀请，例如 /room/demo。')) }
  }
  async function copyInvitation() {
    // Deliberately shares only this local prototype, never an actual room.
    const demoUrl = new URL('ui-prototype.html?invite=demo#room', location.href).href
    try { await navigator.clipboard.writeText(demoUrl); setCopied(true) }
    catch { setError(t('Copy this preview link manually: ', '请手动复制预览链接：') + demoUrl) }
  }
  useEffect(() => {
    if (new URLSearchParams(location.search).get('invite') === 'demo') {
      setHost(false); setRoom(true); setSeats(['human', 'human', 'empty', 'empty']); navigate('room')
    }
  }, [])
  const navigation = <nav aria-label={t('Main navigation', '主导航')} className="dp-nav">
    {(['play', 'replays', 'tools'] as const).map((p, i) => <a key={p} href={`#${p}`} aria-current={(p === 'play' ? !['replays', 'tools'].includes(page) : page === p) ? 'page' : undefined}>{[t('Play', '对局'), t('Replays', '牌谱'), t('Tools', '工具')][i]}</a>)}
  </nav>
  const title = page === 'room' ? t('Your private table', '你的好友房间') : page === 'search' ? t('Finding your table', '正在寻找牌友') : page === 'match' ? t('Everyone is here.', '牌友已到齐。') : null
  return <>
    <div className="dp-review"><span>{t('Direct play · Interactive concept · Sample data only', '直接开局 · 交互原型 · 仅使用示例数据')}</span><button onClick={() => setPhone(v => !v)}>{phone ? t('Full width', '全宽预览') : t('Phone preview', '手机预览')}</button><button onClick={() => { setSignedIn(false); setRoom(false); setStarted(false); setSeats(['human','empty','empty','empty']); setHost(true); setCopied(false); setRules('classic'); setLink(''); navigate('play') }}>{t('Reset demo', '重置演示')}</button></div>
    <div className={`dp-app${phone ? ' dp-phone' : ''}`}>
      <header className="dp-header"><a href="#play" className="dp-brand"><span>奉化麻将<small>Fenghua Mahjong</small></span></a>{navigation}<div className="dp-utilities"><button onClick={() => setZh(v => !v)}>{zh ? 'English' : '中文'}</button><span>{signedIn ? t('Demo player', '演示玩家') : t('Guest', '访客')}</span></div></header>
      <main className="dp-main" ref={main} tabIndex={-1}>
        {title && <div className="dp-page-heading"><h1 tabIndex={-1} ref={heading}>{title}</h1>{page === 'room' && <p>{t('Share your invitation. The host starts when all four seats are filled.', '分享邀请链接。四个座位坐满后，由房主开始对局。')}</p>}{page === 'search' && <p>{rules === 'classic' ? t('Classic Fenghua · Four players', '经典奉化 · 四人对局') : t('Chongci Fenghua · Four players', '冲刺奉化 · 四人对局')}</p>}</div>}
        {page === 'room' && room && <div className="dp-room-share"><button className="dp-button dp-secondary" onClick={() => void copyInvitation()}>{copied ? t('Preview link copied', '预览链接已复制') : t('Copy invitation', '复制邀请链接')}</button></div>}
        {error && <p role="alert" className="dp-error">{error}</p>}
        {page === 'play' && <>
          {room && <div className="dp-resume"><div><strong>{started ? t('Your match is in progress', '你有一场进行中的对局') : t('Your room is still open', '你的房间仍在等待')}</strong><p>{t('Pick up where you left off.', '回到刚才的房间。')}</p></div><button className="dp-button" onClick={() => navigate(started ? 'match' : 'room')}>{started ? t('Rejoin game', '返回对局') : t('Return to room', '返回房间')}</button></div>}
          <div className="dp-play-grid"><section className="dp-quick"><h2>{t('Find a game', '快速匹配')}</h2><p>{t('Take an open seat with other players.', '与其他牌友一起，开始新的对局。')}</p><label className="dp-rule">{t('Rules', '规则')}<select value={rules} onChange={e => setRules(e.target.value)}><option value="classic">{t('Classic Fenghua', '经典奉化')}</option><option value="chongci">{t('Chongci Fenghua', '冲刺奉化')}</option></select></label><button className="dp-button" onClick={() => request('find')}>{t('Find a game', '开始匹配')}</button></section>
          <section className="dp-friends"><h2>{t('Play with friends', '和朋友一起玩')}</h2><p>{t('Open a private table, then send an invitation.', '创建好友房间，再分享邀请链接。')}</p><button className="dp-button dp-secondary" onClick={() => request('create')}>{t('Create a room', '创建房间')}</button><div className="dp-invitation"><form onSubmit={openInvitation}><label htmlFor="invitation">{t('Already have an invitation?', '已经收到邀请？')}</label><div><input id="invitation" value={link} onChange={e => setLink(e.target.value)} placeholder={t('Paste a room link', '粘贴房间链接')} aria-describedby="invite-help"/><button className="dp-button dp-secondary" type="submit">{t('Open', '加入')}</button></div><small id="invite-help">{t('Try the sample: ', '试用示例：')}<button type="button" className="dp-text-button" onClick={() => setLink('/room/demo')}>/room/demo</button></small></form></div></section></div>
          <footer className="dp-home-footer"><span>{t('Your next game starts here.', '下一局，就从这里开始。')}</span><a href="#replays">{t('Browse your replays', '查看你的牌谱')}</a></footer>
        </>}
        {page === 'room' && (room ? <div className="dp-room-grid"><section className="dp-seat-panel"><div className="dp-section-heading"><h2>{t('At the table', '房间座位')}</h2><span>{filled} / 4 {t('seats filled', '人已入座')}</span></div><div className="dp-seats">{seats.map((seat, i) => <div key={i} className={`dp-seat ${seat === 'empty' ? 'dp-seat-empty' : ''}`}><span className="dp-wind">{['東','南','西','北'][i]}</span><div><strong>{seat === 'empty' ? t('Open seat', '空位') : seat === 'bot' ? t('Bot player', '电脑牌友') : i === (host ? 0 : 1) ? t('You', '你') : t('Friend', '好友')}</strong><small>{i === 0 ? t('Host', '房主') : seat === 'empty' ? t('Invite a friend', '邀请好友入座') : t('Joined', '已入座')}</small></div>{host && i > 0 && seat !== 'human' && <button className="dp-small-button" onClick={() => setSeats(v => v.map((s, j) => i === j ? s === 'bot' ? 'empty' : 'bot' : s))}>{seat === 'empty' ? t('Add bot', '添加电脑') : t('Remove', '移除')}</button>}</div>)}</div><div className="dp-start"><p>{!host ? t('Waiting for the host to start.', '等待房主开始对局。') : filled === 4 ? t('All seats filled. You can start.', '座位已满，可以开始对局。') : t(`Invite ${4-filled} more players or add bots.`, `再邀请 ${4-filled} 位牌友，或添加电脑。`)}</p><button className="dp-button" disabled={!host || filled !== 4} onClick={() => { setStarted(true); navigate('match') }}>{t('Start game', '开始对局')}</button></div></section><aside className="dp-room-aside"><h2>{t('Bring your friends', '邀请朋友入座')}</h2><p>{t('One link brings everyone to this table.', '分享同一个链接，一起加入这个房间。')}</p><p role="status" className="dp-muted">{copied ? t('This link opens the guest view of this prototype.', '此链接打开原型的访客视角。') : t('Private room · Demo', '好友房间 · 演示')}</p><hr/><label className="dp-rule">{t('Table rules', '房间规则')}<select disabled={!host} value={rules} onChange={e => setRules(e.target.value)}><option value="classic">{t('Classic Fenghua', '经典奉化')}</option><option value="chongci">{t('Chongci Fenghua', '冲刺奉化')}</option></select></label><p className="dp-muted">{t('Only the host can change rules and fill empty seats.', '只有房主可以修改规则、添加电脑。')}</p><a href="#play">{t('Back to Play', '返回对局首页')}</a><p className="dp-muted">{t('Your room stays open when you browse.', '浏览其他页面时，房间仍会保留。')}</p></aside></div> : <section className="dp-empty"><p>{t('No room is open yet.', '还没有加入房间。')}</p><button className="dp-button" onClick={() => request('create')}>{t('Create a room', '创建房间')}</button></section>)}
        {page === 'search' && <section className="dp-empty"><div className="dp-search-mark" aria-hidden="true">東</div><h2>{t('Looking for three other players', '正在寻找另外三位牌友')}</h2><p>{rules === 'classic' ? t('Classic Fenghua', '经典奉化') : t('Chongci Fenghua', '冲刺奉化')}</p><p>{t('Demo: no real matchmaking request is sent.', '演示状态：不会发起真实匹配。')}</p><button className="dp-button dp-secondary" onClick={() => navigate('play')}>{t('Cancel search', '取消匹配')}</button></section>}
        {page === 'match' && <section className="dp-empty"><div className="dp-search-mark">東</div><h2>{t('The table is ready', '准备开始对局')}</h2><p>{t('End of this navigation prototype. The live game is unchanged.', '导航原型到此结束，真实对局界面保持不变。')}</p><button className="dp-button" onClick={() => navigate('play')}>{t('Back to Play', '返回对局首页')}</button></section>}
        {page === 'replays' && <section className="dp-empty"><h2>{t('No completed games in this demo', '演示中暂无已完成对局')}</h2><p>{t('Completed matches will appear here. Your Play navigation stays in the same place.', '已完成的对局将在此显示，主导航的位置保持一致。')}</p><a className="dp-button" href="#play">{t('Go to Play', '去对局')}</a></section>}
        {page === 'tools' && <section className="dp-empty"><h2>{t('Scoring and hand analysis', '计分与手牌分析')}</h2><p>{t('These links open the existing tools in a separate tab.', '以下链接将在新标签页打开现有工具。')}</p><div className="dp-tool-links"><a className="dp-button" href="/tools/calc" target="_blank" rel="noreferrer">{t('Score calculator', '计分工具')}</a><a className="dp-button dp-secondary" href="/tools/shanten" target="_blank" rel="noreferrer">{t('Shanten calculator', '向听工具')}</a></div></section>}
      </main><div className="dp-mobile-nav">{navigation}</div>
    </div>
    <dialog ref={loginDialog} aria-labelledby="demo-login-title" className="dp-dialog" onCancel={() => setIntent(null)} onClose={() => { setIntent(null); loginOpener.current?.focus() }}><h2 id="demo-login-title">{t('Sign in to take a seat', '登录后入座')}</h2><p>{t('In the real app, sign-in returns you to the action you chose. This demo needs no credentials.', '真实应用将在登录后继续刚才的操作。此演示无需账号密码。')}</p><button className="dp-button" onClick={() => { const next = intent; setSignedIn(true); setIntent(null); if (next) perform(next) }}>{t('Continue as demo player', '以演示玩家继续')}</button><button className="dp-text-button" onClick={() => setIntent(null)}>{t('Cancel', '取消')}</button></dialog>
  </>
}
createRoot(document.getElementById('prototype-root')!).render(<Prototype />)
