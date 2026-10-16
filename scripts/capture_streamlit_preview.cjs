const path = require("path");
const { spawn } = require("child_process");

const moduleRoot = process.env.CODEX_NODE_MODULES;
if (!moduleRoot) {
  throw new Error("CODEX_NODE_MODULES is required");
}

const { chromium } = require(path.join(moduleRoot, "playwright"));

(async () => {
  const targetUrl = process.env.RIDERESOLVE_PREVIEW_URL || "http://127.0.0.1:8502";
  const outputPath = process.env.RIDERESOLVE_PREVIEW_OUTPUT;
  const pythonPath = process.env.RIDERESOLVE_PYTHON;
  const repoPath = process.env.RIDERESOLVE_REPO;
  if (!outputPath) {
    throw new Error("RIDERESOLVE_PREVIEW_OUTPUT is required");
  }
  if (!pythonPath || !repoPath) {
    throw new Error("RIDERESOLVE_PYTHON and RIDERESOLVE_REPO are required");
  }

  const server = spawn(
    pythonPath,
    [
      "-m",
      "streamlit",
      "run",
      "app.py",
      "--server.headless=true",
      "--server.address=127.0.0.1",
      "--server.port=8502",
    ],
    { cwd: repoPath, windowsHide: true, stdio: "ignore" },
  );

  const browser = await chromium.launch({
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    headless: true,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const deadline = Date.now() + 60000;
    while (true) {
      try {
        await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 5000 });
        break;
      } catch (error) {
        if (Date.now() >= deadline || server.exitCode !== null) {
          throw error;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
    await page.getByText("Five-agent reasoning", { exact: false }).waitFor({ timeout: 60000 });
    await page.screenshot({ path: outputPath, fullPage: false });
  } finally {
    await browser.close();
    if (server.exitCode === null) {
      server.kill();
    }
  }
})();
