import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's auto-cleanup only self-registers when it can
// see a global `afterEach` (e.g. with vitest's `globals: true`, which
// this project doesn't enable — explicit imports are kept instead, so
// every file's `vi`/`describe`/`it` import is visible at a glance).
// Without this, every render() in a component test file accumulates in
// the DOM instead of unmounting between tests.
afterEach(() => {
  cleanup();
});
