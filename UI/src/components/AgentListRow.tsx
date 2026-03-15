import type { AgentState } from '../types'
import { AGENT_COLORS, STAT_COLORS } from '../constants'

interface Props {
  agent: AgentState
  agentIndex: number
  selected: boolean
  onClick: () => void
}

export default function AgentListRow({ agent, agentIndex, selected, onClick }: Props) {
  const color = AGENT_COLORS[agentIndex % AGENT_COLORS.length]

  return (
    <div
      className={`agent-list-row ${selected ? 'agent-list-row--selected' : ''} ${!agent.alive ? 'agent-list-row--dead' : ''}`}
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
      aria-label={`${agent.name}, ${agent.alive ? 'alive' : 'dead'}${agent.alive ? `, life ${agent.life}` : ''}`}
    >
      <span className="agent-dot" style={{ backgroundColor: color }} aria-hidden="true" />
      <span className="agent-name">{agent.name}</span>

      {agent.alive && (
        <div className="mini-stats">
          <div className="mini-bar" title={`Life: ${agent.life}`}>
            <div className="mini-bar-fill" style={{ width: `${agent.life}%`, backgroundColor: STAT_COLORS.life }} />
          </div>
          <div className="mini-bar" title={`Hunger: ${agent.hunger}`}>
            <div className="mini-bar-fill" style={{ width: `${agent.hunger}%`, backgroundColor: agent.hunger >= 80 ? STAT_COLORS.danger : STAT_COLORS.hunger }} />
          </div>
          <div className="mini-bar" title={`Energy: ${agent.energy}`}>
            <div className="mini-bar-fill" style={{ width: `${agent.energy}%`, backgroundColor: STAT_COLORS.energy }} />
          </div>
        </div>
      )}

      <span className={`agent-badge ${agent.alive ? 'badge-alive' : 'badge-dead'}`}>
        {agent.alive ? 'alive' : 'dead'}
      </span>
    </div>
  )
}
