/**
 * MCP text-content helpers.
 * Every tool result is returned to the client as MCP "text" content blocks.
 */

export function text(value) {
  return { type: "text", text: typeof value === "string" ? value : JSON.stringify(value, null, 2) };
}

export function result(blocks) {
  return { content: Array.isArray(blocks) ? blocks : [blocks] };
}

export function errorResult(message) {
  return { content: [text(`Error: ${message}`)], isError: true };
}

export function keyValue(lines) {
  return text(lines.filter(Boolean).join("\n"));
}

export function describeError(err) {
  const base = err?.message || String(err);
  const cause = err?.cause;
  const detail = cause?.code || cause?.message;
  return detail && !base.includes(detail) ? `${base} (${detail})` : base;
}
