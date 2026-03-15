import type { AgentState, WorldState } from '../types'
import { tickToHour, tickToPeriod } from '../constants'
import PanelOverlay from './PanelOverlay'

interface Props {
  tick: number
  world: WorldState | null
  agents: AgentState[]
  onClose: () => void
}

export default function WorldStatsPanel({ tick, world, agents, onClose }: Props) {
  const hour = tickToHour(tick)
  const period = tickToPeriod(tick)
  const aliveCount = agents.filter(a => a.alive).length
  const deadCount = agents.length - aliveCount

  // Count total resources
  const totalResources = world
    ? Object.values(world.resources).reduce((sum, r) => sum + r.quantity, 0)
    : 0

  const periodIcon = period === 'day' ? '\u2600' : period === 'sunset' ? '\uD83C\uDF05' : '\uD83C\uDF19'

  return (
    <PanelOverlay open={true} title="WORLD" onClose={onClose}>
      <div className="world-stats">
        <div className="world-stat-item">
          <span className="world-stat-label">Tick</span>
          <span className="world-stat-value">{tick}</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">Time</span>
          <span className="world-stat-value">{periodIcon} {hour}:00 ({period})</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">World Size</span>
          <span className="world-stat-value">{world ? `${world.width} x ${world.height}` : '—'}</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">Agents Alive</span>
          <span className="world-stat-value" style={{ color: 'var(--green)' }}>{aliveCount}</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">Agents Dead</span>
          <span className="world-stat-value" style={{ color: deadCount > 0 ? 'var(--danger)' : undefined }}>{deadCount}</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">Total Agents</span>
          <span className="world-stat-value">{agents.length}</span>
        </div>

        <div className="world-stat-item">
          <span className="world-stat-label">Resources</span>
          <span className="world-stat-value" style={{ color: 'var(--orange)' }}>{totalResources}</span>
        </div>
      </div>
    </PanelOverlay>
  )
}
