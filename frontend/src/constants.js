import {
  BrainCircuit,
  Files,
  GitCompare,
  Network
} from "lucide-react";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export const tabs = [
  { id: "Ask", label: "Аналитика", icon: BrainCircuit },
  { id: "Sources", label: "Источники", icon: Files },
  { id: "Graph", label: "Граф знаний", icon: Network },
  { id: "Compare", label: "Сравнение", icon: GitCompare },
  { id: "Gaps", label: "Пробелы", icon: Network },
  { id: "Curate", label: "Проверка", icon: BrainCircuit },
  { id: "Dashboard", label: "Покрытие", icon: Files }
];

export const pageMeta = {
  Ask: { title: "Исследуйте научные связи", subtitle: "Задайте вопрос и получите ответ с фактами, фрагментами и ссылками на источники.", icon: BrainCircuit },
  Sources: { title: "Источники", subtitle: "Документы и наборы данных, на которые опираются ответы системы.", icon: Files },
  Graph: { title: "Карта связей", subtitle: "Материалы, процессы, параметры и результаты в виде понятной карты.", icon: Network },
  Compare: { title: "Сравнение", subtitle: "Сопоставление решений, доказательств, противоречий и пробелов.", icon: GitCompare },
  Gaps: { title: "Пробелы", subtitle: "Слабые места корпуса, противоречия и недостающие параметры.", icon: Network },
  Curate: { title: "Проверка фактов", subtitle: "Быстрая экспертная проверка фактов из текущего ответа.", icon: BrainCircuit },
  Dashboard: { title: "Покрытие корпуса", subtitle: "Состояние документов, фактов, источников и качества покрытия.", icon: Files }
};

export const sourceTypeLabels = {
  article_review: "Научные статьи и обзоры",
  internal_report: "Внутренние технические отчеты",
  experiment_protocol: "Протоколы экспериментов",
  patent_regulation: "Патенты и нормативные документы",
  reference_catalog: "Справочники и каталоги",
  expert_directory: "Каталоги экспертов и команд",
  taxonomy_catalog: "Классификаторы и таксономии"
};

export const relationLabels = {
  USES_MATERIAL: "использует материал",
  USES_EQUIPMENT: "использует оборудование",
  OPERATES_AT_CONDITION: "работает при условии",
  PRODUCES_OUTPUT: "получает результат",
  DESCRIBED_IN: "описано в",
  VALIDATED_BY: "подтверждено",
  CONTRADICTS: "противоречит",
  AUTHORED_BY: "автор",
  EXPERT_IN: "экспертиза",
  LOCATED_IN: "расположено в",
  SAME_AS: "то же самое",
  QUERY_MATCH: "связано с запросом",
  "из справочника": "из справочника",
  "включает": "включает",
  "запрошено": "запрошено",
  "не найдено в графе": "не найдено",
  "USхS_эсTхRщсь": "использует материал",
  "USхS_хёUщPэхюT": "использует оборудование",
  "ьяусTхф_щю": "расположено в"
};


export const qualityLabels = {
  high: "\u0432\u044b\u0441\u043e\u043a\u043e\u0435",
  strong: "\u0445\u043e\u0440\u043e\u0448\u0435\u0435",
  medium: "\u0441\u0440\u0435\u0434\u043d\u0435\u0435",
  emerging: "\u043d\u0430\u0447\u0430\u043b\u044c\u043d\u043e\u0435"
};

export function percentText(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "-";
  return `${Math.round(Math.min(number, 1) * 100)}%`;
}

export const nodeTypeLabels = {
  Material: "Материал",
  Process: "Процесс",
  Equipment: "Оборудование",
  Facility: "Объект",
  Property: "Свойство",
  Experiment: "Опыт",
  Publication: "Публикация",
  Expert: "Эксперт",
  Organization: "Организация",
  Parameter: "Параметр",
  Condition: "Условие",
  Result: "Результат",
  Claim: "Утверждение",
  Geo: "География",
  Topic: "Тема",
  Query: "Запрос",
  SourceFragment: "Фрагмент",
  Gap: "Пробел",
  Contradiction: "Противоречие",
  Unknown: "Сущность"
};

export function buildGraphLayout(nodes, edges = []) {
  const width = 980;
  const height = 560;
  const cx = width / 2;
  const cy = height / 2;
  const positions = {};
  const velocities = {};
  const typeRadius = {
    Topic: 0,
    Query: 0,
    Material: 165,
    Process: 190,
    Equipment: 230,
    Parameter: 250,
    Condition: 270,
    Result: 255,
    Claim: 285,
    Publication: 315,
    Experiment: 305,
    Geo: 285,
    SourceFragment: 315,
    Gap: 330,
    Contradiction: 330,
    Unknown: 300
  };

  const sorted = [...(nodes || [])].sort((a, b) => {
    if (a.is_query || a.type === "Query") return -1;
    if (b.is_query || b.type === "Query") return 1;
    return String(a.type || "").localeCompare(String(b.type || "")) || String(a.label || "").localeCompare(String(b.label || ""));
  });

  sorted.forEach((node, index) => {
    if (node.is_query || node.type === "Topic" || node.type === "Query") {
      positions[node.id] = { x: cx, y: cy };
    } else {
      const radius = typeRadius[node.type] || 295;
      const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(sorted.length - 1, 1);
      positions[node.id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius * 0.72 };
    }
    velocities[node.id] = { x: 0, y: 0 };
  });

  const edgeList = (edges || []).filter((edge) => positions[edge.source] && positions[edge.target]);
  for (let iteration = 0; iteration < 120; iteration += 1) {
    for (let i = 0; i < sorted.length; i += 1) {
      const a = sorted[i];
      if (a.is_query || a.type === "Query") continue;
      for (let j = i + 1; j < sorted.length; j += 1) {
        const b = sorted[j];
        const pa = positions[a.id];
        const pb = positions[b.id];
        const dx = pa.x - pb.x || 0.1;
        const dy = pa.y - pb.y || 0.1;
        const dist2 = Math.max(dx * dx + dy * dy, 900);
        const force = 8200 / dist2;
        const fx = dx * force;
        const fy = dy * force;
        velocities[a.id].x += fx;
        velocities[a.id].y += fy;
        if (!b.is_query && b.type !== "Query") {
          velocities[b.id].x -= fx;
          velocities[b.id].y -= fy;
        }
      }
    }

    edgeList.forEach((edge) => {
      const source = positions[edge.source];
      const target = positions[edge.target];
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const desired = edge.label === "QUERY_MATCH" ? 145 : 185;
      const strength = Math.min(0.035, 0.012 + Number(edge.weight || 1) * 0.004);
      const force = (dist - desired) * strength;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      if (!nodes.find((n) => n.id === edge.source)?.is_query && nodes.find((n) => n.id === edge.source)?.type !== "Query") {
        velocities[edge.source].x += fx;
        velocities[edge.source].y += fy;
      }
      if (!nodes.find((n) => n.id === edge.target)?.is_query && nodes.find((n) => n.id === edge.target)?.type !== "Query") {
        velocities[edge.target].x -= fx;
        velocities[edge.target].y -= fy;
      }
    });

    sorted.forEach((node) => {
      if (node.is_query || node.type === "Query") {
        positions[node.id] = { x: cx, y: cy };
        return;
      }
      const p = positions[node.id];
      const v = velocities[node.id];
      v.x += (cx - p.x) * 0.004;
      v.y += (cy - p.y) * 0.004;
      p.x = Math.max(90, Math.min(width - 90, p.x + v.x * 0.62));
      p.y = Math.max(55, Math.min(height - 55, p.y + v.y * 0.62));
      v.x *= 0.66;
      v.y *= 0.66;
    });
  }

  Object.keys(positions).forEach((key) => {
    positions[key] = { x: Math.round(positions[key].x), y: Math.round(positions[key].y) };
  });
  return positions;
}

export function truncate(value, length) {
  if (!value) return "";
  return value.length > length ? `${value.slice(0, length - 1)}...` : value;
}

const cp1251ByteByChar = new Map();
for (let code = 0x0410; code <= 0x044f; code += 1) {
  cp1251ByteByChar.set(String.fromCharCode(code), 0xc0 + code - 0x0410);
}
[
  ["Ђ", 0x80], ["Ѓ", 0x81], ["‚", 0x82], ["ѓ", 0x83], ["„", 0x84], ["…", 0x85], ["†", 0x86], ["‡", 0x87], ["€", 0x88], ["‰", 0x89], ["Љ", 0x8a], ["‹", 0x8b], ["Њ", 0x8c], ["Ќ", 0x8d], ["Ћ", 0x8e], ["Џ", 0x8f], ["ђ", 0x90], ["‘", 0x91], ["’", 0x92], ["“", 0x93], ["”", 0x94], ["•", 0x95], ["–", 0x96], ["—", 0x97], ["™", 0x99], ["љ", 0x9a], ["›", 0x9b], ["њ", 0x9c], ["ќ", 0x9d], ["ћ", 0x9e], ["џ", 0x9f], ["Ў", 0xa1], ["ў", 0xa2], ["Ј", 0xa3], ["¤", 0xa4], ["Ґ", 0xa5], ["¦", 0xa6], ["§", 0xa7], ["Ё", 0xa8], ["©", 0xa9], ["Є", 0xaa], ["«", 0xab], ["¬", 0xac], ["®", 0xae], ["Ї", 0xaf], ["°", 0xb0], ["±", 0xb1], ["І", 0xb2], ["і", 0xb3], ["ґ", 0xb4], ["µ", 0xb5], ["¶", 0xb6], ["·", 0xb7], ["ё", 0xb8], ["№", 0xb9], ["є", 0xba], ["»", 0xbb], ["ј", 0xbc], ["Ѕ", 0xbd], ["ѕ", 0xbe], ["ї", 0xbf]
].forEach(([char, byte]) => cp1251ByteByChar.set(char, byte));

function isTechnicalToken(value) {
  return /^[A-Z][A-Z0-9_:/.-]{2,}$/.test(value.trim());
}

function mojibakeScore(value) {
  return (
    (value.match(/[\u00d0\u00d1\u00c2\ufffd]/g) || []).length * 10 +
    (value.match(/Р[\u0400-\u04ff]/g) || []).length * 8 +
    (value.match(/С[\u0400-\u04ff]/g) || []).length * 8 +
    (value.match(/[РС][°-ї]/g) || []).length * 8 +
    (value.match(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g) || []).length * 8
  );
}

function decodeBytesAsUtf8(bytes) {
  try {
    return new TextDecoder("utf-8", { fatal: false }).decode(Uint8Array.from(bytes));
  } catch {
    return null;
  }
}

function encodeCp1251Like(value) {
  const bytes = [];
  for (const char of value) {
    const code = char.charCodeAt(0);
    if (code <= 0xff) {
      bytes.push(code);
    } else if (cp1251ByteByChar.has(char)) {
      bytes.push(cp1251ByteByChar.get(char));
    } else {
      return null;
    }
  }
  return bytes;
}

export function repairText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "string") return String(value);
  if (isTechnicalToken(value)) return value;
  const score = mojibakeScore(value);
  if (!score) return value;

  const latin1Decoded = decodeBytesAsUtf8(Array.from(value, (char) => char.charCodeAt(0) & 255));
  const cp1251Bytes = encodeCp1251Like(value);
  const cp1251Decoded = cp1251Bytes ? decodeBytesAsUtf8(cp1251Bytes) : null;

  return [latin1Decoded, cp1251Decoded]
    .filter(Boolean)
    .reduce((best, candidate) => (mojibakeScore(candidate) < mojibakeScore(best) ? candidate : best), value);
}

export function displayText(value, maxLength = 90) {
  const repaired = repairText(value).trim();
  let readable = repaired;
  if (repaired.startsWith("{") && repaired.endsWith("}")) {
    try {
      const parsed = JSON.parse(repaired);
      readable = parsed.title || parsed.material || parsed.process || parsed.result_summary || repaired;
    } catch {
      readable = repaired;
    }
  }
  return truncate(readable, maxLength);
}

export function relationText(value) {
  const repaired = repairText(value);
  return relationLabels[repaired] || relationLabels[value] || displayText(repaired, 48);
}

export function nodeTypeText(value) {
  const repaired = repairText(value);
  return nodeTypeLabels[repaired] || displayText(repaired, 32);
}

export function uniqueGraphEdges(edges) {
  const seen = new Set();
  return (edges || []).filter((edge) => {
    const key = `${edge.source}|${edge.target}|${relationText(edge.label)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function uniqueBy(items, keyFactory) {
  const seen = new Set();
  return (items || []).filter((item) => {
    const key = keyFactory(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}



