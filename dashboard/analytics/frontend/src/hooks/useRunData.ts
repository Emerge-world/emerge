// src/hooks/useRunData.ts
import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api'
import type { RunDetail, Event, TimeseriesPoint } from '../types'

export interface RunData {
  detail: RunDetail | null
  events: Event[]
  timeseries: TimeseriesPoint[]
  loading: boolean
  error: string | null
  currentTick: number
  setTick: (tick: number) => void
  playing: boolean
  setPlaying: (v: boolean) => void
  speed: number          // ticks per second
  setSpeed: (v: number) => void
}

export function useRunData(runId: string): RunData {
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [events, setEvents] = useState<Event[]>([])
  const [timeseries, setTimeseries] = useState<TimeseriesPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentTick, setCurrentTick] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    Promise.all([api.getRun(runId), api.getEvents(runId), api.getTimeseries(runId)])
      .then(([d, e, ts]) => {
        setDetail(d)
        setEvents(e)
        setTimeseries(ts)
        setCurrentTick(0)
      })
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false))
  }, [runId])

  // Playback loop
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current)
    if (!playing || !detail) return
    const maxTick = detail.metadata.max_ticks
    const ms = Math.round(1000 / speed)
    intervalRef.current = setInterval(() => {
      setCurrentTick(t => {
        if (t >= maxTick) { setPlaying(false); return t }
        return t + 1
      })
    }, ms)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [playing, speed, detail])

  const setTick = useCallback((tick: number) => {
    setCurrentTick(tick)
    setPlaying(false)
  }, [])

  return { detail, events, timeseries, loading, error, currentTick, setTick, playing, setPlaying, speed, setSpeed }
}
