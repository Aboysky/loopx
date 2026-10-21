import {useEffect, useRef, useState} from "react";
import type {ExperiencePlan, ExperienceRun} from "../../../../../../loopx/control_plane/capabilities/content_experience_contract";
import {drawExperienceScene, experienceSceneHeight, experienceFrameFeedback, type ExperienceSceneRow} from "./content-experience-scene";
import {useWorkspaceI18n} from "./i18n";
import "./content-experience-workbench.css";

type Artifact = {experience_id: string; revision: number; plan_digest: string; plan: ExperiencePlan};
type Entry = {experience_id: string; title: string; status: string; revision?: number};
type Mode = "explore" | "game" | "world";
const ENDPOINT = "/api/chat/content-experience";
async function request(goalId: string, action: string, values: Record<string, unknown> = {}) {
  const response = await fetch(ENDPOINT, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({goal_id: goalId, action, ...values})});
  if (!response.ok) throw new Error("source_unavailable");
  return response.json();
}
function download(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ContentExperienceWorkbench({goalId, onRecordingChange}: {goalId: string; onRecordingChange?: (active: boolean) => void}) {
  const {locale} = useWorkspaceI18n(), cn = locale === "zh-CN";
  const [entries, setEntries] = useState<Entry[] | null>(null), [selected, setSelected] = useState<Artifact | null>(null);
  const [error, setError] = useState(""), [loading, setLoading] = useState(false), [recording, setRecording] = useState(false);
  const generation = useRef(0);
  async function load(ident?: string) {
    const revision = ++generation.current; setLoading(true); setError("");
    try {
      const library = await request(goalId, "list");
      const target = ident ?? library.experiences.find((e: Entry) => e.status === "ready")?.experience_id;
      const item = target ? await request(goalId, "inspect", {experience_id: target}) : null;
      if (revision === generation.current) {setEntries(library.experiences); setSelected(item);}
    } catch {if (revision === generation.current) setError(cn ? "模型不可读或来源已变化。请重新读取，或让 Agent 修复原模型。" : "The model is unreadable or changed. Reload, or ask your Agent to repair its source.");}
    finally {if (revision === generation.current) setLoading(false);}
  }
  useEffect(() => {setSelected(null); setEntries(null); void load(); return () => {generation.current++;};}, [goalId]);
  return <section className="content-experience" aria-label={cn ? "交互创作" : "Interactive creation"}>
    <header className="experience-heading"><div><h3>{cn ? "把机制变成可操作的学习任务" : "Turn a mechanism into a learning task"}</h3>
      <p>{cn ? "让 Agent 准备目标、条件与转移规则，在这里探索、决策并回看结果。" : "Have your Agent prepare the goal, conditions and transition rules. Explore, decide and inspect the result here."}</p></div>
      <button type="button" disabled={loading || recording} onClick={() => void load(selected?.experience_id)}>{cn ? "重新读取" : "Reload source"}</button></header>
    {error ? <p role="alert">{error}</p> : null}
    {loading ? <p role="status">{cn ? "正在读取模型…" : "Loading the model…"}</p> : null}
    {entries && !entries.length ? <p>{cn ? "还没有准备好的模型。把要解释的机制交给 Agent，它会通过 Content-Ops 保存可复用的学习任务。" : "No model is prepared yet. Tell your Agent what to explain; Content-Ops can retain the reusable learning task."}</p> : null}
    {entries?.length ? <label className="experience-model-picker">{cn ? "学习模型" : "Learning model"}<select disabled={loading || recording} value={selected?.experience_id ?? ""} onChange={e => void load(e.target.value)}>
      {entries.map(e => <option key={e.experience_id} value={e.experience_id}>{e.title}{e.status === "damaged" ? (cn ? " · 来源损坏" : " · source damaged") : ""}</option>)}</select></label> : null}
    {selected ? <ExperiencePlayer key={`${goalId}:${selected.experience_id}:${selected.revision}`} artifact={selected} goalId={goalId} stale={loading || Boolean(error)} reload={() => void load(selected.experience_id)}
      onRecording={value => {setRecording(value); onRecordingChange?.(value);}} /> : null}
  </section>;
}

function ExperiencePlayer({artifact, goalId, stale, reload, onRecording}: {artifact: Artifact; goalId: string; stale: boolean; reload: () => void; onRecording: (active: boolean) => void}) {
  const {locale} = useWorkspaceI18n(), cn = locale === "zh-CN", p = artifact.plan;
  const [mode, setMode] = useState<Mode>("explore"), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [needsReload, setNeedsReload] = useState(false);
  useEffect(() => {setNeedsReload(false); setError("");}, [artifact]);
  const defaults = Object.fromEntries(p.parameters.map(v => [v.id, v.default]));
  const [conditions, setConditions] = useState([ {...defaults, ...p.scenarios[0]!.parameters}, {...defaults, ...(p.scenarios[1] ?? p.scenarios[0])!.parameters} ]);
  const [explorePolicy, setExplorePolicy] = useState(p.policies[0]!.id), [explored, setExplored] = useState<ExperienceRun[]>([]);
  const [gameScenario, setGameScenario] = useState(p.scenarios[0]!.id), [actions, setActions] = useState<string[]>([]), [game, setGame] = useState<ExperienceRun | null>(null);
  const [worldScenarios, setWorldScenarios] = useState([p.scenarios[0]!.id, p.scenarios[0]!.id]), [worldPolicies, setWorldPolicies] = useState([p.policies[0]!.id, (p.policies[1] ?? p.policies[0])!.id]);
  const [world, setWorld] = useState<ExperienceRun[]>([]), [positions, setPositions] = useState([0, 0]);
  const [prediction, setPrediction] = useState(""), [explanation, setExplanation] = useState("");
  const [recording, setRecording] = useState(false), [recordUrl, setRecordUrl] = useState("");
  const [recordAvailable, setRecordAvailable] = useState(false);
  const pending = useRef(false), mounted = useRef(true), player = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null), recorder = useRef<MediaRecorder | null>(null), recordFile = useRef("");
  const [focused, setFocused] = useState(false);
  const recordUrlRef = useRef("");
  const releaseRecording = useRef(() => {});
  useEffect(() => {const changed = () => setFocused(document.fullscreenElement === player.current); document.addEventListener("fullscreenchange", changed); return () => document.removeEventListener("fullscreenchange", changed);}, []);
  useEffect(() => {mounted.current = true; setRecordAvailable(typeof MediaRecorder !== "undefined" && typeof HTMLCanvasElement.prototype.captureStream === "function");
    return () => {mounted.current = false; if (recorder.current?.state === "recording") recorder.current.stop(); releaseRecording.current(); if (recordUrlRef.current) URL.revokeObjectURL(recordUrlRef.current); onRecording(false);};}, []);
  const status = (r?: ExperienceRun | null) => ({in_progress: cn ? "等待下一步" : "Next decision", goal_reached: cn ? "模型目标达成" : "Model goal reached", terminal: cn ? "目标未达成" : "Goal not reached", budget_exhausted: cn ? "预算不足" : "Budget exhausted", action_unavailable: cn ? "条件不允许这一步" : "Action unavailable", step_limit: cn ? "达到步数上限" : "Step limit", policy_incomplete: cn ? "策略未覆盖当前状态" : "Policy incomplete"}[r?.status ?? "in_progress"]);
  async function run(input: Record<string, unknown>): Promise<ExperienceRun> {
    return request(goalId, "run", {experience_id: artifact.experience_id, expected_revision: artifact.revision, run: input});
  }
  async function perform(work: () => Promise<void>) {
    if (pending.current || stale) return; pending.current = true; setBusy(true); setError("");
    try {await work();} catch {if (mounted.current) {setNeedsReload(true); setError(cn ? "本次结果未确认，原结果保留。请重新读取来源后再操作。" : "This result is unconfirmed; the last result is retained. Reload the source before continuing.");}}
    finally {pending.current = false; if (mounted.current) setBusy(false);}
  }
  const gameState = p.states.find(s => s.id === (game?.trace.at(-1)?.state ?? p.initial_state))!;
  const rows: ExperienceSceneRow[] = mode === "game" ? [{label: cn ? "你的决策" : "Your decisions", run: game, index: game ? game.trace.length - 1 : 0}]
    : mode === "explore" ? [0, 1].map(i => ({label: `${cn ? "条件" : "Conditions"} ${i ? "B" : "A"}`, run: explored[i] ?? null, index: explored[i] ? explored[i]!.trace.length - 1 : 0}))
      : [0, 1].map(i => ({label: p.policies.find(v => v.id === worldPolicies[i])!.label, run: world[i] ?? null, index: positions[i]!}));
  useEffect(() => {
    const el = canvas.current; if (!el) return;
    let animation = 0;
    const draw = () => {
      const width = Math.max(280, Math.round(el.getBoundingClientRect().width)), height = experienceSceneHeight(width, rows.length), ratio = Math.min(devicePixelRatio || 1, 2);
      if (el.width !== Math.round(width * ratio) || el.height !== Math.round(height * ratio)) {el.width = Math.round(width * ratio); el.height = Math.round(height * ratio); el.style.height = `${height}px`;}
      const ctx = el.getContext("2d"); if (ctx) {ctx.setTransform(ratio, 0, 0, ratio, 0, 0); drawExperienceScene(ctx, width, height, p, rows, artifact.plan_digest, locale);}
      if (recording) animation = requestAnimationFrame(draw);
    };
    const observer = new ResizeObserver(() => {if (!recording) draw();}); observer.observe(el); draw();
    return () => {cancelAnimationFrame(animation); observer.disconnect();};
  }, [mode, explored, game, world, positions, locale, recording]);
  function startRecording() {
    if (!canvas.current || recording || !recordAvailable) return;
    let stream: MediaStream | null = null;
    try {
      const type = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find(v => MediaRecorder.isTypeSupported(v));
      if (!type) throw new Error("codec unavailable");
      stream = canvas.current.captureStream(24); const chunks: Blob[] = [];
      const capture = new MediaRecorder(stream, {mimeType: type}); recorder.current = capture;
      if (recordUrlRef.current) {URL.revokeObjectURL(recordUrlRef.current); recordUrlRef.current = ""; setRecordUrl("");}
      recordFile.current = `${artifact.experience_id}-${mode}.webm`;
      let failed = false;
      capture.ondataavailable = event => {if (event.data.size) chunks.push(event.data);};
      const timer = setTimeout(() => {if (capture.state === "recording") capture.stop();}, 120000);
      const activeStream = stream;
      const release = () => {clearTimeout(timer); activeStream.getTracks().forEach(t => t.stop());};
      releaseRecording.current = release;
      capture.onstop = () => {
        release();
        if (!mounted.current || recorder.current !== capture) return;
        setRecording(false); onRecording(false);
        if (failed) return;
        const blob = new Blob(chunks, {type});
        if (!blob.size) {setError(cn ? "录制没有产生文件，请重试。" : "Recording produced no file. Retry."); return;}
        if (recordUrlRef.current) URL.revokeObjectURL(recordUrlRef.current);
        recordUrlRef.current = URL.createObjectURL(blob); setRecordUrl(recordUrlRef.current);
      };
      capture.onerror = () => {failed = true; if (capture.state === "recording") capture.stop(); release(); if (mounted.current && recorder.current === capture) {setRecording(false); onRecording(false); setError(cn ? "录制失败，请重试。" : "Recording failed. Retry.");}};
      capture.start(250); setRecording(true); onRecording(true);
    } catch {stream?.getTracks().forEach(t => t.stop()); releaseRecording.current(); setError(cn ? "此浏览器无法录制模型画面，仍可导出操作轨迹。" : "This browser cannot record the model. You can still export its decision trace.");}
  }
  async function toggleFocus() {
    try {
      if (focused) await document.exitFullscreen();
      else if (player.current?.requestFullscreen) await player.current.requestFullscreen();
      else throw new Error("fullscreen unavailable");
    } catch {setError(cn ? "专注视图暂不可用，可继续在当前页面操作。" : "Focus view is unavailable; continue in this page.");}
  }
  const disabled = busy || stale || needsReload;
  const scenarioOptions = p.scenarios.map(s => <option key={s.id} value={s.id}>{s.label}</option>);
  const policyOptions = p.policies.map(s => <option key={s.id} value={s.id}>{s.label}</option>);
  return <div className="experience-player" ref={player}>
    <div className="experience-goal"><span>{cn ? "学习目标" : "Learning goal"}</span><h4>{p.title}</h4><p>{p.learning_goal}</p>
      <button className="experience-focus" type="button" disabled={recording} onClick={() => void toggleFocus()}>{focused ? (cn ? "退出专注视图" : "Leave focus view") : (cn ? "专注学习" : "Focus on this task")}</button></div>
    <div className="experience-modes" role="group" aria-label={cn ? "学习形式" : "Learning format"}>{(["explore", "game", "world"] as Mode[]).map((value, i) => <button key={value} type="button" aria-pressed={mode === value} disabled={disabled || recording} onClick={() => {setMode(value); setError("");}}>{[cn ? "HTML · 条件探索" : "HTML · Explore conditions", cn ? "Game · 决策训练" : "Game · Make decisions", cn ? "Mini-World · 策略回放" : "Mini-World · Replay strategies"][i]}</button>)}</div>
    {error ? <div role="alert"><p>{error}</p><button type="button" disabled={busy || recording} onClick={reload}>{cn ? "重新读取来源" : "Reload source"}</button></div> : null}
    {mode === "explore" ? <section aria-label={cn ? "条件对照" : "Condition comparison"}>
      <p>{cn ? "保持策略相同，调整两组条件。先预测路径和成本，再运行并解释差异。" : "Keep the policy fixed and change the conditions. Predict the path and cost, then run and explain the difference."}</p>
      <div className="experience-controls"><label>{cn ? "共同策略" : "Shared policy"}<select disabled={disabled} value={explorePolicy} onChange={e => {setExplorePolicy(e.target.value); setExplored([]);}}>{policyOptions}</select></label></div>
      <div className="experience-comparison">{[0, 1].map(i => <fieldset key={i} disabled={disabled}><legend>{`${cn ? "条件" : "Conditions"} ${i ? "B" : "A"}`}</legend>{p.parameters.map(parameter => <label key={parameter.id}>{parameter.label}<select value={conditions[i]![parameter.id]} onChange={e => {setConditions(conditions.map((v, j) => j === i ? {...v, [parameter.id]: e.target.value} : v)); setExplored([]);}}>{parameter.choices.map(c => <option value={c.id} key={c.id}>{c.label}</option>)}</select></label>)}</fieldset>)}</div>
      <details className="experience-prediction"><summary>{cn ? "记录你的预测（可选）" : "Record your prediction (optional)"}</summary><label className="experience-reflection">{cn ? "你的预测" : "Your prediction"}<textarea maxLength={2000} value={prediction} onChange={e => setPrediction(e.target.value)} /></label></details>
      <button className="experience-primary" type="button" disabled={disabled} onClick={() => void perform(async () => {const result = await Promise.all(conditions.map(parameters => run({parameters, policy_id: explorePolicy}))); if (mounted.current) setExplored(result);})}>{cn ? "运行条件对照" : "Compare conditions"}</button>
      {explored.length ? <div className="experience-results">{explored.map((r, i) => <p key={i}><strong>{i ? "B" : "A"} · {status(r)}</strong><span>{cn ? "模型用量" : "Model effort"} {p.budget - r.remaining_budget} / {p.budget} · {r.trace.filter(f => f.action && f.applied).length} {cn ? "次有效行动" : "applied decisions"}</span></p>)}</div> : null}
    </section> : mode === "game" ? <section aria-label={cn ? "预算内达成目标" : "Reach the goal within budget"}>
      <div className="experience-controls"><label>{cn ? "任务条件（更换后重新开始）" : "Task conditions (changing restarts)"}<select disabled={disabled || recording} value={gameScenario} onChange={e => {setGameScenario(e.target.value); setActions([]); setGame(null);}}>{scenarioOptions}</select></label>
        <button type="button" disabled={disabled} onClick={() => void perform(async () => {const r = await run({scenario_id: gameScenario, actions: []}); if (mounted.current) {setActions([]); setGame(r);}})}>{cn ? "重新开始" : "Restart task"}</button></div>
      <div className="experience-game-status" role="status"><strong>{gameState.label}</strong><span>{status(game)} · {cn ? "剩余模型预算" : "Model effort left"} {game?.remaining_budget ?? p.budget}</span><p>{game ? experienceFrameFeedback(game.trace.at(-1)!, game.status, cn) : gameState.description}</p></div>
      <div className="experience-actions" aria-label={cn ? "选择下一步" : "Choose the next action"}>{p.actions.filter(a => p.transitions.some(t => t.from === gameState.id && t.action === a.id)).map(action => <button key={action.id} type="button" disabled={disabled || Boolean(game && game.status !== "in_progress")} onClick={() => void perform(async () => {const next = [...actions, action.id], r = await run({scenario_id: gameScenario, actions: next}); if (mounted.current) {setActions(next); setGame(r);}})}><span>{action.label}</span><small>{cn ? "成本" : "Cost"} {action.cost}</small></button>)}</div>
      {gameState.terminal ? <p>{cn ? "本次任务已结束。可导出记录，或重新开始检验另一条路径。" : "This attempt ended. Export the trace or restart to test another path."}</p> : null}
    </section> : <section aria-label={cn ? "策略与路径比较" : "Compare strategies and paths"}>
      <p>{cn ? "选择环境与策略，观察连续决策的后果。运行后拖动步骤，比较另一条路径。" : "Choose the environment and policy, then inspect the consequences of successive decisions. Scrub each run to compare another path."}</p>
      <div className="experience-comparison">{[0, 1].map(i => <fieldset key={i} disabled={disabled}><legend>{cn ? `路径 ${i ? "B" : "A"}` : `Path ${i ? "B" : "A"}`}</legend>
        <label>{cn ? "环境" : "Environment"}<select value={worldScenarios[i]} onChange={e => {setWorldScenarios(worldScenarios.map((v, j) => j === i ? e.target.value : v)); setWorld([]);}}>{scenarioOptions}</select></label>
        <label>{cn ? "策略" : "Policy"}<select value={worldPolicies[i]} onChange={e => {setWorldPolicies(worldPolicies.map((v, j) => j === i ? e.target.value : v)); setWorld([]);}}>{policyOptions}</select></label></fieldset>)}</div>
      <button className="experience-primary" type="button" disabled={disabled} onClick={() => void perform(async () => {const result = await Promise.all(worldScenarios.map((scenario_id, i) => run({scenario_id, policy_id: worldPolicies[i]}))); if (mounted.current) {setWorld(result); setPositions(result.map(r => r.trace.length - 1));}})}>{cn ? "运行两条策略" : "Run both strategies"}</button>
      {world.length ? <div className="experience-comparison">{world.map((r, i) => <label className="experience-replay" key={i}>{`${i ? "B" : "A"} · ${cn ? "最终" : "Final"}: ${status(r)} · ${cn ? "回放" : "Replay"} ${positions[i]} / ${r.trace.length - 1}`}<input aria-label={cn ? `路径 ${i ? "B" : "A"} 回放步骤` : `Path ${i ? "B" : "A"} replay step`} type="range" min={0} max={r.trace.length - 1} value={positions[i]} onChange={e => setPositions(positions.map((v, j) => j === i ? Number(e.target.value) : v))} /></label>)}</div> : null}
    </section>}
    <canvas ref={canvas} className="experience-canvas" role="img" aria-label={cn ? "模型路径画面；当前状态和反馈见相邻文字" : "Model path scene; current states and feedback are provided in adjacent text"} />
    {mode !== "game" ? <div className="experience-comparison experience-frame-readback" aria-live="polite">{rows.map((row, i) => {
      const frame = row.run?.trace[Math.min(row.index, row.run.trace.length - 1)];
      return frame ? <div key={i}><strong>{i ? "B" : "A"} · {p.states.find(s => s.id === frame.state)!.label}</strong><p>{experienceFrameFeedback(frame, row.run?.status, cn)}</p></div> : null;
    })}</div> : null}
    {busy ? <p role="status">{cn ? "正在计算模型路径…" : "Computing the model path…"}</p> : null}
    <div className="experience-record"><button type="button" disabled={!recording && (!recordAvailable || disabled)} aria-pressed={recording} onClick={() => recording ? recorder.current?.stop() : startRecording()}>{recording ? (cn ? "停止录制" : "Stop recording") : (cn ? "录制模型画面（静音）" : "Record model scene (silent)")}</button>
      {recording ? <span role="status">{cn ? "正在录制 · 最长 2 分钟" : "Recording · up to 2 minutes"}</span> : null}
      {!recordAvailable ? <span>{cn ? "此浏览器不支持画面录制，可导出操作轨迹。" : "Scene recording is unavailable in this browser; decision traces remain exportable."}</span> : null}
      {recordUrl ? <a download={recordFile.current} href={recordUrl}>{cn ? "下载录制 WebM" : "Download recording WebM"}</a> : null}
      <button type="button" onClick={() => download({schema_version: "content_ops_experience_session_v0", experience_id: artifact.experience_id, revision: artifact.revision, plan_digest: artifact.plan_digest, plan: p, mode, explored, game, world, prediction, explanation, learning_effect: "not_tested"}, `${artifact.experience_id}-session.json`)}>{cn ? "导出模型与操作轨迹" : "Export model and decision trace"}</button></div>
    <label className="experience-reflection">{cn ? "你观察到什么？（可选，本机导出）" : "What did you observe? (optional, local export)"}<textarea maxLength={2000} value={explanation} onChange={e => setExplanation(e.target.value)} /></label>
    <details><summary>{cn ? "规则、来源与模型边界" : "Rules, source and model boundaries"}</summary><p>{p.boundary}</p><p>{p.source_ref} · {cn ? "修订" : "Revision"} {artifact.revision}</p><ul>{p.assumptions.map(a => <li key={a}>{a}</li>)}</ul>
      <div className="experience-rules" tabIndex={0} aria-label={cn ? "模型转移规则" : "Model transition rules"}><table><thead><tr><th>{cn ? "起点" : "From"}</th><th>{cn ? "行动" : "Action"}</th><th>{cn ? "条件" : "Conditions"}</th><th>{cn ? "结果" : "To"}</th></tr></thead><tbody>{p.transitions.map((t, i) => <tr key={i}><td>{p.states.find(s => s.id === t.from)!.label}</td><td>{p.actions.find(a => a.id === t.action)!.label}</td><td>{Object.entries(t.when).map(([k, v]) => `${p.parameters.find(p => p.id === k)!.label}: ${p.parameters.find(p => p.id === k)!.choices.find(c => c.id === v)!.label}`).join("; ") || (cn ? "所有条件" : "All conditions")}</td><td>{p.states.find(s => s.id === t.to)!.label}</td></tr>)}</tbody></table></div>
      <p>{cn ? "这些结果来自声明的有限模型。学习效果需要独立评估；记录与回答只在本页保留，导出后由你保存。" : "Results follow this declared finite model. Learning effects need independent evaluation. Traces and answers remain in this page until you export them."}</p></details>
  </div>;
}
