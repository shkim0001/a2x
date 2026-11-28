// API 레이아웃 가져오기: Sample JSON, Swagger(OpenAPI JSON), CSV(엑셀 저장본).
// 형식 판정과 필드 추출은 규칙 코드로 한다.
import { parse as parseYaml } from "yaml";
import type { HttpMethod, LayoutField, Operation } from "./sample-data";

function typeOf(v: unknown): string {
  if (v === null) return "null";
  if (Array.isArray(v)) return "array";
  if (typeof v === "number") return Number.isInteger(v) ? "integer" : "number";
  return typeof v; // string | boolean | object
}

// Sample JSON → 필드 목록 (중첩은 a.b, 배열 요소는 a[].b 로 펼친다)
export function inferFromJson(text: string): LayoutField[] {
  const out: LayoutField[] = [];
  const walk = (v: unknown, prefix: string) => {
    if (Array.isArray(v)) {
      if (v.length > 0 && typeof v[0] === "object" && v[0] !== null) walk(v[0], `${prefix}[]`);
      return;
    }
    if (typeof v === "object" && v !== null) {
      for (const [k, val] of Object.entries(v)) {
        const name = prefix ? `${prefix}.${k}` : k;
        out.push({ name, type: typeOf(val), required: true, description: "" });
        if (typeof val === "object" && val !== null) walk(val, name);
      }
    }
  };
  walk(JSON.parse(text), "");
  return out;
}

// CSV: 필드명,타입,필수(Y/N),설명 — 첫 줄이 머리글이면 건너뛴다
export function parseCsv(text: string): LayoutField[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (lines.length && /^(필드명|name)/i.test(lines[0])) lines.shift();
  return lines.map((l) => {
    const [name = "", type = "string", req = "N", ...desc] = l.split(",").map((c) => c.trim());
    return { name, type, required: /^(y|yes|true|필수)$/i.test(req), description: desc.join(",") };
  });
}

export const CSV_TEMPLATE = "필드명,타입,필수(Y/N),설명\norderId,string,Y,주문 번호\nqty,integer,N,수량\n";

type Json = Record<string, any>;

export type SwaggerResult = {
  title: string;
  version: string;
  baseUrl: string;
  resources: Operation[];
  requestLayout: LayoutField[];
  responseLayout: LayoutField[];
};

// Swagger 2.0 / OpenAPI 3.x (JSON 또는 YAML) → 리소스와 첫 오퍼레이션의 요청·응답 레이아웃
export function parseSwagger(text: string): SwaggerResult {
  let doc: Json;
  try {
    // JSON은 YAML의 부분집합이지만, 오류 메시지가 명확하도록 JSON을 먼저 시도한다
    doc = text.trimStart().startsWith("{") ? JSON.parse(text) : parseYaml(text);
  } catch (e) {
    throw new Error(`문서를 읽을 수 없습니다: ${(e as Error).message.split("\n")[0]}`);
  }
  if (!doc || typeof doc !== "object" || !doc.paths || typeof doc.paths !== "object") throw new Error("paths 항목이 없습니다. OpenAPI/Swagger 문서인지 확인하세요.");

  const resolve = (s: Json | undefined): Json | undefined => {
    if (!s?.$ref) return s;
    const parts = String(s.$ref).replace(/^#\//, "").split("/");
    return resolve(parts.reduce<Json | undefined>((o, p) => o?.[p], doc));
  };
  const fields = (schema: Json | undefined, prefix = ""): LayoutField[] => {
    const s = resolve(schema);
    if (!s) return [];
    if (s.type === "array") return fields(s.items, `${prefix}[]`);
    const req: string[] = s.required ?? [];
    return Object.entries<Json>(s.properties ?? {}).flatMap(([k, raw]) => {
      const p = resolve(raw) ?? {};
      const name = prefix ? `${prefix}.${k}` : k;
      const self = { name, type: p.type ?? "object", required: req.includes(k), description: p.description ?? "" };
      const nested = p.type === "object" || p.properties ? fields(p, name) : p.type === "array" ? fields(p.items, `${name}[]`) : [];
      return [self, ...nested];
    });
  };

  const methods: HttpMethod[] = ["GET", "POST", "PUT", "DELETE"];
  const resources: Operation[] = [];
  let first: Json | undefined;
  for (const [path, item] of Object.entries<Json>(doc.paths)) {
    for (const m of methods) {
      const op = item[m.toLowerCase()];
      if (!op) continue;
      first ??= op;
      resources.push({ method: m, path, summary: op.summary ?? op.operationId ?? "" });
    }
  }

  const params: LayoutField[] = (first?.parameters ?? [])
    .map((p: Json) => resolve(p) ?? {})
    .filter((p: Json) => p.in !== "body")
    .map((p: Json) => ({ name: p.name, type: p.schema?.type ?? p.type ?? "string", required: !!p.required, description: `${p.in} · ${p.description ?? ""}` }));
  const bodyParam = (first?.parameters ?? []).find((p: Json) => p.in === "body"); // Swagger 2.0
  const reqSchema = first?.requestBody?.content?.["application/json"]?.schema ?? bodyParam?.schema;
  const okResp = resolve(first?.responses?.["200"] ?? first?.responses?.["201"]);
  const resSchema = okResp?.content?.["application/json"]?.schema ?? okResp?.schema;

  const baseUrl = doc.servers?.[0]?.url ?? (doc.host ? `https://${doc.host}${doc.basePath ?? ""}` : "");

  return {
    title: doc.info?.title ?? "",
    version: doc.info?.version ?? "",
    baseUrl,
    resources,
    requestLayout: [...params, ...fields(reqSchema)],
    responseLayout: fields(resSchema),
  };
}

// 시연용 Swagger 예시
export const SAMPLE_SWAGGER = JSON.stringify(
  {
    openapi: "3.0.1",
    info: { title: "출고 API", version: "1.2.0" },
    servers: [{ url: "https://wms.internal.example/api/v2" }],
    paths: {
      "/outbounds/{outboundId}": {
        get: {
          summary: "출고 상세 조회",
          parameters: [{ name: "outboundId", in: "path", required: true, schema: { type: "string" }, description: "출고 번호" }],
          responses: { "200": { content: { "application/json": { schema: { $ref: "#/components/schemas/Outbound" } } } } },
        },
      },
      "/outbounds": {
        get: { summary: "출고 목록 조회" },
        post: { summary: "출고 요청 등록" },
      },
    },
    components: {
      schemas: {
        Outbound: {
          type: "object",
          required: ["outboundId", "status"],
          properties: {
            outboundId: { type: "string", description: "출고 번호" },
            status: { type: "string", description: "출고 상태" },
            warehouse: { type: "object", properties: { code: { type: "string" }, name: { type: "string" } } },
            items: { type: "array", items: { type: "object", properties: { sku: { type: "string" }, qty: { type: "integer" } } } },
          },
        },
      },
    },
  },
  null,
  2,
);
