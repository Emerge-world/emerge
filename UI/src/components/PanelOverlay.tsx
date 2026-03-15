interface Props {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
}

export default function PanelOverlay({ open, title, onClose, children }: Props) {
  return (
    <aside
      className={`panel-overlay ${open ? 'panel-overlay--open' : ''}`}
      aria-label={title}
      aria-hidden={!open}
    >
      <div className="panel-header">
        <span className="panel-title">{title}</span>
        <button className="panel-close" onClick={onClose} aria-label="Close panel">
          &times;
        </button>
      </div>
      <div className="panel-body">
        {children}
      </div>
    </aside>
  )
}
