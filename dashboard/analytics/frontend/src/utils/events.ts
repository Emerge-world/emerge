// src/utils/events.ts
import type {
  Event,
  AgentState,
  EventFilter,
  AgentStatePayload,
  ParsedAction,
} from '../types'

export function filterEvents(
  events: Event[],
  filter: EventFilter,
  currentTick: number
): Event[] {
  return events.filter(e => {
    if (e.tick > currentTick) return false
    if (filter === 'all') return true
    if (filter === 'innovations') return e.event_type === 'innovation_validated'
    if (filter === 'thoughts') return e.event_type === 'agent_decision'
    if (filter === 'deaths') {
      if (e.event_type !== 'agent_state') return false
      const p = e.payload as AgentStatePayload
      return p.alive === false
    }
    if (filter === 'social') {
      if (e.event_type !== 'agent_decision') return false
      const p = e.payload as { parsed_action?: ParsedAction }
      const action = p.parsed_action?.action ?? ''
      return ['teach', 'communicate', 'give_item'].includes(action)
    }
    return true
  })
}

export function deriveAgentStates(
  events: Event[],
  currentTick: number
): AgentState[] {
  // Collect all agent_ids seen
  const agentIds = new Set<string>()
  for (const e of events) {
    if (e.agent_id && e.tick <= currentTick) agentIds.add(e.agent_id)
  }

  const states: AgentState[] = []
  for (const agentId of agentIds) {
    const agentEvents = events.filter(
      e => e.agent_id === agentId && e.tick <= currentTick
    )

    // Last agent_state event
    const stateEvents = agentEvents.filter(e => e.event_type === 'agent_state')
    const lastState = stateEvents[stateEvents.length - 1]

    // Last agent_decision for thought
    const decisionEvents = agentEvents.filter(e => e.event_type === 'agent_decision')
    const lastDecision = decisionEvents[decisionEvents.length - 1]
    const lastThought = lastDecision
      ? ((lastDecision.payload as { parsed_action?: ParsedAction })
          .parsed_action?.reason ?? null)
      : null
    const lastAction = lastDecision
      ? ((lastDecision.payload as { parsed_action?: ParsedAction })
          .parsed_action?.action ?? null)
      : null

    // Death tick: first agent_state where alive=false
    const deathEvent = stateEvents.find(
      e => (e.payload as AgentStatePayload).alive === false
    )
    const deathTick = deathEvent ? deathEvent.tick : null

    if (lastState) {
      const p = lastState.payload as AgentStatePayload
      states.push({
        agent_id: agentId,
        life: p.life,
        hunger: p.hunger,
        energy: p.energy,
        pos: p.pos,
        alive: p.alive,
        last_thought: lastThought,
        last_action: lastAction,
        death_tick: deathTick,
      })
    }
  }
  return states
}

export function getDeathTicks(events: Event[]): number[] {
  const seen = new Set<string>()
  const ticks: number[] = []
  for (const e of events) {
    if (e.event_type !== 'agent_state') continue
    if (!e.agent_id) continue
    const p = e.payload as AgentStatePayload
    if (p.alive === false && !seen.has(e.agent_id)) {
      seen.add(e.agent_id)
      ticks.push(e.tick)
    }
  }
  return [...new Set(ticks)].sort((a, b) => a - b)
}

export function getInnovationTicks(events: Event[]): number[] {
  return [
    ...new Set(
      events
        .filter(e => e.event_type === 'innovation_validated')
        .map(e => e.tick)
    ),
  ].sort((a, b) => a - b)
}
