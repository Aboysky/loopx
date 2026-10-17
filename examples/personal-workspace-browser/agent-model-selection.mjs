import assert from "node:assert/strict";
import { openWorkspacePage } from "./scenario-context.mjs";

// Compiled UI with synthetic HTTP Session storage; ACP adoption has its own stdio smoke.
export const agentModelSelectionScenario = {
  id: "agent-model-selection",
  async run({ browser, collectCoverage, url }) {
    let createdCount = 0;
    const requests = [];
    const context = await openWorkspacePage(browser, url, {
      collectCoverage,
      beforeGoto: async (_api, page) => {
        await page.route("**/api/chat/agent-model-options", route => route.fulfill({ json: {
          ok: true, schema_version: "loopx_chat_agent_model_options_v1", agent_id: "codex", supported: true,
          model: { id: "engine", label: "Model", selected: "safe", options: [
            { value: "safe", label: "Safe" }, { value: "vendor/model  fast", label: "Fast" },
          ] },
        } }));
        await page.route("**/api/chat/sessions", async route => {
          if (route.request().method() !== "POST") return route.fallback();
          const body = route.request().postDataJSON();
          requests.push(body);
          const runtime = page.__loopxRuntime;
          const channel = body.context_kind === "manager" ? "manager" : `goal.${body.goal_id}`;
          const existing = body.mode === "resume_latest" ? [...runtime.sessions.values()].find(session =>
            session.channel_id === channel && session.agent_id === body.agent_id) : null;
          const session = existing ?? {
            session_id: `model-session-${++createdCount}`, goal_id: body.goal_id, agent_id: body.agent_id,
            agent_model_id: body.agent_model_id ?? "runtime-default", agent_reasoning_effort: "high", agent_service_tier: "priority", adapter_kind: "codex_app_server", channel_id: channel,
            status: "ready", active_turn_id: null, last_error_code: null, resumable: true,
            created_at: "2026-08-13T01:00:00Z", updated_at: "2026-08-13T01:00:00Z",
          };
          runtime.sessions.set(session.session_id, session);
          runtime.messages.set(session.session_id, runtime.messages.get(session.session_id) ?? []);
          await route.fulfill({ status: existing ? 200 : 201, json: {
            ok: true, session_id: session.session_id, session, resumed: Boolean(existing), agent_id: session.agent_id,
          } });
        });
      },
    });
    const { page, api } = context;
    try {
      await page.locator(".personal-goal-link").first().click();
      await page.getByRole("navigation", { name: "Goal 视图" }).getByRole("button", { name: /^(Chat|对话)$/ }).click();
      const modelControl = page.getByRole("combobox", {name: "选择模型"});
      await modelControl.filter({hasText: "runtime-default"}).waitFor();
      assert.equal(requests.at(-1).agent_model_id, undefined, "catalog order never becomes an implicit model choice");
      await page.reload({waitUntil: "networkidle"});
      await modelControl.filter({hasText: "runtime-default"}).waitFor();
      assert.equal(requests.at(-1).agent_model_id, undefined, "reading the current model never pins the default on refresh");
      const selectModel = async label => {
        await page.getByRole("combobox", { name: "选择模型" }).click();
        await page.getByRole("option", { name: label, exact: true }).click();
      };
      const send = async message => {
        const count = api.turnRequests.length;
        await page.getByLabel("向 LoopX 发送消息").fill(message);
        await page.getByRole("button", { name: "发送", exact: true }).click();
        const deadline = Date.now() + 5000;
        while (api.turnRequests.length === count && Date.now() < deadline) await page.waitForTimeout(25);
        assert.equal(api.turnRequests.length, count + 1);
        await page.locator(".personal-message-pending").waitFor({ state: "hidden" });
        return api.turnRequests.at(-1).sessionId;
      };
      await selectModel("Safe");
      const original = await send("解释模型选择如何保持当前对话。");
      await modelControl.filter({ hasText: "safe" }).waitFor();
      const before = createdCount;
      await selectModel("safe");
      assert.equal(await send("继续同一个对话。"), original);
      assert.equal(createdCount, before, "reselecting the current model must not create another Session");
      await selectModel("Fast");
      const changed = await send("使用新模型继续分析。");
      assert.notEqual(changed, original);
      assert.equal(createdCount, before + 1, "a real model change creates exactly one distinct Session");
      assert.equal(page.__loopxRuntime.sessions.get(changed).agent_model_id, "vendor/model  fast");
      assert.ok(page.__loopxRuntime.sessions.has(original), "prior history remains addressable");
      assert.equal(requests.at(-1).agent_model_id, "vendor/model  fast", "an explicit choice uses the exact model identifier");
      await page.setViewportSize({width: 390, height: 844});
      const width = await modelControl.locator(".personal-select-value").evaluate(node => node.clientWidth);
      assert.ok(width >= 100, "the exact current model remains readable on a phone");
      const readback = page.getByText("速度 Fast · 推理 high", {exact: true});
      assert.ok((await readback.boundingBox()).height < 30, "speed and reasoning do not wrap into a vertical column");
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
      return { coverageEntries: context.coverageEntries, note: "Same-model selection preserves Session identity; a changed exact model value creates one distinct Session through the compiled UI and synthetic HTTP store." };
    } finally {
      await context.close();
    }
  },
};
