// Assinatura única de SSE que invalida as queries certas conforme os eventos chegam.
import { fetchEventSource } from "@microsoft/fetch-event-source";
import type { QueryClient } from "@tanstack/react-query";
import { engine } from "./client";

export interface EngineEvent {
  event: string;
  data: Record<string, unknown>;
}

export async function startEventStream(qc: QueryClient, signal: AbortSignal): Promise<void> {
  const { baseUrl, token } = await engine();
  await fetchEventSource(`${baseUrl}/api/v1/events`, {
    signal,
    headers: { Authorization: `Bearer ${token}` },
    openWhenHidden: true,
    onmessage(msg) {
      if (!msg.event) return;
      let data: Record<string, unknown> = {};
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;
      }
      if (msg.event === "job.updated") {
        qc.invalidateQueries({ queryKey: ["jobs"] });
        const status = data.status as string;
        if (status === "done" || status === "failed") {
          qc.invalidateQueries({ queryKey: ["projects"] });
          qc.invalidateQueries({ queryKey: ["sources"] });
          qc.invalidateQueries({ queryKey: ["cuts"] });
          qc.invalidateQueries({ queryKey: ["shorts"] });
        }
      } else if (msg.event === "render.progress") {
        qc.invalidateQueries({ queryKey: ["renders"] });
      }
    },
    onerror() {
      // fetchEventSource re-tenta sozinho; retornar undefined mantém o retry
    },
  });
}
