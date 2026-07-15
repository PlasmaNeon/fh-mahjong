import { useId, type CSSProperties, type InputHTMLAttributes } from 'react'

// Labelled text input. `style` is applied to the field wrapper (e.g. vertical spacing);
// all other props pass through to the <input>.
export default function Field({
    label,
    style,
    ...inputProps
}: { label: string; style?: CSSProperties } & InputHTMLAttributes<HTMLInputElement>) {
    const generatedId = useId()
    const inputId = inputProps.id ?? generatedId
    return (
        <div className="ldg-field" style={style}>
            <label className="ldg-field__label" htmlFor={inputId}>{label}</label>
            <input className="ldg-input" {...inputProps} id={inputId} />
        </div>
    )
}
