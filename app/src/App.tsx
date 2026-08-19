import { useQuery } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { get } from "./api/client";
import BrandKits from "./pages/BrandKits";
import Dashboard from "./pages/Dashboard";
import ProjectPage from "./pages/Project";
import RenderQueue from "./pages/RenderQueue";
import Reports from "./pages/Reports";
import SettingsPage from "./pages/Settings";

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
        <NavLink to="/" end className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
          Painel
        </NavLink>
        <NavLink to="/kits" className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
          Kits de Marca
        </NavLink>
        <NavLink to="/fila" className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
          Fila de Renderização
        </NavLink>
        <NavLink to="/relatorios" className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
          Relatórios
        </NavLink>
        <NavLink to="/config" className={({ isActive }) => `navlink${isActive ? " active" : ""}`}>
          Configurações
        </NavLink>
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
          <Route path="/kits" element={<BrandKits />} />
          <Route path="/fila" element={<RenderQueue />} />
          <Route path="/relatorios" element={<Reports />} />
          <Route path="/config" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
