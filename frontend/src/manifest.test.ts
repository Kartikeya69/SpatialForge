import { describe, expect, it } from "vitest";
import { validateSceneManifest } from "./manifest";

describe("validateSceneManifest", () => {
  it("rejects unsupported and incomplete metadata", () => {
    expect(() => validateSceneManifest({ schema_version: "2.0.0" })).toThrow("Unsupported scene schema");
    expect(() => validateSceneManifest({ schema_version: "1.0.0", scene_id: "x" })).toThrow("identity");
  });
});
