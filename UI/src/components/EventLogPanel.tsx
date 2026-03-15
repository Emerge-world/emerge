import { useEffect, useRef } from 'react'
import type { LogEntry } from '../types'
import { AGENT_COLORS } from '../constants'
import PanelOverlay from './PanelOverlay'

interface Props {
  events: LogEntry[]
  /** Map agent name → color index */
  agentColorMap: Record<string, number>
  onClose: () => void
}

export default function EventLogPanel({ events, agentColorMap, onClose }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to newest events
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <PanelOverlay open={true} title="EVENT LOG" onClose={onClose}>
      {events.length === 0 ? (
        <div className="panel-empty">No events yet</div>
      ) : (
        <ul className="event-log-list">
          {events.map((ev, i) => {
            const colorIdx = agentColorMap[ev.agent] ?? 0
            const color = AGENT_COLORS[colorIdx % AGENT_COLORS.length]

            return (
              <li
                key={i}
                className={`event-entry ${ev.success ? 'event-entry--success' : 'event-entry--fail'}`}
              >
                <span className="event-tick">{ev.tick}</span>
                <span className={`event-icon ${ev.success ? 'event-icon--success' : 'event-icon--fail'}`}>
                  {ev.success ? '\u2713' : '\u2717'}
                </span>
                <span className="event-agent" style={{ color }}>{ev.agent}</span>
                <span className="event-message">{ev.action} — {ev.message}</span>
              </li>
            )
          })}
          <div ref={bottomRef} />
        </ul>
      )}
    </PanelOverlay>
  )
}
