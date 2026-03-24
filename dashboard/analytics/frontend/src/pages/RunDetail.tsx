import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useRunData } from '../hooks/useRunData'
import TimelineScrubber from '../components/TimelineScrubber'
import EventStream from '../components/EventStream'
import AgentPanel from '../components/AgentPanel'
import AnalyticsSidebar from '../components/AnalyticsSidebar'
import { getInnovationTicks, getDeathTicks } from '../utils/events'

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const { detail, events, timeseries, loading, error,
          currentTick, setTick, playing, setPlaying, speed, setSpeed } = useRunData(runId!)

  const innovationTicks = useMemo(() => getInnovationTicks(events), [events])
  const deathTicks = useMemo(() => getDeathTicks(events), [events])

  // Derive simTime at currentTick from events
  const simTime = useMemo(() => {
    const e = events.find(ev => ev.tick === currentTick)
    return e?.sim_time ?? null
  }, [events, currentTick])

  if (loading) return <div style={center}>Loading run {runId}...</div>
  if (error) return (
    <div style={center}>
      <div>Error: {error}</div>
      <Link to="/" style={{ marginTop: 12 }}>← Back to runs</Link>
    </div>
  )
  if (!detail) return <div style={center}>Run not found. <Link to="/">← Back</Link></div>

  const maxTick = detail.metadata.max_ticks

  return (
    <div style={styles.page}>
      {/* Top bar: run ID + back link */}
      <div style={styles.topBar}>
        <Link to="/" style={styles.back}>← Runs</Link>
        <span style={styles.runId}>{runId}</span>
      </div>

      {/* Timeline */}
      <TimelineScrubber
        currentTick={currentTick}
        maxTick={maxTick}
        simTime={simTime}
        playing={playing}
        speed={speed}
        innovationTicks={innovationTicks}
        deathTicks={deathTicks}
        onTickChange={setTick}
        onPlayPause={() => setPlaying(!playing)}
        onSpeedChange={setSpeed}
      />

      {/* Three columns */}
      <div style={styles.columns}>
        <div style={styles.col}>
          <EventStream events={events} currentTick={currentTick} />
        </div>
        <div style={{ ...styles.col, flex: 1.5 }}>
          <AgentPanel events={events} currentTick={currentTick} simTime={simTime} />
        </div>
        <div style={styles.col}>
          <AnalyticsSidebar
            detail={detail}
            timeseries={timeseries}
            events={events}
            currentTick={currentTick}
          />
        </div>
      </div>
    </div>
  )
}

const center: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', alignItems: 'center',
  justifyContent: 'center', minHeight: '60vh', color: '#8b949e', gap: 8,
}

const styles: Record<string, React.CSSProperties> = {
  page: { display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' },
  topBar: { display: 'flex', alignItems: 'center', gap: 12, padding: '6px 12px',
            borderBottom: '1px solid #30363d', background: '#0d1117' },
  back: { color: '#58a6ff', fontSize: 11 },
  runId: { color: '#8b949e', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis' },
  columns: { flex: 1, display: 'flex', gap: 4, padding: 4, overflow: 'hidden' },
  col: { flex: 1, minWidth: 0, overflow: 'hidden' },
}
