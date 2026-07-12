import { Navigate } from 'react-router-dom'
import { createPrivateTablePath } from './navigation'

// Legacy entry point: old bookmarks still work, but table creation is now one step.
export default function CreateRoom() {
  return <Navigate to={createPrivateTablePath()} replace />
}
