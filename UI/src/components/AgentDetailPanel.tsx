import type { AgentState } from '../types'
import { AGENT_COLORS, STAT_COLORS } from '../constants'
import PanelOverlay from './PanelOverlay'
import StatBar from './StatBar'

interface Props {
  agent: AgentState | null
  agentIndex: number
  onClose: () => void
}

export default function AgentDetailPanel({ agent, agentIndex, onClose }: Props) {
  if (!agent) return null

  const color = AGENT_COLORS[agentIndex % AGENT_COLORS.length]

  return (
    <PanelOverlay open={true} title={agent.name} onClose={onClose}>
      <div className="agent-detail">
        {/* Header */}
        <div className="agent-detail-header">
          <span className="agent-dot" style={{ backgroundColor: color }} aria-hidden="true" />
          <span className="agent-detail-name">{agent.name}</span>
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
            <div className="agent-detail-section">
              <div className="agent-detail-section-title">Position</div>
              <div className="agent-pos">({agent.x}, {agent.y})</div>
            </div>

            {/* Actions */}
            {agent.actions.length > 0 && (
              <div className="agent-detail-section">
                <div className="agent-detail-section-title">Actions</div>
                <div className="agent-actions">
                  {agent.actions.map((action) => (
                    <span key={action} className="action-tag">{action}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Memory */}
            {agent.memory.length > 0 && (
              <div className="agent-detail-section">
                <div className="agent-detail-section-title">Recent Memory</div>
                <ul className="memory-list" aria-label={`${agent.name} memory`}>
                  {[...agent.memory].reverse().map((entry, i) => (
                    <li key={i} className="memory-entry">{entry}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </PanelOverlay>
  )
}
