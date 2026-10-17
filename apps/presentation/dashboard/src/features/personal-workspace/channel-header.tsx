import { List, Bot, Eye, FolderOpen, Menu, RefreshCw, SlidersHorizontal } from "lucide-react";
import { GoalLifecycleControl, GoalMastheadIdentity } from "./goal-masthead";

import { useWorkspaceI18n } from "./i18n";
import type { ManagerChannelBinding, ManagerRuntimeSessionReadback } from "../../data/chat";
import type { WorkspaceAgentOption, WorkspaceGoal, WorkspaceGoalTab } from "./personal-workspace-model";
import { WorkspaceSelect } from "./workspace-select";
import { discoverAgentModelOptions, type AgentModelDiscovery } from "../../data/chat";
import { useEffect, useState } from "react";

export function ChannelHeader({
  agents,
  agentWorkActive = false,
  conversationScope,
  goalLifecycleBusy,
  managerChannelBinding,
  managerChatOpen,
  managerRuntime,
  mobileNavigationOpen,
  onOpenGoalCapabilities,
  onOpenGoalDetails,
  onOpenAllWork,
  allWorkOpen,
  onOpenManagerChat,
  onOpenManagerSettings,
  onOpenConversationSettings,
  onOpenWorkspace,
  onRefresh,
  onRequestGoalLifecycle,
  onOpenNavigation,
  onSelectGoalTab,
  onSelectAgent,
  onSelectAgentModel,
  onReturnManagerHome,
  refreshState,
  readOnlySourceLabel,
  resumeReviewed,
  selectedAgentId,
  selectedAgentModelId,
  selectedAgentModelReadback,
  selectedGoal,
  selectedGoalTab,
  workspaceGrantLabel,
}: {
  agents: WorkspaceAgentOption[];
  agentWorkActive?: boolean;
  /** Steward conversation scope; absent when the host grants no workspace. */
  conversationScope?: { options: { disabled?: boolean; label: string; value: string }[]; value: string; onChange: (value: string) => void } | null;
  goalLifecycleBusy?: boolean;
  /** Set while the steward conversation is scoped to a workspace. */
  workspaceGrantLabel?: string | null;
  managerChannelBinding?: ManagerChannelBinding | null;
  managerChatOpen?: boolean;
  managerRuntime?: ManagerRuntimeSessionReadback | null;
  mobileNavigationOpen?: boolean;
  onOpenGoalCapabilities?: () => void;
  onOpenGoalDetails?: () => void;
  onOpenAllWork?: () => void;
  allWorkOpen?: boolean;
  onOpenManagerChat?: () => void;
  onOpenManagerSettings?: () => void;
  onOpenConversationSettings?: () => void;
  onOpenWorkspace?: () => void;
  onRefresh?: () => void;
  /** Absent when the selected source does not authorize Goal lifecycle changes. */
  onRequestGoalLifecycle?: (operation: "stop" | "resume") => void;
  onOpenNavigation?: () => void;
  onSelectGoalTab: (tab: WorkspaceGoalTab) => void;
  onSelectAgent: (agentId: string) => void;
  onSelectAgentModel?: (modelId: string) => void;
  onReturnManagerHome?: () => void;
  refreshState?: "idle" | "loading" | "done" | "error";
  readOnlySourceLabel?: string;
  /** Resume opens the owner's reviewed preview instead of a local confirmation. */
  resumeReviewed?: boolean;
  selectedAgentId: string;
  selectedAgentModelId?: string;
  selectedAgentModelReadback?: import("../../data/chat").ChatSessionSummary;
  selectedGoal: WorkspaceGoal | null;
  selectedGoalTab: WorkspaceGoalTab;
}) {
  const { locale, t } = useWorkspaceI18n();
  const [modelDiscovery, setModelDiscovery] = useState<AgentModelDiscovery | null>(null);
  const [modelDiscoveryState, setModelDiscoveryState] = useState<"idle" | "loading" | "error">("idle");
  useEffect(() => {
    if (readOnlySourceLabel || agentWorkActive) return;
    const controller = new AbortController();
    setModelDiscovery(null);
    setModelDiscoveryState("loading");
    void discoverAgentModelOptions(selectedAgentId, controller.signal, selectedGoal?.goalId)
      .then((result) => { if (!controller.signal.aborted) { setModelDiscovery(result); setModelDiscoveryState("idle"); } })
      .catch(() => { if (!controller.signal.aborted) setModelDiscoveryState("error"); });
    return () => controller.abort();
  }, [readOnlySourceLabel, selectedAgentId, selectedGoal?.goalId, agentWorkActive]);
  const model = modelDiscovery?.model;
  const selectedModel = selectedAgentModelId ?? "";
  const pendingModel = Boolean(selectedAgentModelReadback?.agent_model_id && selectedModel
    && selectedAgentModelReadback.agent_model_id !== selectedModel);
  const modelControl = model && model.options.length ? (
    <WorkspaceSelect
      ariaLabel={locale === "zh-CN" ? "选择模型" : "Select model"}
      className="personal-agent-select personal-model-select"
      onChange={(value) => onSelectAgentModel?.(value)}
      options={[
        ...(!selectedModel ? [{ disabled: true, label: selectedAgentModelId === undefined
          ? (locale === "zh-CN" ? "正在读取当前模型…" : "Reading current model…")
          : (locale === "zh-CN" ? "运行时尚未回传模型" : "Runtime has not reported a model"), value: "" }] : []),
        ...(selectedModel && !model.options.some((option) => option.value === selectedModel)
          ? [{ disabled: true, label: `${locale === "zh-CN" ? "当前模型" : "Current model"}: ${selectedModel}`, value: selectedModel }] : []),
        ...model.options.map((option) => ({ label: option.value === selectedModel ? option.value : option.label, value: option.value })),
      ]}
      prefixLabel={pendingModel ? (locale === "zh-CN" ? "下次模型" : "Next model") : (locale === "zh-CN" ? "当前模型" : "Current model")}
      value={selectedModel}
    />
  ) : selectedModel ? <small className="personal-model-discovery">{selectedModel}</small>
    : selectedAgentModelId === "" ? <small className="personal-model-discovery">{locale === "zh-CN" ? "运行时尚未回传模型" : "Runtime has not reported a model"}</small>
    : modelDiscoveryState === "loading" ? <small className="personal-model-discovery">{locale === "zh-CN" ? "正在读取模型…" : "Reading models…"}</small>
    : modelDiscoveryState === "error" ? <small className="personal-model-discovery">{locale === "zh-CN" ? "无法读取模型" : "Models unavailable"}</small> : null;
  // The chip reports the selected executor, whose credential pays for it, and
  // the resolved model, so an executor and a model that disagree are visible
  // instead of arriving as one silent configuration.
  const managerExecutionKindLabel = managerChannelBinding
    ? managerChannelBinding.executor_kind === "individual"
      ? t("header.managerExecutorKindIndividual")
      : managerChannelBinding.executor_kind === "managed"
        ? t("header.managerExecutorKindManaged")
        : t("header.managerExecutorKindRegistered")
    : null;
  const managerExecutionUnavailable = managerChannelBinding?.available === false;
  const managerOutputTokenBudget = managerChannelBinding?.output_token_budget;
  const managerOutputTokenBudgetLabel = managerOutputTokenBudget?.scope === "per_model_request"
    && managerOutputTokenBudget.valid
    && typeof managerOutputTokenBudget.max_tokens === "number"
    ? t("header.managerOutputTokenBudget", {
      tokens: new Intl.NumberFormat(locale).format(managerOutputTokenBudget.max_tokens),
    })
    : null;
  // Name the reason instead of one hardcoded host: the channel can hold the
  // managed host through its segment transport now, so "this channel needs
  // codex" would be both wrong and unactionable. An unknown reason stays
  // unclaimed rather than being rendered as a reason this build invented.
  const managerExecutionUnavailableReason = managerChannelBinding?.available === false
    ? managerChannelBinding.unavailable_reason
    : null;
  const managerExecutionUnavailableKey = managerExecutionUnavailableReason === "operator_credential_unconfigured"
    ? "header.managerExecutionUnavailableCredential"
    : managerExecutionUnavailableReason === "dsh_runtime_unavailable"
      ? "header.managerExecutionUnavailableRuntime"
      : managerExecutionUnavailableReason === "invalid_reasoning_effort"
        ? "header.managerExecutionUnavailableEffort"
        : managerExecutionUnavailableReason === "invalid_output_token_limit"
          ? "header.managerExecutionUnavailableOutputBudget"
        : "header.managerExecutionUnavailable";
  // The shipped default is one endpoint, so the chip names it and the one way
  // to move it; without this a steward the operator selected looks identical to
  // the one every machine runs, and the reason stays in the binding's typed
  // field instead of being invented here.
  const managerExecutionDefaultReason = managerChannelBinding
    && managerChannelBinding.executor_endpoint_source === "product_default"
    && managerChannelBinding.executor_endpoint_default_reason === "steward_channel_default"
    ? "header.managerEndpointStewardDefault"
    : null;
  const managerSelectionPolicyLabel = managerChannelBinding
    ? t(managerChannelBinding.selection_policy === "pinned"
      ? "header.managerSelectionPinned"
      : managerChannelBinding.selection_policy === "flexible"
        ? "header.managerSelectionFlexible"
        : "header.managerSelectionPreferred")
    : null;
  const managerAllocationReasonLabel = managerChannelBinding?.allocation_reason
    ? t(managerChannelBinding.allocation_reason === "user_explicit"
      ? "header.managerAllocationUser"
      : managerChannelBinding.allocation_reason === "pinned_configuration"
        ? "header.managerAllocationPinned"
        : managerChannelBinding.allocation_reason === "flexible_availability_fallback"
          ? "header.managerAllocationFallback"
          : managerChannelBinding.allocation_reason === "flexible_pool_unavailable"
            ? "header.managerAllocationUnavailable"
            : managerChannelBinding.allocation_reason === "flexible_primary_available"
              ? "header.managerAllocationPrimary"
              : managerChannelBinding.allocation_reason === "product_default"
                ? "header.managerAllocationProductDefault"
                : managerChannelBinding.allocation_reason === "service_override"
                  ? "header.managerAllocationService"
                  : "header.managerAllocationConfigured")
    : null;

  const runtimeControl = agentWorkActive ? null : readOnlySourceLabel ? (
    <span className="personal-read-only-source" title={t("header.readOnlySourceDescription", { source: readOnlySourceLabel })}><Eye size={15} />{readOnlySourceLabel}<small>{t("common.readOnly")}</small></span>
  ) : <>
    <WorkspaceSelect
            ariaLabel={t("header.selectChatRuntime")}
            className="personal-agent-select"
            icon={<Bot size={16} />}
            onChange={onSelectAgent}
            options={agents.map((agent) => ({
              disabled: !agent.available,
              label: `${agent.label}${agent.available ? "" : ` · ${t("header.agentUnavailable")}`}`,
              value: agent.agentId,
            }))}
            prefixLabel={selectedGoal ? (locale === "zh-CN" ? "执行器" : "Executor") : t("header.chatRuntime")}
            value={selectedAgentId}
    />
    {modelControl}
    {pendingModel ? <small className="personal-model-discovery">{locale === "zh-CN" ? "当前" : "Current"}: {selectedAgentModelReadback?.agent_model_id}</small> : null}
    {selectedAgentModelReadback?.agent_model_id === selectedModel && selectedModel
      && (selectedAgentModelReadback.agent_service_tier || selectedAgentModelReadback.agent_reasoning_effort)
      ? <small className="personal-model-discovery" title={`${locale === "zh-CN" ? "运行时回传" : "Runtime readback"}: service_tier=${selectedAgentModelReadback.agent_service_tier ?? "—"}; reasoning_effort=${selectedAgentModelReadback.agent_reasoning_effort ?? "—"}`}>
        {[selectedAgentModelReadback.agent_service_tier ? `${locale === "zh-CN" ? "速度" : "Speed"} ${["priority", "fast"].includes(selectedAgentModelReadback.agent_service_tier) ? "Fast" : selectedAgentModelReadback.agent_service_tier}` : null,
          selectedAgentModelReadback.agent_reasoning_effort ? `${locale === "zh-CN" ? "推理" : "Reasoning"} ${selectedAgentModelReadback.agent_reasoning_effort}` : null].filter(Boolean).join(" · ")}
      </small> : null}
    {selectedGoal && onOpenConversationSettings ? <button className="personal-icon-button" onClick={onOpenConversationSettings}
      aria-label={locale === "zh-CN" ? "对话与模型设置" : "Conversation and model settings"} type="button"><SlidersHorizontal size={16}/></button> : null}
  </>;

  const executionChipClass = managerExecutionUnavailable
    ? "personal-execution-chip is-unavailable" : "personal-execution-chip";
  const executionChipContent = managerChannelBinding ? <>
    <span className="personal-execution-chip-endpoint">{managerChannelBinding.executor_endpoint}</span>
    {managerExecutionKindLabel ? <span className="personal-execution-chip-kind">{managerExecutionKindLabel}</span> : null}
    <span className="personal-execution-chip-model">{managerChannelBinding.model}</span>
    {managerChannelBinding.reasoning_effort ? <span className="personal-execution-chip-model">{managerChannelBinding.reasoning_effort}</span> : null}
    {managerOutputTokenBudgetLabel ? <span className="personal-execution-chip-budget">{managerOutputTokenBudgetLabel}</span> : null}
    {onOpenManagerSettings ? <SlidersHorizontal aria-hidden size={12} /> : null}
  </> : null;

  // The steward channel binding describes the steward executor; a workspace
  // conversation runs on the selected runtime instead.
  const stewardBindingVisible = !selectedGoal && !workspaceGrantLabel;
  const scopeControl = !selectedGoal && managerChatOpen && conversationScope && !readOnlySourceLabel ? (
    <WorkspaceSelect
      ariaLabel={t("header.conversationScope")}
      className="personal-agent-select personal-scope-select"
      icon={<FolderOpen size={16} />}
      onChange={conversationScope.onChange}
      options={conversationScope.options}
      prefixLabel={t("header.conversationScope")}
      value={conversationScope.value}
    />
  ) : null;

  return (
    <header className="personal-channel-header" data-goal-selected={Boolean(selectedGoal)} data-workspace-scope={workspaceGrantLabel ? "true" : undefined}>
      <button aria-expanded={mobileNavigationOpen ?? false} aria-label={t("header.openGoalNavigation")} className="personal-icon-button personal-mobile-menu" onClick={onOpenNavigation} type="button"><Menu size={18} /></button>
      <div className="personal-channel-title">
        {selectedGoal ? <GoalMastheadIdentity goal={selectedGoal} onOpenDetails={onOpenGoalDetails} onOpenWorkspace={onOpenWorkspace ?? (() => undefined)} /> : <h1>{t("header.manager")}</h1>}
        {workspaceGrantLabel ? <p className="personal-channel-activity">{t("workspace.conversation", { grant: workspaceGrantLabel })}</p> : null}
        <div className="personal-manager-context">
        {stewardBindingVisible && managerChannelBinding ? (
          <p className="personal-manager-execution">
            {onOpenManagerSettings ? <button aria-label={t("header.managerModelSettings")} title={t("header.managerModelSettings")}
              className={executionChipClass} onClick={onOpenManagerSettings} type="button">{executionChipContent}</button>
              : <span className={executionChipClass}>{executionChipContent}</span>}
            {managerExecutionUnavailable ? (
              <span className="personal-execution-note">
                {t(managerExecutionUnavailableKey, {
                  executor: managerChannelBinding.executor_endpoint,
                  credential: managerChannelBinding.credential_env_var,
                })}
              </span>
            ) : null}
          </p>
        ) : null}
        {stewardBindingVisible && (managerRuntime || managerExecutionDefaultReason) ? <details className="personal-runtime-details" open={managerRuntime != null && managerRuntime.status !== "ready" ? true : undefined}><summary>{locale === "zh-CN" ? "运行环境" : "Execution environment"}</summary>
        {!selectedGoal && managerRuntime ? (
          <p>{managerRuntime.status === "ready"
            ? t("header.managerRuntime", {
              profile: managerRuntime.runtime_profile,
              sandbox: managerRuntime.sandbox,
            })
            : t("header.managerRuntimeFallback", {
              profile: managerRuntime.runtime_profile,
              sandbox: managerRuntime.sandbox,
            })}</p>
        ) : null}
            {managerSelectionPolicyLabel && managerAllocationReasonLabel && managerChannelBinding ? (
              <p>{t("header.managerAllocation", {
                policy: managerSelectionPolicyLabel,
                reason: managerAllocationReasonLabel,
              })}</p>
            ) : null}
            {managerExecutionDefaultReason && managerChannelBinding ? (
              <span className="personal-execution-rule-note">
                {t(managerExecutionDefaultReason, { executor: managerChannelBinding.executor_endpoint })}
              </span>
            ) : null}
        </details> : null}
        </div>
        {selectedGoal?.loadState ? <p role="status">{t(selectedGoal.loadState === "error" ? "startup.goalError" : "startup.goalLoading")}</p> : null}
      </div>
      {selectedGoal ? (
        <div className="personal-goal-navigation">
        <nav aria-label={t("header.goalView")} className="personal-goal-tabs">
          <button aria-current={selectedGoalTab === "overview" ? "page" : undefined} onClick={() => onSelectGoalTab("overview")} type="button">{t("header.overview")}</button>
          <button aria-current={selectedGoalTab === "tasks" ? "page" : undefined} onClick={() => onSelectGoalTab("tasks")} type="button">{t("header.tasks")}</button>
          <button aria-current={selectedGoalTab === "chat" ? "page" : undefined} onClick={() => onSelectGoalTab("chat")} type="button">{t("header.chat")}</button>
          <button aria-current={selectedGoalTab === "files" ? "page" : undefined} onClick={() => onSelectGoalTab("files")} type="button">{t("header.files")}</button>
        </nav>
        {runtimeControl}
        </div>
      ) : (
        <nav aria-label={t("header.managerView")} className="personal-goal-tabs">
          <button aria-current={!managerChatOpen ? "page" : undefined} onClick={onReturnManagerHome} type="button">{t("header.managerOverview")}</button>
          <button aria-current={managerChatOpen ? "page" : undefined} onClick={onOpenManagerChat} type="button">{t("header.chat")}</button>
        </nav>
      )}
      <div className="personal-channel-actions">
        {selectedGoal && onOpenAllWork ? <button type="button" className="personal-icon-button goal-all-work-trigger" aria-label={locale === "zh-CN" ? "打开全部工作" : "Open all work"} aria-expanded={allWorkOpen} aria-haspopup="dialog" onClick={onOpenAllWork}><List size={17} aria-hidden/></button> : null}
        {selectedGoal && !selectedGoal.loadState && onRequestGoalLifecycle ? (
          <GoalLifecycleControl busy={goalLifecycleBusy ?? false} goal={selectedGoal} onRequest={onRequestGoalLifecycle} resumeReviewed={resumeReviewed ?? true} />
        ) : null}
        {selectedGoal && onOpenGoalCapabilities ? (
          <button aria-label={t("header.goalSettings")} title={t("header.goalSettingsDescription")} className="personal-icon-button personal-goal-settings-action" onClick={onOpenGoalCapabilities} type="button"><SlidersHorizontal aria-hidden size={17} /></button>
        ) : null}
        {scopeControl}
        {!selectedGoal ? runtimeControl : null}
        {onRefresh ? (
          <span className={`personal-refresh-control is-${refreshState ?? "idle"}`}>
            {refreshState === "loading" ? <small>{t("header.refreshing")}</small> : refreshState === "done" ? <small>{t("header.refreshDone")}</small> : refreshState === "error" ? <small>{t("header.refreshFailed")}</small> : null}
            <button aria-label={refreshState === "loading" ? t("header.refreshing") : t("header.refresh")} className="personal-icon-button" disabled={refreshState === "loading"} onClick={onRefresh} type="button">
              <RefreshCw className={refreshState === "loading" ? "is-spinning" : undefined} size={17} />
            </button>
          </span>
        ) : null}
      </div>
    </header>
  );
}
