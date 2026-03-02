import type { AgentState } from '../types'
import AgentCard from './AgentCard'

interface Props {
  agents: AgentState[]
  selectedAgentId: number | null
  onSelect: (id: number) => void
  /** Controls visibility on mobile (ignored on desktop via CSS). */
  open: boolean
}

export default function AgentPanel({ agents, selectedAgentId, onSelect, open }: Props) {
  if (agents.length === 0) {
    return (
      <aside
        className={`agent-panel ${open ? 'agent-panel--open' : ''}`}
        aria-label="Agents"
      >
        <div className="panel-empty">Waiting for agents…</div>
      </aside>
    )
  }

  return (
    <aside
      className={`agent-panel ${open ? 'agent-panel--open' : ''}`}
      aria-label="Agents"
    >
      {agents.map((agent, idx) => (
        <AgentCard
          key={agent.id}
          agent={agent}
          agentIndex={idx}
          selected={agent.id === selectedAgentId}
          onClick={() => onSelect(agent.id)}
        />
      ))}
    </aside>
  )
}
