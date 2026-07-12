import { NavLink } from 'react-router-dom'

export default function ToolTabs() {
  return (
    <nav className="tool-tabs" aria-label="Table tools">
      <NavLink to="/tools/calc" className={({ isActive }) => isActive ? 'is-active' : ''}>Scoring</NavLink>
      <NavLink to="/tools/shanten" className={({ isActive }) => isActive ? 'is-active' : ''}>Shanten</NavLink>
    </nav>
  )
}
