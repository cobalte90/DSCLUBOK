import { useEffect, useMemo, useState } from "react";
import { pageMeta, tabs, API_BASE, repairText } from "./constants";
import { AppShell, Sidebar } from "./components/layout";
import { Button, PageHeader, StatusBadge } from "./components/ui";
import { AskView, CompareView, CurateView, DashboardView, GapsView, GraphView, SourcesView } from "./components/views";

export default function App() {
  const [activeTab, setActiveTab] = useState("Ask");
  const [health, setHealth] = useState(null);
  const [sources, setSources] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [query, setQuery] = useState("Какие методы очистки шахтных вод применимы при сульфатах 200-300 мг/л?");
  const [langFilter, setLangFilter] = useState("all");
  const [answer, setAnswer] = useState(null);
  const [compare, setCompare] = useState(null);
  const [graph, setGraph] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [message, setMessage] = useState("");
  const [selectedSourceIds, setSelectedSourceIds] = useState([]);
  const [uploadResult, setUploadResult] = useState(null);
  const [selectedFact, setSelectedFact] = useState(null);
  const [exportPreview, setExportPreview] = useState(null);
  const [savedQueries, setSavedQueries] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [expertQuery, setExpertQuery] = useState("nickel");
  const [experts, setExperts] = useState([]);
  const [contradictionNote, setContradictionNote] = useState("");
  const [selectedScenarioId, setSelectedScenarioId] = useState(null);
  const [loading, setLoading] = useState({});
  const [error, setError] = useState({});

  useEffect(() => {
    hydrate();
  }, []);

  async function hydrate() {
    await Promise.all([loadHealth(), loadSources(), loadDashboard(), loadScenarios(), loadSavedQueries(), loadAlerts()]);
  }

  async function fetchJson(url, options, key) {
    if (key) {
      setLoading((prev) => ({ ...prev, [key]: true }));
      setError((prev) => ({ ...prev, [key]: "" }));
    }
    try {
      const response = await fetch(url, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.message || "Запрос завершился ошибкой.");
      return data;
    } catch (err) {
      if (key) setError((prev) => ({ ...prev, [key]: err.message || "Произошла ошибка." }));
      throw err;
    } finally {
      if (key) setLoading((prev) => ({ ...prev, [key]: false }));
    }
  }

  async function loadHealth() {
    try {
      const data = await fetchJson(`${API_BASE}/health`);
      setHealth(data);
    } catch {
      setHealth({ status: "offline", mode: "unknown", graph: { available: false } });
    }
  }

  async function loadSources() {
    try {
      const data = await fetchJson(`${API_BASE}/api/sources`);
      const items = data.data.items || [];
      setSources(items);
      setSelectedSourceIds((prev) => prev.filter((id) => items.some((item) => item.id === id)));
    } catch {
      setSources([]);
    }
  }

  async function loadDashboard() {
    try {
      const data = await fetchJson(`${API_BASE}/api/dashboard/coverage`);
      setDashboard(data.data || {});
    } catch {
      setDashboard({});
    }
  }

  async function loadScenarios() {
    try {
      const data = await fetchJson(`${API_BASE}/api/demo/scenarios`);
      const items = data.data.items || [];
      setScenarios(items);
      if (items.length) setSelectedScenarioId((current) => current || items[0].id);
    } catch {
      setScenarios([]);
    }
  }

  async function loadSavedQueries() {
    try {
      const data = await fetchJson(`${API_BASE}/api/saved-queries`, undefined, "savedQueries");
      setSavedQueries(data.data.items || []);
    } catch {
      setSavedQueries([]);
    }
  }

  async function loadAlerts() {
    try {
      const data = await fetchJson(`${API_BASE}/api/alerts/feed`);
      setAlerts(data.data.items || []);
    } catch {
      setAlerts([]);
    }
  }

  async function waitForIngestJob(jobId) {
    for (let index = 0; index < 40; index += 1) {
      const data = await fetchJson(`${API_BASE}/api/ingest/jobs/${jobId}`);
      const job = data.data.job;
      setUploadResult((current) => current ? { ...current, job } : { job });
      if (["done", "partial", "failed"].includes(job.status)) return job;
      await new Promise((resolve) => setTimeout(resolve, 1200));
    }
    return null;
  }

  async function uploadDocuments({ files, sourceType, name }) {
    if (!files?.length) {
      setMessage("Выберите документы для загрузки.");
      return;
    }
    try {
      setMessage("Загружаем документы...");
      setUploadResult(null);
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      form.append("source_type", sourceType);
      form.append("access_level", "internal");
      form.append("tags", JSON.stringify(["user_upload"]));
      if (name?.trim()) form.append("name", name.trim());
      const uploaded = await fetchJson(`${API_BASE}/api/sources/upload`, { method: "POST", body: form }, "upload");
      const sourceId = uploaded.data.source.id;
      setUploadResult({ source: uploaded.data.source, documents: uploaded.data.documents || [], job: null });
      setMessage("Документы загружены. Запускаем обработку...");
      const imported = await fetchJson(`${API_BASE}/api/sources/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_ids: [sourceId], extraction_profile: "default", force_reingest: false })
      }, "upload");
      setUploadResult((current) => ({ ...(current || {}), job: { id: imported.data.job_id, status: imported.data.status, stage: "queued", progress: 0 } }));
      const job = await waitForIngestJob(imported.data.job_id);
      await Promise.all([loadSources(), loadDashboard()]);
      setMessage(job?.status === "failed" ? "Документы загружены, но обработка завершилась ошибкой." : "Документы добавлены и обработаны.");
    } catch (err) {
      setMessage(err.message || "Не удалось загрузить документы.");
    }
  }


  function updateQuery(nextQuery) {
    setQuery(nextQuery);
    setGraph(null);
    setCompare(null);
  }

  function currentFilters(extra = {}) {
    return {
      ...(langFilter !== "all" ? { language: langFilter } : {}),
      ...extra
    };
  }

  async function runAnswer() {
    try {
      setMessage("Собираем ответ по подтвержденным фрагментам...");
      const data = await fetchJson(`${API_BASE}/api/answer`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, filters: currentFilters(), limit: 8 }) }, "answer");
      setAnswer(data);
      setSelectedFact(data.data.evidence_view?.[0]?.fact || null);
      setMessage(data.warnings?.join(" ") || "Ответ готов. Граф обновляется автоматически.");
      setActiveTab("Ask");
      setExpertQuery(query);
      await Promise.all([loadGraph(query, { open: false, silent: true }), runExpertSearch(query, { silent: true })]);
    } catch {
      setMessage("Не удалось построить answer.");
    }
  }

  async function runExternalSearch() {
    try {
      setMessage("Ищем внешние научные источники...");
      const data = await fetchJson(`${API_BASE}/api/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          filters: currentFilters({
            include_external_sources: true,
            external_limit: 5,
            external_connectors: ["openalex", "crossref", "google_patents"]
          }),
          limit: 8
        })
      }, "externalSources");
      setAnswer(data);
      setSelectedFact(data.data.evidence_view?.[0]?.fact || null);
      setMessage(data.warnings?.join(" ") || "Внешние источники добавлены к ответу. Граф обновляется автоматически.");
      setActiveTab("Ask");
      setExpertQuery(query);
      await Promise.all([loadGraph(query, { open: false, silent: true }), runExpertSearch(query, { silent: true })]);
    } catch {
      setMessage("Не удалось найти внешние источники.");
    }
  }

  async function runCompare(targetTab = "Compare") {
    try {
      setMessage("Строим compare view...");
      const data = await fetchJson(`${API_BASE}/api/compare`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, filters: currentFilters(), group_by: "document" }) }, "compare");
      setCompare(data);
      setMessage("Сравнение построено.");
      setActiveTab(targetTab);
    } catch {
      setMessage("Не удалось построить compare.");
    }
  }

  async function loadGraph(seed, options = {}) {
    const { open = true, silent = false } = options;
    try {
      const resolvedSeed = repairText(resolveGraphSeed(seed));
      const data = await fetchJson(`${API_BASE}/api/graph/query`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: resolvedSeed, mode: "auto", max_nodes: 48, max_hops: 2 }) }, "graph");
      setGraph(data);
      if (!silent) setMessage(`Граф загружен для '${resolvedSeed}'.`);
      if (open) setActiveTab("Graph");
      return data;
    } catch {
      if (!silent) setMessage("Не удалось загрузить граф.");
      return null;
    }
  }

  async function exportAnswer(format) {
    try {
      const data = await fetchJson(`${API_BASE}/api/export`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, filters: currentFilters(), format }) }, "export");
      setExportPreview(data.data);
      setMessage(`Экспорт подготовлен в формате ${format}.`);
    } catch {
      setMessage("Не удалось подготовить экспорт.");
    }
  }

  async function saveCurrentQuery() {
    try {
      const data = await fetchJson(`${API_BASE}/api/saved-queries`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query, filters: currentFilters(), alert_enabled: true, owner: "demo-user" }) }, "savedQueries");
      setMessage(`Saved query ${data.data.saved_query_id}.`);
      await loadSavedQueries();
    } catch {
      setMessage("Не удалось сохранить запрос.");
    }
  }

  async function runExpertSearch(searchQuery, options = {}) {
    const resolvedQuery = repairText(searchQuery || expertQuery || query).trim();
    if (!resolvedQuery) return;
    try {
      const data = await fetchJson(`${API_BASE}/api/experts/search?q=${encodeURIComponent(resolvedQuery)}&limit=8`, undefined, "experts");
      setExperts(data.data.items || []);
      if (!options.silent) setMessage(data.warnings?.join(" ") || `Найдено экспертов: ${(data.data.items || []).length}.`);
    } catch {
      if (!options.silent) setMessage("Не удалось выполнить поиск экспертов.");
    }
  }

  async function reviewFact(fact, decision) {
    if (!fact?.id) return;
    try {
      if (String(fact.id).startsWith("demo-")) {
        setMessage(decision === "approved" ? "Demo-факт подтвержден локально." : "Demo-факт отклонен локально.");
        return;
      }
      await fetchJson(`${API_BASE}/api/facts/${fact.id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, comment: null, actor: "demo-curator" })
      }, "curate");
      setMessage(decision === "approved" ? "Факт подтвержден." : "Факт отклонен.");
      await loadAlerts();
    } catch {
      setMessage("Не удалось сохранить решение по факту.");
    }
  }

  async function resolveContradiction(item, decision) {
    try {
      const data = await fetchJson(`${API_BASE}/api/contradictions/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ signature: item.signature, left_fact_id: item.left.id, right_fact_id: item.right.id, decision, comment: contradictionNote || null, actor: "demo-curator" }) }, "compare");
      setMessage(`Contradiction resolved: ${data.data.decision}.`);
      await Promise.all([runCompare(), loadAlerts()]);
    } catch {
      setMessage("Не удалось разрешить противоречие.");
    }
  }


  async function handleTabChange(tabId) {
    if (tabId === "Sources") {
      setActiveTab(tabId);
      await Promise.all([loadSources(), loadDashboard()]);
      return;
    }
    if (tabId === "Graph") {
      await loadGraph();
      return;
    }
    if (tabId === "Gaps") {
      if (!compare) {
        await runCompare("Gaps");
        return;
      }
      setActiveTab(tabId);
      return;
    }
    if (tabId === "Dashboard") {
      setActiveTab(tabId);
      await Promise.all([loadSources(), loadDashboard()]);
      return;
    }
    if (tabId === "Compare") {
      if (!compare) {
        await runCompare();
        return;
      }
      setActiveTab(tabId);
      return;
    }
    setActiveTab(tabId);
  }
  function resolveGraphSeed(seed) {
    const explicitSeed = repairText(seed || "").trim();
    if (explicitSeed) return explicitSeed;
    const currentQuery = repairText(query || "").trim();
    if (currentQuery) return currentQuery;
    return repairText(selectedScenario?.query || selectedScenario?.graph_seed || "научные связи");
  }
  function toggleSource(sourceId) {
    setSelectedSourceIds((prev) => prev.includes(sourceId) ? prev.filter((id) => id !== sourceId) : [...prev, sourceId]);
  }

  function applyScenario(item) {
    setSelectedScenarioId(item.id);
    updateQuery(repairText(item.query));
    setMessage(`Выбран сценарий: ${repairText(item.title)}.`);
    setAnswer(null);
    setCompare(null);
    setGraph(null);
  }

  const selectedScenario = useMemo(() => scenarios.find((item) => item.id === selectedScenarioId) || scenarios[0] || null, [scenarios, selectedScenarioId]);
  const page = pageMeta[activeTab];

  return (
    <AppShell sidebar={<Sidebar tabs={tabs} activeTab={activeTab} onTabChange={handleTabChange} health={health} />}>
      {activeTab !== "Ask" ? (
        <div className="workspace-command">
          <div className="workspace-command__search">
            <span>Поиск</span>
            <input value={query} onChange={(event) => updateQuery(event.target.value)} aria-label="Глобальный запрос" />
          </div>
          <div className="workspace-command__actions">
            <StatusBadge tone={health?.status === "ok" ? "good" : "neutral"}>{message || "Готово"}</StatusBadge>
            <Button tone="ghost" onClick={runExternalSearch} disabled={loading.externalSources}>Внешние источники</Button>
            <Button tone="ghost" onClick={() => loadGraph()} disabled={loading.graph}>Граф</Button>
            <Button tone="primary" onClick={runAnswer} disabled={loading.answer}>Задать вопрос</Button>
          </div>
        </div>
      ) : null}

      {activeTab !== "Ask" && activeTab !== "Graph" ? (
        <PageHeader
          eyebrow="Научный клубок"
          title={page.title}
          subtitle={page.subtitle}
          actions={<div className="header-actions"><Button tone="ghost" onClick={() => setActiveTab("Ask")}>К вопросу</Button><Button tone="ghost" onClick={runExternalSearch} disabled={loading.externalSources}>Внешние источники</Button><Button tone="primary" onClick={runAnswer} disabled={loading.answer}>Обновить ответ</Button></div>}
        />
      ) : null}

      {activeTab === "Ask" ? <AskView query={query} onQueryChange={updateQuery} onRunAnswer={runAnswer} onRunExternalSearch={runExternalSearch} onRunCompare={runCompare} onLoadGraph={loadGraph} onSaveQuery={saveCurrentQuery} onExport={exportAnswer} answer={answer} selectedFact={selectedFact} onSelectFact={setSelectedFact} scenarios={scenarios} selectedScenarioId={selectedScenarioId} onApplyScenario={applyScenario} expertQuery={expertQuery} onExpertQueryChange={setExpertQuery} onRunExpertSearch={runExpertSearch} experts={experts} langFilter={langFilter} onLangFilterChange={setLangFilter} savedQueries={savedQueries} exportPreview={exportPreview} loading={loading} error={error} /> : null}
      {activeTab === "Sources" ? <SourcesView sources={sources} selectedSourceIds={selectedSourceIds} onToggleSource={toggleSource} dashboard={dashboard} onUploadDocuments={uploadDocuments} uploadResult={uploadResult} loading={loading} error={error} /> : null}
      {activeTab === "Graph" ? <GraphView graph={graph} scenarios={scenarios} onLoadGraph={loadGraph} loading={loading} error={error} query={query} /> : null}
      {activeTab === "Compare" ? <CompareView compare={compare} selectedScenario={selectedScenario} contradictionNote={contradictionNote} onContradictionNoteChange={setContradictionNote} onResolveContradiction={resolveContradiction} loading={loading} error={error} /> : null}
      {activeTab === "Gaps" ? <GapsView compare={compare} loading={loading} error={error} /> : null}
      {activeTab === "Curate" ? <CurateView answer={answer} onReviewFact={reviewFact} /> : null}
      {activeTab === "Dashboard" ? <DashboardView dashboard={dashboard} sources={sources} /> : null}
    </AppShell>
  );
}





