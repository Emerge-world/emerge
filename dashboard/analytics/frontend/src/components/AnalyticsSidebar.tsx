// src/components/AnalyticsSidebar.tsx
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine,
  BarChart, Bar,
} from 'recharts'
import type { RunDetail, TimeseriesPoint, Event, InnovationPayload } from '../types'

interface Props {
  detail: RunDetail
  timeseries: TimeseriesPoint[]
  events: Event[]
  currentTick: number
}

export default function AnalyticsSidebar({ detail, timeseries, events, currentTick }: Props) {
  const radarData = detail.ebs_components ? [
    { subject: 'Novelty',     value: detail.ebs_components.novelty },
    { subject: 'Utility',     value: detail.ebs_components.utility },
    { subject: 'Realization', value: detail.ebs_components.realization },
    { subject: 'Stability',   value: detail.ebs_components.stability },
    { subject: 'Autonomy',    value: detail.ebs_components.autonomy },
    { subject: 'Longevity',   value: detail.ebs_components.longevity },
  ] : []

  const innovations = events
    .filter(e => e.event_type === 'innovation_validated')
    .map(e => ({ ...e, payload: e.payload as unknown as InnovationPayload }))

  const actionData = detail.actions
    ? Object.entries(detail.actions.by_type).map(([name, count]) => ({ name, count }))
    : []

  return (
    <div style={styles.container}>
      {/* EBS score */}
      <div style={styles.scoreRow}>
        <span style={styles.label}>EBS</span>
        <span style={{ ...styles.score, color: ebsColor(detail.ebs) }}>
          {detail.ebs != null ? detail.ebs.toFixed(1) : '—'}
        </span>
      </div>

      {/* Radar */}
      {radarData.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Components</div>
          <ResponsiveContainer width="100%" height={140}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="#30363d" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: '#8b949e', fontSize: 9 }} />
              <Radar dataKey="value" fill="#388bfd" fillOpacity={0.35} stroke="#58a6ff" />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Survival chart */}
      {timeseries.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Alive over time</div>
          <ResponsiveContainer width="100%" height={80}>
            <LineChart data={timeseries}>
              <XAxis dataKey="tick" hide />
              <YAxis hide domain={[0, 'dataMax']} />
              <Tooltip
                contentStyle={{ background: '#21262d', border: '1px solid #30363d', fontSize: 10 }}
                labelFormatter={v => `t${v}`}
              />
              <ReferenceLine x={currentTick} stroke="#58a6ff" strokeDasharray="3 3" />
              <Line type="monotone" dataKey="alive" stroke="#3fb950" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Action distribution */}
      {actionData.length > 0 && (
        <div style={styles.section}>
          <div style={styles.sectionLabel}>Actions</div>
          <ResponsiveContainer width="100%" height={60 + actionData.length * 14}>
            <BarChart data={actionData} layout="vertical">
              <XAxis type="number" hide />
              <YAxis dataKey="name" type="category" tick={{ fill: '#8b949e', fontSize: 9 }} width={60} />
              <Bar dataKey="count" fill="#388bfd" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Innovation list */}
      <div style={styles.section}>
        <div style={styles.sectionLabel}>Innovations ({innovations.length})</div>
        {innovations.length === 0 ? (
          <div style={styles.empty}>No innovations in this run</div>
        ) : (
          innovations.map((e, i) => (
            <div key={i} style={styles.innovation}>
              <span style={{ color: e.payload.approved ? '#3fb950' : '#f85149' }}>✦</span>
              <span style={styles.innovName}>{e.payload.name}</span>
              <span style={styles.innovMeta}>t{e.tick} · {e.agent_id}</span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const ebsColor = (ebs: number | null) => {
  if (ebs == null) return '#8b949e'
  if (ebs >= 70) return '#3fb950'
  if (ebs >= 50) return '#e3b341'
  return '#f85149'
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#161b22', borderRadius: 4, height: '100%',
               overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 8 },
  scoreRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  label: { color: '#8b949e', fontSize: 10, textTransform: 'uppercase' },
  score: { fontSize: 20, fontWeight: 'bold' },
  section: { borderTop: '1px solid #21262d', paddingTop: 6 },
  sectionLabel: { color: '#8b949e', fontSize: 9, textTransform: 'uppercase', marginBottom: 4 },
  innovation: { display: 'flex', gap: 4, alignItems: 'center', fontSize: 10, padding: '1px 0' },
  innovName: { color: '#cdd9e5', flex: 1 },
  innovMeta: { color: '#8b949e', fontSize: 9 },
  empty: { color: '#8b949e', fontSize: 10, padding: '4px 0' },
}
