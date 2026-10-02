// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

/**
 * Standardize language code format (e.g. `en-us` -> `en-US`, `hi` -> `hi`).
 * @param {string} code
 */
export function standardizeLangCase(code) {
  if (!code) return "";
  const [lang, region] = code.split("-", 2);
  return region === undefined
    ? lang.toLowerCase()
    : `${lang.toLowerCase()}-${region.toUpperCase()}`;
}

/**
 * Wraps a string or array of strings into standard Model Context Protocol text content objects.
 * @param {string | string[]} param
 */
export function mcpContentifyText(param) {
  if (typeof param !== "string" && !Array.isArray(param)) {
    throw new Error("mcpContentifyText() expects a string or an array of strings");
  }

  const strings = typeof param === "string" ? [param] : param;

  const contentObjects = strings.map((str) => ({
    type: "text",
    text: str,
  }));

  return {
    content: contentObjects,
  };
}
