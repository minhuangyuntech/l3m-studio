const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('locmodelDesktop', {
  isElectron: true,
  platform: process.platform,
  apiBase: '',
  selectDirectory: () => ipcRenderer.invoke('dialog:selectDirectory'),
  selectFile: (filters) => ipcRenderer.invoke('dialog:selectFile', filters),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  toggleFullscreen: () => ipcRenderer.invoke('window:toggleFullscreen'),
});
