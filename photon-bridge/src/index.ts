// Scam Interrupt <-> Photon 2.0 bridge (spectrum-ts, iMessage).
// INBOUND: messages to our line -> POST PYTHON_WEBHOOK {"from","text"}
// OUTBOUND: Python app -> POST http://127.0.0.1:8787/send {"to","text"}
// Opt-in: a person must text the line once first so the bridge knows their conversation.
import { createServer } from "node:http";
import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

const PYTHON_WEBHOOK = process.env.PYTHON_WEBHOOK ?? "http://127.0.0.1:8000/webhooks/photon";
const BRIDGE_PORT = Number(process.env.BRIDGE_PORT ?? 8787);
const WELCOME =
  "You're connected to Scam Interrupt. We'll only message you if a payment looks risky. Reply STOP anytime.";

const spaces = new Map<string, any>();

function normalize(raw: unknown): string {
  const s = String(raw ?? "").trim();
  if (s.includes("@")) return s.toLowerCase();
  const digits = s.replace(/\D/g, "");
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`;
  return digits ? `+${digits}` : "";
}

function senderOf(message: any, space: any): string {
  const candidates = [
    message?.sender?.address, message?.sender?.handle, message?.sender?.phone, message?.sender?.id,
    message?.from?.address, message?.from?.handle, message?.from, message?.author?.id, message?.handle,
    space?.participants?.[0]?.address, space?.participants?.[0]?.id, space?.id,
  ];
  for (const c of candidates) {
    const n = typeof c === "string" ? normalize(c) : "";
    if (n) return n;
  }
  return "";
}

let loggedShape = false;

const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [imessage.config()],
});

createServer(async (req, res) => {
  const reply = (code: number, body: object) => {
    res.writeHead(code, { "Content-Type": "application/json" });
    res.end(JSON.stringify(body));
  };
  if (req.method === "GET" && req.url === "/health") {
    return reply(200, { ok: true, known: [...spaces.keys()] });
  }
  if (req.method !== "POST" || req.url !== "/send") return reply(404, { error: "not found" });
  let raw = "";
  for await (const chunk of req) raw += chunk;
  try {
    const { to, text } = JSON.parse(raw || "{}");
    const space = spaces.get(normalize(to));
    if (!space) return reply(409, { error: `No conversation with ${to} yet. They must text the line once first.` });
    await space.send(String(text));
    console.log(`[out] -> ${normalize(to)}: ${String(text).slice(0, 80)}`);
    return reply(200, { ok: true });
  } catch (e: any) {
    console.error("[out] send failed:", e?.message ?? e);
    return reply(500, { error: String(e?.message ?? e) });
  }
}).listen(BRIDGE_PORT, "127.0.0.1", () => {
  console.log(`[bridge] outbound API on http://127.0.0.1:${BRIDGE_PORT}/send`);
  console.log(`[bridge] forwarding inbound messages to ${PYTHON_WEBHOOK}`);
});

for await (const [space, message] of app.messages) {
  try {
    if (!loggedShape) {
      console.log("[debug] message keys:", Object.keys(message ?? {}), "space keys:", Object.keys(space ?? {}));
      try { console.log("[debug] sender:", JSON.stringify((message as any)?.sender ?? (message as any)?.from)); } catch {}
      loggedShape = true;
    }
    if (message.content.type !== "text") continue;
    const text = message.content.text;
    const from = senderOf(message, space);
    if (from) spaces.set(from, space);
    console.log(`[in]  <- ${from || "(unknown sender)"}: ${text}`);
    let ignored = true;
    try {
      const r = await fetch(PYTHON_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from, text }),
      });
      const body: any = await r.json().catch(() => ({}));
      ignored = Boolean(body?.ignored);
    } catch (e: any) {
      console.error("[in]  Python app not reachable:", e?.message ?? e);
    }
    if (ignored) await space.send(WELCOME);
  } catch (e: any) {
    console.error("[in]  error:", e?.message ?? e);
  }
}
