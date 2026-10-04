"""School plugin source — bundled TypeScript plugin for OpenCode."""

from __future__ import annotations

from school import __version__ as _SCHOOL_VERSION

_TS_PLUGIN_TEMPLATE = r'''import { tool } from "@opencode-ai/plugin/tool"
import type { Plugin } from "@opencode-ai/plugin"
import { execFile, spawn } from "node:child_process"
import { promisify } from "node:util"
import { resolve } from "node:path"
import { existsSync, appendFileSync, readFileSync, writeFileSync,
  mkdirSync, statSync } from "node:fs"
import { execSync } from "node:child_process"

const execFileAsync = promisify(execFile)

/** School version this plugin was generated from — canonical source: school.__version__. */
const SCHOOL_VERSION = "__SCHOOL_VERSION__"

/**
 * Find a usable Python interpreter.
 */
async function findPython(): Promise<string | null> {
  for (const cmd of ["python3", "python"]) {
    try {
      const { stdout } = await execFileAsync(cmd, ["--version"], {
        timeout: 5000,
        windowsHide: true,
      })
      if (stdout.includes("Python")) return cmd
    } catch {
      continue
    }
  }
  return null
}

/**
 * Test if a Python module is available.
 */
async function testModule(python: string, module: string): Promise<boolean> {
  try {
    await execFileAsync(python, ["-c", `import ${module}`], {
      timeout: 5000,
      windowsHide: true,
    })
    return true
  } catch {
    return false
  }
}

/**
 * Check if a file exists.
 */
function fileExists(path: string): boolean {
  try {
    return existsSync(path)
  } catch {
    return false
  }
}

/**
 * Bridge discovery result.
 */
interface BridgeInfo {
  python: string
  bridgePath: string
  tier: string
}

/**
 * Discover the School bridge using a 4-tier cascade.
 */
async function discoverBridge(worktree: string): Promise<BridgeInfo | null> {
  const python = await findPython()

  // Tier 1: SCHOOL_HOME env var
  const schoolHome = process.env.SCHOOL_HOME
  if (schoolHome) {
    const bridgePath = resolve(schoolHome, "school", "bridge.py")
    if (fileExists(bridgePath)) {
      return { python: python ?? "python3", bridgePath, tier: "SCHOOL_HOME" }
    }
  }

  // Tier 2: bridge launcher on PATH
  for (const command of ["school-bridge"]) {
    try {
      const isWin = process.platform === "win32"
      const whereCmd = isWin ? `where ${command}` : `which ${command}`
      const bridgeCmd = execSync(whereCmd, { windowsHide: true, timeout: 3000 })
        .toString().trim()
      if (bridgeCmd) {
        return { python: "", bridgePath: bridgeCmd, tier: "PATH" }
      }
    } catch {
      // Not on PATH — next tier
    }
  }

  // Tier 3: installed module
  if (python) {
    for (const module of ["school.bridge"]) {
      const available = await testModule(python, module)
      if (available) {
        return { python, bridgePath: `-m ${module}`, tier: "installed_module" }
      }
    }
  }

  // Tier 4: Dev fallback
  for (const script of ["school_bridge.py"]) {
    const devBridge = resolve(worktree, "scripts", script)
    if (fileExists(devBridge)) {
      return { python: python ?? "python3", bridgePath: devBridge, tier: "dev_fallback" }
    }
  }

  return null
}

/**
 * Run the bridge child process with a JSON stdin payload.
 * Uses spawn + explicit stdin write: the execFile `input` option is
 * not delivered by every plugin runtime, which leaves the bridge
 * child blocked on stdin until the invoke timeout fires.
 */
function runBridge(
  python: string,
  args: string[],
  json: string,
  timeoutMs = 30000,
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const cmd = `${python} ${args.join(" ")}`
    const child = spawn(python, args, { windowsHide: true })
    let stdout = ""
    let stderr = ""
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill()
      reject(new Error(`Command failed: ${cmd}`))
    }, timeoutMs)

    child.stdout.on("data", (d) => {
      stdout += d
    })
    child.stderr.on("data", (d) => {
      stderr += d
    })
    child.on("error", (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(err)
    })
    child.on("close", (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      if (code !== 0) {
        reject(new Error(`Command failed: ${cmd}`))
        return
      }
      resolve({ stdout, stderr })
    })
    child.stdin.on("error", () => {
      // child may exit before consuming stdin — surfaced via close
    })
    child.stdin.write(json)
    child.stdin.end()
  })
}

/**
 * Invoke the School bridge with a JSON request.
 */
async function invokeBridge(
  python: string,
  bridgePath: string,
  request: Record<string, unknown>,
  timeoutMs?: number,
): Promise<Record<string, unknown>> {
  const json = JSON.stringify(request)
  // Module invocations arrive as "-m <module>" (school.bridge, or the
  // legacy lerev.bridge alias); anything else is a direct script path.
  const args = bridgePath.startsWith("-m ")
    ? ["-m", ...bridgePath.slice(3).split(" ")]
    : [bridgePath]

  try {
    const { stdout, stderr } = await runBridge(python, args, json, timeoutMs)
    if (stderr) console.error("[school bridge stderr]", stderr)
    if (!stdout.trim()) {
      return {
        ok: false,
        error: { type: "protocol", message: "empty bridge response" },
      }
    }
    return JSON.parse(stdout.trim())
  } catch (err: any) {
    return {
      ok: false,
      error: { type: "bridge_error", message: err?.message ?? String(err) },
    }
  }
}

// ---------------------------------------------------------------------------
// Execution hooks — School runs and shows itself on every tool execution
// and every prompt. All hook work is budgeted (top-3, thresholded, timeboxed)
// and must never break the execution it observes.
// ---------------------------------------------------------------------------

const HOOK_TIMEOUT_MS = 1500
const HOOK_LIMIT = 3
const HOOK_THRESHOLD = 0.2
const HOOK_BUDGET = 400

interface RecallOutcome {
  hits: number
  lines: string[]
}

/** In-flight execution recalls, keyed by tool callID. */
const executionRecalls = new Map<string, RecallOutcome | null>()

/** Prompt recalls, keyed by sessionID — injected exactly once per prompt. */
const promptRecalls = new Map<string, RecallOutcome>()

/** Execution start timestamps (ms), keyed by tool callID — evidence timing. */
const executionStart = new Map<string, number>()

function hooksEnabled(): boolean {
  return process.env.SCHOOL_HOOKS !== "0"
}

const ROUTE_TIMEOUT_MS = 10000
const ROUTE_STATS_MAX_LINES = 2000

interface RoutingKnobs {
  recall_threshold: number
  hook_limit: number
  hook_budget: number
  hook_timeout_ms: number
  skip_tools: string[]
  force_tools: string[]
}

const DEFAULT_KNOBS: RoutingKnobs = {
  recall_threshold: HOOK_THRESHOLD,
  hook_limit: HOOK_LIMIT,
  hook_budget: HOOK_BUDGET,
  hook_timeout_ms: HOOK_TIMEOUT_MS,
  skip_tools: [],
  force_tools: [],
}

function engageFor(severity: string): string {
  return severity === "light" ? "skill" : "both"
}

function normalizeSeverity(value: unknown): string {
  const s = String(value ?? "").toLowerCase().trim()
  return s === "light" || s === "medium" || s === "high" ? s : "medium"
}

function memoryRoot(worktree: string): string {
  for (const dir of [".school", ".teacher", ".lerev", ".evo"]) {
    const root = resolve(worktree, dir)
    if (fileExists(resolve(root, "memory"))) return root
  }
  return resolve(worktree, ".school")
}

function clampNum(v: unknown, fallback: number, lo: number, hi: number): number {
  if (v == null || typeof v === "boolean") return fallback
  const n = Number(v)
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback
}

function strList(v: unknown): string[] {
  return Array.isArray(v) ? v.map((x) => String(x)) : []
}

let knobsCache: { mtimeMs: number; knobs: RoutingKnobs } | null = null

function readKnobs(worktree: string): RoutingKnobs {
  try {
    const file = resolve(memoryRoot(worktree), "routing.json")
    if (!fileExists(file)) return DEFAULT_KNOBS
    const mtimeMs = statSync(file).mtimeMs
    if (knobsCache && knobsCache.mtimeMs === mtimeMs) return knobsCache.knobs
    const raw = JSON.parse(readFileSync(file, "utf8")) as Record<string, unknown>
    const knobs: RoutingKnobs = {
      recall_threshold: clampNum(raw.recall_threshold, DEFAULT_KNOBS.recall_threshold, 0, 1),
      hook_limit: clampNum(raw.hook_limit, DEFAULT_KNOBS.hook_limit, 1, 50),
      hook_budget: clampNum(raw.hook_budget, DEFAULT_KNOBS.hook_budget, 64, 8000),
      hook_timeout_ms: clampNum(raw.hook_timeout_ms, DEFAULT_KNOBS.hook_timeout_ms, 250, 5000),
      skip_tools: strList(raw.skip_tools),
      force_tools: strList(raw.force_tools),
    }
    knobsCache = { mtimeMs, knobs }
    return knobs
  } catch {
    return DEFAULT_KNOBS
  }
}

function appendEvidence(worktree: string, entry: Record<string, unknown>): void {
  try {
    const root = memoryRoot(worktree)
    if (!fileExists(root)) mkdirSync(root, { recursive: true })
    const file = resolve(root, "routing-stats.jsonl")
    if (fileExists(file)) {
      const lines = readFileSync(file, "utf8").split("\n").filter((l) => l.trim())
      if (lines.length >= ROUTE_STATS_MAX_LINES * 2) {
        writeFileSync(file, lines.slice(-ROUTE_STATS_MAX_LINES).join("\n") + "\n", "utf8")
      }
    }
    appendFileSync(file, JSON.stringify({ ts: new Date().toISOString(), ...entry }) + "\n", "utf8")
  } catch {
    // Evidence tracking must never break execution.
  }
}

function hasMemoryRoot(worktree: string): boolean {
  for (const dir of [".school", ".teacher", ".lerev", ".evo"]) {
    if (fileExists(resolve(worktree, dir, "memory"))) return true
  }
  return false
}

function capMap(map: Map<string, unknown>): void {
  if (map.size > 300) map.clear()
}

/**
 * Build the recall query from the tool name and its salient arguments so
 * retrieval matches exactly what the agent/model is doing right now.
 */
function buildExecutionQuery(toolName: string, args: unknown): string {
  const parts: string[] = [String(toolName).replace(/[_-]+/g, " ")]
  if (args && typeof args === "object") {
    const record = args as Record<string, unknown>
    for (const key of [
      "pattern",
      "query",
      "path",
      "filePath",
      "command",
      "description",
      "content",
      "glob",
      "url",
      "prompt",
      "keyword",
    ]) {
      const value = record[key]
      if (typeof value === "string" && value.trim()) {
        parts.push(value.slice(0, 300))
      }
    }
    if (parts.length === 1) {
      try {
        parts.push(JSON.stringify(args).slice(0, 300))
      } catch {
        // Non-serializable args: the tool name alone still forms a query.
      }
    }
  }
  return parts.join(" ").slice(0, 500)
}

function formatRecallLines(memories: any[]): string[] {
  return memories.map((m: any, i: number) => {
    const conf =
      typeof m.confidence === "number" ? m.confidence.toFixed(2) : "0.00"
    const text = String(m.content ?? "").slice(0, 240)
    return `${i + 1}. (conf=${conf}) ${text}`
  })
}

// Context optimizer: threshold-gated trimming of large tool outputs.
const CTX_THRESHOLD = 1000
const CTX_TIMEOUT_MS = 2000
const CTX_FOOTER_RE = /\[school ctx: \d+→\d+ tokens\]\s*$/;
const CTX_CODE_RE = new RegExp(
  "\\.(py|pyi|js|jsx|mjs|cjs|ts|tsx|go|rs|java|c|h|cpp|cc|cxx|hpp|hh|hxx" +
    "|sh|bash|rb|php|cs|kt|swift|sql|ya?ml|toml|ini|cfg|conf|lua|pl|r|scala" +
    "|ex|exs|hs|clj|cljs|graphql|proto|tf)$",
  "i"
);
const CTX_NOISE = new Set([
  "import", "from", "as", "require", "const", "let", "var", "use",
  "using", "include", "package", "export", "default", "async", "await", "type",
]);

function ctxEnabled(): boolean {
  return process.env.SCHOOL_CTX !== "0";
}
function ctxEstimate(s: string): number {
  return Math.ceil(s.length / 4);
}
function ctxStripFooter(t: string): string {
  return t.replace(CTX_FOOTER_RE, "").replace(/\s+$/, "");
}
function ctxFooter(i: number, o: number): string {
  return `[school ctx: ${i}→${o} tokens]`;
}
function ctxSuffix(filename: string): string {
  const name = filename.toLowerCase();
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot) : "";
}
function ctxCommentPrefix(filename: string): string {
  const ext = ctxSuffix(filename);
  const slashExt = new RegExp(
    "\\.(c|h|cpp|cc|cxx|hpp|hh|hxx|js|jsx|mjs|cjs|ts|tsx|go|rs|java|kt|cs" +
      "|swift|scala|php)$"
  );
  if (slashExt.test(ext)) return "//";
  if (/\.(sql|lua|pl)$/.test(ext)) return "--";
  return "#";
}
const CTX_LICENSE_RE = /copyright|licensed?\s+under|spdx-|all\s+rights\s+reserved/i;
const CTX_IMPORT_RE = new RegExp(
  "^\\s*(import\\b|from\\s+\\S+\\s+import\\b|require\\s*\\(|use\\s|using\\s" +
    "|include\\s|package\\s+\\w|export\\s+.*\\sfrom\\s" +
    "|#\\s*(include|define|if|ifdef|ifndef|pragma)\\b)"
);
const CTX_DECL_RE = new RegExp(
  "^\\s*(?:(?:export|default|async|pub|public|private|protected|static|final" +
    "|abstract|override|virtual)\\s+)*(def|class|function|fn|func|struct|enum" +
    "|trait|impl|interface|type|namespace|module)\\s+[A-Za-z_$]"
);
const CTX_ARROW_RE = /^\s*(export\s+)?(const|let|var)\s+[\w$]+\s*=.*=>/;
const CTX_CONTROL_RE = new RegExp(
  "^\\s*(if|else|elif|for|while|do|switch|case|default|try|except|catch" +
    "|finally|return|yield|break|continue|match|guard|when|raise|throw|assert)\\b"
);
const CTX_CLOSER_RE = /^\s*[}\])]+;?\s*$/;
const CTX_SIG_RE = /^\s*[A-Za-z_][\w.]*\s*:(\s|$)/;
const CTX_SQL_KEEP_RE = new RegExp(
  "^\\s*(select|from|where|group\\s+by|order\\s+by|having|limit|offset|join" +
    "|left|right|inner|outer|full|union|values|insert\\s+into|update" +
    "|delete\\s+from|create|alter|drop|with|returning|set|into|on|begin" +
    "|end|commit|rollback)\\b",
  "i"
);
const CTX_YAML_KEY_RE = /^[A-Za-z_][\w.-]*\s*:/;

function ctxClassify(lines: string[]): string[] {
  const kinds: string[] = [];
  let mode = "";
  for (const line of lines) {
    const stripped = line.trim();
    if (mode) {
      kinds.push("string_cont");
      if (stripped.includes(mode)) mode = "";
      continue;
    }
    if (!stripped) { kinds.push("blank"); continue; }
    if (stripped.startsWith("#") || stripped.startsWith("//") ||
        stripped.startsWith("/*") || stripped.startsWith("*") ||
        stripped.startsWith("--")) { kinds.push("comment"); continue; }
    const dq = (line.match(/"""/g) || []).length;
    const sq = (line.match(/'{3}/g) || []).length;
    const tick = (line.match(/`/g) || []).length;
    if (dq % 2 === 1) { kinds.push("string_first"); mode = '"""'; }
    else if (sq % 2 === 1) { kinds.push("string_first"); mode = "'".repeat(3); }
    else if (tick % 2 === 1) { kinds.push("string_first"); mode = "`"; }
    else kinds.push("code");
  }
  return kinds;
}
function ctxDepthDelta(line: string): number {
  const cleaned = line
    .replace(/"[^"]*"|'[^']*'/g, "")
    .replace(/(#|\/\/|--).*$/, "");
  let d = 0;
  for (const ch of cleaned) {
    if (ch === "(" || ch === "[" || ch === "{") d += 1;
    else if (ch === ")" || ch === "]" || ch === "}") d -= 1;
  }
  return d;
}
function ctxDeclLabel(line: string): string {
  const m = CTX_DECL_RE.exec(line);
  if (m) {
    const rest = line.slice(m.index + m[0].length).replace(/^\s+/, "");
    const nm = /^[A-Za-z_$][\w$]*/.exec(rest);
    const base = nm ? nm[0] : "";
    if (["def", "function", "fn", "func"].includes(m[1]) && base) return base + "()";
    return base || m[1];
  }
  const rest = line.trim().replace(/^export\s+/, "");
  const m2 = /^(?:const|let|var)\s+([\w$]+)/.exec(rest);
  if (m2 && CTX_ARROW_RE.test(line)) return m2[1] + "()";
  return "body";
}
function ctxKeep(line: string, ext: string, kind: string): string {
  if (kind === "comment") return "comment";
  const s = line.trim();
  if (!s) return "blank";
  if (CTX_IMPORT_RE.test(line)) return "import";
  if (/^\s*@\w/.test(line)) return "decorator";
  if (CTX_DECL_RE.test(line) || CTX_ARROW_RE.test(line)) return "decl";
  if (CTX_CONTROL_RE.test(line)) return "control";
  if (CTX_CLOSER_RE.test(line)) return "closer";
  const sqlish = ext === ".sql" || ext === ".graphql" || ext === ".gql";
  if (sqlish && CTX_SQL_KEEP_RE.test(line)) return "sql";
  if ((ext === ".yaml" || ext === ".yml") && CTX_YAML_KEY_RE.test(line)) return "yaml";
  if (CTX_SIG_RE.test(line)) return "sig";
  return "body";
}
function ctxImportNames(line: string): Set<string> {
  const out = new Set<string>();
  for (const w of line.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []) {
    if (!CTX_NOISE.has(w) && w.length > 1) out.add(w);
  }
  return out;
}
function ctxHeuristic(text: string, filename: string): string {
  const ext = ctxSuffix(filename);
  const prefix = ctxCommentPrefix(filename);
  const lines = text.split("\n");
  if (lines.length === 0) return text;
  const kinds = ctxClassify(lines);
  const drop = new Array(lines.length).fill(false);
  let firstBlock = true;
  let headerEnd = 0;
  let i = 0;
  while (i < lines.length) {
    if (kinds[i] !== "comment") { i += 1; continue; }
    const start = i;
    while (i < lines.length && kinds[i] === "comment") i += 1;
    const block = lines.slice(start, i);
    const beforeAllCode = kinds.slice(0, start).every((k) => k !== "code");
    if (firstBlock && beforeAllCode) {
      if (block.some((c) => CTX_LICENSE_RE.test(c))) {
        for (let j = start; j < i; j += 1) drop[j] = true;
      } else {
        let kept = 0;
        for (let j = start; j < i; j += 1) {
          if (kept < 3) kept += 1; else drop[j] = true;
        }
      }
      headerEnd = i;
      firstBlock = false;
    } else {
      for (let j = start; j < i; j += 1) drop[j] = true;
    }
  }
  const refset = new Set<string>();
  lines.forEach((line, idx) => {
    if (kinds[idx] === "code" && !CTX_IMPORT_RE.test(line)) {
      for (const w of line.match(/[A-Za-z_][A-Za-z0-9_]*/g) || []) refset.add(w);
    }
  });
  let keptDepth = 0;
  let label = "body";
  const keep = new Array(lines.length).fill(false);
  lines.forEach((line, idx) => {
    const kind = kinds[idx];
    if (drop[idx]) return;
    if (kind === "blank") { keep[idx] = true; return; }
    if (kind === "string_first") { keep[idx] = true; return; }
    if (kind === "string_cont") return;
    if (kind === "comment") { keep[idx] = headerEnd > 0 && idx < headerEnd; return; }
    const cls = ctxKeep(line, ext, "code");
    if (keptDepth > 0) {
      keep[idx] = true;
      keptDepth += ctxDepthDelta(line);
      return;
    }
    if (["import", "decorator", "decl", "control", "closer", "sql", "yaml", "sig"].includes(cls)) {
      if (cls === "import") {
        let hit = false;
        for (const n of ctxImportNames(line)) if (refset.has(n)) { hit = true; break; }
        if (!hit) return;
      }
      keep[idx] = true;
      keptDepth += ctxDepthDelta(line);
      if (cls === "decl") label = ctxDeclLabel(line);
    }
  });
  const out: string[] = [];
  let run: number[] = [];
  let runLabel = label;
  let pendingBlank = false;
  let prevStringFirst = false;
  const flush = () => {
    if (run.length > 0) {
      if (run.length >= 2) out.push(`${prefix} … ${runLabel} — ${run.length} lines`);
      run = [];
    }
    runLabel = label;
  };
  lines.forEach((line, idx) => {
    if (drop[idx]) return;
    if (!keep[idx]) {
      if (kinds[idx] === "blank") return;
      run.push(idx);
      if (run.length === 1 && prevStringFirst && kinds[idx] === "string_cont") {
        runLabel = "docstring";
      }
      prevStringFirst = false;
      return;
    }
    flush();
    if (kinds[idx] === "blank") {
      if (pendingBlank) return;
      pendingBlank = true;
      out.push("");
    } else {
      pendingBlank = false;
      out.push(line);
      if (kinds[idx] === "decl") label = ctxDeclLabel(line);
      prevStringFirst = kinds[idx] === "string_first";
    }
  });
  flush();
  while (out.length > 0 && out[out.length - 1] === "") out.pop();
  return out.join("\n");
}
function ctxShape(line: string): string {
  const s = line.trim();
  if (!s) return "";
  if (/^"(?:[^"\\]|\\.)*",?$/.test(s) || /^'(?:[^'\\]|\\.)*',?$/.test(s)) return "S";
  if (/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?,?$/.test(s)) return "N";
  if (/^(true|false|null|nil|undefined),?$/i.test(s)) return "K";
  if (s[0] === "{" || s[0] === "[") return "B";
  if (s[0] === "}" || s[0] === "]") return "C";
  if (/^[\w$.-]+(?:\s*:\s*.+)?,?$/.test(s)) return "I";
  return "O";
}
function ctxPayload(text: string): string {
  const prefix = "#";
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;
  let pendingBlank = false;
  while (i < lines.length) {
    if (!lines[i].trim()) { pendingBlank = true; i += 1; continue; }
    const shape = ctxShape(lines[i]);
    let j = i;
    while (j < lines.length && lines[j].trim() && ctxShape(lines[j]) === shape) j += 1;
    const runLen = j - i;
    if (runLen >= 6) {
      if (pendingBlank) { out.push(""); pendingBlank = false; }
      out.push(lines[i]);
      out.push(lines[i + 1]);
      out.push(`${prefix} … repeated block — ${runLen - 2} lines`);
    } else {
      for (let k = i; k < j; k += 1) {
        if (pendingBlank) { out.push(""); pendingBlank = false; }
        out.push(lines[k]);
      }
    }
    i = j;
  }
  return out.join("\n");
}
async function ctxOptimize(
  python: string,
  bridgePath: string,
  text: string,
  filename: string
): Promise<string | null> {
  try {
    if (!ctxEnabled()) return null;
    const body = ctxStripFooter(text);
    const tokensIn = ctxEstimate(body);
    if (tokensIn < CTX_THRESHOLD) return null;
    if (python && bridgePath) {
      try {
        const resp = await invokeBridge(
          python,
          bridgePath,
          { command: "skeleton", text: body, filename },
          CTX_TIMEOUT_MS
        );
        const r = resp as { ok?: boolean; compressed?: boolean; content?: string };
        if (r.ok) {
          return r.compressed === true && typeof r.content === "string"
            ? r.content
            : null;
        }
      } catch {
        /* fall through to TS heuristic */
      }
    }
    const out = CTX_CODE_RE.test(filename)
      ? ctxHeuristic(body, filename)
      : ctxPayload(body);
    const tokensOut = ctxEstimate(out);
    if (tokensOut >= tokensIn) return null;
    return `${out}\n\n${ctxFooter(tokensIn, tokensOut)}`;
  } catch {
    return null;
  }
}

const School: Plugin = async (ctx) => {
  const bridge = await discoverBridge(ctx.worktree)

  if (!bridge) {
    console.error("[school] No bridge found. School tools will return errors.")
    console.error("[school] Run `school install` to set up School globally.")
  }

  const python = bridge?.python ?? ""
  const bridgePath = bridge?.bridgePath ?? ""

  /**
   * Budgeted recall for one execution or prompt through the existing bridge.
   * Returns null whenever School is unavailable, the worktree has no memory,
   * or the bridge fails/times out — callers degrade to a bare marker.
   */
  const recallForExecution = async (
    sessionID: string,
    query: string,
  ): Promise<RecallOutcome | null> => {
    if (!bridge) return null
    const knobs = readKnobs(ctx.worktree)
    if (!query.trim()) return null
    if (!hasMemoryRoot(ctx.worktree)) return null
    const project = ctx.worktree.split(/[/\\]/).pop() || "unknown"
    try {
      const resp = await invokeBridge(
        python,
        bridgePath,
        {
          command: "recall",
          worktree: ctx.worktree,
          agent: "opencode",
          project,
          session: sessionID || undefined,
          query,
          confidence_threshold: knobs.recall_threshold,
          context_budget: knobs.hook_budget,
          limit: knobs.hook_limit,
        },
        knobs.hook_timeout_ms,
      )
      if (!resp.ok) return null
      const memories = (resp as any).memories ?? []
      return { hits: memories.length, lines: formatRecallLines(memories) }
    } catch {
      return null
    }
  }

  interface RouteDecision { severity: string; engage: string; reason: string }

  function routePrompt(situation: string): string {
    return [
      "You are a routing classifier for school tools. Situation: " + situation.slice(0, 200),
      "severity: light (trivial) | medium (real task) | high (critical).",
      "engage: skill for light, both for medium/high (tool and skill together).",
      "Never choose engage none unless the situation is unrelated to tool routing.",
      'Respond ONLY with JSON: {"severity":"...","engage":"...","reason":"..."}',
    ].join("\n")
  }

  function parseRouteDecision(text: string): RouteDecision | null {
    try {
      const match = text.match(/\{[\s\S]*\}/)
      if (!match) return null
      const raw = JSON.parse(match[0]) as Record<string, unknown>
      const severity = normalizeSeverity(raw.severity)
      // engage stays "none" only when the micro-model said so verbatim;
      // anything else falls back to the engageFor mapping (never "none").
      const engage =
        raw.engage === "none" || raw.engage === "skill" || raw.engage === "both"
          ? String(raw.engage)
          : engageFor(severity)
      return { severity, engage, reason: String(raw.reason ?? "").slice(0, 300) }
    } catch {
      return null
    }
  }

  async function microAssess(
    client: unknown,
    directory: string,
    situation: string,
  ): Promise<RouteDecision | null> {
    if (process.env.SCHOOL_ROUTE === "0") return null
    const c = client as any
    if (!c?.session?.create || !c?.session?.prompt) return null
    try {
      const timeout = new Promise<RouteDecision | null>((r) =>
        setTimeout(() => r(null), ROUTE_TIMEOUT_MS),
      )
      const work = (async (): Promise<RouteDecision | null> => {
        const created = await c.session.create({
          body: { title: "school-route" },
          query: { directory },
        })
        const sessionID = created?.data?.id ?? created?.id
        if (!sessionID) return null
        try {
          let model: { providerID: string; modelID: string } | undefined
          try {
            const cfg = await c.config?.get?.()
            const small = cfg?.data?.small_model ?? cfg?.small_model
            if (typeof small === "string" && small.includes("/")) {
              const i = small.indexOf("/")
              model = { providerID: small.slice(0, i), modelID: small.slice(i + 1) }
            }
          } catch {
            // No small_model config — session default is acceptable.
          }
          const resp = await c.session.prompt({
            path: { id: sessionID },
            query: { directory },
            body: {
              parts: [{ type: "text", text: routePrompt(situation) }],
              ...(model ? { model } : {}),
            },
          })
          const parts = resp?.data?.parts ?? resp?.parts ?? []
          const text = parts
            .filter((p: any) => p?.type === "text")
            .map((p: any) => String(p.text ?? ""))
            .join("\n")
          return parseRouteDecision(text)
        } finally {
          try {
            await c.session.delete({ path: { id: sessionID } })
          } catch {
            // Best-effort scratch-session cleanup.
          }
        }
      })()
      return await Promise.race([work, timeout])
    } catch {
      return null
    }
  }

  return {
    tool: {
      school_status: tool({
        description:
          "Check School runtime status: versions and component health " +
          "(V2.5 routing, V2.6 memory, persistence, security). Use when " +
          "School behaves unexpectedly or right after install/upgrade - " +
          "start here, before deeper diagnostics.",
        args: {},
        async execute(_args, context) {
          if (!bridge) {
            return {
              title: "School Status",
              output: "School: unavailable — no bridge found. Run `school install`.",
            }
          }

          const resp = await invokeBridge(python, bridgePath, {
            command: "status",
            worktree: context.worktree,
          })

          if (!resp.ok) {
            return {
              title: "School Status",
              output: `School bridge error: ${(resp as any).error?.message ?? "unknown"}`,
            }
          }

          const components = (resp as any).components ?? {}
          const bridgeVersion = (resp as any).version ?? "unknown"
          const versionMatch = bridgeVersion === SCHOOL_VERSION
          const lines = Object.entries(components).map(
            ([k, v]) => `  ${k}: ${v}`,
          )
          lines.push(`  Plugin version: ${SCHOOL_VERSION}`)
          lines.push(`  Bridge version: ${bridgeVersion}`)
          lines.push(`  Version match: ${versionMatch ? "yes" : "MISMATCH"}`)
          return {
            title: "School Status",
            output: `School V2.6 Component Status:\n${lines.join("\n")}`,
            metadata: {
              ...components,
              compat: {
                plugin: SCHOOL_VERSION,
                bridge: bridgeVersion,
                match: versionMatch,
              },
            },
          }
        },
      }),

      school_remember: tool({
        description:
          "Store an experience or memory in School V2.6 long-term memory; " +
          "returns the stored memory ID. Use when you learned a durable fact " +
          "(decision, fix, preference, outcome) worth keeping across sessions " +
          "- include outcome and observation. Run school_conflict first if " +
          "it may contradict existing memories.",
        args: {
          content: tool.schema
            .string()
            .describe("The experience or memory content to store"),
          outcome: tool.schema
            .enum(["SUCCESS", "FAILURE", "NEUTRAL", "MIXED"])
            .optional()
            .describe("Outcome of the experience (default: NEUTRAL)"),
          project: tool.schema
            .string()
            .optional()
            .describe("Project scope identifier (default: from workspace)"),
          session: tool.schema
            .string()
            .optional()
            .describe("Session scope identifier (default: from runtime context)"),
          observation: tool.schema
            .string()
            .optional()
            .describe("What was observed (optional, defaults to content)"),
          action: tool.schema
            .string()
            .optional()
            .describe("What action was taken (optional)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Remember",
              output: "School: unavailable — no bridge found. Run `school install`.",
            }
          }

          const projectId = args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown"
          const sessionId = args.session ?? context.sessionID

          const resp = await invokeBridge(python, bridgePath, {
            command: "remember",
            worktree: context.worktree,
            agent: "opencode",
            project: projectId,
            session: sessionId,
            content: args.content,
            outcome: args.outcome ?? "NEUTRAL",
            observation: args.observation,
            action: args.action,
          })

          if (!resp.ok) {
            const err = (resp as any).error ?? {}
            return {
              title: "School Remember — Failed",
              output: `Error [${err.type}]: ${err.message}`,
            }
          }

          const scope = (resp as any).scope ?? {}
          const scopeStr = [
            scope.agent && `agent=${scope.agent}`,
            scope.project && `project=${scope.project}`,
            scope.session && `session=${scope.session}`,
          ]
            .filter(Boolean)
            .join(", ")

          return {
            title: "School Remember",
            output: [
              `Memory stored successfully.`,
              `  ID: ${(resp as any).id}`,
              `  Scope: ${scopeStr}`,
              `  Outcome: ${(resp as any).outcome}`,
            ].join("\n"),
            metadata: {
              id: (resp as any).id,
              scope: (resp as any).scope,
              outcome: (resp as any).outcome,
            },
          }
        },
      }),

      school_recall: tool({
        description:
          "Retrieve memories from School V2.6 long-term memory, scoped to " +
          "project/session. Use when starting a task or answering " +
          "project-specific questions: one short query first - the cheapest " +
          "way to load prior context. Prefer school_search only if recall " +
          "misses.",
        args: {
          query: tool.schema
            .string()
            .describe("Search query to find relevant memories"),
          confidence_threshold: tool.schema
            .number()
            .min(0)
            .max(1)
            .optional()
            .describe("Minimum confidence threshold (0.0-1.0, default: 0.0)"),
          context_budget: tool.schema
            .number()
            .min(0)
            .optional()
            .describe("Maximum tokens for returned memories (default: 2000)"),
          limit: tool.schema
            .number()
            .min(0)
            .max(100)
            .optional()
            .describe("Maximum memories to return (default: 10)"),
          project: tool.schema
            .string()
            .optional()
            .describe("Project scope (default: from workspace)"),
          session: tool.schema
            .string()
            .optional()
            .describe("Session scope (default: from runtime context)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Recall",
              output: "School: unavailable — no bridge found. Run `school install`.",
            }
          }

          const projectId = args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown"
          const sessionId = args.session ?? context.sessionID

          const resp = await invokeBridge(python, bridgePath, {
            command: "recall",
            worktree: context.worktree,
            agent: "opencode",
            project: projectId,
            session: sessionId,
            query: args.query,
            confidence_threshold: args.confidence_threshold ?? 0.0,
            context_budget: args.context_budget ?? 2000,
            limit: args.limit ?? 10,
          })

          if (!resp.ok) {
            const err = (resp as any).error ?? {}
            return {
              title: "School Recall — Failed",
              output: `Error [${err.type}]: ${err.message}`,
            }
          }

          const memories = (resp as any).memories ?? []
          if (memories.length === 0) {
            return {
              title: "School Recall",
              output: "No matching memories found.",
              metadata: { total: 0 },
            }
          }

          const lines = memories.map(
            (m: any, i: number) =>
              `${i + 1}. [${m.kind}] (conf=${m.confidence.toFixed(2)}) ${m.content}`,
          )

          return {
            title: "School Recall",
            output: [
              `Found ${(resp as any).total} matching memories (${memories.length} returned, cost=${(resp as any).context_cost} tokens):`,
              "",
              ...lines,
              "",
              `Provenance: ${memories.map((m: any) => m.id).join(", ")}`,
            ].join("\n"),
            metadata: {
              memories: memories.map((m: any) => ({
                id: m.id,
                kind: m.kind,
                confidence: m.confidence,
                content: m.content,
              })),
              total: (resp as any).total,
              truncated: (resp as any).truncated,
              context_cost: (resp as any).context_cost,
            },
          }
        },
      }),

      school_learn: tool({
        description:
          "Record a learning through School's learn bridge; returns the " +
          "stored memory ID. Use after a meaningful outcome (what worked or " +
          "failed). Stores to the same memory as school_remember - prefer " +
          "this for lessons with an outcome, school_remember for plain facts.",
        args: {
          content: tool.schema
            .string()
            .describe("The learning content to record"),
          outcome: tool.schema
            .enum(["SUCCESS", "FAILURE", "NEUTRAL", "MIXED"])
            .optional()
            .describe("Outcome of the learning (default: NEUTRAL)"),
          project: tool.schema
            .string()
            .optional()
            .describe("Project scope identifier (default: from workspace)"),
          session: tool.schema
            .string()
            .optional()
            .describe("Session scope identifier (default: from runtime context)"),
          observation: tool.schema
            .string()
            .optional()
            .describe("What was observed (optional, defaults to content)"),
          action: tool.schema
            .string()
            .optional()
            .describe("What action was taken (optional)"),
          tags: tool.schema
            .array(tool.schema.string())
            .optional()
            .describe("Tags for filtering this learning (optional)"),
          confidence: tool.schema
            .number()
            .min(0)
            .max(1)
            .optional()
            .describe("Confidence in this learning [0,1] (default: 0.5)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return {
              title: "School Learn",
              output: "School: unavailable — no bridge found. Run `school install`.",
            }
          }

          const projectId = args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown"
          const sessionId = args.session ?? context.sessionID

          const resp = await invokeBridge(python, bridgePath, {
            command: "learn",
            worktree: context.worktree,
            agent: "opencode",
            project: projectId,
            session: sessionId,
            content: args.content,
            outcome: args.outcome ?? "NEUTRAL",
            observation: args.observation,
            action: args.action,
            tags: args.tags ?? [],
            confidence: args.confidence ?? 0.5,
          })

          if (!resp.ok) {
            const err = (resp as any).error ?? {}
            const errors = (resp as any).errors ?? []
            const detail = err.message ?? errors.join("; ") ?? "unknown error"
            return {
              title: "School Learn — Failed",
              output: `Error [${err.type ?? "orchestrator"}]: ${detail}`,
            }
          }

          const result = (resp as any).result ?? resp
          return {
            title: "School Learn",
            output: [
              "Learning recorded.",
              `  ID: ${result.experience_id ?? (resp as any).id ?? "unknown"}`,
              `  Stored: ${result.stored ?? true}`,
            ].join("\n"),
            metadata: {
              result,
              scope: { project: projectId, session: sessionId },
            },
          }
        },
      }),

      school_conflict: tool({
        description:
          "Detect conflicts between incoming content and stored memories, " +
          "with similarity scores. Use BEFORE saving new information that " +
          "might contradict what School already knows (before " +
          "school_remember when the topic changed).",
        args: {
          content: tool.schema
            .string()
            .describe("New content to check for conflicts"),
          project: tool.schema
            .string()
            .optional()
            .describe("Project scope"),
          session: tool.schema
            .string()
            .optional()
            .describe("Session scope"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Conflict", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "conflict",
            worktree: context.worktree,
            agent: "opencode",
            project: args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown",
            session: args.session ?? context.sessionID,
            content: args.content,
          })
          if (!resp.ok) {
            return { title: "School Conflict — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const conflicts = (resp as any).result?.conflicts ?? (resp as any).conflicts ?? []
          if (conflicts.length === 0) {
            return { title: "School Conflict", output: "No conflicts detected." }
          }
          const lines = conflicts.map((c: any, i: number) =>
            `${i + 1}. [${c.type ?? "unknown"}] sim=${(c.similarity ?? 0).toFixed(2)}: ${(c.content ?? "").slice(0, 100)}`
          )
          return {
            title: "School Conflict",
            output: `Found ${conflicts.length} conflict(s):\n${lines.join("\n")}`,
            metadata: { conflicts },
          }
        },
      }),

      school_confidence: tool({
        description:
          "Score how well-supported a claim or memory is (0-1 score, band, " +
          "factors). Use when about to assert something from memory and you " +
          "need to know how solid it is - a low score means verify before " +
          "relying.",
        args: {
          content: tool.schema.string().describe("Content to evaluate"),
          prediction: tool.schema.string().optional().describe("Predicted output"),
          evidence_count: tool.schema.number().optional().describe("Number of supporting evidence (default: 1)"),
          conflict_count: tool.schema.number().optional().describe("Number of conflicts (default: 0)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Confidence", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "confidence",
            worktree: context.worktree,
            content: args.content,
            prediction: args.prediction ?? "",
            evidence_count: args.evidence_count ?? 1,
            conflict_count: args.conflict_count ?? 0,
          })
          if (!resp.ok) {
            return { title: "School Confidence — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const result = (resp as any).result ?? resp
          return {
            title: "School Confidence",
            output: `Confidence: ${(result.confidence ?? 0).toFixed(3)} [${result.band ?? "unknown"}]`,
            metadata: result,
          }
        },
      }),

      school_search: tool({
        description:
          "Semantic TF-IDF search across stored memories, ranked. Use when " +
          "school_recall's scoped query misses or you want broad exploration " +
          "by topic; recall is the better first stop for specific questions.",
        args: {
          query: tool.schema.string().describe("Search query"),
          limit: tool.schema.number().min(1).max(100).optional().describe("Max results (default: 10)"),
          project: tool.schema.string().optional().describe("Project scope"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Search", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "search",
            worktree: context.worktree,
            agent: "opencode",
            project: args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown",
            query: args.query,
            limit: args.limit ?? 10,
          })
          if (!resp.ok) {
            return { title: "School Search — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const memories = (resp as any).result?.memories ?? (resp as any).memories ?? []
          if (memories.length === 0) {
            return { title: "School Search", output: "No matching memories found." }
          }
          const lines = memories.map((m: any, i: number) =>
            `${i + 1}. [${m.kind}] (conf=${(m.confidence ?? 0).toFixed(2)}) ${m.content}`
          )
          return {
            title: "School Search",
            output: `Found ${memories.length} result(s):\n${lines.join("\n")}`,
            metadata: { memories },
          }
        },
      }),

      school_deduplicate: tool({
        description:
          "Find (and optionally merge) duplicate or near-duplicate memories, " +
          "with similarity scores. Use for occasional maintenance when recall " +
          "returns repetitive results - not needed per task.",
        args: {
          content: tool.schema.string().describe("Content to check for duplicates"),
          project: tool.schema.string().optional().describe("Project scope"),
          threshold: tool.schema.number().optional().describe("Similarity threshold (0-1, default: 0.85)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Deduplicate", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "deduplicate",
            worktree: context.worktree,
            agent: "opencode",
            project: args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown",
            content: args.content,
            threshold: args.threshold ?? 0.85,
          })
          if (!resp.ok) {
            return { title: "School Deduplicate — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const result = (resp as any).result ?? resp
          const dups = result.duplicates ?? []
          if (dups.length === 0) {
            return { title: "School Deduplicate", output: "No duplicates found." }
          }
          const lines = dups.map((d: any, i: number) =>
            `${i + 1}. sim=${(d.similarity ?? 0).toFixed(2)}: ${(d.content ?? "").slice(0, 100)}`
          )
          return {
            title: "School Deduplicate",
            output: `Found ${dups.length} duplicate(s):\n${lines.join("\n")}`,
            metadata: { duplicates: dups },
          }
        },
      }),

      school_knowledge: tool({
        description:
          "Extract recurring learnings and knowledge patterns from " +
          "consolidated memories. Use for occasional synthesis of what keeps " +
          "reappearing - not a per-task tool.",
        args: {
          project: tool.schema.string().optional().describe("Project scope"),
          session: tool.schema.string().optional().describe("Session scope"),
          min_occurrences: tool.schema.number().optional().describe("Minimum occurrences to extract (default: 3)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Knowledge", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "knowledge",
            worktree: context.worktree,
            agent: "opencode",
            project: args.project ?? context.worktree.split(/[/\\]/).pop() ?? "unknown",
            session: args.session ?? context.sessionID,
            min_occurrences: args.min_occurrences ?? 3,
          })
          if (!resp.ok) {
            return { title: "School Knowledge — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const result = (resp as any).result ?? resp
          return {
            title: "School Knowledge",
            output: `Knowledge extraction: promoted=${result.promoted_count ?? 0}, retained=${result.retained_count ?? 0}`,
            metadata: result,
          }
        },
      }),

      school_lifecycle: tool({
        description:
          "Manage memory lifecycle: score, decay, promote, or archive " +
          "(action required). Use for maintenance: promote durable memories, " +
          "decay or archive stale ones - not needed during normal recall/store " +
          "flows.",
        args: {
          action: tool.schema
            .enum(["score", "decay", "promote", "archive"])
            .describe("Lifecycle action to perform"),
          memory_id: tool.schema
            .string()
            .optional()
            .describe("Memory ID to operate on (required for promote/archive)"),
          project: tool.schema.string().optional().describe("Project scope"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Lifecycle", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "lifecycle",
            worktree: context.worktree,
            action: args.action,
            memory_id: args.memory_id ?? "",
            project: args.project ?? "",
          })
          if (!resp.ok) {
            return { title: "School Lifecycle — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const result = (resp as any).result ?? resp
          return {
            title: "School Lifecycle",
            output: `Action '${args.action}' completed: ${JSON.stringify(result)}`,
            metadata: result,
          }
        },
      }),

      school_diagnose: tool({
        description:
          "Full system diagnostics: health, stats, pipeline. Use when " +
          "school_status suggests trouble or recall results look wrong - " +
          "deeper than status, heavier to run.",
        args: {
          detail: tool.schema
            .enum(["summary", "full"])
            .optional()
            .describe("Detail level (default: summary)"),
        },
        async execute(args, context) {
          if (!bridge) {
            return { title: "School Diagnose", output: "School: unavailable." }
          }
          const resp = await invokeBridge(python, bridgePath, {
            command: "diagnose",
            worktree: context.worktree,
            detail: args.detail ?? "summary",
          })
          if (!resp.ok) {
            return { title: "School Diagnose — Failed", output: `Error: ${(resp as any).error?.message}` }
          }
          const result = (resp as any).result ?? resp
          const health = result.health ?? {}
          const lines = Object.entries(health).map(([k, v]) => `  ${k}: ${v}`)
          return {
            title: "School Diagnose",
            output: `System Health:\n${lines.join("\n")}`,
            metadata: result,
          }
        },
      }),

      school_route: tool({
        description:
          "Assess how much School routing machinery a situation needs " +
          "(mode assess: tiny real model call -> engage skill or both) or " +
          "store a routing lesson (mode report: what worked where, tagged " +
          "and retrievable). Use when starting non-trivial work or after a " +
          "tool call taught you something about routing - for anything, " +
          "not only coding.",
        args: {
          mode: tool.schema
            .string()
            .describe('Mode: "assess" or "report"'),
          situation: tool.schema
            .string()
            .describe("What is happening (max 500 chars)."),
          severity: tool.schema
            .string()
            .optional()
            .describe("assess fallback: light | medium | high"),
          lesson: tool.schema
            .string()
            .optional()
            .describe("report: the routing lesson to store."),
          outcome: tool.schema
            .string()
            .optional()
            .describe("report: helpful | useless | neutral"),
        },
        async execute(args, context) {
          const mode = String(args.mode ?? "").trim()
          const situation = String(args.situation ?? "").slice(0, 500)
          if (!situation.trim()) {
            return {
              title: "School Route — Failed",
              output: "Error: situation is required (max 500 chars).",
              metadata: { engagement: "failed" },
            }
          }

          if (mode === "report") {
            if (!bridge) {
              return {
                title: "School Route — Failed",
                output: "School: unavailable — no bridge found. Run `school install`.",
                metadata: { engagement: "failed" },
              }
            }
            const lesson = String(args.lesson ?? "").trim().slice(0, 1000)
            if (!lesson) {
              return {
                title: "School Route — Failed",
                output: "Error: lesson is required for mode=report.",
                metadata: { engagement: "failed" },
              }
            }
            const outcome =
              args.outcome === "useless" || args.outcome === "neutral"
                ? String(args.outcome)
                : "helpful"
            const resp = await invokeBridge(python, bridgePath, {
              command: "remember",
              worktree: context.worktree,
              agent: "opencode",
              project: context.worktree.split(/[/\\]/).pop() || "unknown",
              session: context.sessionID || undefined,
              content: `Routing lesson (${outcome}): ${lesson}`,
              observation: situation || undefined,
              action: lesson,
              outcome:
                outcome === "helpful"
                  ? "SUCCESS"
                  : outcome === "useless"
                    ? "FAILURE"
                    : "NEUTRAL",
              tags: ["routing", outcome],
            })
            if (hooksEnabled()) {
              appendEvidence(context.worktree, {
                kind: "report",
                tool: "school_route",
                ms: 0,
                ok: Boolean(resp.ok),
                outcome,
              })
            }
            if (!resp.ok) {
              const err = (resp as any).error ?? {}
              return {
                title: "School Route — Failed",
                output: `Error [${err.type}]: ${err.message}`,
                metadata: { engagement: "failed" },
              }
            }
            return {
              title: "School Route — Reported",
              output:
                `Stored routing lesson (id ${(resp as any).id ?? "?"}, ` +
                `outcome ${outcome}).`,
              metadata: { engagement: "reported" },
            }
          }

          if (mode !== "assess") {
            return {
              title: "School Route — Failed",
              output: 'Error: mode must be "assess" or "report".',
              metadata: { engagement: "failed" },
            }
          }

          let decision = await microAssess(ctx.client, ctx.directory, situation)
          let source = "micro-model"
          if (!decision) {
            const severity = normalizeSeverity(args.severity)
            decision = {
              severity,
              engage: engageFor(severity),
              reason: args.severity
                ? "self-rated (severity argument)"
                : "fallback default (micro-call unavailable)",
            }
            source = process.env.SCHOOL_ROUTE === "0"
              ? "self-rated"
              : args.severity
                ? "self-rated"
                : "fallback"
          }
          if (hooksEnabled()) {
            appendEvidence(context.worktree, {
              kind: "assess",
              tool: "school_route",
              ms: 0,
              ok: true,
              severity: decision.severity,
              engage: decision.engage,
            })
          }
          const nextStep =
            decision.engage === "none"
              ? "\nNo routing machinery needed for this situation."
              : "\nNext: load the `school-routing` skill (skill tool) " +
                "so the tool and skill work together."
          return {
            title: `School Route — ${decision.severity}`,
            output:
              JSON.stringify({ source, ...decision }, null, 2) + nextStep,
            metadata: { engagement: decision.engage },
          }
        },
      }),

      school_route_stats: tool({
        description:
          "Aggregated routing evidence: per-tool call counts and average " +
          "durations, recent assess/report entries, current knobs, and " +
          "recent routing lessons. Use before adjusting how School routes, " +
          "or when the routing skill asks for current numbers - for " +
          "anything, not only coding.",
        args: {
          limit: tool.schema
            .number()
            .min(1)
            .max(100)
            .optional()
            .describe("Recent entries/lessons to include (default 20)"),
        },
        async execute(args, context) {
          const limit = Math.min(Number(args.limit ?? 20) || 20, 100)
          const file = resolve(memoryRoot(context.worktree), "routing-stats.jsonl")
          let entries: Record<string, unknown>[] = []
          if (fileExists(file)) {
            try {
              entries = readFileSync(file, "utf8")
                .split("\n")
                .filter((l) => l.trim())
                .map((l) => JSON.parse(l))
            } catch {
              entries = []
            }
          }
          const perTool: Record<string, { calls: number; total_ms: number }> = {}
          for (const e of entries) {
            if (e.kind !== "exec") continue
            const t = String(e.tool)
            const cur = perTool[t] ?? { calls: 0, total_ms: 0 }
            cur.calls += 1
            cur.total_ms += Number(e.ms ?? 0)
            perTool[t] = cur
          }
          const aggregates: Record<string, { calls: number; avg_ms: number }> = {}
          for (const [t, v] of Object.entries(perTool)) {
            aggregates[t] = {
              calls: v.calls,
              avg_ms: v.calls ? Math.round(v.total_ms / v.calls) : 0,
            }
          }
          let lessons: unknown[] = []
          if (bridge) {
            try {
              const resp = await invokeBridge(
                python,
                bridgePath,
                {
                  command: "recall",
                  worktree: context.worktree,
                  agent: "opencode",
                  project: context.worktree.split(/[/\\]/).pop() || "unknown",
                  query: "routing lesson",
                  confidence_threshold: 0,
                  context_budget: 1500,
                  limit: Math.min(limit, 10),
                },
                HOOK_TIMEOUT_MS,
              )
              if (resp.ok) lessons = (resp as any).memories ?? []
            } catch {
              lessons = []
            }
          }
          const knobs = readKnobs(context.worktree)
          const last = entries.length ? entries[entries.length - 1] : null
          return {
            title: "School Routing Stats",
            output: JSON.stringify(
              {
                last_activity: last ? last.ts : null,
                recent: entries.slice(-limit),
                aggregates,
                knobs,
                lessons: lessons.map((m: any) => ({
                  id: m.experience_id ?? m.id,
                  content: String(m.content ?? "").slice(0, 300),
                })),
              },
              null,
              2,
            ),
            metadata: { engagement: "stats" },
          }
        },
      }),
    },

    "tool.execute.before": async (input, output) => {
      try {
        if (!hooksEnabled()) return
        const knobs = readKnobs(ctx.worktree)
        if (knobs.skip_tools.includes(input.tool) && !knobs.force_tools.includes(input.tool)) {
          executionRecalls.set(input.callID, null)
          return
        }
        executionStart.set(input.callID, Date.now())
        const query = buildExecutionQuery(input.tool, output.args)
        const rec = await recallForExecution(input.sessionID, query)
        capMap(executionRecalls)
        executionRecalls.set(input.callID, rec)
      } catch {
        // Hooks must never break tool execution — degrade to no context.
        executionRecalls.set(input.callID, null)
      }
    },

    "tool.execute.after": async (input, output) => {
      try {
        if (!hooksEnabled()) return
        if (typeof output.output === "string") {
          const raw = output.output;
          const isErr =
            raw.startsWith("Error") || (output as { isError?: boolean }).isError === true;
          if (!isErr && ctxEstimate(ctxStripFooter(raw)) >= CTX_THRESHOLD) {
            const anyOut = output as { args?: { filePath?: string; path?: string } };
            const filename = String(anyOut.args?.filePath ?? anyOut.args?.path ?? "");
            const optimized = await ctxOptimize(python, bridgePath, raw, filename);
            if (optimized !== null) output.output = optimized;
          }
        }
        const rec = executionRecalls.get(input.callID) ?? null
        executionRecalls.delete(input.callID)
        // Visible marker on EVERY execution — hits, zero hits, and degraded.
        const marker = rec ? ` · school: ${rec.hits}` : " · school: –"
        const started = executionStart.get(input.callID) ?? Date.now()
        executionStart.delete(input.callID)
        const meta = (output as any).metadata as Record<string, unknown> | undefined
        const engagement = meta && typeof meta.engagement === "string" ? meta.engagement : ""
        const routingSuffix = engagement ? ` · routing: ${engagement}` : ""
        output.title = `${output.title || input.tool}${marker}${routingSuffix}`
        appendEvidence(ctx.worktree, {
          kind: "exec",
          tool: input.tool,
          ms: Date.now() - started,
          ok: typeof output.output === "string" && !output.output.startsWith("Error"),
          hits: rec ? rec.hits : null,
        })
        if (rec && rec.hits > 0 && typeof output.output === "string") {
          const block = `[school context]\n${rec.lines.join("\n")}\n[/school]`
          output.output = `${output.output}\n\n${block}`
        }
      } catch {
        // School visibility must never break tool execution.
      }
    },

    "chat.message": async (input, output) => {
      try {
        if (!hooksEnabled()) return
        const text = (output.parts ?? [])
          .filter((p: any) => p && p.type === "text")
          .map((p: any) => String(p.text ?? ""))
          .join(" ")
          .slice(0, 500)
        if (!text.trim()) return
        const rec = await recallForExecution(input.sessionID, text)
        if (rec && rec.hits > 0) {
          capMap(promptRecalls)
          promptRecalls.set(input.sessionID, rec)
        }
      } catch {
        // Prompt recall is best-effort.
      }
    },

    "experimental.chat.messages.transform": async (_input, output) => {
      try {
        const messages = output.messages ?? []
        if (!messages.length) return
        const last = messages[messages.length - 1]
        const info: any = last.info
        // Inject only at prompt time (turn starts with a user message),
        // exactly once per prompt, budgeted to the stashed recall.
        if (!info || info.role !== "user" || !info.sessionID) return
        const rec = promptRecalls.get(info.sessionID)
        if (!rec) return
        promptRecalls.delete(info.sessionID)
        last.parts.push({
          id: `school-context-${info.id}`,
          sessionID: info.sessionID,
          messageID: info.id,
          type: "text",
          synthetic: true,
          text: `[school context]\n${rec.lines.join("\n")}\n[/school]`,
        })
      } catch {
        // Context injection is best-effort.
      }
    },
  }
}

export default School
'''

TS_PLUGIN_SOURCE = _TS_PLUGIN_TEMPLATE.replace("__SCHOOL_VERSION__", _SCHOOL_VERSION)
