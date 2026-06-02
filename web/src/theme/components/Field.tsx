import type { CSSProperties, InputHTMLAttributes } from 'react'

// Labelled text input. `style` is applied to the field wrapper (e.g. vertical spacing);
// all other props pass through to the <input>.
export default function Field({
    label,
    style,
    ...inputProps
}: { label: string; style?: CSSProperties } & InputHTMLAttributes<HTMLInputElement>) {
    return (
        <div className="ldg-field" style={style}>
            <label className="ldg-field__label">{label}</label>
            <input className="ldg-input" {...inputProps} />
        </div>
    )
}
