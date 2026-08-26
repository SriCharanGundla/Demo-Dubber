import assert from "node:assert/strict";
import test from "node:test";

import { resolveApiUrl } from "../src/lib/api.js";

test("keeps same-origin API media paths unchanged", () => {
  assert.equal(resolveApiUrl("/api/voices/af_heart/sample", "/api"), "/api/voices/af_heart/sample");
});

test("resolves backend media paths against a separate API origin", () => {
  assert.equal(
    resolveApiUrl(
      "/api/projects/project-1/previews/tts/0/signature/audio",
      "https://api.example.test/api",
    ),
    "https://api.example.test/api/projects/project-1/previews/tts/0/signature/audio",
  );
});

test("preserves absolute media URLs", () => {
  assert.equal(
    resolveApiUrl("https://cdn.example.test/sample.wav", "https://api.example.test/api"),
    "https://cdn.example.test/sample.wav",
  );
});
