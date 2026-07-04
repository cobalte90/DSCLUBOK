import { Activity } from "lucide-react";

export function AppShell({ sidebar, children }) {
  return (
    <div className="app-shell">
      {sidebar}
      <main className="app-main">{children}</main>
    </div>
  );
}

export function Sidebar({ tabs, activeTab, onTabChange, health }) {
  const isReady = health?.status === "ok";

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-brand">
        <div className="ui-eyebrow">R&D Knowledge Graph Copilot</div>
        <h1>Научный клубок</h1>
        <p>Поиск, доказательства, граф связей и сравнение инженерных решений.</p>
      </div>

      <nav className="sidebar-nav" aria-label="Главная навигация">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              className={tab.id === activeTab ? "sidebar-nav__item active" : "sidebar-nav__item"}
              onClick={() => onTabChange(tab.id)}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      <div className="mascot-card">
        <img src="/cat-ds-club.png" alt="Маскот Научного клубка" />
        <div>
          <strong>Научный клубок</strong>
          <p>Задайте вопрос — я соберу факты и источники.</p>
        </div>
      </div>

      <div className="sidebar-connection">
        <span className={isReady ? "connection-dot connection-dot--good" : "connection-dot"} />
        <Activity size={15} />
        <span>{isReady ? "Сервис готов" : "Проверяем сервис"}</span>
      </div>
    </aside>
  );
}

