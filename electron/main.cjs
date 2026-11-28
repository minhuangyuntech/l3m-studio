const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn, execSync } = require('child_process');
const http = require('http');
const net = require('net');
const path = require('path');
const fs = require('fs');

const DEFAULT_PORT = Number(process.env.LOCMODEL_BACKEND_PORT || 18765);
const EXPECTED_VERSION = '1.2.0';
const IS_DEV = process.env.LOCMODEL_DEV === '1';

function getLatestBackendMtimeSec() {
  const appDir = path.resolve(__dirname, '..', 'backend', 'app');
  let latest = 0;
  try {
    for (const f of fs.readdirSync(appDir)) {
      if (f.endsWith('.py')) {
        const st = fs.statSync(path.join(appDir, f));
        if (st.mtimeMs / 1000 > latest) latest = st.mtimeMs / 1000;
      }
    }
  } catch {
    // ignore
  }
  return latest;
}

let activePort = DEFAULT_PORT;
let mainWindow = null;
let backendProc = null;

function probeHealth(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/api/health`, (res) => {
      let body = '';
      res.on('data', (c) => (body += c));
      res.on('end', () => {
        try {
          resolve({ statusCode: res.statusCode, data: JSON.parse(body) });
        } catch {
          resolve(null);
        }
      });
    });
    req.on('error', () => resolve(null));
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(null);
    });
  });
}

function findFreePort(startPort) {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.unref();
    srv.on('error', () => resolve(findFreePort(startPort + 1)));
    srv.listen(startPort, '127.0.0.1', () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function resolvePythonBinary() {
  const rootDir = path.resolve(__dirname, '..');
  const candidates =
    process.platform === 'win32'
      ? [
          path.join(rootDir, 'backend', '.venv', 'Scripts', 'python.exe'),
          'python',
          'py',
        ]
      : [
          path.join(rootDir, 'backend', '.venv', 'bin', 'python'),
          'python3',
          'python',
        ];

  for (const cand of candidates) {
    if (!path.isAbsolute(cand) || fs.existsSync(cand)) {
      return cand;
    }
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

function startBackend(port) {
  const rootDir = path.resolve(__dirname, '..');
  const backendDir = path.join(rootDir, 'backend');
  const mainPy = path.join(backendDir, 'main.py');
  const pythonBin = resolvePythonBinary();

  backendProc = spawn(
    pythonBin,
    [mainPy, '--host', '127.0.0.1', '--port', String(port)],
    {
      cwd: backendDir,
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
      stdio: 'pipe',
      windowsHide: true,
    },
  );

  backendProc.stdout.on('data', (d) => process.stdout.write(`[backend] ${d}`));
  backendProc.stderr.on('data', (d) => process.stderr.write(`[backend] ${d}`));
  backendProc.on('exit', (code) => {
    console.log(`[backend] exited with code ${code}`);
    backendProc = null;
  });
}

function waitForBackend(port, timeoutMs = 25000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = async () => {
      const res = await probeHealth(port);
      if (res && res.statusCode === 200 && res.data && res.data.app === 'L3M Studio') {
        resolve();
        return;
      }
      if (Date.now() - started > timeoutMs) {
        reject(new Error('Backend server startup timed out'));
        return;
      }
      setTimeout(check, 350);
    };
    check();
  });
}

async function createWindow() {
  process.env.LOCMODEL_BACKEND_PORT = String(activePort);
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1080,
    minHeight: 700,
    title: 'L3M Studio',
    backgroundColor: '#0b0f17',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  await mainWindow.webContents.session.clearCache();

  if (IS_DEV) {
    await mainWindow.loadURL('http://127.0.0.1:5173');
  } else {
    await mainWindow.loadURL(`http://127.0.0.1:${activePort}`);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.handle('dialog:selectDirectory', async () => {
  const res = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
  });
  return res.canceled ? null : res.filePaths[0];
});

ipcMain.handle('dialog:selectFile', async (_evt, filters) => {
  const res = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: filters || undefined,
  });
  return res.canceled ? null : res.filePaths[0];
});

ipcMain.handle('shell:openExternal', async (_evt, url) => {
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
    await shell.openExternal(url);
  }
});

ipcMain.handle('window:toggleFullscreen', async () => {
  if (!mainWindow) return false;
  const next = !mainWindow.isFullScreen();
  mainWindow.setFullScreen(next);
  return next;
});

app.whenReady().then(async () => {
  const existing = await probeHealth(DEFAULT_PORT);
  const latestPyMtime = getLatestBackendMtimeSec();
  if (
    existing &&
    existing.statusCode === 200 &&
    existing.data &&
    existing.data.app === 'L3M Studio' &&
    existing.data.version === EXPECTED_VERSION &&
    typeof existing.data.started_at === 'number' &&
    existing.data.started_at >= latestPyMtime
  ) {
    activePort = DEFAULT_PORT;
  } else {
    activePort = await findFreePort(DEFAULT_PORT);
    startBackend(activePort);
    try {
      await waitForBackend(activePort);
    } catch (err) {
      console.error(err);
    }
  }
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  if (backendProc && backendProc.pid) {
    try {
      if (process.platform === 'win32') {
        execSync(`taskkill /F /T /PID ${backendProc.pid}`, { stdio: 'ignore', windowsHide: true });
      } else {
        backendProc.kill();
      }
    } catch {
      try {
        backendProc.kill();
      } catch {
        // ignore
      }
    }
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
