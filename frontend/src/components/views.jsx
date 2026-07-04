import { useMemo, useState } from "react";
import { BrainCircuit, ChevronDown, Download, FileSearch, GitCompare, Network, Play, Save, Search, Upload, Users } from "lucide-react";
import { buildGraphLayout, displayText, nodeTypeText, relationText, repairText, sourceTypeLabels, uniqueBy, uniqueGraphEdges } from "../constants";
import { Button, Card, EmptyState, ErrorState, FactLine, LoadingState, MetricCard, SectionTitle, StatusBadge } from "./ui";
import { KnowledgeGraphPanel } from "./KnowledgeGraphPanel";

function stableKey(...parts) {
  return parts.map((part) => displayText(part, 220).toLowerCase().replace(/\s+/g, " ").trim()).join("|");
}

function cleanAnswerText(value) {
  return repairText(value || "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\s+$/gm, "")
    .trim();
}

function externalUrl(item) {
  const raw = repairText(item?.url || "").trim();
  if (!raw) return "#";
  if (/^https?:\/\//i.test(raw)) return raw;
  return `https://${raw}`;
}

function openExternalSource(item, event) {
  const url = externalUrl(item);
  if (url === "#") return;
  event?.preventDefault?.();
  window.open(url, "_blank", "noopener,noreferrer");
}

function Collapsible({ title, aside, children, open = false }) {
  return (
    <details className="collapsible-panel" open={open}>
      <summary>
        <span>{title}</span>
        <span className="collapsible-panel__aside">{aside}<ChevronDown size={16} /></span>
      </summary>
      <div className="collapsible-panel__body">{children}</div>
    </details>
  );
}

export function AskView(props) {
  const {
    query,
    onQueryChange,
    onRunAnswer,
    onRunExternalSearch,
    onRunCompare,
    onLoadGraph,
    onSaveQuery,
    onExport,
    answer,
    selectedFact,
    onSelectFact,
    scenarios,
    selectedScenarioId,
    onApplyScenario,
    expertQuery,
    onExpertQueryChange,
    onRunExpertSearch,
    experts,
    langFilter,
    onLangFilterChange,
    savedQueries,
    exportPreview,
    loading,
    error
  } = props;

  const evidenceFacts = answer?.data?.evidence_view || [];
  const externalSources = useMemo(
    () => uniqueBy(answer?.data?.external_sources || [], (item) => stableKey(item.doi || item.patent_number || item.url, item.title, item.year)),
    [answer]
  );
  const supportingMatches = useMemo(
    () => uniqueBy(answer?.data?.matches || [], (match) => stableKey(match.filename, match.text || match.fragment_id)),
    [answer]
  );
  const scenarioItems = useMemo(
    () => uniqueBy(scenarios || [], (item) => stableKey(item.title, item.query)),
    [scenarios]
  );
  const uniqueSavedQueries = useMemo(
    () => uniqueBy(savedQueries || [], (item) => stableKey(item.query)),
    [savedQueries]
  );

  return (
    <div className="ask-workspace">
      <div className="ask-stage">
        <Card className="query-card query-card--focus">
          <div className="ask-kicker">Evidence-first workspace</div>
          <SectionTitle title="Что нужно выяснить?" subtitle="Сформулируйте инженерный вопрос. Система найдет факты, источники и связи." />
          <textarea className="query-textarea query-textarea--focus" value={query} onChange={(e) => onQueryChange(e.target.value)} aria-label="Запрос" placeholder="Например: Какие методы очистки шахтных вод применимы при жестких условиях?" />
          <div className="primary-action-row">
            <Button tone="primary" className="main-ask-button" onClick={onRunAnswer} disabled={loading.answer}><Search size={18} /><span>{loading.answer ? "Ищем ответ..." : "Получить ответ"}</span></Button>
            <Button onClick={onRunExternalSearch} disabled={loading.externalSources}><FileSearch size={16} /><span>{loading.externalSources ? "Ищем..." : "Найти внешние источники"}</span></Button>
            <Button onClick={onRunCompare} disabled={loading.compare}><GitCompare size={16} /><span>Сравнить</span></Button>
            <Button onClick={() => onLoadGraph()} disabled={loading.graph}><Network size={16} /><span>Граф</span></Button>
          </div>
          <div className="secondary-action-row">
            <Button tone="ghost" onClick={onSaveQuery} disabled={loading.savedQueries}><Save size={15} /><span>Сохранить</span></Button>
            <Button tone="ghost" onClick={() => onExport("markdown")} disabled={loading.export}><Download size={15} /><span>Экспорт</span></Button>
          </div>
          <div className="scenario-strip scenario-strip--filters" aria-label="Фильтр источников">
            <span className="strip-label">Корпус</span>
            {[
              ["all", "Все"],
              ["ru", "RU"],
              ["en", "World"]
            ].map(([value, label]) => (
              <button key={value} type="button" className={langFilter === value ? "scenario-pill active" : "scenario-pill"} onClick={() => onLangFilterChange(value)}>{label}</button>
            ))}
          </div>
          <div className="scenario-strip" aria-label="Готовые сценарии">
            {scenarioItems.map((item) => (
              <button key={item.id} type="button" className={item.id === selectedScenarioId ? "scenario-pill active" : "scenario-pill"} onClick={() => onApplyScenario(item)}>
                <Play size={13} />
                <span>{displayText(item.title, 32)}</span>
              </button>
            ))}
          </div>
        </Card>

        <Card className="answer-card">
          <SectionTitle title="Ответ" subtitle="Главный вывод и уверенность." aside={<div className="inline-chips"><StatusBadge tone="info">{answer?.confidence || "-"}</StatusBadge><StatusBadge>{supportingMatches.length} источников</StatusBadge></div>} />
          {error.answer ? <ErrorState text={error.answer} /> : null}
          {loading.answer ? <LoadingState title="Формируем ответ" text="Собираем фрагменты, факты и параметры." /> : null}
          {!loading.answer && !answer ? <EmptyState icon={BrainCircuit} title="Ответ появится здесь" text="Нажмите большую кнопку слева или выберите сценарий." /> : null}
          {answer ? (
            <>
              <div className="summary-panel summary-panel--hero"><pre>{cleanAnswerText(answer.data.summary)}</pre></div>
              <div className="external-preview-panel">
                <div className="row-between"><strong>Внешние научные источники</strong><span>{externalSources.length} ссылок</span></div>
                {loading.externalSources ? <LoadingState title="Ищем внешние источники" text="Проверяем OpenAlex, Crossref и Google Patents." /> : null}
                {!loading.externalSources && externalSources.length ? (
                  <div className="external-preview-list">
                    {externalSources.slice(0, 5).map((item) => (
                      <a key={stableKey(item.doi || item.patent_number || item.url, item.title)} href={externalUrl(item)} target="_blank" rel="noreferrer" onClick={(event) => openExternalSource(item, event)}>
                        <strong>{displayText(item.title, 92)}</strong>
                        <span>{displayText(item.source_name || item.connector_id, 24)}{item.year ? ` · ${item.year}` : ""}{item.doi ? " · DOI" : ""}</span>
                      </a>
                    ))}
                  </div>
                ) : null}
                {!loading.externalSources && !externalSources.length ? <p>Нажмите «Найти внешние источники», чтобы добавить 3-5 релевантных научных ссылок к текущему вопросу.</p> : null}
              </div>
            </>
          ) : null}
        </Card>
      </div>

      {answer ? (
        <div className="detail-dock">
          <Collapsible title="Факты и параметры" aside={<StatusBadge>{evidenceFacts.length} фактов</StatusBadge>} open>
            <div className="answer-grid answer-grid--compact">
              <div>
                <div className="subsection-head"><strong>Доказательства</strong><span>выберите факт</span></div>
                <div className="stack-list evidence-scroll">
                  {evidenceFacts.map((item) => (
                    <button key={item.fact.id} type="button" className={selectedFact?.id === item.fact.id ? "evidence-item active" : "evidence-item"} onClick={() => onSelectFact(item.fact)}>
                      <div className="row-between"><strong>{displayText(item.fact.subject, 70)}</strong><span>{item.fact.confidence}</span></div>
                      <p>{displayText(item.fact.predicate, 40)} {displayText(item.fact.object_value, 120)}</p>
                    </button>
                  ))}
                </div>
              </div>
              <Card className="inner-panel fact-detail-panel">
                {selectedFact ? (
                  <div className="fact-sheet">
                    <FactLine label="Субъект" value={displayText(selectedFact.subject, 100)} />
                    <FactLine label="Предикат" value={displayText(selectedFact.predicate, 80)} />
                    <FactLine label="Значение" value={displayText(selectedFact.object_value, 140)} />
                    <FactLine label="Confidence" value={selectedFact.confidence} />
                    <FactLine label="Единица" value={selectedFact.unit || "-"} />
                    <FactLine label="Диапазон" value={`${selectedFact.min_value ?? "-"} .. ${selectedFact.max_value ?? "-"}`} />
                  </div>
                ) : <EmptyState icon={FileSearch} title="Факт не выбран" text="Выберите факт слева." />}
              </Card>
            </div>
          </Collapsible>

          {supportingMatches.length ? (
            <Collapsible title="Фрагменты источников" aside={<StatusBadge>{supportingMatches.length}</StatusBadge>}>
              <div className="fragments-grid fragments-grid--compact">
                {supportingMatches.map((match) => (
                  <div key={`${match.fragment_id}-${stableKey(match.filename, match.text)}`} className="fragment-card">
                    <div className="row-between"><strong>{displayText(match.filename, 80)}</strong><span>score {match.score}</span></div>
                    <p>{displayText(match.text, 360)}</p>
                  </div>
                ))}
              </div>
            </Collapsible>
          ) : null}

          {externalSources.length ? (
            <Collapsible title="Внешние научные источники" aside={<StatusBadge>{externalSources.length} ссылок</StatusBadge>} open>
              <div className="fragments-grid fragments-grid--compact external-sources-grid">
                {externalSources.map((item) => (
                  <a key={stableKey(item.doi || item.patent_number || item.url, item.title)} className="fragment-card external-source-card" href={externalUrl(item)} target="_blank" rel="noreferrer" onClick={(event) => openExternalSource(item, event)}>
                    <div className="row-between"><strong>{displayText(item.title, 96)}</strong><span>{displayText(item.source_name || item.connector_id, 28)}</span></div>
                    <p>{displayText(item.snippet || "Metadata-only source. Open the link to inspect the publication page.", 280)}</p>
                    <div className="inline-chips">
                      {item.year ? <StatusBadge>{item.year}</StatusBadge> : null}
                      {item.doi ? <StatusBadge>DOI</StatusBadge> : null}
                      {item.patent_number ? <StatusBadge>патент</StatusBadge> : null}
                      <StatusBadge tone="info">{item.access_status || "metadata_only"}</StatusBadge>
                      <StatusBadge>{item.relevance_score || 0}</StatusBadge>
                    </div>
                  </a>
                ))}
              </div>
              <p className="helper-note">Это внешние metadata-ссылки. Они не считаются локальными доказательствами, пока документ не импортирован и не проверен.</p>
            </Collapsible>
          ) : null}

          <Collapsible title="Дополнительно" aside={<StatusBadge>эксперты / запросы</StatusBadge>}>
            <div className="two-column-grid compact-secondary-grid">
              <Card>
                <SectionTitle title="Эксперты" subtitle="Специалисты и команды по теме." />
                <div className="inline-form">
                  <input value={expertQuery} onChange={(e) => onExpertQueryChange(e.target.value)} placeholder="nickel, hydrometallurgy" />
                  <Button onClick={onRunExpertSearch} disabled={loading.experts}><Users size={16} /><span>{loading.experts ? "Ищем..." : "Найти"}</span></Button>
                </div>
                {error.experts ? <ErrorState text={error.experts} /> : null}
                <div className="stack-list top-gap">
                  {experts.length ? experts.map((item) => <div key={`${item.name}-${item.organization}`} className="list-row"><strong>{displayText(item.name, 80)}</strong><span>{displayText(item.organization, 80)}</span><small>{(item.topics || []).map((topic) => displayText(topic, 40)).join(", ")}</small></div>) : <EmptyState icon={Users} title="Эксперты появятся здесь" text="Запустите поиск по теме." />}
                </div>
              </Card>
              <Card>
                <SectionTitle title="Сохраненные запросы" subtitle="Быстрый возврат к важным вопросам." />
                <div className="stack-list">
                  {uniqueSavedQueries.slice(0, 5).length ? uniqueSavedQueries.slice(0, 5).map((item) => <div key={item.id} className="list-row"><strong>{displayText(item.query, 88)}</strong></div>) : <div className="helper-note">Сохраненные вопросы появятся здесь.</div>}
                </div>
                {exportPreview ? <pre className="export-preview">{JSON.stringify(exportPreview, null, 2)}</pre> : null}
              </Card>
            </div>
          </Collapsible>
        </div>
      ) : null}
    </div>
  );
}

export function SourcesView({ sources, selectedSourceIds, onToggleSource, dashboard, onUploadDocuments, uploadResult, loading, error }) {
  const uniqueSources = useMemo(
    () => uniqueBy(sources || [], (source) => stableKey(source.name, source.source_type, source.document_count)),
    [sources]
  );
  const sourceTypeEntries = Object.entries(dashboard?.source_types || {});

  return (
    <div className="view-stack">
      <div className="stats-grid four">
        <MetricCard label="Источников" value={uniqueSources.length} />
        <MetricCard label="Документов" value={dashboard?.documents || 0} />
        <MetricCard label="Фактов" value={dashboard?.facts || 0} />
        <MetricCard label="Классов" value={sourceTypeEntries.length} />
      </div>

      <Card>
        <SectionTitle title="Типы источников" subtitle="Какие документы участвуют в анализе." />
        <div className="source-grid">
          {sourceTypeEntries.map(([key, value]) => (
            <div key={key} className="list-row">
              <strong>{sourceTypeLabels[key] || key}</strong>
              <span>{value} документов</span>
            </div>
          ))}
        </div>
      </Card>

      <UploadDocumentsCard onUploadDocuments={onUploadDocuments} uploadResult={uploadResult} loading={loading} error={error} />

      <Card>
        <SectionTitle title="Библиотека" subtitle="Выберите наборы документов для дальнейшей работы." aside={<StatusBadge>{selectedSourceIds.length} выбрано</StatusBadge>} />
        <div className="source-grid wide">
          {uniqueSources.map((source) => (
            <button key={source.id} type="button" className={selectedSourceIds.includes(source.id) ? "source-card active" : "source-card"} onClick={() => onToggleSource(source.id)}>
              <div className="row-between"><strong>{displayText(source.name, 80)}</strong><input type="checkbox" checked={selectedSourceIds.includes(source.id)} readOnly /></div>
              <p>{sourceTypeLabels[source.source_type] || displayText(source.source_type, 80)}</p>
              <div className="meta-wrap"><span>{source.document_count} docs</span><span>{source.fact_count || 0} facts</span></div>
              <div className="inline-chips"><StatusBadge tone={qualityTone(source.quality_label)}>{source.quality_label}</StatusBadge><StatusBadge>score {source.quality_score}</StatusBadge></div>
            </button>
          ))}
        </div>
      </Card>
    </div>
  );
}

function UploadDocumentsCard({ onUploadDocuments, uploadResult, loading, error }) {
  const [sourceType, setSourceType] = useState("article_review");
  const [name, setName] = useState("");
  const [files, setFiles] = useState([]);
  const sourceTypeOptions = Object.entries(sourceTypeLabels);
  const job = uploadResult?.job;

  function submit(event) {
    event.preventDefault();
    onUploadDocuments?.({ files, sourceType, name });
  }

  return (
    <Card className="upload-card">
      <SectionTitle
        title="Добавить свои документы"
        subtitle="Загрузите PDF, DOCX, XLSX, TXT или другой поддерживаемый формат. Система сама распарсит документ, извлечет факты и добавит их в поиск и граф."
        aside={uploadResult?.source ? <StatusBadge tone="good">добавлено</StatusBadge> : null}
      />
      <form className="upload-form" onSubmit={submit}>
        <div className="upload-form__row">
          <label>
            <span>Тип документа</span>
            <select value={sourceType} onChange={(event) => setSourceType(event.target.value)}>
              {sourceTypeOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
          </label>
          <label>
            <span>Название набора</span>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Например: Отчет по выщелачиванию" />
          </label>
        </div>
        <label className="file-drop">
          <Upload size={18} />
          <span>{files.length ? `${files.length} файл(ов) выбрано` : "Выберите документы"}</span>
          <input type="file" multiple onChange={(event) => setFiles(Array.from(event.target.files || []))} />
        </label>
        <div className="primary-action-row upload-actions">
          <Button tone="primary" type="submit" disabled={loading?.upload || !files.length}>
            <Upload size={16} />
            <span>{loading?.upload ? "Загружаем..." : "Загрузить и обработать"}</span>
          </Button>
          {job ? <StatusBadge tone={job.status === "failed" ? "danger" : job.status === "done" ? "good" : "info"}>{job.status} · {Math.round((job.progress || 0) * 100)}%</StatusBadge> : null}
        </div>
      </form>
      {error?.upload ? <ErrorState text={error.upload} /> : null}
      {uploadResult?.documents?.length ? (
        <div className="uploaded-list">
          {uploadResult.documents.slice(0, 4).map((item) => (
            <div key={item.document_id} className="list-row">
              <strong>{displayText(item.filename, 80)}</strong>
              <span>{item.status || "queued"}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  );
}


export function GraphView({ graph, scenarios, onLoadGraph, loading, error, query }) {
  const graphData = graph?.data || graph || null;
  const nodes = graphData?.nodes || [];
  const edges = useMemo(() => uniqueGraphEdges(graphData?.edges || []), [graphData]);
  const nodeById = useMemo(() => Object.fromEntries(nodes.map((node) => [node.id, node])), [nodes]);
  const typeCounts = useMemo(() => {
    return nodes.reduce((acc, node) => {
      const key = nodeTypeText(node.type || "Unknown");
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
  }, [nodes]);
  const readableEdges = useMemo(
    () => edges.slice(0, 10).map((edge) => ({
      ...edge,
      sourceLabel: displayText(nodeById[edge.source]?.label || edge.source, 56),
      targetLabel: displayText(nodeById[edge.target]?.label || edge.target, 56)
    })),
    [edges, nodeById]
  );
  const scenarioItems = useMemo(() => uniqueBy(scenarios || [], (item) => stableKey(item.title, item.query)).slice(0, 4), [scenarios]);

  return (
    <div className="graph-workspace graph-workspace--focused">
      <Card className="graph-hero-card graph-hero-card--interactive">
        <SectionTitle
          title="Карта знаний"
          subtitle="Граф строится по текущему вопросу: сущности, документы, параметры и слабые места связаны в одну читаемую карту."
          aside={
            <div className="inline-chips graph-actions">
              <Button tone="primary" onClick={() => onLoadGraph(query)} disabled={loading.graph}>Построить по запросу</Button>
              {scenarioItems.map((item) => (
                <Button key={item.id} tone="ghost" onClick={() => onLoadGraph(item.query)} disabled={loading.graph}>{displayText(item.title, 26)}</Button>
              ))}
            </div>
          }
        />
        <KnowledgeGraphPanel graph={graphData} loading={loading.graph} error={error.graph} onRetry={() => onLoadGraph(query)} />
      </Card>

      <div className="two-column-grid compact-secondary-grid">
        <Card>
          <SectionTitle title="Что есть в графе" subtitle="Короткая сводка по типам узлов." />
          {nodes.length ? (
            <div className="coverage-bars">
              {Object.entries(typeCounts).map(([key, value]) => (
                <div key={key} className="coverage-row"><span>{key}</span><strong>{value}</strong><i style={{ width: `${Math.min(100, Number(value) * 18)}%` }} /></div>
              ))}
            </div>
          ) : <EmptyState icon={Network} title="Граф еще не построен" text="Нажмите «Построить по запросу» или задайте вопрос на главном экране." />}
        </Card>
        <Card>
          <SectionTitle title="Ключевые связи" subtitle="Ребра графа в читабельном виде." />
          <div className="stack-list">
            {readableEdges.length ? readableEdges.map((edge) => (
              <div key={edge.id || stableKey(edge.source, edge.target, edge.label)} className="list-row">
                <strong>{relationText(edge.label)}</strong>
                <span>{edge.sourceLabel} → {edge.targetLabel}</span>
              </div>
            )) : <EmptyState icon={Network} title="Связи появятся после анализа" text="Граф автоматически подтянется после ответа или вручную из этой вкладки." />}
          </div>
        </Card>
      </div>
    </div>
  );
}

export function CompareView({ compare, selectedScenario, contradictionNote, onContradictionNoteChange, onResolveContradiction, loading, error }) {
  const compareGroups = Object.entries(compare?.data?.groups || {});
  const contradictionCount = compare?.data?.contradictions?.length || 0;
  const gapItems = compare?.data?.coverage_gaps || [];

  return (
    <div className="view-stack">
      <div className="stats-grid four">
        <MetricCard label="Matches" value={compare?.data?.overview?.match_count || 0} />
        <MetricCard label="Facts" value={compare?.data?.overview?.fact_count || 0} />
        <MetricCard label="Experiments" value={compare?.data?.overview?.experiment_count || 0} />
        <MetricCard label="Contradictions" value={compare?.data?.overview?.contradiction_count || 0} />
      </div>
      {error.compare ? <ErrorState text={error.compare} /> : null}
      {loading.compare ? <LoadingState title="Строим сравнение" text="Сопоставляем документы, режимы, доказательства и противоречия." /> : null}
      {!loading.compare && !compare ? <EmptyState icon={GitCompare} title="Сравнение пока не построено" text="Запустите compare из основного сценария." /> : null}
      {compare ? (
        <div className="two-column-grid compare-user-grid">
          <Card>
            <SectionTitle title="Сценарий и группы" subtitle="Контекст сравнения и документы в текущей выборке." />
            <div className="stack-list">
              {selectedScenario ? <div className="list-row list-row--emphasis"><strong>{displayText(selectedScenario.title, 70)}</strong><p>{displayText(selectedScenario.query, 160)}</p><small>{displayText(selectedScenario.why, 130)}</small></div> : null}
              {compareGroups.map(([key, group]) => <div key={key} className="list-row"><strong>{displayText(key, 80)}</strong><span>sources {group.sources.length}</span><small>facts {group.facts.length}</small></div>)}
            </div>
          </Card>
          <Card>
            <SectionTitle title="Противоречия" subtitle="Где источники расходятся по значениям или утверждениям." aside={<StatusBadge tone={contradictionCount ? "warn" : "good"}>{contradictionCount} open</StatusBadge>} />
            <div className="stack-list">{contradictionCount ? compare.data.contradictions.map((item, index) => <div key={`${item.subject}-${index}`} className="list-row list-row--warning"><strong>{displayText(item.subject, 80)}</strong><span>{displayText(item.reason, 110)}</span><small>{displayText(item.left.object_value, 70)} vs {displayText(item.right.object_value, 70)}</small><div className="inline-chips"><Button tone="ghost" onClick={() => onResolveContradiction(item, "prefer_left")}>Prefer left</Button><Button tone="ghost" onClick={() => onResolveContradiction(item, "prefer_right")}>Prefer right</Button></div></div>) : <EmptyState icon={GitCompare} title="Конфликтов не найдено" text="По текущей выборке явных противоречий не обнаружено." />}</div>
            {contradictionCount ? <textarea className="note-input" value={contradictionNote} onChange={(e) => onContradictionNoteChange(e.target.value)} placeholder="Комментарий к сравнению" /> : null}
          </Card>
          <Card>
            <SectionTitle title="Пробелы в данных" subtitle="Какие темы и комбинации параметров покрыты слабее всего." />
            <div className="stack-list">{gapItems.length ? gapItems.map((gap) => <div key={`${gap.type}-${gap.message}`} className="list-row"><strong>{displayText(gap.type, 70)}</strong><small>{displayText(gap.message, 130)}</small></div>) : <EmptyState icon={Search} title="Критичных пробелов нет" text="Текущая выборка достаточно покрыта для базового анализа." />}</div>
          </Card>
          <Card>
            <SectionTitle title="Экспериментальные режимы" subtitle="Опыты и режимы в scope текущего сравнения." />
            <div className="stack-list">{compare?.data?.experiments?.length ? compare.data.experiments.map((item) => <div key={item.id} className="list-row"><strong>{displayText(item.title, 90)}</strong><span>{displayText(item.material || "-", 70)}</span><small>{displayText(item.process || item.result_summary || item.regime || "-", 110)}</small></div>) : <EmptyState icon={GitCompare} title="Режимы не найдены" text="В текущей выборке нет experiment passports для вывода на экран." />}</div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}


export function GapsView({ compare, loading, error }) {
  const gaps = compare?.data?.coverage_gaps?.length ? compare.data.coverage_gaps : [
    { type: "missing_parameter", message: "Не найден точный диапазон скорости потока для выбранного режима." },
    { type: "weak_recent_sources", message: "Для части параметров мало свежих зарубежных источников в локальном корпусе." },
    { type: "source_diversity", message: "Усильте вывод патентами, нормативами и протоколами экспериментов." }
  ];
  const contradictions = compare?.data?.contradictions || [];
  return (
    <div className="view-stack">
      {error.compare ? <ErrorState text={error.compare} /> : null}
      {loading.compare ? <LoadingState title="Ищем пробелы" text="Проверяем покрытие, противоречия и слабые параметры." /> : null}
      <div className="stats-grid four">
        <MetricCard label="Пробелов" value={gaps.length} />
        <MetricCard label="Противоречий" value={contradictions.length} />
        <MetricCard label="Источник" value={compare ? "real" : "demo"} />
        <MetricCard label="Статус" value="ready" />
      </div>
      <Card>
        <SectionTitle title="Research gaps" subtitle="Что нужно усилить перед инженерным решением." />
        <div className="source-grid">
          {gaps.map((gap) => <div key={`${gap.type}-${gap.message}`} className="list-row list-row--warning"><strong>{displayText(gap.type, 48)}</strong><span>{displayText(gap.message, 180)}</span></div>)}
        </div>
      </Card>
      <Card>
        <SectionTitle title="Противоречия" subtitle="Конфликты параметров и claims." />
        <div className="stack-list">
          {contradictions.length ? contradictions.map((item, index) => <div key={`${item.signature}-${index}`} className="list-row list-row--warning"><strong>{displayText(item.subject, 80)}</strong><span>{displayText(item.reason, 120)}</span></div>) : <EmptyState icon={GitCompare} title="Критичных противоречий нет" text="Для текущей выборки явных конфликтов не найдено." />}
        </div>
      </Card>
    </div>
  );
}

export function CurateView({ answer, onReviewFact }) {
  const facts = answer?.data?.evidence_view?.map((item) => item.fact) || [];
  const [decisions, setDecisions] = useState({});
  const reviewFacts = facts.length ? facts : [
    { id: "demo-fact-1", subject: "шахтные воды", predicate: "USES_MATERIAL", object_value: "коагуляция / флотация", confidence: 0.72 },
    { id: "demo-fact-2", subject: "электроэкстракция", predicate: "OPERATES_AT_CONDITION", object_value: "60-65 °C", confidence: 0.81 }
  ];
  function decide(fact, decision) {
    setDecisions((current) => ({ ...current, [fact.id]: decision }));
    onReviewFact?.(fact, decision);
  }
  return (
    <div className="view-stack">
      <Card>
        <SectionTitle title="Факты на проверку" subtitle="Экспертное решение сохраняется через review endpoint или локально для demo-фактов." aside={<StatusBadge>{Object.keys(decisions).length} reviewed</StatusBadge>} />
        <div className="stack-list">
          {reviewFacts.map((fact) => <div key={fact.id} className="list-row curate-row"><strong>{displayText(fact.subject, 80)}</strong><span>{relationText(fact.predicate)} → {displayText(fact.object_value, 120)}</span><small>confidence {fact.confidence}</small><div className="inline-chips"><Button tone="ghost" onClick={() => decide(fact, "approved")}>Подтвердить</Button><Button tone="ghost" onClick={() => decide(fact, "rejected")}>Отклонить</Button><StatusBadge tone={decisions[fact.id] === "approved" ? "good" : decisions[fact.id] === "rejected" ? "danger" : "neutral"}>{decisions[fact.id] || "needs review"}</StatusBadge></div></div>)}
        </div>
      </Card>
    </div>
  );
}

export function DashboardView({ dashboard, sources }) {
  const sourceTypes = Object.entries(dashboard?.source_types || {});
  const parsed = sources.reduce((sum, source) => sum + (source.document_count || 0), 0);
  return (
    <div className="view-stack">
      <div className="stats-grid four">
        <MetricCard label="Документов" value={dashboard?.documents || parsed || 0} />
        <MetricCard label="Фактов" value={dashboard?.facts || 0} />
        <MetricCard label="Типов источников" value={sourceTypes.length || 0} />
        <MetricCard label="Режим" value="demo-ready" />
      </div>
      <Card>
        <SectionTitle title="Покрытие источников" subtitle="Сколько данных участвует в текущем vertical slice." />
        <div className="coverage-bars">
          {(sourceTypes.length ? sourceTypes : [["article_review", 4], ["experiment_protocol", 2], ["patent_regulation", 1], ["reference_catalog", 1]]).map(([key, value]) => <div key={key} className="coverage-row"><span>{sourceTypeLabels[key] || key}</span><strong>{value}</strong><i style={{ width: `${Math.min(100, Number(value) * 14)}%` }} /></div>)}
        </div>
      </Card>
    </div>
  );
}
function qualityTone(value) {
  if (value === "high") return "good";
  if (value === "strong") return "info";
  if (value === "medium") return "warn";
  if (value === "emerging") return "danger";
  return "neutral";
}




