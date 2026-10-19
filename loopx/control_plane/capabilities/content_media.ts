/** Content-ops composition semantics. Rendering is an optional, local-only effect.
 * These render states are local to a composition, never publication approvals.
 */
import {createHash} from "node:crypto";
import {EffectRuntimeRequestError} from "../effect_runtime_errors.ts";
import layouts from "../../capabilities/content_ops/templates/layout-catalog-v0.json" with {type: "json"};

export const MEDIA_PLAN_SCHEMA = "content_ops_media_plan_v0";
export const MEDIA_PROTOCOL = "content_ops_media_renderer_v0";
type ObjectValue = Record<string, unknown>;
function fail(message: string): never {throw new EffectRuntimeRequestError(message);}
function object(value: unknown): ObjectValue {
  if (!value || typeof value !== "object" || Array.isArray(value)) fail("Expected an object");
  return value as ObjectValue;
}
function fields(value: ObjectValue, allowed: string[]) {
  if (Object.keys(value).some(key => !allowed.includes(key))) fail("Unsupported composition fields");
}
function text(value: unknown, max = 500): string {
  if (typeof value !== "string" || !value.trim() || value.length > max || /[\x00-\x08\x0b-\x1f]/.test(value)) fail("Invalid composition text");
  return value.trim();
}
function token(value: unknown): string {
  const result = text(value, 80);
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]*$/.test(result)) fail("Invalid composition reference");
  return result;
}
function number(value: unknown, min: number, max: number, integer = false): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max || (integer && !Number.isInteger(value))) fail("Composition timing or dimensions are outside the supported range");
  return value;
}
function array(value: unknown, max: number): unknown[] {
  if (!Array.isArray(value) || value.length > max) fail("Invalid composition list");
  return value;
}
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${stable(v)}`).join(",")}}`;
  return JSON.stringify(value);
}
export function validateMediaPlan(input: unknown) {
  const request = object(input), raw = object(request.plan);
  fields(raw, ["schema_version", "title", "width", "height", "fps", "shots", "assets", "captions", "narration", "layout_template_id"]);
  if (raw.schema_version !== MEDIA_PLAN_SCHEMA) fail("Unsupported composition schema");
  const layout = layouts.templates.find(entry => entry.template_id === (raw.layout_template_id ?? "monochrome-editorial"));
  if (!layout) fail("Select an existing content-ops layout template");
  const width = number(raw.width, 320, 1920, true), height = number(raw.height, 240, 1080, true);
  if (width % 2 || height % 2) fail("Video dimensions must be even");
  const fps = number(raw.fps, 12, 30, true);
  const assets = array(raw.assets ?? [], 20).map(value => {
    const asset = object(value);
    fields(asset, ["id", "path", "sha256", "kind", "source_ref", "visibility"]);
    const path = text(asset.path, 400);
    if (path.startsWith("/") || path.includes("\\") || path.split("/").some(part => part === ".." || !part || part === ".")) fail("Assets must be relative files inside the explicit source directory");
    if (typeof asset.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(asset.sha256)) fail("Each source requires its exact SHA256");
    if (typeof asset.kind !== "string" || !["image", "video", "audio"].includes(asset.kind)) fail("Unsupported asset kind");
    if (typeof asset.visibility !== "string" || !["local_private", "public_safe"].includes(asset.visibility)) fail("Each source requires its visibility boundary");
    return {id: token(asset.id), path, sha256: asset.sha256, kind: asset.kind as string,
      source_ref: text(asset.source_ref, 240), visibility: asset.visibility as string};
  });
  if (new Set(assets.map(asset => asset.id)).size !== assets.length) fail("Duplicate source reference");
  const shots = array(raw.shots, 30).map(value => {
    const shot = object(value);
    fields(shot, ["id", "kind", "seconds", "title", "body", "nodes", "asset_id", "start_seconds", "source_ref", "boundary"]);
    const kind = shot.kind;
    if (typeof kind !== "string" || !["title", "diagram", "excerpt"].includes(kind)) fail("Unsupported shot kind");
    const base = {id: token(shot.id), kind, seconds: number(shot.seconds, 1, 30), title: text(shot.title, 100),
      body: shot.body == null || shot.body === "" ? "" : text(shot.body, 300), source_ref: text(shot.source_ref, 240), boundary: text(shot.boundary, 180)};
    if (kind === "diagram") {
      const nodes = array(shot.nodes, 5).map(node => text(node, 48));
      if (nodes.length < 2) fail("A diagram requires at least two nodes");
      return {...base, nodes};
    }
    if (kind === "excerpt") {
      const asset_id = token(shot.asset_id), asset = assets.find(entry => entry.id === asset_id);
      if (!asset || !["image", "video"].includes(asset.kind)) fail("Excerpt source is missing or has the wrong kind");
      return {...base, asset_id, start_seconds: number(shot.start_seconds ?? 0, 0, 86400)};
    }
    return base;
  });
  if (!shots.length || new Set(shots.map(shot => shot.id)).size !== shots.length) fail("Shots require distinct IDs");
  const duration = shots.reduce((total, shot) => total + shot.seconds, 0);
  if (duration > 90 || shots.some(shot => Math.abs(shot.seconds * fps - Math.round(shot.seconds * fps)) > 1e-7)) fail("Use frame-aligned shots within a 90-second composition");
  let end = 0;
  const captions = array(raw.captions ?? [], 80).map(value => {
    const cue = object(value);
    fields(cue, ["start", "end", "text", "language"]);
    const start = number(cue.start, end, duration), stop = number(cue.end, start + 0.001, duration);
    const language = text(cue.language, 12);
    if (!/^[a-z]{2}(?:-[A-Z]{2})?$/.test(language)) fail("Invalid caption language");
    const content = text(cue.text, 220);
    if (content.includes("-->")) fail("Invalid caption delimiter");
    end = stop;
    return {start, end: stop, text: content, language};
  });
  const narration = object(raw.narration);
  fields(narration, ["mode", "asset_id", "voice", "words_per_minute"]);
  let sound: ObjectValue;
  if (narration.mode === "supplied") {
    fields(narration, ["mode", "asset_id"]);
    const id = token(narration.asset_id);
    if (!assets.some(asset => asset.id === id && asset.kind === "audio")) fail("Narration audio is missing");
    sound = {mode: "supplied", asset_id: id};
  } else if (narration.mode === "system_speech") {
    fields(narration, ["mode", "voice", "words_per_minute"]);
    if (!captions.length) fail("Timed system speech requires captions");
    sound = {mode: "system_speech", voice: token(narration.voice), words_per_minute: number(narration.words_per_minute ?? 155, 90, 220, true)};
  } else if (narration.mode === "silent") {fields(narration, ["mode"]); sound = {mode: "silent"};}
  else fail("Select supplied audio, available system speech, or explicit silence");
  const plan = {schema_version: MEDIA_PLAN_SCHEMA, title: text(raw.title, 100), width, height, fps, shots, assets, captions, narration: sound, layout_template_id: layout.template_id};
  return {ok: true, plan, duration_seconds: duration, frame_count: Math.round(duration * fps),
    plan_digest: `sha256:${createHash("sha256").update(stable({plan, layout_style: layout.style_tokens})).digest("hex")}`,
    layout_style: layout.style_tokens,
    capability_id: "content-ops", protocol: MEDIA_PROTOCOL, visibility: "local_private", publish_authorized: false};
}

/** Only validated, path-free result fields can enter the workbench projection. */
export function validateMediaResult(input: unknown) {
  const request = object(input), result = object(request.result), qa = object(result.qa), cost = object(result.cost);
  if (result.ok !== true || result.protocol !== MEDIA_PROTOCOL || result.plan_digest !== request.plan_digest || result.publish_authorized !== false) fail("Renderer result is not bound to this composition");
  if (qa.full_decode !== "passed" || qa.frames !== request.frame_count || qa.width !== request.width || qa.height !== request.height || qa.fps !== request.fps || qa.source_hashes_verified !== true) fail("Renderer did not qualify the declared timeline");
  const entries = object(result.files), files: Record<string, {sha256: string; bytes: number}> = {};
  const allowed = ["video.mp4", "poster.png", "captions.vtt", "captions.srt", "transcript.txt", "narration.wav"];
  for (const [name, raw] of Object.entries(entries)) {
    if (!allowed.includes(name)) fail("Unexpected renderer file");
    const entry = object(raw);
    if (typeof entry.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(entry.sha256)) fail("Invalid renderer digest");
    files[name] = {sha256: entry.sha256, bytes: number(entry.bytes, 0, 128 * 1024 * 1024, true)};
  }
  if (["video.mp4", "poster.png", "captions.vtt", "captions.srt", "transcript.txt"].some(name => !files[name])) fail("Renderer output incomplete");
  const narration = object(qa.narration);
  if (!["silent", "supplied", "system_speech"].includes(String(narration.mode)) || narration.mode !== request.narration_mode) fail("Narration result differs from the admitted plan");
  if (narration.mode !== "silent" && !files["narration.wav"]) fail("Narration output is missing");
  const audioMetrics = narration.mode === "silent" ? {} : {
    peak_dbfs: narration.peak_dbfs === null ? null : number(narration.peak_dbfs, -100, 0),
    clipped_samples: number(narration.clipped_samples, 0, 44100 * 90, true),
  };
  return {ok: true, protocol: MEDIA_PROTOCOL, plan_digest: request.plan_digest, files,
    qa: {full_decode: "passed", frames: qa.frames, width: qa.width, height: qa.height, fps: qa.fps,
      source_hashes_verified: true, narration: {mode: narration.mode, ...audioMetrics, subjective_listening: "not_tested"},
      audience_understanding: "not_tested", creative_review: "not_tested"},
    cost: {render_wall_seconds: number(cost.render_wall_seconds, 0, 120)}, publish_authorized: false};
}

/** A private render attempt has no authority to transition a content item to published. */
export function transitionMediaRender(input: unknown) {
  const value = object(input), state = object(value.state);
  number(state.revision, 1, Number.MAX_SAFE_INTEGER, true);
  if (state.revision !== value.expected_revision) fail("Composition revision changed; inspect before retrying");
  const current = state.status, action = value.action;
  const allowed = action === "start" ? ["prepared", "failed", "cancelled", "interrupted", "ready"] : ["rendering"];
  if (typeof current !== "string" || !allowed.includes(current)) fail("This render transition is unavailable");
  const status = action === "start" ? "rendering" : action === "success" ? "ready" : action === "cancel" ? "cancelled" : action === "interrupt" ? "interrupted" : action === "failure" ? "failed" : fail("Unsupported render action");
  const observedAt = text(value.observed_at, 40);
  if (!/^\d{4}-\d\d-\d\dT/.test(observedAt) || !/(Z|[+-]\d\d:\d\d)$/.test(observedAt) || !Number.isFinite(Date.parse(observedAt))) fail("Render transition requires a timezone-aware observation");
  return {ok: true, state: {...state, status, updated_at: observedAt}};
}
