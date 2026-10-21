// Meterless engines sidecar for whycore: the unmodified open references of H-MEM, World Model and Markovian
// (./engines/<name>, Apache-2.0, pinned commit in ./engines/NOTICE) behind one small HTTP surface on 127.0.0.1.
// State lives under METERLESS_DIR (hmem/, world/, markovian/).
//
// H-MEM (memory mirror; whycore.memory)
//   POST /hmem/add {content, tags, source, ...}   GET /hmem/records?tag=   POST /hmem/query {query}
//   POST /hmem/delete {tag, reason}               GET /hmem/stats          GET /hmem/history?id=
// World Model (what the estate looks like across runs; whycore.engines:world_model)
//   POST /wm/observe {namespace, runId, by, items:[{type, id, name, at, facts:{predicate: value}}]}
//        -> {entities, facts, changes:[{id, predicate, from, to}]}  (a re-observation with equal values is a no-op)
//   GET  /wm/entity?namespace=&id=   GET /wm/stats?namespace=
// Markovian (bounded-carryover chunked generation; whycore.engines:brief)
//   POST /markovian/run {goal, attachments:[{name, content}], chunkConfig, endpoint:{base, key, model, thinkingOff, headers}}
//
// Run: node --experimental-transform-types --no-warnings whycore/meterless/server.ts   (Node 22)
import http from "node:http";
import path from "node:path";
import { HMEM } from "./engines/hmem/index.ts";
import { snapshot } from "./engines/hmem/memoryStore.ts";
import { WorldModel, externalId } from "./engines/world-model/index.ts";
import { Markovian } from "./engines/markovian/index.ts";

const dir = process.env.METERLESS_DIR ?? "data/memory/meterless";
const port = Number(process.env.METERLESS_PORT ?? 8790);
const hmem = new HMEM({ persistDir: path.join(dir, "hmem"), actor: "whycore" });
const worlds = new Map<string, WorldModel>();
const world = (ns: string) => {
  if (!worlds.has(ns)) worlds.set(ns, new WorldModel({ namespace: ns, storage: "local", directory: path.join(dir, "world") }));
  return worlds.get(ns)!;
};
const strip = (r: any) => snapshot(r);

function body(req: http.IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    let s = "";
    req.on("data", (c) => (s += c));
    req.on("end", () => { try { resolve(s ? JSON.parse(s) : {}); } catch (e) { reject(e); } });
  });
}

function send(res: http.ServerResponse, code: number, js: unknown): void {
  res.writeHead(code, { "content-type": "application/json" });
  res.end(JSON.stringify(js));
}

async function hmemRoute(req: http.IncomingMessage, url: URL, res: http.ServerResponse): Promise<boolean> {
  const p = url.pathname.replace(/^\/hmem/, "");
  if (req.method === "POST" && p === "/add") return send(res, 200, strip(hmem.add(await body(req)))), true;
  if (req.method === "GET" && p === "/records") {
    const tag = url.searchParams.get("tag") ?? "";
    const recs = hmem.store.all().filter((r) => r.tags.includes(tag));
    for (const r of recs) {
      hmem.store.touch(r.id);
      hmem.ledger.log(r.id, "read", "whycore", { details: { reason: "recall by tag", tag } });
    }
    return send(res, 200, recs.map(strip)), true;
  }
  if (req.method === "POST" && p === "/query") {
    const b = await body(req);
    const q = hmem.query(b.query ?? "", { topN: b.topN, threshold: b.threshold });
    return send(res, 200, { ...q, memories: q.memories.map((m) => ({ relevance: m.relevance, memory: strip(m.memory) })) }), true;
  }
  if (req.method === "POST" && p === "/delete") {
    const b = await body(req);
    const ids = hmem.store.all().filter((r) => r.tags.includes(b.tag)).map((r) => r.id);
    for (const id of ids) hmem.store.delete(id, b.reason ?? "reset");
    return send(res, 200, { deleted: ids.length }), true;
  }
  if (req.method === "GET" && p === "/stats") return send(res, 200, { engine: "meterless/hmem reference", records: hmem.store.all().length, ledger: hmem.ledger.stats() }), true;
  if (req.method === "GET" && p === "/history") return send(res, 200, hmem.ledger.history(url.searchParams.get("id") ?? "")), true;
  return false;
}

async function wmRoute(req: http.IncomingMessage, url: URL, res: http.ServerResponse): Promise<boolean> {
  const p = url.pathname.replace(/^\/wm/, "");
  if (req.method === "POST" && p === "/observe") {
    const b = await body(req);
    const wm = world(b.namespace ?? "whycore");
    const changes: { id: string; predicate: string; from: unknown; to: unknown }[] = [];
    let facts = 0;
    for (const it of b.items ?? []) {
      const source = { kind: "pipeline", by: b.by ?? "whycore", at: it.at, runId: b.runId };
      // upsertEntity replaces attrs, and attrs carry the winning fact values: create the entity once, then only assert facts
      const eid = externalId(it.type, b.namespace ?? "whycore", it.id);
      const ent = wm.view("graph").entity(eid) ?? (await wm.upsertEntity({ type: it.type, externalKey: { system: b.namespace ?? "whycore", id: it.id }, name: it.name, source }));
      for (const [pred, value] of Object.entries(it.facts ?? {})) {
        const before = ent.attrs[pred];
        const f = await wm.assertFact({ about: ent.id, predicate: pred, value, confidence: 1, source });
        facts += 1;
        if (before !== undefined && JSON.stringify(before) !== JSON.stringify(value) && !f.supersededBy) changes.push({ id: it.id, predicate: pred, from: before, to: value });
      }
    }
    return send(res, 200, { entities: (b.items ?? []).length, facts, changes, events: wm.events().length }), true;
  }
  if (req.method === "GET" && p === "/entity") {
    const wm = world(url.searchParams.get("namespace") ?? "whycore");
    const id = url.searchParams.get("id") ?? "";
    const ent = wm.view("graph").entity(id);
    return send(res, ent ? 200 : 404, ent ? { entity: ent, facts: wm.view("facts").about(id) } : { error: "no such entity" }), true;
  }
  if (req.method === "GET" && p === "/stats") {
    const wm = world(url.searchParams.get("namespace") ?? "whycore");
    const shape: any = wm.stateShape();
    return send(res, 200, { engine: "meterless/world-model reference", events: wm.events().length, audit: wm.audit().length,
      entities: shape?.entities?.length ?? shape?.entityCount, facts: shape?.facts?.length ?? shape?.factCount }), true;
  }
  return false;
}

async function markovianRoute(req: http.IncomingMessage, url: URL, res: http.ServerResponse): Promise<boolean> {
  if (!(req.method === "POST" && url.pathname === "/markovian/run")) return false;
  const b = await body(req);
  const ep = b.endpoint ?? {};
  let measured = 0;
  const generator = async (prompt: string, attachments: { name: string; content: string }[], systemPrompt?: string) => {
    const user = attachments?.length ? `${prompt}\n\n${attachments.map((a) => `[ATTACHMENT ${a.name}]\n${a.content}`).join("\n\n")}` : prompt;
    const payload: any = { model: ep.model, temperature: 0.2, max_tokens: ep.maxTokens ?? 900,
      messages: [...(systemPrompt ? [{ role: "system", content: systemPrompt }] : []), { role: "user", content: user }] };
    if (ep.thinkingOff) payload.chat_template_kwargs = { enable_thinking: false };
    const r = await fetch(`${ep.base}/chat/completions`, { method: "POST", body: JSON.stringify(payload),
      headers: { "content-type": "application/json", authorization: `Bearer ${ep.key}`, ...(ep.headers ?? {}) } });
    if (!r.ok) throw new Error(`HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const js: any = await r.json();
    measured += js.usage?.total_tokens ?? 0;
    return { text: js.choices?.[0]?.message?.content ?? "" };
  };
  const m = new Markovian({ chunkConfig: b.chunkConfig, historyDir: path.join(dir, "markovian") });
  const run = await m.run({ goal: b.goal, mode: "RESEARCH", attachments: b.attachments ?? [], generator, reflect: false });
  return send(res, 200, { ...run, measuredTokens: measured }), true;
}

http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  try {
    if (url.pathname === "/healthz") return send(res, 200, { ok: true, engines: ["hmem", "world-model", "markovian"] });
    if (url.pathname.startsWith("/hmem/") && (await hmemRoute(req, url, res))) return;
    if (url.pathname.startsWith("/wm/") && (await wmRoute(req, url, res))) return;
    if (url.pathname.startsWith("/markovian/") && (await markovianRoute(req, url, res))) return;
    send(res, 404, { error: "not found" });
  } catch (e: any) {
    send(res, 400, { error: String(e?.message ?? e).slice(0, 300) });
  }
}).listen(port, "127.0.0.1", () => console.log(JSON.stringify({ msg: "meterless engines sidecar up", port, dir })));
