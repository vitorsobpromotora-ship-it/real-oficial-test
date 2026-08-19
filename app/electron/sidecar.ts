/**
 * Ciclo de vida do motor (sidecar Python/FastAPI):
 * porta livre → spawn → poll /health → ler token → shutdown gracioso.
 */
import { type ChildProcess, spawn } from "node:child_process";
import * as fs from "node:fs";
import * as net from "node:net";
import * as path from "node:path";

export interface EngineInfo {
  baseUrl: string;
  token: string;
  port: number;
}

const PORT_RANGE_START = 8756;
const PORT_RANGE_END = 8856;
const HEALTH_TIMEOUT_MS = 60_000;

let child: ChildProcess | null = null;
let info: EngineInfo | null = null;

function tryBind(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once("error", () => resolve(false));
    srv.once("listening", () => srv.close(() => resolve(true)));
    srv.listen(port, "127.0.0.1");
  });
}

export async function pickPort(): Promise<number> {
  for (let p = PORT_RANGE_START; p <= PORT_RANGE_END; p++) {
    if (await tryBind(p)) return p;
  }
  throw new Error("Nenhuma porta livre entre 8756 e 8856");
}

async function waitHealth(baseUrl: string): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${baseUrl}/health`, { signal: AbortSignal.timeout(1500) });
      if (res.ok) return;
    } catch {
      /* motor ainda subindo */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("O motor não respondeu ao health check em 60s");
}

interface SpawnOptions {
  resourcesPath: string;
  userDataDir: string;
  isDev: boolean;
  appRoot: string;
}

export async function startSidecar(opts: SpawnOptions): Promise<EngineInfo> {
  const externalUrl = process.env.REAL_OFICIAL_ENGINE_URL;
  const dataDir = process.env.REAL_OFICIAL_DATA_DIR
    ?? path.join(opts.userDataDir, "engine-data");
  if (externalUrl) {
    // Motor já rodando (dev avançado): só descobre o token.
    const token = fs.readFileSync(path.join(dataDir, "api_token"), "utf-8").trim();
    info = { baseUrl: externalUrl, token, port: Number(new URL(externalUrl).port) };
    return info;
  }

  const port = await pickPort();
  fs.mkdirSync(dataDir, { recursive: true });

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    REAL_OFICIAL_DATA_DIR: dataDir,
    PYTHONUNBUFFERED: "1",
  };
  const ffmpegDir = path.join(opts.resourcesPath, "ffmpeg");
  if (fs.existsSync(ffmpegDir)) env.REAL_OFICIAL_FFMPEG_DIR = ffmpegDir;

  const args = ["--port", String(port), "--parent-pid", String(process.pid)];
  if (opts.isDev) {
    const engineDir = path.join(opts.appRoot, "..", "engine");
    const python = process.env.REAL_OFICIAL_PYTHON
      ?? path.join(engineDir, ".venv", process.platform === "win32" ? "Scripts" : "bin",
        process.platform === "win32" ? "python.exe" : "python");
    child = spawn(python, ["-m", "app.main", ...args], { cwd: engineDir, env, stdio: "pipe" });
  } else {
    const exe = path.join(opts.resourcesPath, "engine",
      process.platform === "win32" ? "real-oficial-engine.exe" : "real-oficial-engine");
    child = spawn(exe, args, { env, stdio: "pipe" });
  }
  child.stdout?.on("data", (d) => console.log(`[engine] ${d}`.trimEnd()));
  child.stderr?.on("data", (d) => console.error(`[engine] ${d}`.trimEnd()));
  child.on("exit", (code) => console.log(`[engine] processo saiu com código ${code}`));

  const baseUrl = `http://127.0.0.1:${port}`;
  await waitHealth(baseUrl);
  const token = fs.readFileSync(path.join(dataDir, "api_token"), "utf-8").trim();
  info = { baseUrl, token, port };
  return info;
}

export function getEngineInfo(): EngineInfo | null {
  return info;
}

export async function stopSidecar(): Promise<void> {
  if (!child) return;
  const proc = child;
  child = null;
  try {
    if (info) {
      await fetch(`${info.baseUrl}/system/shutdown`, {
        method: "POST",
        headers: { Authorization: `Bearer ${info.token}` },
        signal: AbortSignal.timeout(2500),
      });
    }
  } catch {
    /* segue para o kill */
  }
  await new Promise((r) => setTimeout(r, 1500));
  if (proc.exitCode === null) {
    proc.kill(process.platform === "win32" ? undefined : "SIGTERM");
    await new Promise((r) => setTimeout(r, 1500));
    if (proc.exitCode === null) proc.kill("SIGKILL");
  }
}
