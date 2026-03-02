import type { AgentState } from '../types'
import { AGENT_COLORS, STAT_COLORS } from '../constants'

interface StatBarProps {
  label: string
  value: number
  max?: number
  color: string
  /** Optionally invert so "full" is bad (e.g. hunger) */
  invert?: boolean
}

function StatBar({ label, value, max = 100, color, invert = false }: StatBarProps) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const displayColor = invert && pct >= 80 ? STAT_COLORS.danger : color
  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <div
        className="stat-bar-track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <div
          className="stat-bar-fill"
          style={{ width: `${pct}%`, backgroundColor: displayColor }}
        />
      </div>
      <span className="stat-value">{value}</span>
    </div>
  )
}

interface Props {
  agent: AgentState
  agentIndex: number
  selected: boolean
  onClick: () => void
}

export default function AgentCard({ agent, agentIndex, selected, onClick }: Props) {
  const color = AGENT_COLORS[agentIndex % AGENT_COLORS.length]

  return (
    <div
      className={`agent-card ${selected ? 'agent-card--selected' : ''} ${!agent.alive ? 'agent-card--dead' : ''}`}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${agent.name}, ${agent.alive ? 'alive' : 'dead'}${agent.alive ? `, life ${agent.life}, hunger ${agent.hunger}, energy ${agent.energy}` : ''}`}
      style={{ borderLeftColor: color }}
    >
      {/* Header */}
      <div className="agent-card-header">
        <span className="agent-dot" style={{ backgroundColor: color }} aria-hidden="true" />
        <span className="agent-name">{agent.name}</span>
        <span className={`agent-badge ${agent.alive ? 'badge-alive' : 'badge-dead'}`}>
          {agent.alive ? 'alive' : 'dead'}
        </span>
      </div>

      {agent.alive && (
        <>
          {/* Stats */}
          <div className="stat-rows">
            <StatBar label="Life"   value={agent.life}   color={STAT_COLORS.life} />
            <StatBar label="Hunger" value={agent.hunger} color={STAT_COLORS.hunger} invert />
            <StatBar label="Energy" value={agent.energy} color={STAT_COLORS.energy} />
          </div>

          {/* Position */}
          <div className="agent-pos">
            ({agent.x}, {agent.y})
          </div>

          {/* Memory / action history */}
          <div className="agent-memory">
            <div className="memory-title">Recent memory</div>
            <ul className="memory-list" aria-label={`${agent.name} memory`}>
              {[...agent.memory].reverse().map((entry, i) => (
                <li key={i} className="memory-entry">{entry}</li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}
