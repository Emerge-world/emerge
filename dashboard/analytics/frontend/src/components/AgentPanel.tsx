// src/components/AgentPanel.tsx
import { useMemo } from 'react'
import { deriveAgentStates } from '../utils/events'
import type { Event } from '../types'

interface Props { events: Event[]; currentTick: number; simTime: { day: number; hour: number } | null }

function StatBar({ value, max, color }: { value: number; max: number; color: string }) {
  return (
    <div style={{ background: '#30363d', borderRadius: 2, height: 4, width: '100%' }}>
      <div style={{ background: color, borderRadius: 2, height: 4, width: `${Math.min(100, (value / max) * 100)}%` }} />
    </div>
  )
}

export default function AgentPanel({ events, currentTick, simTime }: Props) {
  const states = useMemo(() => deriveAgentStates(events, currentTick), [events, currentTick])
  const alive = states.filter(s => s.alive)
  const dead = states.filter(s => !s.alive)

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        TICK {currentTick}
        {simTime && <span style={styles.simTime}>Day {simTime.day} · {String(simTime.hour).padStart(2, '0')}:00</span>}
        <span style={styles.count}>{alive.length} alive</span>
      </div>
      <div style={styles.cards}>
        {[...alive, ...dead].map(agent => (
          <div
            key={agent.agent_id}
            style={{ ...styles.card, opacity: agent.alive ? 1 : 0.45,
                     borderLeft: `2px solid ${agent.alive ? '#3fb950' : '#f85149'}` }}
          >
            <div style={styles.cardHeader}>
              <span style={styles.name}>{agent.agent_id}</span>
              {!agent.alive && <span style={styles.deadTag}>died t{agent.death_tick}</span>}
              <span style={styles.pos}>({agent.pos[0]}, {agent.pos[1]})</span>
            </div>
            <div style={styles.bars}>
              <div style={styles.barRow}>
                <span style={{ color: '#3fb950', fontSize: 9 }}>♥</span>
                <StatBar value={agent.life} max={100} color="#3fb950" />
                <span style={styles.barVal}>{agent.life}</span>
              </div>
              <div style={styles.barRow}>
                <span style={{ color: '#e3b341', fontSize: 9 }}>🍖</span>
                <StatBar value={agent.hunger} max={100} color="#e3b341" />
                <span style={styles.barVal}>{agent.hunger}</span>
              </div>
              <div style={styles.barRow}>
                <span style={{ color: '#58a6ff', fontSize: 9 }}>⚡</span>
                <StatBar value={agent.energy} max={100} color="#58a6ff" />
                <span style={styles.barVal}>{agent.energy}</span>
              </div>
            </div>
            {agent.last_action && (
              <div style={styles.action}>action: {agent.last_action}</div>
            )}
            {agent.last_thought && (
              <div style={styles.thought}>"{agent.last_thought}"</div>
            )}
          </div>
        ))}
        {states.length === 0 && (
          <div style={styles.empty}>No agent data at tick {currentTick}</div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { background: '#161b22', borderRadius: 4, height: '100%',
               display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  header: { padding: '6px 10px', borderBottom: '1px solid #30363d', fontSize: 10,
            color: '#8b949e', display: 'flex', gap: 8, alignItems: 'center' },
  simTime: { color: '#58a6ff' },
  count: { marginLeft: 'auto', color: '#3fb950' },
  cards: { flex: 1, overflowY: 'auto', padding: 6, display: 'flex', flexDirection: 'column', gap: 6 },
  card: { background: '#21262d', borderRadius: 4, padding: '6px 8px' },
  cardHeader: { display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 },
  name: { color: '#cdd9e5', fontWeight: 'bold', fontSize: 11 },
  deadTag: { color: '#f85149', fontSize: 9 },
  pos: { color: '#8b949e', fontSize: 9, marginLeft: 'auto' },
  bars: { display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 4 },
  barRow: { display: 'flex', gap: 4, alignItems: 'center' },
  barVal: { color: '#8b949e', fontSize: 9, minWidth: 20, textAlign: 'right' },
  action: { color: '#cdd9e5', fontSize: 9, marginTop: 2 },
  thought: { color: '#8b949e', fontStyle: 'italic', fontSize: 9, marginTop: 2 },
  empty: { color: '#8b949e', fontSize: 11, padding: 12, textAlign: 'center' },
}
