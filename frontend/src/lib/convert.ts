// API 오퍼레이션 → MCP Tool 정의 변환 규칙 (샘플).
// 실제 변환도 LLM이 아니라 규칙 코드로 하고, 설명 보강만 LLM을 덧붙인다(CLAUDE.md 작업 규칙).
import type { Operation, Tool } from "./sample-data";

const ACTION_WORDS = ["search", "cancel", "approve", "reject", "confirm"];

const singular = (w: string) => (w.endsWith("ies") ? w.slice(0, -3) + "y" : w.endsWith("s") ? w.slice(0, -1) : w);
const isParam = (seg: string) => seg.startsWith("{") && seg.endsWith("}");

export function pathParams(path: string): string[] {
  return path.split("/").filter(isParam).map((s) => s.slice(1, -1));
}

export function toolName(op: Operation): string {
  const segs = op.path.split("/").filter(Boolean);
  const endsWithParam = segs.length > 0 && isParam(segs[segs.length - 1]);
  let statics = segs.filter((s) => !isParam(s));

  let verb: string;
  const last = statics[statics.length - 1];
  if (last && ACTION_WORDS.includes(last)) {
    verb = last;
    statics = statics.slice(0, -1);
  } else {
    verb = { GET: endsWithParam ? "get" : "list", POST: "create", PUT: "update", DELETE: "delete" }[op.method];
  }

  // 파라미터 앞의 리소스명과 단건 동작의 마지막 리소스명은 단수로
  const words = statics.map((w, i) => {
    const followedByParam = segs.indexOf(w) + 1 < segs.length && isParam(segs[segs.indexOf(w) + 1]);
    const lastWord = i === statics.length - 1;
    return followedByParam || (lastWord && (verb !== "list" && verb !== "search")) ? singular(w) : w;
  });
  return [verb, ...words].join("_").replace(/-/g, "_").toLowerCase();
}

export function toTool(op: Operation): Tool {
  return {
    name: toolName(op),
    description: op.summary,
    kind: op.method === "GET" ? "조회" : "변경",
    source: `${op.method} ${op.path}`,
  };
}

// MCP tools/list 응답 형태의 미리보기
export function toolSchema(t: Tool, op: Operation) {
  const params = pathParams(op.path);
  return {
    name: t.name,
    description: t.description,
    inputSchema: {
      type: "object",
      properties: Object.fromEntries(params.map((p) => [p, { type: "string", description: `경로 파라미터 ${p}` }])),
      required: params,
    },
  };
}
