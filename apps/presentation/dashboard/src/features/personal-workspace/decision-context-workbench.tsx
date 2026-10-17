import {useEffect, useRef, useState} from "react";
import {inspectDecisionContext, recallDecisionContext, type DecisionContextActivation, type DecisionContextRecall} from "../../data/decision-context";
import {useWorkspaceI18n} from "./i18n";
import "./content-reference-workbench.css";

/** Explicit per-page profile copy; no browser storage or durable binding. */
export function DecisionContextWorkbench({goalId}: Readonly<{goalId: string}>) {
  const {locale} = useWorkspaceI18n();
  const copy = (cn: string, en: string) => locale === "zh-CN" ? cn : en;
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [agent, setAgent] = useState("");
  const [scope, setScope] = useState("");
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState(4);
  const [activation, setActivation] = useState<DecisionContextActivation | null>(null);
  const [result, setResult] = useState<DecisionContextRecall | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const importGeneration = useRef(0);
  const recallReady = activation?.available && activation.context_provider_configured;

  function invalidate() {
    generation.current += 1;
    pending.current?.abort(); pending.current = null;
    setResult(null); setError(""); setBusy(false);
  }
  useEffect(() => () => {generation.current += 1; importGeneration.current += 1; pending.current?.abort();}, []);

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setActivation(null); setResult(null); setError(""); setBusy(false);
    if (!profile || !agent.trim()) return () => controller.abort();
    void inspectDecisionContext({goal_id: goalId, agent_id: agent, profile}, controller.signal)
      .then(value => {if (current) setActivation(value);})
      .catch(() => {if (current) setError(copy("配置检查失败，请重试。", "Profile inspection failed. Retry."));});
    return () => {current = false; controller.abort();};
  }, [profile, agent, goalId]);

  function clear({keepFile = false, keepQuery = false} = {}) {
    importGeneration.current += 1; invalidate(); setProfile(null); setAgent("");
    setActivation(null); if (!keepQuery) setQuery(""); setScope(""); setLimit(4);
    if (!keepFile && input.current) input.current.value = "";
  }
  async function importProfile(file?: File) {
    clear({keepFile: true, keepQuery: true}); const revision = importGeneration.current;
    if (!file) return;
    try {
      if (file.size > 240 * 1024) throw new Error();
      const value: unknown = JSON.parse(await file.text());
      if (revision !== importGeneration.current) return;
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error();
      const next = value as Record<string, unknown>;
      const agents = Array.isArray(next.enabled_agents) ? next.enabled_agents.filter((item): item is string => typeof item === "string") : [];
      const context = next.context_provider && typeof next.context_provider === "object" ? next.context_provider as Record<string, unknown> : {};
      setProfile(next); setAgent(agents[0] ?? "");
      setScope(typeof context.scope_ref === "string" ? context.scope_ref : "goal");
      setLimit(typeof context.max_results === "number" ? context.max_results : 4);
    } catch {
      if (revision === importGeneration.current) setError(copy("无法导入 profile。请使用不超过 240 KiB 的 JSON 对象。", "Cannot import profile. Use a JSON object up to 240 KiB."));
    }
  }
  async function recall() {
    if (pending.current || busy || !profile || !recallReady || !query.trim()) return;
    invalidate(); const revision = generation.current;
    const controller = new AbortController(); pending.current = controller; setBusy(true);
    try {
      const value = await recallDecisionContext({goal_id: goalId, agent_id: agent, profile, query, context_scope_ref: scope, max_results: limit}, controller.signal);
      if (revision === generation.current) setResult(value);
    } catch {
      if (revision === generation.current) setError(copy("召回失败。配置或服务恢复后可重试。", "Recall failed. Restore the profile or service and retry."));
    } finally {if (revision === generation.current) {setBusy(false); pending.current = null;}}
  }
  const status = result?.status ?? activation?.status;
  const reason = result?.reason_code ?? activation?.reason_code;
  const statusCopy: Record<string, string> = {
    available: copy("配置检查通过，可以尝试召回", "Profile checks passed; recall can be attempted"),
    disabled: copy("本页召回已停用", "Recall disabled in this page"),
    agent_not_enabled: copy("此 Agent 未在 profile 中启用", "Agent is not enabled by the profile"),
    profile_invalid: copy("Profile 无效或与当前 Goal 不符", "Profile invalid or outside the selected Goal"),
    provider_unavailable: copy("Provider 暂不可用", "Provider unavailable"),
    unavailable: copy("Provider 暂不可用", "Provider unavailable"),
    failed: copy("Provider 召回失败，可恢复后重试", "Provider recall failed; restore and retry"),
    completed: copy("召回完成", "Recall completed"),
  };
  const reasonCopy: Record<string, string> = {
    scope_mismatch: copy("本次 Scope 与语料不匹配", "This scope does not match the corpus"),
    corpus_unavailable: copy("语料缺失或不可读，恢复后可重试", "Corpus missing or unreadable; restore and retry"),
    context_provider_not_configured: copy("Profile 尚未配置召回 provider", "No recall provider configured in this profile"),
  };
  return <section className="personal-capability-field-summary personal-content-reference personal-decision-context" aria-label={copy("决策证据召回", "Decision evidence recall")}>
    <p>{copy("导入现有私有 profile，为当前问题召回证据。配置发给本机服务；发起召回时，查询才发送给所选 provider。离开或清除本页后移除配置与结果。", "Import an existing private profile to recall evidence for your question. The profile goes to this local service; only recall sends the query to the selected provider. Leaving or clearing the page removes its profile and results.")}</p>
    <label>{copy("导入私有 profile JSON", "Import private profile JSON")}<input ref={input} type="file" accept=".json,application/json" onChange={event => void importProfile(event.target.files?.[0])} /></label>
    {!profile ? <p>{copy("尚未导入 profile；不会调用 provider。", "No profile loaded; the provider is not called.")}</p> : <>
      <label>{copy("Agent", "Agent")}<input value={agent} maxLength={200} onChange={event => {invalidate(); setActivation(null); setAgent(event.target.value);}} /></label>
      <label><input type="checkbox" checked={profile.enabled === true} onChange={event => {invalidate(); setActivation(null); setProfile({...profile, enabled: event.target.checked});}} />{copy("仅在本页启用召回", "Enable recall in this page only")}</label>
      <label>{copy("要找什么证据？", "What evidence do you need?")}<textarea rows={3} maxLength={1000} value={query} onChange={event => {invalidate(); setQuery(event.target.value);}} /></label>
      <details><summary>{copy("调整本次检索范围", "Adjust this retrieval")}</summary>
        <label>{copy("Scope", "Scope")}<input value={scope} maxLength={2048} onChange={event => {invalidate(); setScope(event.target.value);}} /></label>
        <label>{copy("最多结果数", "Maximum results")}<input type="number" min={1} max={8} value={limit} onChange={event => {invalidate(); setLimit(Number(event.target.value));}} /></label>
      </details>
      <div className="personal-capability-actions">
        <button className="is-primary" type="button" disabled={busy || !recallReady || !query.trim() || !scope.trim()} onClick={() => void recall()}>{busy ? copy("召回中…", "Recalling…") : copy("召回证据", "Recall evidence")}</button>
        <button type="button" onClick={() => {invalidate(); setProfile({...profile});}}>{copy("重新检查配置", "Recheck profile")}</button>
      </div>
    </>}
    {status ? <p role="status">{!result && activation?.available && !activation.context_provider_configured
      ? reasonCopy.context_provider_not_configured
      : reason && reasonCopy[reason] ? reasonCopy[reason] : statusCopy[status] ?? status}{reason ? ` · ${reason}` : ""}</p> : null}
    {error ? <p role="alert" className="personal-machine-error">{error}</p> : null}
    {result?.ok ? <section aria-label={copy("召回结果", "Recall results")} aria-live="polite">
      <p>{result.results.length} {copy("条结果", "results")} · {result.provider} · {result.observed_at}</p>
      <small>{copy("分数只用于该 provider 内的排序，不代表置信度。", "Scores rank hits within this provider; they are not confidence.")}</small>
      {!result.results.length ? <p>{copy("没有匹配证据。可修改问题或本次检索范围。", "No matching evidence. Refine your question or retrieval scope.")}</p> : null}
      {result.results.map(hit => <article key={hit.provider_ref} className="personal-capability-linked-setting"><div>
        <strong>{hit.summary}</strong><p className="decision-context-hit">{hit.content}</p>
        {hit.score !== null ? <small>{copy("相关度", "Relevance")}: {hit.score.toPrecision(3)}</small> : null}
      </div></article>)}
    </section> : null}
    <p><small>{copy("召回内容是不可信的参考材料。当前操作不写入原 profile、记忆、游标或 Goal，不启用自动 hook，也不授予执行权限。", "Retrieved content is untrusted advisory material. This operation does not write the original profile, memory, cursors or Goal, enable automatic hooks, or grant execution authority.")}</small></p>
    <div className="personal-capability-actions"><button type="button" onClick={() => clear()}>{copy("清除本页配置与结果", "Clear page profile and results")}</button></div>
  </section>;
}
