# Local video renderer

`loopx-media` is an optional distribution for the existing **content-ops**
capability. It renders an admitted composition; it does not choose sources,
run commands from a brief, use an account, call a model, or publish a movie.
Shared TypeScript admission and render transitions remain in LoopX core.
Pillow, FontTools, FFmpeg and platform speech are specialized local computation.

From a source checkout, install the executable and register its manifest:

```sh
uv tool install ./packages/loopx-media
loopx extension install --manifest packages/loopx-media/extension.toml --execute
loopx extension doctor loopx-media --execute
```

The LoopX process must have `loopx-media` on its PATH. Installation explicitly
enables the local extension. No renderer is installed, enabled or downloaded
by `content-ops media prepare`, page loading or a missing-provider read.
The manifest requests `content_media_write` for private composition output.
Use the existing extension state owner; there is no second media setting.
An isolated environment is also supported if its executable is on that PATH.

An Agent prepares the story, source SHA256s and timing through
[`content-ops media`](../../docs/reference/protocols/content-ops-media-v0.md).
In the packaged App, open **Settings → Capabilities → a Goal → Content
production**. Select the prepared composition, render, then view the video,
captions, transcript and source boundaries in the same workbench. The CLI
exposes the same operation. Rendering is local work; it grants no publication
approval. Revise the brief through the Agent rather than re-entering source
paths or protocol JSON in the browser.

Supported atoms are title scenes, measured text wrapping, animated node
diagrams, hash-bound image/video excerpts, timed captions, supplied audio,
macOS system speech, H.264/AAC encoding, a first-frame poster and full video
decode. Images retain their orientation; video excerpts retain aspect ratio.
Installed fonts must cover the visible text, with CJK line breaking supported.
RTL shaping and arbitrary font discovery are not qualified. macOS speech is
optional; other platforms require supplied audio or explicit silence.
No cloud voice, generative image/video, Blender or game engine is bundled here.

The renderer refuses a short excerpt, changed source, missing glyphs, text
overflow or speech longer than its cue. It does not fill missing footage,
silently truncate text or speed up speech to hide those failures. Prepare a
new revision for story/source/timing changes. Repair a local dependency and
run doctor again before retrying an unchanged brief. Cancellation is requested
in place and read back after the worker stops; a host interruption is recovered
by an explicit retry. An intact completed result is reused without encoding
again. Damaged result bytes cannot be downloaded as verified output.

## Bounds and review

Plans are limited to 90 seconds, 30 shots, 20 local assets and 80 ordered
caption cues, with at most 1920×1080 at 30 fps. Each source is at most 64 MiB;
all source snapshots together are at most 128 MiB. The render has a 120-second
process budget. A complex valid plan can exceed the local machine's budget;
that is a failed attempt, not a reason to mark a partial movie ready.

The result records exact output digests, decoded frames, render wall time,
PCM peak/clipping measurements when audio exists, and untested creative,
listening and audience-understanding judgments. These mechanical checks do
not establish narration quality, factual truth, source rights, learning gain,
virality or a better film. Review the actual result before sharing. Existing
content-item approval and delivery intent are invalidated when the plan or
rendered bytes change. The outputs remain private until separately authorized.

Disable new renders with the existing owner:

```sh
loopx extension disable loopx-media --execute
```

Existing verified results remain readable. Re-enable and run doctor after a
dependency repair. Prepared files and failed attempts remain in the registered
project's private `.local/content-media/` directory for inspection; disabling
does not delete them. There is no automatic cleanup of source evidence.

## Focused validation

Core tests do not need this distribution. To exercise the actual optional
extension, encoder, source reuse, recovery and HTTP byte serving after installing
the executable in an isolated environment:

```sh
LOOPX_MEDIA_RENDERER_TEST=1 uv run --extra test pytest -q tests/test_content_media.py
node --test tests/control_plane_ts/content_media.test.ts
```

The opt-in test uses synthetic local sources and no model or cloud service.
It is integration evidence, not a subjective or comparative creative study.
