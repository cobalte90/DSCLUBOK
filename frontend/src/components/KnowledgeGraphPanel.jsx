import { useEffect, useMemo, useRef, useState } from "react";
import { Download, Maximize2, Network, RotateCcw, Tags } from "lucide-react";
import { displayText, percentText } from "../constants";
import { Button, EmptyState, LoadingState, StatusBadge } from "./ui";

const NODE_STYLES = {
  Query: { fill: "#eef0ff", stroke: "#5b5ce2", text: "#3730a3", label: "\u0417\u0430\u043f\u0440\u043e\u0441" },
  Material: { fill: "#eff6ff", stroke: "#2563eb", text: "#1e40af", label: "\u041c\u0430\u0442\u0435\u0440\u0438\u0430\u043b" },
  Process: { fill: "#f0fdf4", stroke: "#15803d", text: "#166534", label: "\u041f\u0440\u043e\u0446\u0435\u0441\u0441" },
  Equipment: { fill: "#faf5ff", stroke: "#7e22ce", text: "#6b21a8", label: "\u041e\u0431\u043e\u0440\u0443\u0434\u043e\u0432\u0430\u043d\u0438\u0435" },
  Parameter: { fill: "#fffbeb", stroke: "#b45309", text: "#92400e", label: "\u041f\u0430\u0440\u0430\u043c\u0435\u0442\u0440" },
  Condition: { fill: "#f0fdfa", stroke: "#0d9488", text: "#115e59", label: "\u0423\u0441\u043b\u043e\u0432\u0438\u0435" },
  Result: { fill: "#ecfdf5", stroke: "#059669", text: "#065f46", label: "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442" },
  Publication: { fill: "#f0f9ff", stroke: "#0369a1", text: "#075985", label: "\u041f\u0443\u0431\u043b\u0438\u043a\u0430\u0446\u0438\u044f" },
  SourceFragment: { fill: "#f0f9ff", stroke: "#0284c7", text: "#0369a1", label: "\u0424\u0440\u0430\u0433\u043c\u0435\u043d\u0442" },
  Claim: { fill: "#f8fafc", stroke: "#64748b", text: "#475569", label: "\u0423\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u0435" },
  Gap: { fill: "#fff7ed", stroke: "#ea580c", text: "#c2410c", label: "\u041f\u0440\u043e\u0431\u0435\u043b" },
  Contradiction: { fill: "#fff1f2", stroke: "#be123c", text: "#9f1239", label: "\u041f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0435" },
  Unknown: { fill: "#f1f5f9", stroke: "#94a3b8", text: "#64748b", label: "\u0421\u0443\u0449\u043d\u043e\u0441\u0442\u044c" }
};

const EDGE_STYLES = {
  related: { stroke: "#94a3b8", dash: null },
  evidence: { stroke: "#15803d", dash: null },
  parameter: { stroke: "#b45309", dash: null },
  contradiction: { stroke: "#be123c", dash: "7 5" },
  gap: { stroke: "#ea580c", dash: "5 5" },
  source: { stroke: "#0284c7", dash: "2 4" }
};

const MODE_BADGES = {
  real: { tone: "good", text: "\u0413\u0440\u0430\u0444 \u0438\u0437 \u0431\u0430\u0437\u044b \u0437\u043d\u0430\u043d\u0438\u0439" },
  hybrid: { tone: "info", text: "Hybrid: \u0441\u0443\u0449\u043d\u043e\u0441\u0442\u0438 \u0438 \u043d\u0430\u0439\u0434\u0435\u043d\u043d\u044b\u0435 \u0438\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u0438" },
  fallback: { tone: "warn", text: "\u0413\u0440\u0430\u0444 \u043f\u043e\u0441\u0442\u0440\u043e\u0435\u043d \u043f\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0443, \u0442\u043e\u0447\u043d\u044b\u0445 \u0441\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u0439 \u0432 \u0431\u0430\u0437\u0435 \u043c\u0430\u043b\u043e" }
};

export const DEMO_GRAPH = {
  graph_mode: "fallback",
  query: "\u0414\u0435\u043c\u043e\u043d\u0441\u0442\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0439 \u0433\u0440\u0430\u0444",
  nodes: [
    { id: "demo_q", label: "\u0414\u0435\u043c\u043e\u043d\u0441\u0442\u0440\u0430\u0446\u0438\u043e\u043d\u043d\u044b\u0439 \u0433\u0440\u0430\u0444", type: "Query", confidence: 1, sourceCount: 0 },
    { id: "demo_m", label: "\u043d\u0438\u043a\u0435\u043b\u044c", type: "Material", confidence: 0.7, sourceCount: 0 },
    { id: "demo_p", label: "\u044d\u043b\u0435\u043a\u0442\u0440\u043e\u044d\u043a\u0441\u0442\u0440\u0430\u043a\u0446\u0438\u044f", type: "Process", confidence: 0.7, sourceCount: 0 },
    { id: "demo_par", label: "200-240 A/m2", type: "Parameter", confidence: 0.6, sourceCount: 0 },
    { id: "demo_gap", label: "\u0421\u0435\u0440\u0432\u0438\u0441 \u0433\u0440\u0430\u0444\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d", type: "Gap", confidence: 1, sourceCount: 0 }
  ],
  edges: [
    { id: "demo_e1", source: "demo_q", target: "demo_m", label: "\u0437\u0430\u043f\u0440\u043e\u0448\u0435\u043d\u043e", type: "related", confidence: 0.7 },
    { id: "demo_e2", source: "demo_q", target: "demo_p", label: "\u0437\u0430\u043f\u0440\u043e\u0448\u0435\u043d\u043e", type: "related", confidence: 0.7 },
    { id: "demo_e3", source: "demo_p", target: "demo_par", label: "\u0438\u043c\u0435\u0435\u0442 \u0434\u0438\u0430\u043f\u0430\u0437\u043e\u043d", type: "parameter", confidence: 0.6 },
    { id: "demo_e4", source: "demo_q", target: "demo_gap", label: "\u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e \u0432 \u0433\u0440\u0430\u0444\u0435", type: "gap", confidence: 1 }
  ],
  warnings: []
};

function nodeStyle(type) {
  return NODE_STYLES[type] || NODE_STYLES.Unknown;
}

function pillWidth(label) {
  const text = displayText(label, 26);
  return Math.max(96, Math.min(224, 30 + text.length * 7.8));
}

function nodeHalfExtents(node) {
  return {
    hw: pillWidth(node.label) / 2 + 16,
    hh: (node.type === "Query" ? 28 : 23) + 13
  };
}

function resolveCollisions(nodes, positions, pinnedId) {
  const items = nodes
    .filter((node) => positions[node.id])
    .map((node) => ({ id: node.id, ...nodeHalfExtents(node) }));
  for (let iteration = 0; iteration < 260; iteration++) {
    let moved = false;
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i];
        const b = items[j];
        const pa = positions[a.id];
        const pb = positions[b.id];
        const dx = pb.x - pa.x;
        const dy = pb.y - pa.y;
        const overlapX = a.hw + b.hw - Math.abs(dx);
        const overlapY = a.hh + b.hh - Math.abs(dy);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        if (overlapX / (a.hw + b.hw) < overlapY / (a.hh + b.hh)) {
          const push = overlapX / 2 + 1;
          const dir = dx !== 0 ? Math.sign(dx) : (j % 2 ? 1 : -1);
          if (a.id !== pinnedId) pa.x -= dir * push;
          if (b.id !== pinnedId) pb.x += dir * push;
          else if (a.id !== pinnedId) pa.x -= dir * push;
        } else {
          const push = overlapY / 2 + 1;
          const dir = dy !== 0 ? Math.sign(dy) : (j % 2 ? 1 : -1);
          if (a.id !== pinnedId) pa.y -= dir * push;
          if (b.id !== pinnedId) pb.y += dir * push;
          else if (a.id !== pinnedId) pa.y -= dir * push;
        }
      }
    }
    if (!moved) break;
  }
}

function computeLayout(nodes, edges) {
  const positions = {};
  if (!nodes.length) return positions;
  const queryNode = nodes.find((node) => node.type === "Query") || nodes[0];
  const adjacency = new Map(nodes.map((node) => [node.id, []]));
  edges.forEach((edge) => {
    adjacency.get(edge.source)?.push(edge.target);
    adjacency.get(edge.target)?.push(edge.source);
  });

  const depth = new Map([[queryNode.id, 0]]);
  const queue = [queryNode.id];
  while (queue.length) {
    const current = queue.shift();
    for (const next of adjacency.get(current) || []) {
      if (!depth.has(next)) {
        depth.set(next, depth.get(current) + 1);
        queue.push(next);
      }
    }
  }
  const maxDepth = Math.max(1, ...depth.values());
  nodes.forEach((node) => {
    if (!depth.has(node.id)) depth.set(node.id, maxDepth + 1);
  });

  const rings = new Map();
  nodes.forEach((node) => {
    if (node.id === queryNode.id) return;
    const level = depth.get(node.id);
    rings.set(level, [...(rings.get(level) || []), node]);
  });

  positions[queryNode.id] = { x: 0, y: 0 };
  [...rings.keys()].sort((a, b) => a - b).forEach((level, ringIndex) => {
    const ringNodes = rings.get(level).slice().sort((a, b) => (a.type + a.label).localeCompare(b.type + b.label));
    const baseRadius = 210 + ringIndex * 165;
    ringNodes.forEach((node, index) => {
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / ringNodes.length + ringIndex * 0.35;
      const wobble = ringNodes.length > 8 ? (index % 2 === 0 ? -34 : 34) : 0;
      const radiusX = baseRadius + wobble + 60;
      const radiusY = (baseRadius + wobble) * 0.62;
      positions[node.id] = { x: radiusX * Math.cos(angle), y: radiusY * Math.sin(angle) };
    });
  });
  resolveCollisions(nodes, positions, queryNode.id);
  return positions;
}

function contentBounds(nodes, positions) {
  let minX = -140, minY = -90, maxX = 140, maxY = 90;
  nodes.forEach((node) => {
    const point = positions[node.id];
    if (!point) return;
    const halfWidth = pillWidth(node.label) / 2 + 26;
    minX = Math.min(minX, point.x - halfWidth);
    maxX = Math.max(maxX, point.x + halfWidth);
    minY = Math.min(minY, point.y - 58);
    maxY = Math.max(maxY, point.y + 58);
  });
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function edgePath(source, target) {
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const norm = Math.sqrt(dx * dx + dy * dy) || 1;
  const bend = Math.min(46, norm * 0.14);
  const cx = midX - (dy / norm) * bend;
  const cy = midY + (dx / norm) * bend;
  return { d: `M ${source.x} ${source.y} Q ${cx} ${cy} ${target.x} ${target.y}`, labelX: cx, labelY: cy };
}

export function KnowledgeGraphPanel({ graph, loading, error, onRetry }) {
  const failed = Boolean(error) && !graph;
  const activeGraph = graph && Array.isArray(graph.nodes) ? graph : failed ? DEMO_GRAPH : null;
  const nodes = activeGraph?.nodes || [];
  const edges = useMemo(() => {
    const ids = new Set(nodes.map((node) => node.id));
    return (activeGraph?.edges || []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  }, [activeGraph, nodes]);

  const positions = useMemo(() => computeLayout(nodes, edges), [nodes, edges]);
  const bounds = useMemo(() => contentBounds(nodes, positions), [nodes, positions]);
  const labelObstacles = useMemo(
    () =>
      nodes
        .filter((node) => positions[node.id])
        .map((node) => ({ ...positions[node.id], ...nodeHalfExtents(node) })),
    [nodes, positions]
  );

  const [viewBox, setViewBox] = useState(null);
  const [showLabels, setShowLabels] = useState(true);
  const [hoveredId, setHoveredId] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const svgRef = useRef(null);
  const dragRef = useRef(null);

  const view = viewBox || bounds;

  useEffect(() => {
    setViewBox(null);
    setSelectedId(null);
    setHoveredId(null);
  }, [activeGraph]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;
    function onWheel(event) {
      event.preventDefault();
      const factor = event.deltaY > 0 ? 1.12 : 0.89;
      setViewBox((current) => {
        const base = current || bounds;
        const w = base.w * factor;
        const h = base.h * factor;
        return { x: base.x + (base.w - w) / 2, y: base.y + (base.h - h) / 2, w, h };
      });
    }
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [bounds]);

  const neighborIds = useMemo(() => {
    const focus = hoveredId || selectedId;
    if (!focus) return null;
    const set = new Set([focus]);
    edges.forEach((edge) => {
      if (edge.source === focus) set.add(edge.target);
      if (edge.target === focus) set.add(edge.source);
    });
    return set;
  }, [hoveredId, selectedId, edges]);

  const selectedNode = useMemo(() => nodes.find((node) => node.id === selectedId) || null, [nodes, selectedId]);
  const selectedEdges = useMemo(
    () => (selectedId ? edges.filter((edge) => edge.source === selectedId || edge.target === selectedId) : []),
    [edges, selectedId]
  );
  const nodeById = useMemo(() => Object.fromEntries(nodes.map((node) => [node.id, node])), [nodes]);

  const typeCounts = useMemo(() => {
    const counts = {};
    nodes.forEach((node) => {
      counts[node.type] = (counts[node.type] || 0) + 1;
    });
    return counts;
  }, [nodes]);

  function fitView() {
    setViewBox(null);
  }

  function resetView() {
    setViewBox(null);
    setSelectedId(null);
    setHoveredId(null);
  }

  function exportJson() {
    if (!activeGraph) return;
    const blob = new Blob([JSON.stringify(activeGraph, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "knowledge-graph.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function onPointerDown(event) {
    if (event.target.closest(".kg-node")) return;
    dragRef.current = { startX: event.clientX, startY: event.clientY, view: { ...view } };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event) {
    const drag = dragRef.current;
    if (!drag) return;
    const svg = svgRef.current;
    const rect = svg.getBoundingClientRect();
    const scaleX = drag.view.w / rect.width;
    const scaleY = drag.view.h / rect.height;
    setViewBox({
      ...drag.view,
      x: drag.view.x - (event.clientX - drag.startX) * scaleX,
      y: drag.view.y - (event.clientY - drag.startY) * scaleY
    });
  }

  function onPointerUp() {
    dragRef.current = null;
  }

  const mode = MODE_BADGES[activeGraph?.graph_mode] || MODE_BADGES.fallback;

  if (loading) {
    return <LoadingState title="\u0421\u0442\u0440\u043e\u0438\u043c \u0433\u0440\u0430\u0444" text="\u0418\u0437\u0432\u043b\u0435\u043a\u0430\u0435\u043c \u0441\u0443\u0449\u043d\u043e\u0441\u0442\u0438, \u0441\u0432\u044f\u0437\u044b\u0432\u0430\u0435\u043c \u0438\u0445 \u0441 \u0431\u0430\u0437\u043e\u0439 \u0437\u043d\u0430\u043d\u0438\u0439 \u0438 \u0440\u0430\u0441\u043a\u043b\u0430\u0434\u044b\u0432\u0430\u0435\u043c \u043a\u0430\u0440\u0442\u0443." />;
  }
  if (!activeGraph) {
    return <EmptyState icon={Network} title="\u0413\u0440\u0430\u0444 \u043f\u043e\u043a\u0430 \u043f\u0443\u0441\u0442" text="\u0417\u0430\u0434\u0430\u0439\u0442\u0435 \u0432\u043e\u043f\u0440\u043e\u0441 \u0438\u043b\u0438 \u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0441\u0446\u0435\u043d\u0430\u0440\u0438\u0439, \u0438 \u0433\u0440\u0430\u0444 \u043f\u043e\u0441\u0442\u0440\u043e\u0438\u0442\u0441\u044f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438." />;
  }
  if (!nodes.length) {
    return (
      <EmptyState
        icon={Network}
        title="\u0414\u043b\u044f \u044d\u0442\u043e\u0433\u043e \u0437\u0430\u043f\u0440\u043e\u0441\u0430 \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0441\u0442\u0440\u043e\u0438\u0442\u044c \u0443\u0437\u043b\u044b"
        text="\u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u043f\u0435\u0440\u0435\u0444\u043e\u0440\u043c\u0443\u043b\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0437\u0430\u043f\u0440\u043e\u0441: \u0434\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b, \u043f\u0440\u043e\u0446\u0435\u0441\u0441 \u0438\u043b\u0438 \u043f\u0430\u0440\u0430\u043c\u0435\u0442\u0440\u044b."
        action={onRetry ? <Button tone="ghost" onClick={onRetry}>{"\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c"}</Button> : null}
      />
    );
  }

  return (
    <div className="kg-panel">
      <div className="kg-topbar">
        <div className="inline-chips">
          <StatusBadge tone={mode.tone}>{mode.text}</StatusBadge>
          <StatusBadge>{`${nodes.length} \u0443\u0437\u043b\u043e\u0432 - ${edges.length} \u0441\u0432\u044f\u0437\u0435\u0439`}</StatusBadge>
          {failed ? <StatusBadge tone="danger">{"\u0421\u0435\u0440\u0432\u0438\u0441 \u0433\u0440\u0430\u0444\u0430 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d, \u043f\u043e\u043a\u0430\u0437\u0430\u043d \u0434\u0435\u043c\u043e-\u0433\u0440\u0430\u0444"}</StatusBadge> : null}
        </div>
        <div className="kg-toolbar">
          <Button tone="ghost" onClick={fitView} title="\u0412\u043f\u0438\u0441\u0430\u0442\u044c \u0433\u0440\u0430\u0444 \u0432 \u044d\u043a\u0440\u0430\u043d"><Maximize2 size={14} /><span>{"\u0412\u043f\u0438\u0441\u0430\u0442\u044c"}</span></Button>
          <Button tone="ghost" onClick={resetView} title="\u0421\u0431\u0440\u043e\u0441\u0438\u0442\u044c \u0432\u0438\u0434 \u0438 \u0432\u044b\u0431\u043e\u0440"><RotateCcw size={14} /><span>{"\u0421\u0431\u0440\u043e\u0441"}</span></Button>
          <Button tone="ghost" onClick={() => setShowLabels((value) => !value)} title="\u041f\u043e\u043a\u0430\u0437\u0430\u0442\u044c \u0438\u043b\u0438 \u0441\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u0438 \u0441\u0432\u044f\u0437\u0435\u0439"><Tags size={14} /><span>{showLabels ? "\u0421\u043a\u0440\u044b\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u0438" : "\u041f\u043e\u0434\u043f\u0438\u0441\u0438"}</span></Button>
          <Button tone="ghost" onClick={exportJson} title="\u0421\u043a\u0430\u0447\u0430\u0442\u044c \u0433\u0440\u0430\u0444 \u0432 JSON"><Download size={14} /><span>JSON</span></Button>
        </div>
      </div>

      {failed ? <p className="kg-error-note">{"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0433\u0440\u0430\u0444 \u0441 \u0441\u0435\u0440\u0432\u0435\u0440\u0430: "}{String(error)}{". \u041d\u0438\u0436\u0435 \u043f\u043e\u043a\u0430\u0437\u0430\u043d \u0434\u0435\u043c\u043e-\u0433\u0440\u0430\u0444, \u043f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 backend \u0438 \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u0437\u0430\u043f\u0440\u043e\u0441."}</p> : null}
      {(activeGraph.warnings || []).slice(0, 2).map((warning) => (
        <p key={warning} className="kg-warning-note">{displayText(warning, 220)}</p>
      ))}

      <div className="kg-canvas-shell">
        <svg
          ref={svgRef}
          className="kg-canvas"
          viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
          role="img"
          aria-label="\u041a\u0430\u0440\u0442\u0430 \u0437\u043d\u0430\u043d\u0438\u0439"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          {edges.map((edge) => {
            const source = positions[edge.source];
            const target = positions[edge.target];
            if (!source || !target) return null;
            const style = EDGE_STYLES[edge.type] || EDGE_STYLES.related;
            const dimmed = neighborIds && !(neighborIds.has(edge.source) && neighborIds.has(edge.target));
            const { d, labelX, labelY } = edgePath(source, target);
            const labelText = displayText(edge.label, 24);
            const labelHalfWidth = labelText.length * 2.8 + 6;
            const labelClear = !labelObstacles.some(
              (box) => Math.abs(labelX - box.x) < box.hw + labelHalfWidth - 10 && Math.abs(labelY - box.y) < box.hh + 4
            );
            return (
              <g key={edge.id} className={dimmed ? "kg-edge kg-edge--dim" : "kg-edge"}>
                <path d={d} fill="none" stroke={style.stroke} strokeWidth="1.7" strokeDasharray={style.dash || undefined} opacity="0.75" />
                {showLabels && edges.length <= 30 && labelClear ? (
                  <text x={labelX} y={labelY} textAnchor="middle" className="kg-edge__label">{labelText}</text>
                ) : null}
              </g>
            );
          })}
          {nodes.map((node) => {
            const point = positions[node.id];
            if (!point) return null;
            const style = nodeStyle(node.type);
            const width = pillWidth(node.label);
            const isQuery = node.type === "Query";
            const height = isQuery ? 56 : 46;
            const dimmed = neighborIds && !neighborIds.has(node.id);
            const isSelected = node.id === selectedId;
            return (
              <g
                key={node.id}
                className={`kg-node${dimmed ? " kg-node--dim" : ""}${isSelected ? " kg-node--selected" : ""}`}
                transform={`translate(${point.x}, ${point.y})`}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                onClick={() => setSelectedId((current) => (current === node.id ? null : node.id))}
              >
                <title>{displayText(node.label, 200)}</title>
                <rect
                  x={-width / 2}
                  y={-height / 2}
                  width={width}
                  height={height}
                  rx={height / 2}
                  fill={style.fill}
                  stroke={style.stroke}
                  strokeWidth={isQuery || isSelected ? 2.6 : 1.6}
                />
                <text y={showLabels ? -3 : 5} textAnchor="middle" className="kg-node__label" fill={style.text}>
                  {displayText(node.label, isQuery ? 30 : 24)}
                </text>
                {showLabels ? (
                  <text y={14} textAnchor="middle" className="kg-node__type" fill={style.stroke}>
                    {style.label}{node.sourceCount ? ` - ${node.sourceCount} \u0438\u0441\u0442.` : ""}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>

        {selectedNode ? (
          <aside className="kg-details">
            <div className="kg-details__head">
              <StatusBadge tone="info">{nodeStyle(selectedNode.type).label}</StatusBadge>
              <button type="button" className="kg-details__close" onClick={() => setSelectedId(null)} aria-label="\u0417\u0430\u043a\u0440\u044b\u0442\u044c">{"\u00d7"}</button>
            </div>
            <strong>{displayText(selectedNode.label, 160)}</strong>
            {selectedNode.description ? <p>{displayText(selectedNode.description, 320)}</p> : null}
            <div className="kg-details__meta">
              <span>{"\u0423\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0441\u0442\u044c: "}{percentText(selectedNode.confidence)}</span>
              <span>{"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: "}{selectedNode.sourceCount || 0}</span>
            </div>
            {selectedEdges.length ? (
              <div className="kg-details__edges">
                {selectedEdges.slice(0, 8).map((edge) => {
                  const otherId = edge.source === selectedNode.id ? edge.target : edge.source;
                  const other = nodeById[otherId];
                  return (
                    <button key={edge.id} type="button" onClick={() => setSelectedId(otherId)}>
                      <em>{displayText(edge.label, 28)}</em>
                      <span>{displayText(other?.label || otherId, 48)}</span>
                    </button>
                  );
                })}
              </div>
            ) : null}
          </aside>
        ) : null}
      </div>

      <div className="kg-legend">
        {Object.entries(typeCounts).map(([type, count]) => {
          const style = nodeStyle(type);
          return (
            <span key={type}>
              <i style={{ background: style.fill, borderColor: style.stroke }} />
              {style.label}: {count}
            </span>
          );
        })}
      </div>
    </div>
  );
}
