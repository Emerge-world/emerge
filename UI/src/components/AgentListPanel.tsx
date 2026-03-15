import type { AgentState } from '../types'
import PanelOverlay from './PanelOverlay'
import AgentListRow from './AgentListRow'

interface Props {
  agents: AgentState[]
  selectedAgentId: number | null
  onSelectAgent: (id: number) => void
  onClose: () => void
}

export default function AgentListPanel({ agents, selectedAgentId, onSelectAgent, onClose }: Props) {
  return (
    <PanelOverlay open={true} title="AGENTS" onClose={onClose}>
      {agents.length === 0 ? (
        <div className="panel-empty">No agents yet</div>
      ) : (
        agents.map((agent, idx) => (
          <AgentListRow
            key={agent.id}
            agent={agent}
            agentIndex={idx}
            selected={agent.id === selectedAgentId}
            onClick={() => onSelectAgent(agent.id)}
          />
        ))
      )}
    </PanelOverlay>
  )
}
