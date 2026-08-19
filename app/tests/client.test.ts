import { beforeEach, describe, expect, it, vi } from "vitest";

describe("api client", () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.setItem("engine_url", "http://127.0.0.1:9999");
    localStorage.setItem("engine_token", "tok-teste");
  });

  it("envia Authorization Bearer e monta a URL do motor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const { get } = await import("../src/api/client");
    const res = await get<{ ok: boolean }>("/api/v1/projects");
    expect(res.ok).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://127.0.0.1:9999/api/v1/projects");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-teste");
  });

  it("lança ApiError com detail do backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({ detail: "Token inválido" }), { status: 401 }))));
    const { get, ApiError } = await import("../src/api/client");
    await expect(get("/api/v1/projects")).rejects.toThrowError(ApiError);
    await expect(get("/api/v1/projects")).rejects.toThrow("Token inválido");
  });

  it("mediaUrl anexa token em query", async () => {
    const { mediaUrl } = await import("../src/api/client");
    const url = await mediaUrl("/api/v1/media/abc/file");
    expect(url).toBe("http://127.0.0.1:9999/api/v1/media/abc/file?token=tok-teste");
  });
});
