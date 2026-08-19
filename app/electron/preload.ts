import { contextBridge, ipcRenderer } from "electron";

export interface RealOficialBridge {
  getEngine(): Promise<{ baseUrl: string; token: string; port: number } | null>;
  pickVideoFile(): Promise<string | null>;
  pickImageFile(): Promise<string | null>;
  pickDirectory(): Promise<string | null>;
  openPath(p: string): Promise<string>;
  showInFolder(p: string): Promise<void>;
  openExternal(url: string): Promise<void>;
}

const bridge: RealOficialBridge = {
  getEngine: () => ipcRenderer.invoke("engine:info"),
  pickVideoFile: () => ipcRenderer.invoke("dialog:pickVideo"),
  pickImageFile: () => ipcRenderer.invoke("dialog:pickImage"),
  pickDirectory: () => ipcRenderer.invoke("dialog:pickDirectory"),
  openPath: (p) => ipcRenderer.invoke("shell:openPath", p),
  showInFolder: (p) => ipcRenderer.invoke("shell:showInFolder", p),
  openExternal: (url) => ipcRenderer.invoke("shell:openExternal", url),
};

contextBridge.exposeInMainWorld("realOficial", bridge);
