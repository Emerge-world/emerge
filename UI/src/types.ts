// Tile types matching simulation/config.py
export type TileType = 'water' | 'land' | 'tree'

export interface WorldState {
  width: number
  height: number
  /** tiles[row][col] — row 0 is y=0 (top) */
  tiles: TileType[][]
  /** key = "x,y", value = resource info */
  resources: Record<string, { type: string; quantity: number }>
}

export interface AgentState {
  id: number
  name: string
  x: number
  y: number
  life: number
  hunger: number
  energy: number
  alive: boolean
  actions: string[]
  /** last 10 memory entries */
  memory: string[]
}

export interface SimEvent {
  agent: string
  action: string
  success: boolean
  message: string
}

// Messages received FROM the server
export type ServerMessage =
  | {
      type: 'init'
      tick: number
      world: WorldState
      agents: AgentState[]
    }
  | {
      type: 'tick'
      tick: number
      agents: AgentState[]
      events: SimEvent[]
      world_resources: Record<string, { type: string; quantity: number }>
    }
  | {
      type: 'control'
      paused: boolean
    }

// Messages sent TO the server
export type ClientMessage =
  | { type: 'pause' }
  | { type: 'resume' }
