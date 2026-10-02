/**
 * GlossaryEntries — encapsulates glossary term pairs.
 *
 * Diagram layer: Translation resources [glossaryEntries.ts]
 *
 * Used by `GlobalTalkClient.createGlossary()` to pass term pairs,
 * and returned by `getGlossaryEntries()` after parsing the TSV response.
 *
 * ```ts
 * const entries = new GlossaryEntries({ GlobalTalk: "GlobalTalk", Hello: "Namaste" });
 * await client.createGlossary("My glossary", "EN", "HI", entries);
 * ```
 */

export interface GlossaryEntriesPair {
  source: string;
  target: string;
}

export class GlossaryEntries {
  private readonly _map: Map<string, string>;

  /**
   * Construct from a plain object mapping source → target terms.
   * @throws {Error} if duplicate source terms are detected.
   */
  constructor(entries: Record<string, string>) {
    this._map = new Map();
    for (const [source, target] of Object.entries(entries)) {
      if (!source.trim()) throw new Error("Glossary source term cannot be empty");
      if (this._map.has(source)) {
        throw new Error(`Duplicate source term in glossary: "${source}"`);
      }
      this._map.set(source, target);
    }
  }

  /** Number of term pairs. */
  get size(): number {
    return this._map.size;
  }

  /** Look up a source term. Returns `undefined` if not found. */
  get(source: string): string | undefined {
    return this._map.get(source);
  }

  /** Check whether a source term exists. */
  has(source: string): boolean {
    return this._map.has(source);
  }

  /** Iterate over all [source, target] pairs. */
  entries(): IterableIterator<[string, string]> {
    return this._map.entries();
  }

  /** Return all pairs as a plain object. */
  toRecord(): Record<string, string> {
    return Object.fromEntries(this._map);
  }

  /**
   * Serialise to TSV (the wire format accepted by `POST /v2/glossaries`).
   *
   * Each line: `source_term\ttarget_term\n`
   */
  toTSV(): string {
    return [...this._map.entries()]
      .map(([s, t]) => `${s}\t${t}`)
      .join("\n");
  }

  /**
   * Parse glossary entries from a TSV string.
   * Silently skips blank lines.
   *
   * @throws {Error} if a line is missing the tab separator.
   */
  static fromTSV(tsv: string): GlossaryEntries {
    const record: Record<string, string> = {};
    let lineNum = 0;
    for (const line of tsv.split("\n")) {
      lineNum++;
      const trimmed = line.trim();
      if (!trimmed) continue;
      const tab = trimmed.indexOf("\t");
      if (tab === -1) {
        throw new Error(`Invalid TSV at line ${lineNum}: missing tab separator`);
      }
      record[trimmed.slice(0, tab)] = trimmed.slice(tab + 1);
    }
    return new GlossaryEntries(record);
  }

  /**
   * Parse glossary entries from a CSV string (comma-separated, with optional quotes).
   */
  static fromCSV(csv: string): GlossaryEntries {
    const record: Record<string, string> = {};
    for (const line of csv.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      // Naïve CSV split — does not handle quoted commas; sufficient for term pairs
      const comma = trimmed.indexOf(",");
      if (comma === -1) continue;
      const source = trimmed.slice(0, comma).replace(/^"|"$/g, "").trim();
      const target = trimmed.slice(comma + 1).replace(/^"|"$/g, "").trim();
      record[source] = target;
    }
    return new GlossaryEntries(record);
  }
}
