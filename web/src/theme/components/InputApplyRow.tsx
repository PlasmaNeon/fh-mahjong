/**
 * The `.ldg-input-row` text-entry + apply-button pair used by the tool pages.
 *
 * `submitOnEnter` is an explicit prop rather than always-on: the shanten page
 * applies its hand on Enter, while the calc page's three rows do not bind the
 * key at all.
 */
export function InputApplyRow({
  value,
  onChange,
  onApply,
  applyLabel,
  placeholder,
  submitOnEnter = false,
}: {
  value: string
  onChange: (value: string) => void
  onApply: () => void
  applyLabel: string
  placeholder?: string
  submitOnEnter?: boolean
}) {
  return (
    <div className="ldg-input-row">
      <input
        className="ldg-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={submitOnEnter ? (event) => { if (event.key === 'Enter') onApply() } : undefined}
        placeholder={placeholder}
      />
      <button type="button" className="ldg-btn" onClick={onApply}>
        {applyLabel}
      </button>
    </div>
  )
}
