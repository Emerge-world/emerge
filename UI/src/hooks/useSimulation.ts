import { useCallback, useEffect, useReducer, useRef } from 'react'
import type { AgentState, ClientMessage, LogEntry, ServerMessage, WorldState } from '../types'

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
export interface SimState {
  connected: boolean
  tick: number
  paused: boolean
  world: WorldState | null
  agents: AgentState[]
  /** Rolling event log — last 200 entries, stamped with tick */
  eventLog: LogEntry[]
}

const INITIAL_STATE: SimState = {
  connected: false,
  tick: 0,
  paused: false,
  world: null,
  agents: [],
  eventLog: [],
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------
type Action =
  | { type: 'CONNECTED' }
  | { type: 'DISCONNECTED' }
  | { type: 'INIT'; payload: { tick: number; world: WorldState; agents: AgentState[] } }
  | {
      type: 'TICK'
      payload: {
        tick: number
        agents: AgentState[]
        events: LogEntry[]
        world_resources: WorldState['resources']
      }
    }
  | { type: 'CONTROL'; payload: { paused: boolean } }

function reducer(state: SimState, action: Action): SimState {
  switch (action.type) {
    case 'CONNECTED':
      return { ...state, connected: true }
    case 'DISCONNECTED':
      return { ...state, connected: false }
    case 'INIT':
      return {
        ...state,
        tick: action.payload.tick,
        world: action.payload.world,
        agents: action.payload.agents,
      }
    case 'TICK': {
      const nextWorld = state.world
        ? { ...state.world, resources: action.payload.world_resources }
        : state.world
      const nextLog = [...state.eventLog, ...action.payload.events].slice(-200)
      return {
        ...state,
        tick: action.payload.tick,
        world: nextWorld,
        agents: action.payload.agents,
        eventLog: nextLog,
      }
    }
    case 'CONTROL':
      return { ...state, paused: action.payload.paused }
    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------
const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`
const MAX_RECONNECT_DELAY_MS = 8000

export function useSimulation() {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectDelay = useRef(500)
  const unmounted = useRef(false)

  const send = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const pause = useCallback(() => send({ type: 'pause' }), [send])
  const resume = useCallback(() => send({ type: 'resume' }), [send])

  useEffect(() => {
    unmounted.current = false

    function connect() {
      if (unmounted.current) return

      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectDelay.current = 500
        dispatch({ type: 'CONNECTED' })
      }

      ws.onmessage = (ev) => {
        let msg: ServerMessage
        try {
          msg = JSON.parse(ev.data as string) as ServerMessage
        } catch {
          return
        }
        switch (msg.type) {
          case 'init':
            dispatch({ type: 'INIT', payload: msg })
            break
          case 'tick': {
            // Stamp each event with the tick number
            const stamped: LogEntry[] = msg.events.map(e => ({ ...e, tick: msg.tick }))
            dispatch({ type: 'TICK', payload: { ...msg, events: stamped } })
            break
          }
          case 'control':
            dispatch({ type: 'CONTROL', payload: msg })
            break
        }
      }

      ws.onclose = () => {
        dispatch({ type: 'DISCONNECTED' })
        if (!unmounted.current) {
          setTimeout(connect, reconnectDelay.current)
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY_MS)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      unmounted.current = true
      wsRef.current?.close()
    }
  }, [])

  return { state, pause, resume }
}
