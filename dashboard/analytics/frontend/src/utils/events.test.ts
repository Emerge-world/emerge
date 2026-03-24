import { describe, it, expect } from 'vitest'
import { filterEvents, deriveAgentStates, getDeathTicks, getInnovationTicks } from './events'
import type { Event } from '../types'

const makeEvent = (overrides: Partial<Event>): Event => ({
  run_id: 'test',
  seed: 0,
  tick: 1,
  sim_time: { day: 1, hour: 6 },
  event_type: 'agent_decision',
  agent_id: 'Alice',
  payload: {},
  ...overrides,
})

const EVENTS: Event[] = [
  makeEvent({
    tick: 1,
    event_type: 'agent_decision',
    agent_id: 'Alice',
    payload: {
      parsed_action: { action: 'move', direction: 'north', reason: 'exploring' },
      parse_ok: true,
      action_origin: 'base',
    },
  }),
  makeEvent({
    tick: 1,
    event_type: 'agent_state',
    agent_id: 'Alice',
    payload: {
      life: 90,
      hunger: 20,
      energy: 80,
      pos: [3, 4],
      alive: true,
      inventory: {},
      memory_semantic: 0,
    },
  }),
  makeEvent({
    tick: 2,
    event_type: 'innovation_validated',
    agent_id: 'Bob',
    payload: {
      name: 'forage_deep',
      approved: true,
      category: 'GATHERING',
      reason_code: 'INNOVATION_APPROVED',
      requires: {},
      produces: {},
    },
  }),
  makeEvent({
    tick: 3,
    event_type: 'agent_state',
    agent_id: 'Alice',
    payload: {
      life: 0,
      hunger: 100,
      energy: 0,
      pos: [3, 4],
      alive: false,
      inventory: {},
      memory_semantic: 0,
    },
  }),
]

describe('filterEvents', () => {
  it('returns all events for filter=all', () => {
    expect(filterEvents(EVENTS, 'all', 3)).toHaveLength(4)
  })
  it('returns only innovation_validated for filter=innovations', () => {
    const r = filterEvents(EVENTS, 'innovations', 3)
    expect(r).toHaveLength(1)
    expect(r[0].event_type).toBe('innovation_validated')
  })
  it('returns only agent_decision for filter=thoughts', () => {
    const r = filterEvents(EVENTS, 'thoughts', 3)
    expect(r).toHaveLength(1)
    expect(r[0].event_type).toBe('agent_decision')
  })
  it('respects currentTick upper bound', () => {
    expect(filterEvents(EVENTS, 'all', 1)).toHaveLength(2)
  })
})

describe('deriveAgentStates', () => {
  it('returns last known state per agent at tick', () => {
    const states = deriveAgentStates(EVENTS, 3)
    const alice = states.find(s => s.agent_id === 'Alice')
    expect(alice).toBeDefined()
    expect(alice!.alive).toBe(false)
    expect(alice!.death_tick).toBe(3)
    expect(alice!.last_thought).toBe('exploring')
  })
  it('state at tick 1 shows alive=true', () => {
    const states = deriveAgentStates(EVENTS, 1)
    const alice = states.find(s => s.agent_id === 'Alice')
    expect(alice!.alive).toBe(true)
    expect(alice!.death_tick).toBeNull()
  })
})

describe('getDeathTicks', () => {
  it('returns ticks where agents first die', () => {
    expect(getDeathTicks(EVENTS)).toEqual([3])
  })
})

describe('getInnovationTicks', () => {
  it('returns ticks of innovation_validated events', () => {
    expect(getInnovationTicks(EVENTS)).toEqual([2])
  })
})
