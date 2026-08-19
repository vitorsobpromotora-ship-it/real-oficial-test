import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, del, get, patch, post } from "../api/client";
import type { BrandKit } from "../api/types";

const PRESETS = ["bold_karaoke", "clean", "podcast", "minimal"];

function KitForm({ kit, onDone }: { kit: BrandKit | null; onDone(): void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    name: kit?.name ?? "",
    logo_position: kit?.logo_position ?? "tr",
    logo_opacity: kit?.logo_opacity ?? 1.0,
    primary_color: kit?.primary_color ?? "#FFFFFF",
    secondary_color: kit?.secondary_color ?? "#FFD400",
    font_family: kit?.font_family ?? "Inter",
    caption_preset: kit?.caption_preset ?? "bold_karaoke",
    headline_template: kit?.headline_template ?? "",
    is_default: kit?.is_default ?? false,
  });
  const [err, setErr] = useState("");

  const salvar = useMutation({
    mutationFn: async () => {
      if (kit) return patch<BrandKit>(`/api/v1/brand-kits/${kit.id}`, form);
      return post<BrandKit>("/api/v1/brand-kits", form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["brand-kits"] });
      onDone();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <div className="modal-backdrop" onClick={onDone}>
      <div className="modal" style={{ width: 620 }} onClick={(e) => e.stopPropagation()}>
        <h2>{kit ? `Editar kit “${kit.name}”` : "Novo kit de marca"}</h2>
        <label>Nome</label>
        <input value={form.name} onChange={(e) => set("name", e.target.value)} />
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Cor do texto</label>
            <input type="color" value={form.primary_color}
                   onChange={(e) => set("primary_color", e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Cor de destaque (karaokê)</label>
            <input type="color" value={form.secondary_color}
                   onChange={(e) => set("secondary_color", e.target.value)} />
          </div>
          <div style={{ flex: 1 }}>
            <label>Fonte</label>
            <select value={form.font_family} onChange={(e) => set("font_family", e.target.value)}>
              <option>Inter</option>
              <option>Montserrat</option>
            </select>
          </div>
        </div>
        <div className="row" style={{ gap: 16 }}>
          <div style={{ flex: 1 }}>
            <label>Estilo de legenda</label>
            <select value={form.caption_preset}
                    onChange={(e) => set("caption_preset", e.target.value)}>
              {PRESETS.map((p) => <option key={p}>{p}</option>)}
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Posição do logo</label>
            <select value={form.logo_position} onChange={(e) => set("logo_position", e.target.value)}>
              <option value="tr">Canto superior direito</option>
              <option value="tl">Canto superior esquerdo</option>
              <option value="br">Canto inferior direito</option>
              <option value="bl">Canto inferior esquerdo</option>
            </select>
          </div>
          <div style={{ flex: 1 }}>
            <label>Opacidade do logo ({Math.round(form.logo_opacity * 100)}%)</label>
            <input type="range" min={0.1} max={1} step={0.05} value={form.logo_opacity}
                   onChange={(e) => set("logo_opacity", parseFloat(e.target.value))} />
          </div>
        </div>
        <label>Headline (texto no topo; use {"{titulo}"} para o título do corte)</label>
        <input value={form.headline_template}
               onChange={(e) => set("headline_template", e.target.value)}
               placeholder="ex.: {titulo}" />
        <label>
          <input type="checkbox" checked={form.is_default}
                 onChange={(e) => set("is_default", e.target.checked)}
                 style={{ width: 16, marginRight: 8 }} />
          Usar como kit padrão
        </label>
        {err ? <div className="err">{err}</div> : null}
        <div className="row" style={{ marginTop: 16 }}>
          <button className="right" onClick={onDone}>Cancelar</button>
          <button className="primary" disabled={!form.name.trim() || salvar.isPending}
                  onClick={() => salvar.mutate()}>
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}

export default function BrandKits() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<BrandKit | null | "novo">(null);
  const kits = useQuery({ queryKey: ["brand-kits"], queryFn: () => get<BrandKit[]>("/api/v1/brand-kits") });

  const excluir = useMutation({
    mutationFn: (id: string) => del(`/api/v1/brand-kits/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["brand-kits"] }),
  });

  async function uploadLogo(kit: BrandKit, file: File) {
    const fd = new FormData();
    fd.append("file", file);
    await api(`/api/v1/brand-kits/${kit.id}/logo`, { method: "POST", body: fd });
    qc.invalidateQueries({ queryKey: ["brand-kits"] });
  }

  return (
    <div>
      <div className="pagehead">
        <h1>Kits de Marca</h1>
        <button className="primary" onClick={() => setEditing("novo")}>+ Novo kit</button>
      </div>
      {kits.data?.length === 0 ? (
        <div className="empty">
          Crie um kit com suas cores, fonte e logo — e aplique em dezenas de cortes de uma vez.
        </div>
      ) : null}
      <div className="grid">
        {kits.data?.map((k) => (
          <div key={k.id} className="card">
            <h3>
              {k.name} {k.is_default ? <span className="chip claude">padrão</span> : null}
            </h3>
            <div className="row" style={{ margin: "8px 0" }}>
              <span className="chip" style={{ background: k.primary_color, color: "#000" }}>texto</span>
              <span className="chip" style={{ background: k.secondary_color, color: "#000" }}>destaque</span>
              <span className="chip">{k.font_family}</span>
              <span className="chip">{k.caption_preset}</span>
            </div>
            <div className="sub">{k.logo_path ? "Logo enviado ✓" : "Sem logo"}</div>
            <div className="row" style={{ marginTop: 10 }}>
              <button onClick={() => setEditing(k)}>Editar</button>
              <label style={{ margin: 0 }}>
                <input type="file" accept="image/png,image/jpeg,image/webp" style={{ display: "none" }}
                       onChange={(e) => e.target.files?.[0] && uploadLogo(k, e.target.files[0])} />
                <span className="chip" style={{ cursor: "pointer" }}>Enviar logo…</span>
              </label>
              <button className="danger right" onClick={() => excluir.mutate(k.id)}>Excluir</button>
            </div>
          </div>
        ))}
      </div>
      {editing !== null ? (
        <KitForm kit={editing === "novo" ? null : editing} onDone={() => setEditing(null)} />
      ) : null}
    </div>
  );
}
