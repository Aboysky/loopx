import assert from "node:assert/strict";
import { resolve } from "node:path";
import { outputDir } from "./fixture.mjs";
import { openWorkspacePage } from "./scenario-context.mjs";

// A fresh install without a usable Agent: the service refuses the first Goal's
// preview with a typed gate (which Agent, the catalog's reason). The page must
// tell the owner in their own language what is missing and what to do, never
// show the protocol sentence, write nothing, keep the form's draft, and go
// through once the Agent is available. The fixture answers the preview with
// the same gate shape the real service sends.

function emptyWorkspace(fixture) {
  fixture.goal_count = 0;
  fixture.run_count = 0;
  fixture.run_history.goals = [];
  fixture.run_history.recent_runs = [];
  fixture.run_history.goal_count = 0;
  fixture.run_history.run_count = 0;
  fixture.attention_queue.items = [];
  fixture.attention_queue.item_count = 0;
  fixture.attention_queue.needs_user_or_controller = 0;
  fixture.attention_queue.needs_codex = 0;
  fixture.attention_queue.watching_external_evidence = 0;
  if (fixture.usage_summary) fixture.usage_summary.goals = [];
  fixture.contract = { ok: true, summary: { errors: 0, warnings: 1, checks: 1 }, errors: [],
    warnings: ["registry file does not exist: [local-path]"], checks: ["run-history goals=0 runs=0"] };
}

export const firstGoalAgentUnavailableScenario = {
  id: "first-goal-agent-unavailable",
  async run({ browser, collectCoverage, url }) {
    const session = await openWorkspacePage(browser, url, { collectCoverage, viewport: { width: 1440, height: 900 },
      beforeGoto: (api) => { api.transformStatus = (fixture) => emptyWorkspace(fixture); } });
    const { api, page } = session;
    try {
      const firstGoal = page.getByTestId("personal-first-goal");
      await firstGoal.waitFor({ state: "visible", timeout: 15_000 });
      await firstGoal.locator(".personal-first-goal-create").click();
      const form = page.locator("dialog.personal-action-form");
      await form.waitFor({ state: "visible", timeout: 10_000 });
      await form.getByLabel("目标").fill("Track the weekly release checklist");
      await form.getByLabel("完成标准").fill("A checklist exists and is reviewed every week");
      api.nextActionPreviewGate = { kind: "agent_unavailable", agent_id: "codex", registered: true, unavailable_reason: "executable_not_found", executable: "/opt/loopx/bin/codex",
        summary: "The selected Agent (codex) is not available to start this Goal.", next_action: "Install and sign in to the Agent, then create the Goal again.", detail: "selected Agent endpoint is not healthy" };
      await form.locator("button[type=submit]").click();
      const drawer = page.locator(".personal-context-drawer");
      await drawer.waitFor({ state: "visible", timeout: 10_000 });
      const text = (await drawer.innerText()).replace(/\s+/g, " ");
      assert.match(text, /还不能开始这个 Goal/, `the owner reads which Agent cannot start the Goal: ${text.slice(0, 300)}`);
      assert.match(text, /本机没有找到命令 \/opt\/loopx\/bin\/codex/, "the catalog's own reason is shown");
      assert.match(text, /先安装并登录/, "the next action is stated");
      assert.match(text, /没有写入任何 Goal/, "nothing was written");
      assert.doesNotMatch(text, /endpoint is not healthy|not available to start/, "no protocol sentence reaches the owner");
      await page.screenshot({ path: resolve(outputDir, "first-goal-agent-unavailable.png"), animations: "disabled" });
      assert.equal(api.actionPreviews.filter((row) => row.gated).length, 1, "exactly one refused preview");

      // Once the Agent is available the same request previews normally.
      await page.locator(".personal-drawer-close").click();
      await firstGoal.locator(".personal-first-goal-create").click();
      await form.waitFor({ state: "visible", timeout: 10_000 });
      await form.getByLabel("目标").fill("Track the weekly release checklist");
      await form.getByLabel("完成标准").fill("A checklist exists and is reviewed every week");
      await form.locator("button[type=submit]").click();
      await drawer.waitFor({ state: "visible", timeout: 10_000 });
      await drawer.getByText("新 Goal · 待你确认", { exact: true }).waitFor({ state: "visible", timeout: 10_000 });
      return { coverageEntries: await session.close() };
    } catch (error) {
      await session.close().catch(() => {});
      throw error;
    }
  },
};
