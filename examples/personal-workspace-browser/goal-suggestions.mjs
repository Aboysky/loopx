import assert from "node:assert/strict";
import { resolve } from "node:path";
import { outputDir } from "./fixture.mjs";
import { openWorkspacePage } from "./scenario-context.mjs";

// The Goal composer's suggestions are derived from the Goal's own projection.
// The fixture's first Goal carries blocked advancement tasks and, once a gate
// is added, a decision waiting on the owner; each suggestion must cite those
// facts and either act in place or send a question that names them. A stopped
// Goal gets no derived suggestion, and the shipped steward prompt row stays.

const gateText = "Approve the restated FY2023 operating cash flow";

function addGate(fixture) {
  const first = fixture.attention_queue.items[0];
  first.waiting_on = "user_or_controller";
  first.user_todos ??= { items: [], open_count: 0, source_section: "User Todo", total_count: 0 };
  first.user_todos.items.push({ done: false, status: "open", goal_id: first.goal_id, index: first.user_todos.items.length, role: "user", task_class: "user_gate", todo_id: "gate-restatement", text: gateText, updated_at: "2026-10-15T08:00:00Z" });
  first.user_todos.open_count = first.user_todos.items.filter((todo) => !todo.done).length;
  first.user_todos.total_count = first.user_todos.items.length;
}

export const goalSuggestionsScenario = {
  id: "goal-suggestions",
  async run({ browser, collectCoverage, url }) {
    const session = await openWorkspacePage(browser, url, { collectCoverage, viewport: { width: 1440, height: 900 },
      beforeGoto: (api) => { api.transformStatus = addGate; } });
    const { api, page } = session;
    try {
      await page.locator(".personal-goal-row").first().locator(".personal-goal-link").click();
      await page.getByTestId("goal-vitals").waitFor({ state: "visible", timeout: 15_000 });
      await page.getByRole("navigation", { name: "Goal 视图" }).getByRole("button", { name: "对话", exact: true }).click();
      const tools = page.locator(".personal-composer-tools");
      const summary = tools.locator("> summary");
      await summary.waitFor({ state: "visible", timeout: 15_000 });
      await page.screenshot({ path: resolve(outputDir, "goal-suggestions-collapsed.png"), animations: "disabled" });
      assert.match(await summary.innerText(), /快捷提问 · 先处理 \d+ 项等你决定的事项/, "The collapsed summary carries the first suggestion");
      await summary.click();
      const row = page.getByTestId("goal-suggestions");
      await row.waitFor({ state: "visible" });
      const labels = (await row.locator("button").allInnerTexts()).map((label) => label.trim());
      assert.ok(labels.length >= 2 && labels.length <= 3, `two or three suggestions, got ${labels.join(" / ")}`);
      assert.match(labels[0], /^先处理 \d+ 项等你决定的事项$/);
      assert.match(labels[1], /^解释 \d+ 项受阻任务$/);
      const stewardRow = page.locator(".personal-quick-prompts").first();
      assert.match(await stewardRow.innerText(), /询问下一步[\s\S]*看阻塞[\s\S]*查证据/, "The shipped steward prompt row stays below");
      await page.screenshot({ path: resolve(outputDir, "goal-suggestions-row.png"), animations: "disabled" });

      // Decisions: acting in place opens the overview with its owner rail.
      await row.locator('button[data-suggestion="open_decisions"]').click();
      await page.getByTestId("goal-vitals").waitFor({ state: "visible" });
      const overview = page.locator(".goal-overview, [data-testid=\"goal-overview\"]").first();
      await overview.waitFor({ state: "visible", timeout: 10_000 });
      assert.match(await page.locator("main, .personal-channel-body, body").first().innerText(), new RegExp(gateText.slice(0, 20)), "The overview shows the waiting decision");
      await page.screenshot({ path: resolve(outputDir, "goal-suggestions-decisions.png"), animations: "disabled" });
      await page.getByRole("navigation", { name: "Goal 视图" }).getByRole("button", { name: "对话", exact: true }).click();
      await summary.waitFor({ state: "visible", timeout: 15_000 });
      if (!(await row.isVisible())) await summary.click();

      // Blocked work: the question names the real blocked tasks and sends immediately.
      await row.locator('button[data-suggestion="explain_blocked"]').click();
      let turn;
      for (let attempt = 0; attempt < 60 && !turn; attempt += 1) {
        turn = api.turnRequests.find((request) => /受阻：/.test(request.message));
        if (!turn) await page.waitForTimeout(50);
      }
      assert.ok(turn, "Explaining blocked work sends a Turn");
      assert.match(turn.message, /这个 Goal 里有 \d+ 项任务受阻：「[^」]+」/, "The question quotes a real blocked task title");
      assert.ok(/Rerun SkillsBench|Run the next SkillsBench|Run the SkillsBench/.test(turn.message), `names a fixture task, got: ${turn.message.slice(0, 160)}`);
      assert.equal(await page.getByLabel("向 LoopX 发送消息").inputValue(), "", "A suggestion sends immediately and leaves no draft");

      // A stopped Goal invites nothing derived; the steward row remains.
      const stoppedGoals = page.locator(".personal-stopped-goals");
      if (await stoppedGoals.count()) await stoppedGoals.locator("summary").click();
      const stopped = stoppedGoals.locator(".personal-goal-row").first();
      if (await stopped.count()) {
        await stopped.locator(".personal-goal-link").click();
        await page.getByRole("navigation", { name: "Goal 视图" }).getByRole("button", { name: "对话", exact: true }).click();
        await summary.waitFor({ state: "visible" });
        assert.equal((await summary.innerText()).trim(), "快捷提问", "A stopped Goal shows no derived suggestion");
        await summary.click();
        assert.equal(await page.getByTestId("goal-suggestions").count(), 0);
        await page.locator(".personal-quick-prompts").first().waitFor({ state: "visible" });
      }
      return { coverageEntries: await session.close() };
    } catch (error) {
      await session.close().catch(() => {});
      throw error;
    }
  },
};
