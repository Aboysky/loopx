import { AlertCircle, ChevronRight, LoaderCircle, Pause, RotateCcw } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import {
  compileGoalWorkspaceDigest,
  type DigestExecution,
  type GoalWorkspaceDigest,
} from "../../../../../../loopx/control_plane/presentation/goal_workspace_digest.js";
import { goalHostSurfaces, hostSurfaceLabel, presentGoalActivity } from "./goal-activity";
import { relativeTime, useExecutionDetail } from "./goal-activity-view";
import { useWorkspaceI18n, type WorkspaceMessageKey } from "./i18n";
import { formatCostUsd, formatDurationMs, type WorkspaceGoal, type WorkspaceModel, type WorkspaceTimelineItem } from "./personal-workspace-model";
import "./goal-masthead.css";

function digestExecution(execution: WorkspaceGoal["execution"]): DigestExecution | undefined {
  if (!execution) return undefined;
  if (execution.kind !== "running") return execution.kind === "idle" ? { kind: "idle" } : { kind: "unknown" };
  return { kind: "running", observed: !execution.hostClaimed, quiet: execution.quiet, lastActivityAt: execution.lastActivityAt };
}

export function useGoalWorkspaceDigest(goal: WorkspaceGoal, userTodos: WorkspaceModel["userTodos"], items: WorkspaceTimelineItem[]): GoalWorkspaceDigest {
  return useMemo(() => compileGoalWorkspaceDigest({
    observedAt: new Date().toISOString(),
    activation: goal.activationState,
    todos: goal.agentTodos.map((todo) => ({
      todoId: todo.todoId, done: todo.done, status: todo.status, taskClass: todo.taskClass, dependencies: todo.dependencies,
    })),
    doneCount: goal.doneTodoCount,
    openCount: goal.openTodoCount,
    runningTodoIds: items.flatMap((item) => item.kind === "run" && item.run.goalId === goal.goalId && item.run.status === "running" && item.run.todoId ? [item.run.todoId] : []),
    attention: goal.loadState === "error" ? null : userTodos.filter((item) => item.goalId === goal.goalId).map((item) => ({ blocking: item.blocking, updatedAt: item.updatedAt })),
    usage: goal.usage,
    execution: digestExecution(goal.execution),
    activity: (goal.hostThreadActivity?.threads ?? []).map((thread) => ({ actor: hostSurfaceLabel(thread.hostSurface), at: thread.lastEventAt })),
  }), [goal, userTodos, items]);
}

export function GoalMastheadIdentity({ goal, onOpenWorkspace }: { goal: WorkspaceGoal; onOpenWorkspace: () => void }) {
  const { t } = useWorkspaceI18n();
  const agents = (goal.agentLanes ?? []).map((lane) => lane.label);
  const context = [
    agents.length > 1 ? t("masthead.team", { count: agents.length }) : agents[0],
    goal.repository?.label,
  ].filter(Boolean);
  return (
    <>
      <nav aria-label={t("masthead.breadcrumb")} className="goal-masthead-breadcrumb">
        <button onClick={onOpenWorkspace} type="button">{t("masthead.workspace")}</button>
        <ChevronRight aria-hidden size={12} />
        <span>{t("masthead.goals")}</span>
        <ChevronRight aria-hidden size={12} />
        <span aria-current="page" title={goal.title}>{goal.title}</span>
      </nav>
      <h1>{goal.title}</h1>
      {context.length ? <p className="goal-masthead-context" title={agents.join(", ")}>{context.join(" · ")}</p> : null}
    </>
  );
}

/** The one consequential control, confirmed once with the owner's stated effect.
 * A reviewed Resume already shows the owner's preview, so it is not asked twice. */
export function GoalLifecycleControl({ busy, goal, onRequest, resumeReviewed }: {
  busy: boolean; goal: WorkspaceGoal; onRequest: (operation: "stop" | "resume") => void; resumeReviewed: boolean;
}) {
  const { t } = useWorkspaceI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const stopped = goal.activationState === "stopped";
  const operation = stopped ? "resume" : "stop";
  useEffect(() => {
    if (!open) return;
    confirmRef.current?.focus();
    const close = (event: PointerEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key !== "Escape" : rootRef.current?.contains(event.target as Node)) return;
      setOpen(false);
      if (event instanceof KeyboardEvent) triggerRef.current?.focus();
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  useEffect(() => setOpen(false), [goal.goalId, goal.activationState]);
  const label = busy ? t("masthead.stopping") : t(stopped ? "sidebar.resume" : "sidebar.stop");
  return (
    <div className="goal-lifecycle-control" ref={rootRef}>
      <button
        aria-busy={busy || undefined}
        aria-expanded={stopped && resumeReviewed ? undefined : open}
        aria-haspopup={stopped && resumeReviewed ? undefined : "dialog"}
        className="goal-lifecycle-trigger"
        disabled={busy}
        onClick={() => (stopped && resumeReviewed ? onRequest("resume") : setOpen((current) => !current))}
        ref={triggerRef}
        type="button"
      >
        {busy ? <LoaderCircle aria-hidden className="is-spinning" size={15} /> : stopped ? <RotateCcw aria-hidden size={15} /> : <Pause aria-hidden size={15} />}
        <span>{label}</span>
      </button>
      {open ? (
        <div aria-labelledby={titleId} className="goal-lifecycle-confirm" role="dialog">
          <strong id={titleId}>{t(stopped ? "masthead.resumeTitle" : "masthead.stopTitle")}</strong>
          <p>{t(stopped ? "masthead.resumeEffect" : "masthead.stopEffect")}</p>
          <div>
            <button onClick={() => { setOpen(false); triggerRef.current?.focus(); }} type="button">{t("common.cancel")}</button>
            <button className="is-primary" onClick={() => { setOpen(false); onRequest(operation); }} ref={confirmRef} type="button">
              {t(stopped ? "sidebar.resumeGoal" : "sidebar.stopGoal")}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export type GoalVitalRegion = "overview" | "tasks" | "attention" | "usage";

const ribbonOrder = ["done", "running_observed", "open", "waiting_dependency", "blocked", "deferred"] as const;

function Vital({ children, label, onClick, sub, tone }: {
  children: ReactNode; label: string; onClick: () => void; sub?: ReactNode; tone?: string;
}) {
  return (
    <button className={`goal-vital${tone ? ` is-${tone}` : ""}`} onClick={onClick} type="button">
      <span className="goal-vital-label">{label}</span>
      <span className="goal-vital-value">{children}</span>
      {sub ? <span className="goal-vital-sub">{sub}</span> : null}
    </button>
  );
}

export function GoalVitals({ goal, items, onFocusRegion, userTodos }: {
  goal: WorkspaceGoal; items: WorkspaceTimelineItem[]; onFocusRegion: (region: GoalVitalRegion) => void; userTodos: WorkspaceModel["userTodos"];
}) {
  const { locale, t } = useWorkspaceI18n();
  const digest = useGoalWorkspaceDigest(goal, userTodos, items);
  const activity = presentGoalActivity(goal);
  const detail = useExecutionDetail(goal.execution);
  const finishing = digest.lifecycle.finishingTurn;
  const stateSub = finishing ? t("vitals.turnFinishing")
    : activity.alsoKey ? t(activity.alsoKey as WorkspaceMessageKey, { host: goalHostSurfaces(goal).map(hostSurfaceLabel).join(" / ") })
      : detail.length ? detail.join(" · ")
        : goal.execution?.kind === "unknown" ? t("vitals.activityUnknown") : null;

  const { work } = digest;
  const workSub = [
    work.classes.running_observed ? t("vitals.workRunning", { count: work.classes.running_observed }) : null,
    t("vitals.workOpen", { count: work.open }),
    work.classes.blocked ? t("vitals.workBlocked", { count: work.classes.blocked }) : null,
    work.done === null ? t("vitals.workDoneUnknown") : null,
  ].filter(Boolean).join(" · ");
  const ribbonTotal = ribbonOrder.reduce((sum, name) => sum + work.classes[name], 0);

  const windowLabel = digest.usage.window === "7d" ? t("vitals.window7d") : digest.usage.window === "24h" ? t("vitals.window24h") : t("vitals.notMeasured");
  const needs = digest.needsYou;
  const last = digest.lastActivity;
  const lastTime = last ? relativeTime(last.at, locale) : null;

  return (
    <section aria-label={t("vitals.label")} className="goal-vitals" data-testid="goal-vitals">
      <Vital label={t("vitals.state")} onClick={() => onFocusRegion("overview")} sub={stateSub}
        tone={finishing ? "stopped" : activity.tone}>
        <span aria-hidden className={`goal-vital-dot${activity.live && !finishing ? " is-live" : ""}`} />
        {finishing ? t("vitals.stopping") : t(activity.labelKey as WorkspaceMessageKey)}
      </Vital>
      <Vital label={t("vitals.work")} onClick={() => onFocusRegion("tasks")} sub={<>
        {work.coverage === "partial" && work.projectedOpen !== null
          ? <span className="goal-vital-partial">{t("vitals.workPartial", { listed: work.listedOpen, projected: work.projectedOpen })}</span> : workSub}
        {ribbonTotal > 0 ? <span aria-hidden className="goal-work-ribbon">{ribbonOrder.map((name) => work.classes[name]
          ? <i className={`is-${name}`} key={name} style={{ flexGrow: work.classes[name] }} /> : null)}</span> : null}
      </>}>
        {work.total === null ? work.open : <span>{work.done}<small>/{work.total}</small></span>}
      </Vital>
      <Vital label={t("vitals.needsYou")} onClick={() => onFocusRegion("attention")}
        tone={needs.availability === "ok" && needs.blocking > 0 ? "danger" : needs.availability === "ok" ? "recede" : undefined}
        sub={needs.availability !== "ok" ? null : [
          needs.blocking === 0 ? t("vitals.needsYouNone") : null,
          needs.oldestWaitingSince ? t("vitals.needsYouOldest", { time: relativeTime(needs.oldestWaitingSince, locale) ?? "" }) : null,
          needs.optional ? t("vitals.needsYouOptional", { count: needs.optional }) : null,
        ].filter(Boolean).join(" · ")}>
        {needs.availability !== "ok" ? t("vitals.unavailable") : <>{needs.blocking > 0 ? <AlertCircle aria-hidden size={15} /> : null}{needs.blocking}</>}
      </Vital>
      <Vital label={t("vitals.agentTime")} onClick={() => onFocusRegion("usage")} sub={windowLabel}
        tone={digest.usage.agentTimeMs === null ? "recede" : undefined}>
        {digest.usage.agentTimeMs === null ? "—" : formatDurationMs(digest.usage.agentTimeMs)}
      </Vital>
      <Vital label={t("vitals.cost")} onClick={() => onFocusRegion("usage")} sub={windowLabel}
        tone={digest.usage.costUsd === null ? "recede" : undefined}>
        {digest.usage.costUsd === null ? "—" : formatCostUsd(digest.usage.costUsd)}
      </Vital>
      <Vital label={t("vitals.lastActivity")} onClick={() => onFocusRegion("overview")}
        sub={last ? last.actor || t("vitals.turn") : t("vitals.noActivity")} tone={last ? undefined : "recede"}>
        {last && lastTime ? lastTime : "—"}
      </Vital>
      <span className="goal-vitals-scope">{t("vitals.scope")}</span>
    </section>
  );
}
