import type { ReactNode } from 'react'

// Segmented control. Generic over the option value type.
export default function Toggle<T extends string | number>({
    options,
    value,
    onChange,
    disabled = false,
}: {
    options: Array<{ value: T; label: ReactNode }>
    value: T
    onChange: (value: T) => void
    disabled?: boolean
}) {
    return (
        <div className="ldg-toggle">
            {options.map(opt => (
                <button
                    key={String(opt.value)}
                    type="button"
                    className={`ldg-toggle__btn${opt.value === value ? ' is-active' : ''}`}
                    disabled={disabled}
                    onClick={() => onChange(opt.value)}
                >
                    {opt.label}
                </button>
            ))}
        </div>
    )
}
