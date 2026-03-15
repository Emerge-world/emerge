import { STAT_COLORS } from '../constants'

interface Props {
  label: string
  value: number
  max?: number
  color: string
  /** If true, bar turns red when value is high (e.g. hunger) */
  invert?: boolean
}

export default function StatBar({ label, value, max = 100, color, invert = false }: Props) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const displayColor = invert && pct >= 80 ? STAT_COLORS.danger : color

  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <div
        className="stat-bar-track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
      >
        <div
          className="stat-bar-fill"
          style={{ width: `${pct}%`, backgroundColor: displayColor }}
        />
      </div>
      <span className="stat-value">{value}</span>
    </div>
  )
}
