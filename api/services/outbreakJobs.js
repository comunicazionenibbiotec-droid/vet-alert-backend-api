import { spawn } from "node:child_process";
import path from "node:path";

const ROOT_DIR = process.cwd();

function runPythonScript(scriptPath, args = []) {
  return new Promise((resolve, reject) => {
    const fullScriptPath = path.join(ROOT_DIR, scriptPath);

    const child = spawn("python", [fullScriptPath, ...args], {
      cwd: ROOT_DIR,
      env: process.env,
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      if (code !== 0) {
        reject({
          code,
          stdout,
          stderr,
        });
        return;
      }

      resolve({
        code,
        stdout,
        stderr,
      });
    });
  });
}

export async function updateSingleEventOutbreakLink(eventId) {
  return runPythonScript("scripts/update_single_event_outbreak_link.py", [
    "--event-id",
    eventId,
  ]);
}

export async function recalculateOutbreakWindow(eventId, daysBefore = 30, daysAfter = 30) {
  return runPythonScript("scripts/recalculate_outbreak_window.py", [
    "--event-id",
    eventId,
    "--days-before",
    String(daysBefore),
    "--days-after",
    String(daysAfter),
  ]);
}

export async function rebuildOutbreakSeries() {
  return runPythonScript("scripts/rebuild_outbreak_series.py", []);
}
