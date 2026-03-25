import { Routes, Route, Navigate } from 'react-router-dom'
import RunBrowser from './pages/RunBrowser'
import RunDetail from './pages/RunDetail'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RunBrowser />} />
      <Route path="/runs/:runId" element={<RunDetail />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
