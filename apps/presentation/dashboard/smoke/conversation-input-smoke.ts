import assert from "node:assert/strict";
import { conversationInputKey, recoverBoundConversationInput } from "../src/features/personal-workspace/use-conversation-input-state";
import { legacySteeringRequests, readSteeringRequest, retainSteeringRequest, restoreLegacySteeringRequest } from "../src/features/personal-workspace/steering-recovery";

// A source read cannot change the owner of unsent input or of an uncertain send.
// Ordinary multi-executor drafts remain independent; recovery never combines them.
const original = "bound/source-one/session-one";
const peer = "bound/source-two/session-two";
assert.equal(conversationInputKey(original, "original-conversation", true), conversationInputKey(original, "codex", true));
assert.notEqual(conversationInputKey("manager", "codex", false), conversationInputKey("manager", "claude", false));
assert.notEqual(conversationInputKey(original, "codex", true), conversationInputKey(peer, "codex", true));
const image = { name: "draft.png", mimeType: "image/png", dataUrl: "data:image/png;base64,c3ludGhldGlj", id: "draft-image", size: 9 };
const input = (composer: string) => ({ composer, sending: false, steering: false, actionFeedback: null,
  imageAttachments: [], imageAttachmentError: null, loopxMessageReceipt: "" });
const oldKey = `${original}:codex`;
const legacy = { [oldKey]: { ...input("Retain this unsent message"), imageAttachments: [image] }, [peer]: input("Peer stays separate") };
const recovered = recoverBoundConversationInput(legacy, original);
assert.equal(recovered[original], legacy[oldKey], "A unique old draft keeps all in-memory fields");
assert.equal(recovered[peer], legacy[peer]);
assert.equal(recovered[oldKey], undefined);
assert.equal(legacy[oldKey].composer, "Retain this unsent message", "Recovery does not mutate its input");
const conflicting = { ...legacy, [`${original}:original-conversation`]: input("A different draft") };
assert.equal(recoverBoundConversationInput(conflicting, original), conflicting, "Multiple drafts require selection, never overwrite or concatenate");
const current = { ...legacy, [original]: input("") };
assert.equal(recoverBoundConversationInput(current, original), current, "Clearing an existing draft stays cleared");
assert.deepEqual(recoverBoundConversationInput({ [peer]: input("Peer") }, original), { [peer]: input("Peer") });

const storage = new Map<string, string>();
Object.assign(globalThis, { window: { sessionStorage: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => storage.set(key, value),
} } });
const request = { sessionId: "session-one", turnId: "original-turn", text: "Keep the original retry", id: "original-request", delivery: "queue" as const };
assert.ok(retainSteeringRequest(oldKey, request));
assert.ok(retainSteeringRequest(`${peer}:codex`, { ...request, sessionId: "session-two", id: "peer-request" }));
assert.deepEqual(legacySteeringRequests("session-one", original), [[oldKey, request]]);
assert.equal(restoreLegacySteeringRequest(peer, oldKey, "session-two"), undefined, "A peer cannot adopt an uncertain send");
assert.deepEqual(restoreLegacySteeringRequest(original, oldKey, "session-one"), request);
assert.deepEqual(readSteeringRequest(original), request, "Recovery retains exact request, Turn and delivery identity");
assert.equal(readSteeringRequest(oldKey), undefined);
assert.ok(retainSteeringRequest(oldKey, { ...request, id: "conflicting-request" }));
assert.equal(restoreLegacySteeringRequest(original, oldKey, "session-one"), undefined, "A distinct pending request cannot replace the current one");
assert.equal(readSteeringRequest(original)?.id, "original-request");
const unavailable = "bound/source-three/session-three";
const unavailableLegacy = `${unavailable}:codex`;
assert.ok(retainSteeringRequest(unavailableLegacy, { ...request, sessionId: "session-three", id: "storage-failure-request" }));
window.sessionStorage.setItem = () => { throw new Error("Synthetic storage is unavailable"); };
assert.equal(restoreLegacySteeringRequest(unavailable, unavailableLegacy, "session-three"), undefined,
  "A failed durable copy cannot be presented as a recovered request");
assert.equal(readSteeringRequest(unavailable), undefined);
assert.equal(readSteeringRequest(unavailableLegacy)?.id, "storage-failure-request");
console.log("conversation-input: passed (stable original Session, independent ordinary drafts, lossless legacy recovery and exact uncertain-send identity)");
