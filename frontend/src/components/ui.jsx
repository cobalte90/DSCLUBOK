export function Button({ children, tone = "secondary", className = "", ...props }) {
  return (
    <button className={`ui-button ui-button--${tone} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

export function Card({ children, className = "", ...props }) {
  return (
    <section className={`ui-card ${className}`.trim()} {...props}>
      {children}
    </section>
  );
}

export function PageHeader({ eyebrow, title, subtitle, actions, status }) {
  return (
    <header className="page-header">
      <div className="page-header__copy">
        {eyebrow ? <div className="ui-eyebrow">{eyebrow}</div> : null}
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <div className="page-header__aside">
        {status ? <div className="page-header__status">{status}</div> : null}
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}

export function SectionTitle({ title, subtitle, aside }) {
  return (
    <div className="section-title">
      <div>
        <h3>{title}</h3>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {aside ? <div className="section-title__aside">{aside}</div> : null}
    </div>
  );
}

export function MetricCard({ label, value, help }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      {help ? <small>{help}</small> : null}
    </div>
  );
}

export function StatusBadge({ children, tone = "neutral" }) {
  return <span className={`status-badge status-badge--${tone}`}>{children}</span>;
}

export function EmptyState({ icon: Icon, title, text, action }) {
  return (
    <div className="state-panel state-panel--empty">
      {Icon ? <Icon size={18} /> : null}
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
      {action ? <div className="state-panel__action">{action}</div> : null}
    </div>
  );
}

export function LoadingState({ title = "Загрузка", text = "Подготавливаем данные..." }) {
  return (
    <div className="state-panel state-panel--loading" aria-live="polite">
      <span className="loading-dot" />
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </div>
  );
}

export function ErrorState({ title = "Не удалось загрузить данные", text }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    </div>
  );
}

export function FactLine({ label, value }) {
  return (
    <div className="fact-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
