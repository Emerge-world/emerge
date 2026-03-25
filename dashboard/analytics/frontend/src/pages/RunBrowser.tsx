// src/pages/RunBrowser.tsx
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import type { RunSummary } from '../types'

const EBS_COLOR = (ebs: number | null) => {
  if (ebs === null) return '#8b949e'
  if (ebs >= 70) return '#3fb950'
  if (ebs >= 50) return '#e3b341'
  return '#f85149'
}

export default function RunBrowser() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<'ebs' | 'date'>('date')
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  // Deep-link: ?run_id=xxx jumps directly to run detail
  useEffect(() => {
    const runId = searchParams.get('run_id')
    if (runId) navigate(`/runs/${runId}`, { replace: true })
  }, [searchParams, navigate])

  useEffect(() => {
    api.listRuns({ limit: 200 })
      .then(setRuns)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const filtered = runs
    .filter(r => r.run_id.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      if (sortBy === 'ebs') return (b.ebs ?? -1) - (a.ebs ?? -1)
      return b.created_at.localeCompare(a.created_at)
    })

  if (loading) return <div style={styles.center}>Loading runs...</div>
  if (error) return <div style={styles.center}>Error: {error}</div>

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <h1 style={styles.title}>Emerge Analytics</h1>
        <span style={styles.count}>{filtered.length} runs</span>
      </div>

      <div style={styles.toolbar}>
        <input
          style={styles.search}
          placeholder="Search run ID..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select style={styles.select} value={sortBy} onChange={e => setSortBy(e.target.value as 'ebs' | 'date')}>
          <option value="date">Sort: date ↓</option>
          <option value="ebs">Sort: EBS ↓</option>
        </select>
      </div>

      {filtered.length === 0 ? (
        <div style={styles.center}>No runs found.</div>
      ) : (
        <div style={styles.grid}>
          {filtered.map(run => (
            <div key={run.run_id} style={styles.card} onClick={() => navigate(`/runs/${run.run_id}`)}>
              <div style={{ ...styles.ebs, color: EBS_COLOR(run.ebs) }}>
                EBS {run.ebs != null ? run.ebs.toFixed(1) : '—'}
              </div>
              <div style={styles.runId}>{run.run_id}</div>
              {run.tree_id && (
                <div style={styles.meta}>{run.tree_id} {run.node_id ? `· ${run.node_id}` : ''}</div>
              )}
              <div style={styles.stats}>
                <span>👥 {run.survival_rate != null ? Math.round(run.survival_rate * 100) + '%' : '—'}</span>
                <span style={{ color: '#3fb950' }}>✦ {run.innovations_approved ?? 0}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: { padding: 20, maxWidth: 1200, margin: '0 auto' },
  header: { display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 16 },
  title: { fontSize: 18, color: '#cdd9e5' },
  count: { color: '#8b949e', fontSize: 12 },
  toolbar: { display: 'flex', gap: 8, marginBottom: 16 },
  search: { flex: 1, background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
             padding: '6px 10px', color: '#cdd9e5', fontFamily: 'monospace' },
  select: { background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
             padding: '6px 10px', color: '#cdd9e5', fontFamily: 'monospace' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 8 },
  card: { background: '#161b22', border: '1px solid #30363d', borderRadius: 6, padding: 12,
          cursor: 'pointer', transition: 'border-color 0.15s' },
  ebs: { fontSize: 15, fontWeight: 'bold', marginBottom: 4 },
  runId: { color: '#8b949e', fontSize: 10, marginBottom: 4, overflow: 'hidden',
           textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { color: '#8b949e', fontSize: 10, marginBottom: 4 },
  stats: { display: 'flex', gap: 12, fontSize: 11 },
  center: { display: 'flex', alignItems: 'center', justifyContent: 'center',
            minHeight: '40vh', color: '#8b949e' },
}
