// src/types.ts

export interface SimTime {
  day: number
  hour: number
}

export interface RunSummary {
  run_id: string
  created_at: string
  total_ticks: number
  ebs: number | null
  survival_rate: number | null
  innovations_approved: number | null
  tree_id: string | null
  node_id: string | null
}

export interface RunMetadata {
  run_id: string
  seed: number
  width: number
  height: number
  max_ticks: number
  agent_count: number
  agent_names: string[]
  agent_model_id: string
  oracle_model_id: string
  git_commit: string
  created_at: string
  precedents_file: string | null
}

export interface EbsComponents {
  novelty: number
  utility: number
  realization: number
  stability: number
  autonomy: number
  longevity: number
}

export interface RunDetail {
  metadata: RunMetadata
  agents:
    | {
        initial_count: number
        final_survivors: string[]
        deaths: number
        survival_rate: number
      }
    | null
  actions:
    | {
        total: number
        by_type: Record<string, number>
        oracle_success_rate: number
        parse_fail_rate: number
      }
    | null
  innovations:
    | {
        attempts: number
        approved: number
        rejected: number
        used: number
        approval_rate: number
        realization_rate: number
      }
    | null
  ebs: number | null
  ebs_components: EbsComponents | null
}

export interface ParsedAction {
  action: string
  direction?: string
  reason?: string
  [key: string]: unknown
}

export interface InnovationPayload {
  name: string
  approved: boolean
  category: string
  reason_code: string
  requires: Record<string, unknown>
  produces: Record<string, unknown>
}

export interface AgentStatePayload {
  life: number
  hunger: number
  energy: number
  pos: [number, number]
  alive: boolean
  inventory: Record<string, number>
  memory_semantic: number
}

export interface Event {
  run_id: string
  seed: number
  tick: number
  sim_time: SimTime
  event_type: string
  agent_id: string | null
  payload: Record<string, unknown>
}

export interface TimeseriesPoint {
  tick: number
  sim_time: SimTime
  alive: number
  mean_life: number
  mean_hunger: number
  mean_energy: number
  deaths: number
  actions: number
  innovations_attempted: number
  innovations_approved: number
}

export interface TreeSummary {
  tree_id: string
  node_count: number
}

/** Derived agent state at a specific tick — computed from event stream. */
export interface AgentState {
  agent_id: string
  life: number
  hunger: number
  energy: number
  pos: [number, number]
  alive: boolean
  last_thought: string | null // reason from most recent agent_decision
  last_action: string | null
  death_tick: number | null
}

export type EventFilter = 'all' | 'innovations' | 'social' | 'thoughts' | 'deaths'
