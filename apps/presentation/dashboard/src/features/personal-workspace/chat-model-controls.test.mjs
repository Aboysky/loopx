import assert from "node:assert/strict";
import { test } from "node:test";
import { chatModelControls } from "./chat-model-controls.ts";

const discovery = { model: { selected: "catalog-default", options: [
  { value: "first", label: "First", reasoning_efforts: ["low", "high"] },
  { value: "second", label: "Second", reasoning_efforts: ["low"] },
] } };

test("catalog defaults cannot become an observed model or unknown choice", () => {
  const state = chatModelControls(discovery, "", undefined);
  assert.equal(state.observedModel, null);
  assert.deepEqual(state.modelOptions.map((option) => option.value), ["first", "second"]);
  assert.deepEqual(state.reasoningOptions, []);
});

test("reasoning choices follow the selected model, without inheriting old effort", () => {
  const state = chatModelControls(discovery, "second", undefined,
    { agent_model_id: "first", agent_reasoning_effort: "high" });
  assert.deepEqual(state.reasoningOptions, [{ value: "low", label: "low" }]);
  assert.equal(state.effort, "");
  assert.equal(state.observedModel, "first");
  assert.equal(state.observedEffort, "high");
});

test("ACP-advertised thought level remains separate from observed Session", () => {
  const state = chatModelControls({ model: null, reasoning_effort: {
    selected: "low", options: [{ value: "low", label: "Quick" }, { value: "high", label: "Deep" }],
  } }, "acp-model", "high", { agent_model_id: "acp-model", agent_reasoning_effort: "low" });
  assert.equal(state.effort, "high");
  assert.equal(state.observedEffort, "low");
  assert.equal(state.reasoningOptions[1].label, "Deep");
});

test("unsupported or unavailable reasoning is not replaced with invented options", () => {
  assert.deepEqual(chatModelControls(null, "first", "high").reasoningOptions, []);
  assert.deepEqual(chatModelControls({ model: { options: [{ value: "first" }] } }, "first", undefined).reasoningOptions, []);
});
