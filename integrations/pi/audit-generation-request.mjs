// Read a prepared Pi v0.3 model/settings configuration; capture one request at
// an isolated local stub. This never runs the prepared task or contacts Ollama.
import { readFileSync, writeFileSync, mkdirSync, mkdtempSync, realpathSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const [preparedPath, outputPath] = process.argv.slice(2);
if (!preparedPath || !outputPath) throw new Error("Usage: audit-generation-request.mjs PREPARED_RUN OUTPUT_JSON");
const output = resolve(outputPath);
// Refuse overwrites, including evidence from earlier attempts.
const { openSync, closeSync } = await import("node:fs");
closeSync(openSync(output, "wx"));
const root = mkdtempSync(join(tmpdir(), "pi-generation-audit-"));
const agent = join(root, "agent"), workspace = join(root, "workspace");
mkdirSync(agent); mkdirSync(workspace);
const models = JSON.parse(readFileSync(join(preparedPath, "pi-agent/models.json"), "utf8"));
const settings = JSON.parse(readFileSync(join(preparedPath, "pi-agent/settings.json"), "utf8"));
const captured = [];
let child;
const server = createServer(async (req, res) => {
  try {
    let raw = "";
    for await (const chunk of req) raw += chunk.toString();
    captured.push({ path: req.url, body: JSON.parse(raw) });
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    const common = { id: "generation-audit", object: "chat.completion.chunk", created: 0, model: "benchmark-stub" };
    res.write(`data: ${JSON.stringify({ ...common, choices: [{ index: 0, delta: { role: "assistant", content: "Offline audit finished." }, finish_reason: null }] })}\n\n`);
    res.end(`data: ${JSON.stringify({ ...common, choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } })}\n\ndata: [DONE]\n\n`);
  } catch (e) { res.writeHead(500); res.end(String(e)); }
});
try {
  await new Promise((ok, fail) => { server.once("error", fail); server.listen(0, "127.0.0.1", ok); });
  models.providers.ollama.baseUrl = `http://127.0.0.1:${server.address().port}/v1`;
  writeFileSync(join(agent, "models.json"), JSON.stringify(models));
  writeFileSync(join(agent, "settings.json"), JSON.stringify(settings));
  const model = models.providers.ollama.models[0].id;
  const pi = realpathSync(join(dirname(fileURLToPath(import.meta.url)), "node_modules/.bin/pi"));
  child = spawn(process.execPath, [pi, "--mode", "json", "--print", "--provider", "ollama",
    "--model", model, "--api-key", "ollama", "--thinking", "off", "--tools", "read",
    "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-themes",
    "--no-context-files", "--no-approve", "--offline", "--system-prompt", "Answer briefly.",
    "--", "Offline request-format audit. Do not use tools."], {
    cwd: workspace, env: { HOME: agent, PATH: process.env.PATH, PI_CODING_AGENT_DIR: agent,
      PI_OFFLINE: "1", PI_SKIP_VERSION_CHECK: "1", PI_TELEMETRY: "0" }, stdio: ["ignore", "pipe", "pipe"],
  });
  let stdout = "", stderr = "";
  child.stdout.on("data", b => { stdout += b.toString(); });
  child.stderr.on("data", b => { stderr += b.toString(); });
  const timer = setTimeout(() => child.kill("SIGKILL"), 10_000);
  let exitCode;
  try { exitCode = await new Promise((ok, fail) => { child.once("error", fail); child.once("close", ok); }); }
  finally { clearTimeout(timer); }
  const proof = { schema_version: "pi-v0.3-generation-request-audit-v1", model_requests: 0,
    prepared_model_configuration: JSON.parse(readFileSync(join(preparedPath, "pi-agent/models.json"), "utf8")),
    changes_for_probe: ["fresh isolated directories", "loopback stub URL", "brief probe prompt", "read-only tool set; no extensions"],
    exit_code: exitCode, requests: captured, stdout, stderr };
  writeFileSync(output, JSON.stringify(proof, null, 2) + "\n");
  if (exitCode !== 0 || captured.length !== 1) throw new Error("Pi audit did not complete exactly once; inspect private evidence");
  console.log(JSON.stringify({ output, exit_code: exitCode, request_count: captured.length,
    settings: Object.fromEntries(Object.entries(captured[0].body).filter(([k]) => !["messages", "tools"].includes(k))) }));
} finally {
  if (child && child.exitCode === null) child.kill("SIGKILL");
  server.closeAllConnections();
  await new Promise(ok => server.close(ok));
  rmSync(root, { recursive: true, force: true });
}
