import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, get, post } from "../api/client";
import type { Agent, Settings } from "../api/types";

const CUSTO_POR_HORA: Record<string, string> = {
  "claude-opus-5": "≈ US$ 0,30–0,60 por hora de vídeo (máxima qualidade)",
  "claude-sonnet-5": "≈ US$ 0,15–0,35 por hora de vídeo (equilíbrio)",
  "claude-haiku-4-5": "≈ US$ 0,05–0,10 por hora de vídeo (econômico)",
  "gpt-5.1": "≈ US$ 0,10–0,25 por hora de vídeo",
  "gpt-5-mini": "≈ US$ 0,02–0,06 por hora de vídeo (econômico)",
};

const AGENTES: { id: Agent; nome: string; desc: string }[] = [
  { id: "claude", nome: "Claude (Anthropic)", desc: "análise editorial padrão" },
  { id: "gpt", nome: "GPT (OpenAI)", desc: "análise editorial padrão" },
  { id: "local", nome: "Análise local", desc: "sem IA, sem custo" },
];

export default function SettingsPage() {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => get<Settings>("/api/v1/settings") });
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [form, setForm] = useState<Partial<Settings>>({});
  const [testeClaude, setTesteClaude] = useState("");
  const [testeGpt, setTesteGpt] = useState("");
  const [salvoMsg, setSalvoMsg] = useState("");

  useEffect(() => {
    if (settings.data) setForm(settings.data);
  }, [settings.data]);

  const salvar = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Settings>("/api/v1/settings", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      setAnthropicKey("");
      setOpenaiKey("");
      setSalvoMsg("Configurações salvas.");
      setTimeout(() => setSalvoMsg(""), 2500);
    },
    onError: (e: Error) => {
      setSalvoMsg(`Falha ao salvar: ${e.message}`);
      setTimeout(() => setSalvoMsg(""), 6000);
    },
  });

  const testar = useMutation({
    mutationFn: (p: { provider: "claude" | "gpt"; key: string }) =>
      post<{ ok: boolean; detail: string }>("/api/v1/settings/test-ai",
        p.key ? { provider: p.provider, api_key: p.key } : { provider: p.provider }),
    onSuccess: (r, p) => {
      const setMsg = p.provider === "claude" ? setTesteClaude : setTesteGpt;
      if (r.ok && p.key.trim()) {
        // Teste passou com uma chave digitada → já persiste (à prova de esquecimento).
        salvar.mutate(p.provider === "claude"
          ? { anthropic_api_key: p.key.trim() }
          : { openai_api_key: p.key.trim() });
        setMsg(`✓ ${r.detail} — chave salva.`);
      } else {
        setMsg(r.ok ? `✓ ${r.detail}` : `✗ ${r.detail}`);
      }
    },
    onError: (e: Error, p) =>
      (p.provider === "claude" ? setTesteClaude : setTesteGpt)(`✗ ${e.message}`),
  });

  function set<K extends keyof Settings>(k: K, v: Settings[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function submit() {
    const body: Record<string, unknown> = {
      default_agent: form.default_agent,
      claude_model: form.claude_model,
      claude_fallback_model: form.claude_fallback_model ?? "claude-sonnet-5",
      openai_model: form.openai_model ?? "gpt-5.1",
      openai_fallback_model: form.openai_fallback_model ?? "",
      whisper_model: form.whisper_model,
      output_dir: form.output_dir ?? "",
      use_batches: form.use_batches,
      max_cuts_per_30min: form.max_cuts_per_30min,
      censor_enabled: form.censor_enabled,
      censor_mode: form.censor_mode,
      censor_extra_words: form.censor_extra_words,
    };
    if (anthropicKey.trim()) body.anthropic_api_key = anthropicKey.trim();
    if (openaiKey.trim()) body.openai_api_key = openaiKey.trim();
    salvar.mutate(body);
  }

  if (!settings.data) return <div className="empty">Carregando…</div>;
  const s = settings.data;

  return (
    <div style={{ maxWidth: 780 }}>
      <div className="pagehead"><h1>Configurações</h1></div>

      <div className="card">
        <h3>Agente de IA padrão</h3>
        <div className="sub">Quem analisa e escolhe os cortes quando você não escolher na
        importação. A escolha também aparece a cada processamento.</div>
        <div className="agent-picker" style={{ marginTop: 10 }}>
          {AGENTES.map((a) => (
            <button key={a.id}
                    className={`agent-opt${(form.default_agent ?? "claude") === a.id ? " on" : ""}`}
                    onClick={() => set("default_agent", a.id)}>
              <b>{a.nome}</b>
              <span>{a.desc}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Claude (Anthropic)</h3>
        <label>Chave da API {s.has_anthropic_api_key
          ? `(configurada: ${s.anthropic_api_key_masked})` : "(não configurada)"}</label>
        <div className="row">
          <input type="password"
                 placeholder={s.has_anthropic_api_key
                   ? `chave salva (${s.anthropic_api_key_masked}) — cole aqui para substituir`
                   : "sk-ant-…"}
                 value={anthropicKey}
                 onChange={(e) => setAnthropicKey(e.target.value)} />
          <button onClick={() => testar.mutate({ provider: "claude", key: anthropicKey })}
                  disabled={testar.isPending}>
            {testar.isPending ? "Testando…" : "Testar"}
          </button>
        </div>
        <div className="sub" style={{ marginTop: 6 }}>
          {testeClaude || "O teste usa o MESMO caminho da análise real (streaming + saída estruturada)."}
        </div>
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Modelo principal</label>
            <select value={form.claude_model ?? ""} onChange={(e) => set("claude_model", e.target.value)}>
              <option value="claude-opus-5">Claude Opus 5</option>
              <option value="claude-sonnet-5">Claude Sonnet 5</option>
              <option value="claude-haiku-4-5">Claude Haiku 4.5</option>
            </select>
            <div className="sub" style={{ marginTop: 4 }}>
              {CUSTO_POR_HORA[form.claude_model ?? ""] ?? ""}
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <label>Modelo de contingência</label>
            <select value={form.claude_fallback_model ?? ""}
                    onChange={(e) => set("claude_fallback_model", e.target.value)}>
              <option value="claude-sonnet-5">Claude Sonnet 5</option>
              <option value="claude-haiku-4-5">Claude Haiku 4.5</option>
            </select>
          </div>
        </div>
        <label>
          <input type="checkbox" checked={!!form.use_batches}
                 onChange={(e) => set("use_batches", e.target.checked)}
                 style={{ width: 16, marginRight: 8 }} />
          Análise econômica (Batches, −50% de custo; exclusiva do Claude; pode demorar mais)
        </label>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>GPT (OpenAI)</h3>
        <label>Chave da API {s.has_openai_api_key
          ? `(configurada: ${s.openai_api_key_masked})` : "(não configurada)"}</label>
        <div className="row">
          <input type="password"
                 placeholder={s.has_openai_api_key
                   ? `chave salva (${s.openai_api_key_masked}) — cole aqui para substituir`
                   : "sk-proj-…"}
                 value={openaiKey}
                 onChange={(e) => setOpenaiKey(e.target.value)} />
          <button onClick={() => testar.mutate({ provider: "gpt", key: openaiKey })}
                  disabled={testar.isPending}>
            {testar.isPending ? "Testando…" : "Testar"}
          </button>
        </div>
        <div className="sub" style={{ marginTop: 6 }}>
          {testeGpt || "O teste usa o MESMO caminho da análise real (saída estruturada estrita)."}
        </div>
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Modelo principal</label>
            <input list="modelos-gpt" value={form.openai_model ?? ""}
                   placeholder="gpt-5.1"
                   onChange={(e) => set("openai_model", e.target.value)} />
            <datalist id="modelos-gpt">
              <option value="gpt-5.1" />
              <option value="gpt-5" />
              <option value="gpt-5-mini" />
              <option value="gpt-4.1" />
            </datalist>
            <div className="sub" style={{ marginTop: 4 }}>
              {CUSTO_POR_HORA[form.openai_model ?? ""] ?? "Digite qualquer modelo da sua conta OpenAI."}
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <label>Modelo de contingência (opcional)</label>
            <input list="modelos-gpt" value={form.openai_fallback_model ?? ""}
                   placeholder="(nenhum)"
                   onChange={(e) => set("openai_fallback_model", e.target.value)} />
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Transcrição e cortes</h3>
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Modelo Whisper (transcrição local)</label>
            <select value={form.whisper_model ?? ""} onChange={(e) => set("whisper_model", e.target.value)}>
              <option value="tiny">tiny — mais rápido</option>
              <option value="base">base</option>
              <option value="small">small — recomendado</option>
              <option value="medium">medium — mais preciso</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Cortes por 30 min de vídeo</label>
            <input type="number" min={1} max={100} value={form.max_cuts_per_30min ?? 15}
                   onChange={(e) => set("max_cuts_per_30min", parseInt(e.target.value, 10) || 15)} />
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Censura de palavrões</h3>
        <label>
          <input type="checkbox" checked={!!form.censor_enabled}
                 onChange={(e) => set("censor_enabled", e.target.checked)}
                 style={{ width: 16, marginRight: 8 }} />
          Censurar palavrões automaticamente nos renders
        </label>
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Modo</label>
            <select value={form.censor_mode ?? "beep"}
                    onChange={(e) => set("censor_mode", e.target.value as "beep" | "mute")}>
              <option value="beep">Beep (1 kHz)</option>
              <option value="mute">Silenciar</option>
            </select>
          </div>
          <div style={{ flex: 2 }}>
            <label>Palavras adicionais (separadas por vírgula; use * para prefixo)</label>
            <input value={(form.censor_extra_words ?? []).join(", ")}
                   onChange={(e) => set("censor_extra_words",
                     e.target.value.split(",").map((w) => w.trim()).filter(Boolean))} />
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>Saída e integração</h3>
        <label>Pasta dos vídeos renderizados (vazio = pasta padrão do app)</label>
        <div className="row">
          <input value={form.output_dir ?? ""} onChange={(e) => set("output_dir", e.target.value)} />
          {window.realOficial ? (
            <button onClick={async () => {
              const d = await window.realOficial!.pickDirectory();
              if (d) set("output_dir", d);
            }}>Escolher…</button>
          ) : null}
        </div>
        <label>Token da API local (para automações externas — API compatível com o fluxo /shorts)</label>
        <div className="row">
          <input readOnly value={s.api_token} />
          <button onClick={() => navigator.clipboard.writeText(s.api_token)}>Copiar</button>
        </div>
        <div className="sub" style={{ marginTop: 6 }}>
          Dados em {s.data_dir} · motor v{s.version}
        </div>
      </div>

      <div className="row" style={{ marginTop: 18 }}>
        {salvoMsg ? <span className="sub">{salvoMsg}</span> : null}
        <button className="primary right" disabled={salvar.isPending} onClick={submit}>
          Salvar configurações
        </button>
      </div>
    </div>
  );
}
