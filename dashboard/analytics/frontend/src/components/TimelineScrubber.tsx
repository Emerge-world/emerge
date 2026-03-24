// src/components/TimelineScrubber.tsx
import type { SimTime } from '../types'

interface Props {
  currentTick: number
  maxTick: number
  simTime: SimTime | null
  playing: boolean
  speed: number
  innovationTicks: number[]
  deathTicks: number[]
  onTickChange: (tick: number) => void
  onPlayPause: () => void
  onSpeedChange: (speed: number) => void
}

export default function TimelineScrubber({
  currentTick, maxTick, simTime, playing, speed,
  innovationTicks, deathTicks,
  onTickChange, onPlayPause, onSpeedChange,
}: Props) {
  const pct = maxTick > 0 ? (currentTick / maxTick) * 100 : 0

  return (
    <div style={styles.container}>
      <button style={styles.btn} onClick={onPlayPause}>
        {playing ? '⏸' : '▶'}
      </button>

      <div style={styles.trackWrapper}>
        {/* Innovation markers */}
        {innovationTicks.map(t => (
          <div
            key={`i-${t}`}
            title={`Innovation at t${t}`}
            onClick={() => onTickChange(t)}
            style={{ ...styles.marker, left: `${(t / maxTick) * 100}%`, background: '#3fb950' }}
          />
        ))}
        {/* Death markers */}
        {deathTicks.map(t => (
          <div
            key={`d-${t}`}
            title={`Death at t${t}`}
            onClick={() => onTickChange(t)}
            style={{ ...styles.marker, left: `${(t / maxTick) * 100}%`, background: '#f85149' }}
          />
        ))}
        {/* Progress bar */}
        <div style={{ ...styles.progress, width: `${pct}%` }} />
        {/* Slider */}
        <input
          type="range"
          min={0}
          max={maxTick}
          value={currentTick}
          onChange={e => onTickChange(Number(e.target.value))}
          style={styles.slider}
        />
      </div>

      <span style={styles.tick}>t {currentTick} / {maxTick}</span>
      {simTime && (
        <span style={styles.simTime}>Day {simTime.day} · {String(simTime.hour).padStart(2, '0')}:00</span>
      )}

      <select
        style={styles.speed}
        value={speed}
        onChange={e => onSpeedChange(Number(e.target.value))}
      >
        <option value={0.5}>0.5×</option>
        <option value={1}>1×</option>
        <option value={5}>5×</option>
        <option value={20}>20×</option>
      </select>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
               background: '#161b22', borderBottom: '1px solid #30363d' },
  btn: { background: 'none', border: '1px solid #30363d', borderRadius: 4,
         color: '#cdd9e5', padding: '2px 8px', fontSize: 14 },
  trackWrapper: { flex: 1, position: 'relative', height: 8 },
  progress: { position: 'absolute', top: 0, left: 0, height: 8,
              background: '#58a6ff', borderRadius: 2, pointerEvents: 'none' },
  marker: { position: 'absolute', top: -4, width: 4, height: 16,
            borderRadius: 2, cursor: 'pointer', zIndex: 2 },
  slider: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            opacity: 0, cursor: 'pointer', zIndex: 3, margin: 0 },
  tick: { color: '#58a6ff', fontSize: 11, whiteSpace: 'nowrap' },
  simTime: { color: '#8b949e', fontSize: 11, whiteSpace: 'nowrap' },
  speed: { background: '#161b22', border: '1px solid #30363d', borderRadius: 4,
           color: '#8b949e', fontSize: 11, padding: '2px 4px', fontFamily: 'monospace' },
}
