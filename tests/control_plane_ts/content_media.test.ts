import assert from "node:assert/strict";
import test from "node:test";
import {validateMediaPlan as plan, validateMediaResult as result, transitionMediaRender as transition} from "../../loopx/control_plane/capabilities/content_media.ts";

const brief = () => ({schema_version: "content_ops_media_plan_v0", title: "Return the evidence", width: 1280, height: 720, fps: 24,
  shots: [{id: "flow", kind: "diagram", seconds: 6, title: "A complete handoff", nodes: ["Intent", "Owner", "Evidence"], source_ref: "synthetic:handoff", boundary: "Mechanism illustration"}],
  assets: [], captions: [{start: 0, end: 6, text: "Return evidence to the requester.", language: "en"}], narration: {mode: "silent"}});

test("one composition digest binds story, timing, narration, source and scope", () => {
  const original = plan({plan: brief()});
  assert.equal(original.frame_count, 144);
  assert.equal(original.publish_authorized, false);
  assert.equal(original.visibility, "local_private");
  assert.equal(plan({plan: JSON.parse(JSON.stringify(brief()))}).plan_digest, original.plan_digest);
  assert.equal(plan({plan: original.plan}).plan_digest, original.plan_digest, "canonical plans must be replayable even with an empty optional body");
  for (const changed of [
    {...brief(), title: "Revised story"}, {...brief(), fps: 30},
    {...brief(), layout_template_id: "control-plane-hybrid"},
    {...brief(), captions: [{start: 0, end: 6, text: "Different claim", language: "en"}]},
    {...brief(), narration: {mode: "system_speech", voice: "Samantha"}},
    {...brief(), assets: [{id: "a", kind: "image", path: "screenshot.png", sha256: "a".repeat(64), source_ref: "synthetic:source", visibility: "local_private"}]},
  ]) assert.notEqual(plan({plan: changed}).plan_digest, original.plan_digest);
});

test("renderer readback cannot change the admitted narration, frame count or output scope", () => {
  const expected = {plan_digest: "sha256:" + "a".repeat(64), frame_count: 144, width: 1280, height: 720, fps: 24, narration_mode: "silent"};
  const output = {ok: true, protocol: "content_ops_media_renderer_v0", plan_digest: expected.plan_digest,
    files: Object.fromEntries(["video.mp4", "poster.png", "captions.vtt", "captions.srt", "transcript.txt"].map(name => [name, {sha256: "b".repeat(64), bytes: 16}])),
    qa: {full_decode: "passed", frames: 144, width: 1280, height: 720, fps: 24, source_hashes_verified: true, narration: {mode: "silent"}, creative_review: "passed"},
    cost: {render_wall_seconds: 1}, publish_authorized: false, private_path: "must-not-project"};
  const projected = result({...expected, result: output});
  assert.equal(projected.qa.creative_review, "not_tested");
  assert.equal("private_path" in projected, false);
  for (const changed of [
    {...output, publish_authorized: true},
    {...output, files: {...output.files, "../outside.mp4": {sha256: "b".repeat(64), bytes: 16}}},
    {...output, qa: {...output.qa, frames: 143}},
    {...output, qa: {...output.qa, narration: {mode: "supplied"}}},
    {...output, files: {...output.files, "video.mp4": {sha256: "invalid", bytes: 16}}},
  ]) assert.throws(() => result({...expected, result: changed}));
});

test("reject escaping assets, wrong kinds, ambiguous timing and overflow", () => {
  for (const path of ["../secret", "/etc/passwd", "a/../b", "a\\b", "a//b"]) {
    assert.throws(() => plan({plan: {...brief(), assets: [{id: "a", kind: "image", path, sha256: "a".repeat(64), source_ref: "source:1", visibility: "local_private"}]}}));
  }
  for (const invalid of [
    {...brief(), width: 1279}, {...brief(), fps: 240}, {...brief(), shots: []},
    {...brief(), shots: [{...brief().shots[0], seconds: 6.01}]},
    {...brief(), shots: [{...brief().shots[0], kind: ["diagram"]}]},
    {...brief(), assets: [{id: "a", kind: ["image"], path: "source.png", sha256: "a".repeat(64), source_ref: "synthetic:source", visibility: "local_private"}]},
    {...brief(), assets: [{id: "a", kind: "image", path: "source.png", sha256: "a".repeat(64), source_ref: "synthetic:source", visibility: ["public_safe"]}]},
    {...brief(), shots: [{...brief().shots[0], kind: "excerpt", asset_id: "missing"}]},
    {...brief(), captions: [{start: 3, end: 7, text: "Past the end", language: "en"}]},
    {...brief(), narration: {mode: "supplied", asset_id: "missing"}},
    {...brief(), publish_authorized: true},
  ]) assert.throws(() => plan({plan: invalid}));
});

test("render transitions are revision-bound and separate from publication", () => {
  const state = {status: "prepared", revision: 2, publish_authorized: false};
  const running = transition({state, expected_revision: 2, action: "start", observed_at: "2026-09-01T00:00:00Z"}).state;
  assert.equal(running.status, "rendering");
  for (const action of ["success", "failure", "cancel", "interrupt"]) {
    const result = transition({state: running, expected_revision: 2, action, observed_at: "2026-09-01T00:00:01Z"}).state;
    assert.equal(result.publish_authorized, false);
  }
  assert.throws(() => transition({state, expected_revision: 1, action: "start", observed_at: "now"}), /revision/);
  assert.throws(() => transition({state, expected_revision: 2, action: "success", observed_at: "now"}), /unavailable/);
  assert.throws(() => transition({state: running, expected_revision: 2, action: "publish", observed_at: "now"}));
});

test("caption admission preserves plain text and refuses structural paragraph separators", () => {
  const caption = (text: string) => ({...brief(), captions: [{start: 0, end: 6, text, language: "en"}]});
  const plain = "x & y\nQuoted \"literal\" text";
  assert.equal(plan({plan: caption(plain)}).plan.captions[0]?.text, plain);
  for (const text of ["FIRST LINE\n\nSECOND LINE", "FIRST LINE\n \t\nSECOND LINE"]) {
    assert.throws(() => plan({plan: caption(text)}), /blank lines/);
  }
  for (const text of ["x < y", "x > y", "<b>literal</b>", "&lt;literal&gt;", "&#60;", "&#x3c;"]) {
    assert.throws(() => plan({plan: caption(text)}), /markup and entity/);
  }
});
