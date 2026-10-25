/**
 * TalkFlow 2.0 — engine index (alias of engine/engine.mjs).
 *
 * SPEC names this file as the engine aggregate (`VERSION`, `AGENT_MANIFEST`,
 * all modules). It simply mirrors the server aggregate so both import paths
 * resolve to the same live bindings.
 */

export * from "./engine.mjs";
