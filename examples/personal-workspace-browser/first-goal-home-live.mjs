import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { resolveTestPython } from "../../scripts/test-python.mjs";
import { outputDir, packaged, repoRoot } from "./fixture.mjs";
import { fetchWorkspaceBackend, openWorkspacePage } from "./scenario-context.mjs";

// End to end against the real service: a disposable `loopx chat` on a fresh
// runtime with no registry at all, as an installed LoopX opens for the first
// time. The page reads the real discovery view, which states its source facts:
// zero Goals and the service's own missing-registry warning. The home must
// open to the first-Goal state, not a health banner, keep that warning in the
// collapsed diagnostics without a local path, let an example fill the composer
// without sending, and open the typed Goal form fed by the real project catalog.

export const firstGoalHomeLiveScenario = {
  id: "first-goal-home-live",
  async run({ browser, collectCoverage, url }) {
    // The real service serves the packaged bundle; the development lane has none to serve.
    if (!packaged) return { coverageEntries: [], note: "live first-Goal home runs against the packaged bundle only" };
    const root = await mkdtemp(join(tmpdir(), "loopx-first-goal-live-"));
    const python = resolveTestPython({ repoRoot });
    const child = spawn(python, ["-u", resolve(repoRoot, "examples/personal-workspace-browser/fresh-install-backend.py"), root], { cwd: repoRoot, env: { ...process.env, PYTHONPATH: repoRoot }, stdio: ["ignore", "pipe", "pipe"] });
    const closed = once(child, "close");
    const lines = createInterface({ input: child.stdout });
    let diagnostics = "", session;
    child.stderr.on("data", (chunk) => { diagnostics = (diagnostics + chunk).slice(-4000); });
    try {
      const ready = await Promise.race([once(lines, "line").then(([line]) => JSON.parse(line)), closed.then(() => { throw new Error(`fresh-install backend exited: ${diagnostics}`); })]);
      const backend = `http://127.0.0.1:${ready.port}`;
      for (let attempt = 0; attempt < 100; attempt += 1) {
        try { if ((await fetch(`${backend}/status.json?view=workspace-directory`)).ok) break; } catch { /* not listening yet */ }
        await new Promise((resolveWait) => setTimeout(resolveWait, 200));
      }
      const directory = await (await fetch(`${backend}/status.json?view=workspace-directory`)).json();
      assert.equal(directory.ok, true);
      assert.deepEqual(directory.goals, []);
      assert.ok(directory.contract?.warnings.some((row) => /^registry file does not exist/.test(row)), `the real discovery view names the missing registry: ${JSON.stringify(directory.contract)}`);
      assert.ok(!JSON.stringify(directory.contract).includes(root), "no local path leaves the service");
      session = await openWorkspacePage(browser, url, { collectCoverage, viewport: { width: 1440, height: 900 }, beforeGoto: async (_api, page) => {
        // The document URL also ends in "status.json" (its statusUrl query), so match paths, not a glob.
        const proxied = new Set(["/status.json", "/api/chat/capabilities", "/api/chat/projects"]);
        await page.route((target) => proxied.has(target.pathname), async (route) => {
          try { const response = await fetchWorkspaceBackend(route, backend); await route.fulfill({ response }); }
          catch { await route.abort().catch(() => {}); }
        });
      } });
      const { page } = session;
      const turnRequests = [];
      page.on("request", (request) => { if (request.method() === "POST" && /\/api\/chat\/sessions\/[^/]+\/turns/.test(request.url())) turnRequests.push(request.url()); });
      const firstGoal = page.getByTestId("personal-first-goal");
      await firstGoal.waitFor({ state: "visible", timeout: 20_000 });
      assert.equal(await page.locator(".personal-system-health-banner").count(), 0, "The real missing registry is not shown as a health concern");
      assert.match(await firstGoal.locator("h2").innerText(), /还没有 Goal/);
      const details = firstGoal.locator("details.personal-first-goal-diagnostics");
      await details.waitFor({ state: "visible", timeout: 10_000 });
      assert.equal(await details.getAttribute("open"), null, "Diagnostics stay collapsed");
      // The disclosure stays closed, so read its lines, not the visible text.
      const reasons = await details.locator("li").allTextContents();
      assert.ok(reasons.some((row) => /registry file does not exist/.test(row)), `the diagnostics carry the service's own warning: ${reasons.join(" | ")}`);
      assert.ok(reasons.every((row) => !row.includes(root)), "the diagnostics show no local path");
      await page.screenshot({ path: resolve(outputDir, "first-goal-home-live.png"), animations: "disabled" });

      // An example only fills the composer; nothing is sent to the real service.
      const composer = page.locator(".personal-channel-composer textarea");
      const example = firstGoal.locator(".personal-first-goal-examples button").first();
      const exampleText = (await example.innerText()).trim();
      await example.click();
      assert.equal((await composer.inputValue()).trim(), exampleText);
      assert.equal(turnRequests.length, 0, `an example sends nothing: ${turnRequests.join(", ")}`);
      await page.keyboard.press("Escape");

      // Create a Goal opens the typed form; its working directories come from the real project catalog.
      await firstGoal.locator(".personal-first-goal-create").click();
      const form = page.locator("dialog.personal-action-form");
      await form.waitFor({ state: "visible", timeout: 10_000 });
      const projects = await (await fetch(`${backend}/api/chat/projects`)).json();
      assert.ok(projects.projects.length >= 1, "the real service registers the scan root as a project");
      await form.getByLabel("工作目录").locator("option", { hasText: projects.projects[0].title }).waitFor({ state: "attached", timeout: 10_000 });
      await page.screenshot({ path: resolve(outputDir, "first-goal-home-live-create.png"), animations: "disabled" });
      await page.keyboard.press("Escape");
      await form.waitFor({ state: "hidden", timeout: 10_000 });
      return { coverageEntries: await session.close(), note: "real loopx chat on a fresh runtime: zero-Goal discovery with its own warning, no local path, real project catalog in the Goal form" };
    } catch (error) {
      if (diagnostics) process.stderr.write(diagnostics);
      await session?.close().catch(() => {});
      throw error;
    } finally {
      lines.close();
      if (child.exitCode === null && child.signalCode === null) { child.kill("SIGTERM"); const kill = setTimeout(() => child.kill("SIGKILL"), 5000); try { await closed; } finally { clearTimeout(kill); } }
    }
  },
};
