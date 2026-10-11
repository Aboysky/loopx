import { ArrowRight, Check, Circle, Info, X } from "lucide-react";
import { DeliveryReview } from "./delivery-review";
import { goalAcceptanceContractCopy } from "./delivery-review-copy";
import { GoalAcceptanceObservationCard } from "./goal-acceptance-observation-card";
import type { WorkspaceDrawerSelection, WorkspaceGoal, WorkspaceGoalTab, WorkspaceModel, WorkspaceTimelineItem } from "./personal-workspace-model";
import { useWorkspaceI18n } from "./i18n";
import "./goal-overview.css";

export const goalOverviewAttentionId = "goal-overview-attention";

type CriterionState = "verified" | "failing" | "unverified";

/** Owner-recorded results for the current contract revision; anything else is not yet verified. */
function criterionStates(contract: Extract<NonNullable<NonNullable<WorkspaceGoal["acceptanceObservation"]>["goal_acceptance_contract"]>, { enabled: true }>) {
  const verification = contract.verification?.contract_revision === contract.revision ? contract.verification : null;
  const results = new Map((verification?.results ?? []).map((result) => [result.criterion_id, result.passed]));
  return contract.criteria.map((criterion) => ({
    ...criterion,
    state: (results.has(criterion.id) ? (results.get(criterion.id) ? "verified" : "failing") : "unverified") as CriterionState,
  }));
}

export function GoalOverview({ active, goal, items, userTodos, readOnly, onOpenDetails, onSelect, onView }: {
  active: boolean; goal: WorkspaceGoal; items: WorkspaceTimelineItem[]; userTodos: WorkspaceModel["userTodos"];
  readOnly: boolean; onOpenDetails: () => void; onSelect: (selection: WorkspaceDrawerSelection) => void; onView: (view: WorkspaceGoalTab) => void;
}) {
  const { t, locale } = useWorkspaceI18n();
  const copy = locale === "zh-CN" ? {
    direction: "方向", agentSummary: "Agent 的进展摘要", attention: "需要你", details: "Goal 信息",
    tasks: "查看任务", execution: "执行记录", optional: "{count} 项可选",
    noTarget: "尚未声明可衡量目标。目标通过 Goal 的验收配置声明。",
    verified: "{passed}/{total} 项条件已核验", criterion: { verified: "已核验", failing: "未通过", unverified: "尚未核验" },
    remote: "此来源仅提供同步的状态与验收观察，交付链需要实时本机来源。",
  } : {
    direction: "Direction", agentSummary: "Agent's progress summary", attention: "Needs you", details: "Goal information",
    tasks: "View tasks", execution: "Execution", optional: "{count} optional",
    noTarget: "No measurable target declared. Targets are declared through the Goal's acceptance configuration.",
    verified: "{passed} of {total} criteria verified", criterion: { verified: "Verified", failing: "Failing", unverified: "Not yet verified" },
    remote: "This source provides synchronized status and acceptance observations. The delivery chain requires the live local source.",
  };
  const attention = userTodos.filter(item => item.goalId === goal.goalId);
  const blocking = attention.filter(item => item.blocking).length;
  const run = items.find((item): item is Extract<WorkspaceTimelineItem, { kind: "run" }> => item.kind === "run" && item.run.goalId === goal.goalId);
  const observation = goal.acceptanceObservation?.goal_id === goal.goalId ? goal.acceptanceObservation : null;
  const contract = observation?.goal_acceptance_contract?.enabled === true ? observation.goal_acceptance_contract : null;
  const criteria = contract ? criterionStates(contract) : [];
  const passed = criteria.filter(criterion => criterion.state === "verified").length;
  const acceptanceCopy = goalAcceptanceContractCopy[locale === "zh-CN" ? "zh-CN" : "en"];
  return <section className="goal-overview" aria-label={t("header.overview")}>
    <header className="goal-overview-heading"><h2>{t("header.overview")}</h2><button onClick={onOpenDetails} type="button"><Info size={15} />{copy.details}</button></header>
    <div className={`goal-overview-summary${attention.length ? " has-attention" : ""}`}>
      <section className="goal-overview-direction" aria-label={copy.direction}>
        <header><h3>{copy.direction}</h3>{contract ? <span>{acceptanceCopy.verificationState[contract.status]}</span> : null}</header>
        {contract ? <>
          <strong>{contract.objective || acceptanceCopy.unknown}</strong>
          {criteria.length ? <>
            <p>{copy.verified.replace("{passed}", String(passed)).replace("{total}", String(criteria.length))}</p>
            <ul className="goal-overview-criteria">{criteria.map(criterion => <li className={`is-${criterion.state}`} key={criterion.id}>
              {criterion.state === "verified" ? <Check aria-hidden size={14} /> : criterion.state === "failing" ? <X aria-hidden size={14} /> : <Circle aria-hidden size={12} />}
              <span>{criterion.description}</span><small>{copy.criterion[criterion.state]}</small>
            </li>)}</ul>
          </> : null}
          <p><small>{copy.agentSummary}</small> {goal.nextSentence}</p>
        </> : <>
          <small>{copy.agentSummary}</small>
          <strong>{goal.nextSentence}</strong>
          {goal.agentSentence && goal.agentSentence !== goal.nextSentence ? <p>{goal.agentSentence}</p> : null}
          <p className="goal-overview-quiet">{copy.noTarget}</p>
        </>}
        {run ? <button className="goal-overview-run" type="button" onClick={() => onSelect({ kind: "run", item: run.run })}><small>{copy.execution} · {run.run.agentLabel}</small><strong>{run.run.title}</strong><ArrowRight size={15} /></button> : null}
      </section>
      {attention.length ? <section className="goal-overview-attention" id={goalOverviewAttentionId} tabIndex={-1}>
        <header><h3>{copy.attention}</h3><span>{blocking}{attention.length > blocking ? ` · ${copy.optional.replace("{count}", String(attention.length - blocking))}` : ""}</span></header>
        <ul>{attention.slice(0, 3).map(item => <li key={item.todoId}><button type="button" onClick={() => onSelect({ kind: "attention", item })}><span>{item.text}</span><ArrowRight size={15} /></button></li>)}</ul>
        {attention.length > 3 ? <button type="button" onClick={() => onView("tasks")}>{copy.tasks} ({attention.length})<ArrowRight size={14} /></button> : null}
      </section> : null}
    </div>
    {readOnly ? <><p className="goal-overview-source-note">{copy.remote}</p><GoalAcceptanceObservationCard goal={goal} /></>
      : <DeliveryReview active={active} goal={goal} items={items} userTodos={userTodos} onSelect={onSelect} />}
  </section>;
}
