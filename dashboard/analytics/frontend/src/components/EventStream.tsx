// src/components/EventStream.tsx
import { useEffect, useRef, useState } from 'react'
import { filterEvents } from '../utils/events'
import type { Event, EventFilter, InnovationPayload, ParsedAction } from '../types'

interface Props {
  events: Event[]
  currentTick: number
}

const FILTERS: EventFilter[] = ['all', 'innovations', 'social', 'thoughts', 'deaths']
const FILTER_LABELS: Record<EventFilter, string> = {
  all: 'All', innovations: '✦ Innovations', social: '💬 Social', thoughts: '🤔 Thoughts', deaths: '💀 Deaths',
}

function EventRow({ event, isLatest }: { event: Event; isLatest: boolean }) {
  const [expanded, setExpanded] = useState(false)

  if (event.event_type === 'innovation_validated') {
    const p = event.payload as unknown as InnovationPayload
    return (
      <div
        style={{ ...styles.row, background: isLatest ? '#3fb95022' : undefined,
                 borderLeft: `2px solid ${p.approved ? '#3fb950' : '#f85149'}`,
                 cursor: 'pointer' }}
        onClick={() => setExpanded(x => !x)}
      >
        <span style={{ color: p.approved ? '#3fb950' : '#f85149', marginRight: 4 }}>✦</span>
        <span style={styles.tock}>t{event.tick}</span>
        <span style={{ color: '#cdd9e5' }}>{event.agent_id}</span>
        <span style={styles.sep}>invented</span>
        <span style={{ color: p.approved ? '#3fb950' : '#8b949e', fontWeight: 'bold' }}>{p.name}</span>
        {expanded && (
          <div style={styles.detail}>
            <div>Status: {p.approved ? 'approved' : 'rejected'}</div>
            <div>Category: {p.category}</div>
            <div>Reason: {p.reason_code}</div>
          </div>
        )}
      </div>
    )
  }

  if (event.event_type === 'agent_decision') {
    const p = event.payload as { parsed_action?: ParsedAction }
    const reason = p.parsed_action?.reason
    return (
      <div style={styles.row}>
        <span style={{ color: '#e3b341', marginRight: 4 }}>🤔</span>
        <span style={styles.tock}>t{event.tick}</span>
        <span style={{ color: '#cdd9e5' }}>{event.agent_id}</span>
        {reason && <span style={styles.thought}>"{reason}"</span>}
      </div>
    )
  }

  if (event.event_type === 'agent_state') {
    return (
      <div style={styles.row}>
        <span style={{ color: '#f85149', marginRight: 4 }}>💀</span>
        <span style={styles.tock}>t{event.tick}</span>
        <span style={{ color: '#f85149' }}>{event.agent_id} died</span>
      </div>
    )
  }

  return null
}

export default function EventStream({ events, currentTick }: Props) {
  const [filter, setFilter] = useState<EventFilter>('all')
  const bottomRef = useRef<HTMLDivElement>(null)
  const visible = filterEvents(events, filter, currentTick)

  // Auto-scroll to bottom when tick changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [currentTick])

  return (
    <div style={styles.container}>
      <div style={styles.filters}>
        {FILTERS.map(f => (
          <button
            key={f}
            style={{ ...styles.filterBtn, ...(filter === f ? styles.filterActive : {}) }}
            onClick={() => setFilter(f)}
          >
            {FILTER_LABELS[f]}
          </button>
        ))}
      </div>
      <div style={styles.feed}>
        {visible.length === 0 ? (
          <div style={styles.empty}>No events</div>
        ) : (
          visible.map((e, i) => (
            <EventRow key={i} event={e} isLatest={e.tick === currentTick} />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden',
               background: '#161b22', borderRadius: 4 },
  filters: { display: 'flex', flexWrap: 'wrap', gap: 4, padding: '6px 8px',
             borderBottom: '1px solid #30363d' },
  filterBtn: { background: '#21262d', border: 'none', borderRadius: 3, color: '#8b949e',
               padding: '2px 6px', fontSize: 10, cursor: 'pointer', fontFamily: 'monospace' },
  filterActive: { background: '#388bfd33', color: '#58a6ff' },
  feed: { flex: 1, overflowY: 'auto', padding: '4px 0' },
  row: { padding: '3px 8px', fontSize: 10, display: 'flex', gap: 4,
         alignItems: 'flex-start', flexWrap: 'wrap' },
  tock: { color: '#8b949e', minWidth: 30 },
  sep: { color: '#8b949e' },
  thought: { color: '#8b949e', fontStyle: 'italic', flex: '0 0 100%', paddingLeft: 50 },
  detail: { flex: '0 0 100%', paddingLeft: 50, color: '#8b949e', lineHeight: 1.6, marginTop: 2 },
  empty: { padding: 12, color: '#8b949e', textAlign: 'center' },
}
