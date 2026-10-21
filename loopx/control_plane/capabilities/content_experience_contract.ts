/** Transport types for Content-Ops learning models; no Node runtime dependency. */
export type ExperienceParameter = {id: string; label: string; choices: {id: string; label: string}[]; default: string};
export type ExperienceState = {id: string; label: string; description: string; terminal: boolean; goal: boolean};
export type ExperienceAction = {id: string; label: string; cost: number};
export type ExperiencePolicy = {id: string; label: string; choices: {state: string; action: string}[]};
export type ExperienceScenario = {id: string; label: string; parameters: Record<string, string>};
export type ExperiencePlan = {
  schema_version: "content_ops_experience_v0"; title: string; learning_goal: string;
  source_ref: string; boundary: string; assumptions: string[]; initial_state: string;
  budget: number; max_steps: number; parameters: ExperienceParameter[]; states: ExperienceState[];
  actions: ExperienceAction[]; transitions: {from: string; action: string; to: string; when: Record<string, string>; feedback: string}[];
  policies: ExperiencePolicy[]; scenarios: ExperienceScenario[];
};
export type ExperienceFrame = {state: string; action: string | null; feedback: string; spent: number; applied: boolean};
export type ExperienceRun = {
  ok: true; schema_version: "content_ops_experience_run_v0"; plan_digest: string;
  parameters: Record<string, string>; policy_id: string | null; scenario_id: string | null;
  trace: ExperienceFrame[]; status: "in_progress" | "goal_reached" | "terminal" | "budget_exhausted" | "action_unavailable" | "step_limit" | "policy_incomplete";
  unexecuted_actions: string[]; remaining_budget: number; learning_effect: "not_tested"; publish_authorized: false;
};
