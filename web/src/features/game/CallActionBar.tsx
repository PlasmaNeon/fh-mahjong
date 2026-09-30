import { useRef, useState } from 'react'
import { game } from '../../proto/game'
import { TileComponent } from '../../table/Tile'
import { useI18n } from '../../i18n/I18nContext'
import { getTileName } from '../../utils/tileDisplay'
import { orderTableActions } from './actionOrdering'
import './callActionBar.css'

export type CallAction = game.IPlayerAction
const calls = new Set([game.ActionType.ACTION_CHII, game.ActionType.ACTION_PON, game.ActionType.ACTION_KAN])
const labels = {
  [game.ActionType.ACTION_CHII]: 'game.chii',
  [game.ActionType.ACTION_PON]: 'game.pon',
  [game.ActionType.ACTION_KAN]: 'game.kan',
  [game.ActionType.ACTION_RON]: 'game.ron',
  [game.ActionType.ACTION_TSUMO]: 'game.tsumo',
  [game.ActionType.ACTION_PASS]: 'game.pass',
} as const

// Equivalent physical copies share a choice; retain the original server action.
export function uniqueCallChoices(actions: CallAction[]): CallAction[] {
  const seen = new Set<string>()
  return actions.filter(action => {
    const key = `${action.type}:${(action.meldTiles ?? []).map(tile => `${tile.suit}/${tile.value}`).sort().join(',')}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function callActionKey(actions: CallAction[], context: string): string {
  return JSON.stringify([context, actions.map(action => [action.type, action.tile?.id, (action.meldTiles ?? []).map(tile => [tile.id, tile.suit, tile.value])])])
}

type Props = {
  actions: CallAction[]
  contextKey: string
  onAction: (action: CallAction) => void | boolean
  allowPass?: boolean
  isWildTile?: (tile: game.ITile) => boolean
}

export function CallActionBar(props: Props) {
  // A new discard, turn or legal-action set invalidates the old open chooser
  // synchronously, before another click can submit an obsolete candidate.
  return <ActionSession key={callActionKey(props.actions, props.contextKey)} {...props} />
}

function ActionSession({ actions, onAction, allowPass = false, isWildTile }: Props) {
  const { t } = useI18n()
  const [choosing, setChoosing] = useState<game.ActionType | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const sent = useRef(false)
  const trigger = useRef<game.ActionType | null>(null)
  const choices = uniqueCallChoices(actions.filter(action => action.type === choosing))
  const ordered = orderTableActions(uniqueCallChoices(actions)).filter(action => action.type != null && action.type in labels && action.type !== game.ActionType.ACTION_PASS)
  const types = [...new Set(ordered.map(action => action.type!))]
  const label = (type: game.ActionType) => {
    const text = t(labels[type as keyof typeof labels] ?? 'game.action')
    return text.charAt(0) + text.slice(1).toLowerCase()
  }
  const submit = (action: CallAction) => {
    if (sent.current) return
    sent.current = true
    if (onAction(action) === false) { sent.current = false; return }
    setSubmitted(true)
  }
  const back = () => { setChoosing(null); /* the remounted trigger restores focus */ }
  if (submitted) return <div className="call-action-dock" role="status">{t('game.actionSent')}</div>
  if (!types.length && !allowPass) return null
  return (
    <div className="call-action-dock" onKeyDown={event => {
      if (event.key === 'Escape' && choosing != null) { event.preventDefault(); back() }
    }}>
      {choosing != null && (
        <section className="call-choice-panel" aria-label={t('game.chooseCallGroup')}>
          <div className="call-choice-heading"><span>{label(choosing)}</span>{t('game.chooseCallGroup')}</div>
          <div className="call-choice-options">
            {choices.map((action, index) => (
              <button type="button" className="call-choice-option" key={index} autoFocus={index === 0}
                aria-label={`${label(choosing)}: ${(action.meldTiles ?? []).map(getTileName).join(', ')}`}
                onClick={() => submit(action)}>
                {(action.meldTiles ?? []).map((tile, tileIndex) => (
                  <TileComponent key={tileIndex} tile={{ id: Number(tile.id), suit: Number(tile.suit), value: Number(tile.value) }} size="small" isWild={isWildTile?.(tile)} />
                ))}
              </button>
            ))}
          </div>
        </section>
      )}
      <div className="call-action-buttons">
        {choosing != null ? (
          <button type="button" className="call-action-button call-action-back" onClick={back}>{t('game.backToActions')}</button>
        ) : types.map(type => (
          <button type="button" key={type} className={`call-action-button ${type === game.ActionType.ACTION_RON || type === game.ActionType.ACTION_TSUMO ? 'call-action-win' : ''}`}
            aria-haspopup={calls.has(type) && uniqueCallChoices(actions.filter(action => action.type === type)).length > 1 ? 'true' : undefined}
            ref={element => { if (element && trigger.current === type) { element.focus(); trigger.current = null } }}
            onClick={() => {
              const candidates = uniqueCallChoices(actions.filter(action => action.type === type))
              if (calls.has(type) && candidates.length > 1) { trigger.current = type; setChoosing(type) }
              else if (candidates[0]) submit(candidates[0])
            }}>{label(type)}</button>
        ))}
        {allowPass && <button type="button" className="call-action-button call-action-pass" onClick={() => submit(actions.find(a => a.type === game.ActionType.ACTION_PASS) ?? { type: game.ActionType.ACTION_PASS })}>{label(game.ActionType.ACTION_PASS)}</button>}
      </div>
    </div>
  )
}
