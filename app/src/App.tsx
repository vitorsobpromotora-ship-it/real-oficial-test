import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes, useParams } from "react-router-dom";
import { get } from "./api/client";
import type { Cut } from "./api/types";
import BrandKits from "./pages/BrandKits";
import BrandStudio from "./pages/BrandStudio";
import CutPage from "./pages/CutPage";
import Dashboard from "./pages/Dashboard";
import EditorPage from "./pages/Editor";
import ProjectPage from "./pages/Project";
import RenderQueue from "./pages/RenderQueue";
import Reports from "./pages/Reports";
import SettingsPage from "./pages/Settings";

/** Rota legada /editor/:cutId — descobre o projeto e leva à rota canônica. */
function LegacyEditorRedirect() {
  const { cutId = "" } = useParams();
  const cut = useQuery({
    queryKey: ["cuts", "detail", cutId],
    queryFn: () => get<Cut>(`/api/v1/cuts/${cutId}`),
  });
  if (cut.isError) return <Navigate to="/" replace />;
  if (!cut.data) return <div className="ed-loading">Abrindo o Editor…</div>;
  return <Navigate to={`/projeto/${cut.data.project_id}/corte/${cutId}/editor`} replace />;
}

const I = {
  painel: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  kits: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="13.5" cy="6.5" r="2.5" /><path d="M12 2a10 10 0 1 0 10 10c0-1.5-1.5-2-2.5-2H16a2 2 0 0 1-2-2V6" />
    </svg>
  ),
  fila: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="6 3 20 12 6 21 6 3" />
    </svg>
  ),
  relatorios: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" rx=".8" />
      <rect x="12" y="7" width="3" height="10" rx=".8" /><rect x="17" y="13" width="3" height="4" rx=".8" />
    </svg>
  ),
  config: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

const LINKS = [
  { to: "/", end: true, icone: I.painel, rotulo: "Painel" },
  { to: "/kits", icone: I.kits, rotulo: "Kits de Marca" },
  { to: "/fila", icone: I.fila, rotulo: "Fila de Renderização" },
  { to: "/relatorios", icone: I.relatorios, rotulo: "Relatórios" },
  { to: "/config", icone: I.config, rotulo: "Configurações" },
];

export default function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => get<{ version: string }>("/health"),
    refetchInterval: 15000,
  });

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="logo">real<b>/oficial</b></div>
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}
                   className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
            {l.icone}
            {l.rotulo}
          </NavLink>
        ))}
        <div className="spacer" />
        <div className="enginedot">
          <i style={{ background: health.isSuccess ? "var(--ok)" : "var(--bad)" }} />
          {health.isSuccess ? `Motor ativo · v${health.data.version}` : "Motor indisponível"}
        </div>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projeto/:id" element={<ProjectPage />} />
          {/* rotas explícitas Corte ↔ Editor: o Editor sempre sabe seu cutId e
              Voltar/Salvar e fechar retornam SEMPRE à análise do mesmo corte */}
          <Route path="/projeto/:projectId/corte/:cutId" element={<CutPage />} />
          <Route path="/projeto/:projectId/corte/:cutId/editor" element={<EditorPage />} />
          <Route path="/editor/:cutId" element={<LegacyEditorRedirect />} />
          <Route path="/kits" element={<BrandKits />} />
          <Route path="/estudio/:kitId" element={<BrandStudio />} />
          <Route path="/fila" element={<RenderQueue />} />
          <Route path="/relatorios" element={<Reports />} />
          <Route path="/config" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
