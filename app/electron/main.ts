import { BrowserWindow, app, dialog, ipcMain, shell } from "electron";
import * as path from "node:path";
import { getEngineInfo, startSidecar, stopSidecar } from "./sidecar";

const isDev = !!process.env.VITE_DEV_SERVER_URL || !app.isPackaged;

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

let win: BrowserWindow | null = null;

async function createWindow(): Promise<void> {
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    backgroundColor: "#0d1117",
    title: "Real Oficial",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  win.on("closed", () => {
    win = null;
  });

  try {
    await startSidecar({
      resourcesPath: process.resourcesPath,
      userDataDir: app.getPath("userData"),
      isDev,
      appRoot: app.getAppPath(),
    });
  } catch (err) {
    dialog.showErrorBox("Real Oficial — falha ao iniciar o motor",
      `${err}\n\nVerifique os logs em ${app.getPath("userData")}`);
    app.quit();
    return;
  }

  if (process.env.VITE_DEV_SERVER_URL) {
    await win.loadURL(process.env.VITE_DEV_SERVER_URL);
    win.webContents.openDevTools({ mode: "detach" });
  } else {
    await win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

ipcMain.handle("engine:info", () => getEngineInfo());
ipcMain.handle("dialog:pickVideo", async () => {
  const res = await dialog.showOpenDialog({
    title: "Escolher vídeo",
    properties: ["openFile"],
    filters: [{ name: "Vídeos", extensions: ["mp4", "mov", "mkv", "webm", "avi", "m4v"] }],
  });
  return res.canceled ? null : res.filePaths[0];
});
ipcMain.handle("dialog:pickImage", async () => {
  const res = await dialog.showOpenDialog({
    title: "Escolher logo",
    properties: ["openFile"],
    filters: [{ name: "Imagens", extensions: ["png", "jpg", "jpeg", "webp"] }],
  });
  return res.canceled ? null : res.filePaths[0];
});
ipcMain.handle("dialog:pickDirectory", async () => {
  const res = await dialog.showOpenDialog({
    title: "Escolher pasta",
    properties: ["openDirectory", "createDirectory"],
  });
  return res.canceled ? null : res.filePaths[0];
});
ipcMain.handle("shell:openPath", (_e, p: string) => shell.openPath(p));
ipcMain.handle("shell:showInFolder", (_e, p: string) => shell.showItemInFolder(p));
ipcMain.handle("shell:openExternal", (_e, url: string) => {
  if (url.startsWith("http://") || url.startsWith("https://")) return shell.openExternal(url);
  return Promise.resolve();
});

app.on("second-instance", () => {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

app.whenReady().then(createWindow);

app.on("window-all-closed", async () => {
  await stopSidecar();
  app.quit();
});

app.on("before-quit", async (e) => {
  if (getEngineInfo()) {
    e.preventDefault();
    await stopSidecar();
    app.exit(0);
  }
});
