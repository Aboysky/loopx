import type { AgentModelDiscovery, ChatSessionSummary } from "../../data/chat";

/** Catalog choices describe the next binding; only Session readback is current. */
export function chatModelControls(
  discovery: AgentModelDiscovery | null,
  selectedModel: string,
  selectedEffort: string | undefined,
  readback?: ChatSessionSummary,
) {
  const modelOptions = discovery?.model?.options ?? [];
  const nativeEfforts = modelOptions.find((option) => option.value === selectedModel)?.reasoning_efforts;
  const reasoningOptions = nativeEfforts
    ? nativeEfforts.map((value) => ({ value, label: value }))
    : discovery?.reasoning_effort?.options ?? [];
  const observedModel = readback?.agent_model_id ?? null;
  const effort = selectedEffort ?? (observedModel && observedModel === selectedModel
    ? readback?.agent_reasoning_effort ?? "" : "");
  return { modelOptions, reasoningOptions, effort, observedModel,
    observedEffort: readback?.agent_reasoning_effort ?? null,
    observedTier: readback?.agent_service_tier ?? null };
}
