// H-MEM sidecar for whycore: the unmodified Meterless H-MEM reference engine (./engine, Apache-2.0) behind a tiny
// HTTP surface on 127.0.0.1. whycore.memory mirrors remember()/recall()/reset() here; every write and read lands in
// the engine's append-only trust ledger (ledger.jsonl next to state.json under HMEM_DIR).
//
//   POST /add      {content, tags, source, type?, layer?, confidence?, provenance?}  -> record (without embedding)
//   GET  /records?tag=fp:abc                                                         -> records carrying that tag (logged as "read")
//   POST /query    {query, topN?, threshold?}                                        -> engine hybrid retrieval
//   POST /delete   {tag, reason}                                                     -> delete records with that tag (ledger keeps them)
//   GET  /stats                                                                      -> record count, ledger action counts
//   GET  /history?id=mem-1                                                           -> ledger entries of one record
//
// Run: node --experimental-transform-types whycore/hmem/server.ts   (Node 22; the engine uses TS parameter properties)
import http from "node:http";
import { HMEM } from "./engine/index.ts";
import { snapshot } from "./engine/memoryStore.ts";

const dir = process.env.HMEM_DIR ?? "data/memory/hmem";
const port = Number(process.env.HMEM_PORT ?? 8790);
const hmem = new HMEM({ persistDir: dir, actor: process.env.HMEM_ACTOR ?? "whycore" });

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

http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://x");
  try {
    if (req.method === "POST" && url.pathname === "/add") {
      const b = await body(req);
      return send(res, 200, strip(hmem.add(b)));
    }
    if (req.method === "GET" && url.pathname === "/records") {
      const tag = url.searchParams.get("tag") ?? "";
      const recs = hmem.store.all().filter((r) => r.tags.includes(tag));
      for (const r of recs) {
        hmem.store.touch(r.id);
        hmem.ledger.log(r.id, "read", "whycore", { details: { reason: "recall by tag", tag } });
      }
      return send(res, 200, recs.map(strip));
    }
    if (req.method === "POST" && url.pathname === "/query") {
      const b = await body(req);
      const q = hmem.query(b.query ?? "", { topN: b.topN, threshold: b.threshold });
      return send(res, 200, { ...q, memories: q.memories.map((m) => ({ relevance: m.relevance, memory: strip(m.memory) })) });
    }
    if (req.method === "POST" && url.pathname === "/delete") {
      const b = await body(req);
      const ids = hmem.store.all().filter((r) => r.tags.includes(b.tag)).map((r) => r.id);
      for (const id of ids) hmem.store.delete(id, b.reason ?? "reset");
      return send(res, 200, { deleted: ids.length });
    }
    if (req.method === "GET" && url.pathname === "/stats") {
      return send(res, 200, { engine: "meterless/hmem reference", records: hmem.store.all().length, ledger: hmem.ledger.stats(), dir });
    }
    if (req.method === "GET" && url.pathname === "/history") {
      return send(res, 200, hmem.ledger.history(url.searchParams.get("id") ?? ""));
    }
    send(res, 404, { error: "not found" });
  } catch (e: any) {
    send(res, 400, { error: String(e?.message ?? e).slice(0, 300) });
  }
}).listen(port, "127.0.0.1", () => console.log(JSON.stringify({ msg: "hmem sidecar up", port, dir })));
