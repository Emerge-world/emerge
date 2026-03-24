// src/api.ts
import type { RunSummary, RunDetail, Event, TimeseriesPoint, TreeSummary } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${path}`)
  return r.json() as Promise<T>
}

export const api = {
  listRuns: (params?: {
    tree_id?: string
    node_id?: string
    limit?: number
    offset?: number
  }) => {
    const q = new URLSearchParams()
    if (params?.tree_id) q.set('tree_id', params.tree_id)
    if (params?.node_id) q.set('node_id', params.node_id)
    if (params?.limit != null) q.set('limit', String(params.limit))
    if (params?.offset != null) q.set('offset', String(params.offset))
    return get<RunSummary[]>(`/runs${q.toString() ? '?' + q : ''}`)
  },
  getRun: (runId: string) => get<RunDetail>(`/runs/${runId}`),
  getEvents: (runId: string) => get<Event[]>(`/runs/${runId}/events`),
  getTimeseries: (runId: string) =>
    get<TimeseriesPoint[]>(`/runs/${runId}/timeseries`),
  listTrees: () => get<TreeSummary[]>('/trees'),
}
