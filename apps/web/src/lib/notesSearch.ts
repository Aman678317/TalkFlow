/**
 * Notes-style Decoupled Full-Text Search Engine for Real-Time Multilingual Transcripts
 *
 * Inspired by Apple Notes and Google Keep indexing architectures:
 * - Inverted index mapping token prefixes to turn IDs
 * - Multi-tier normalization (case-folding, diacritics removal, punctuation stripping)
 * - Scoped faceted filtering (by speaker, language, meeting ID)
 * - Relevance scoring (exact matches and speaker hits rank above body text)
 * - Real-time safe: incremental O(1) addition during live audio playback
 */

export interface SearchableTurn {
  id: string;
  meetingId?: string;
  speakerName: string;
  originalText: string;
  sourceLang: string;
  translatedText?: string;
  targetLang?: string;
  timestampMs?: number;
  tags?: string[];
}

export interface SearchOptions {
  speaker?: string;
  language?: string;
  meetingId?: string;
  limit?: number;
}

export interface SearchResult {
  turn: SearchableTurn;
  score: number;
  matchedFields: ('speaker' | 'original' | 'translated' | 'tags')[];
}

export class NotesSearchEngine {
  private turns = new Map<string, SearchableTurn>();
  // Token -> Set of turn IDs
  private invertedIndex = new Map<string, Set<string>>();

  /**
   * Tokenize text into normalized searchable tokens.
   * Strips accents, punctuation, and splits by whitespace.
   */
  public static tokenize(text: string): string[] {
    if (!text) return [];
    return text
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '') // remove diacritics / accents
      .replace(/[^\p{L}\p{N}\s]/gu, ' ') // keep unicode letters and numbers
      .split(/\s+/)
      .filter((token) => token.length > 0);
  }

  /**
   * Add or update a turn in the search index.
   */
  public indexTurn(turn: SearchableTurn): void {
    if (this.turns.has(turn.id)) {
      this.removeTurn(turn.id);
    }

    this.turns.set(turn.id, turn);

    const tokensToMap = new Set<string>();

    const addTokens = (txt?: string) => {
      if (!txt) return;
      for (const t of NotesSearchEngine.tokenize(txt)) {
        tokensToMap.add(t);
      }
    };

    addTokens(turn.speakerName);
    addTokens(turn.originalText);
    addTokens(turn.translatedText);
    turn.tags?.forEach((tag) => addTokens(tag));

    tokensToMap.forEach((token) => {
      if (!this.invertedIndex.has(token)) {
        this.invertedIndex.set(token, new Set());
      }
      this.invertedIndex.get(token)!.add(turn.id);
    });
  }

  /**
   * Remove a turn from the index.
   */
  public removeTurn(id: string): void {
    this.turns.delete(id);
    for (const [token, ids] of this.invertedIndex.entries()) {
      ids.delete(id);
      if (ids.size === 0) {
        this.invertedIndex.delete(token);
      }
    }
  }

  /**
   * Clear the entire index.
   */
  public clear(): void {
    this.turns.clear();
    this.invertedIndex.clear();
  }

  /**
   * Search across indexed turns with optional scoped filtering.
   */
  public search(query: string, options?: SearchOptions): SearchResult[] {
    const trimmedQuery = query.trim();
    const queryTokens = NotesSearchEngine.tokenize(trimmedQuery);

    if (queryTokens.length === 0 && !options?.speaker && !options?.language && !options?.meetingId) {
      return [];
    }

    let candidateIds: Set<string> | null = null;

    if (queryTokens.length > 0) {
      for (const qToken of queryTokens) {
        const matchesForToken = new Set<string>();

        // Prefix match across inverted index tokens
        for (const [indexedToken, ids] of this.invertedIndex.entries()) {
          if (indexedToken.startsWith(qToken)) {
            ids.forEach((id) => matchesForToken.add(id));
          }
        }

        if (candidateIds === null) {
          candidateIds = matchesForToken;
        } else {
          const prev = candidateIds as Set<string>;
          candidateIds = new Set([...prev].filter((id: string) => matchesForToken.has(id)));
        }

        if (candidateIds.size === 0) break;
      }
    } else {
      // If query string is empty but filters are passed, include all indexed turns as candidates
      candidateIds = new Set(this.turns.keys());
    }

    if (!candidateIds || candidateIds.size === 0) {
      return [];
    }

    const results: SearchResult[] = [];
    const lowerQuery = trimmedQuery.toLowerCase();

    for (const id of candidateIds) {
      const turn = this.turns.get(id);
      if (!turn) continue;

      // Scoped filters
      if (options?.meetingId && turn.meetingId !== options.meetingId) continue;
      if (
        options?.speaker &&
        options.speaker !== 'all' &&
        turn.speakerName.toLowerCase() !== options.speaker.toLowerCase()
      ) {
        continue;
      }
      if (
        options?.language &&
        options.language !== 'all' &&
        turn.sourceLang !== options.language &&
        turn.targetLang !== options.language
      ) {
        continue;
      }

      // Compute field matches & relevance scoring
      const matchedFields: ('speaker' | 'original' | 'translated' | 'tags')[] = [];
      let score = 0;

      const speakerTokens = NotesSearchEngine.tokenize(turn.speakerName);
      const originalTokens = NotesSearchEngine.tokenize(turn.originalText);
      const translatedTokens = NotesSearchEngine.tokenize(turn.translatedText || '');

      // Check speaker match
      if (
        queryTokens.some((qt) => speakerTokens.some((st) => st.startsWith(qt))) ||
        (lowerQuery && turn.speakerName.toLowerCase().includes(lowerQuery))
      ) {
        matchedFields.push('speaker');
        score += 15;
      }

      // Check original text match
      if (
        queryTokens.some((qt) => originalTokens.some((ot) => ot.startsWith(qt))) ||
        (lowerQuery && turn.originalText.toLowerCase().includes(lowerQuery))
      ) {
        matchedFields.push('original');
        score += 10;
        if (lowerQuery && turn.originalText.toLowerCase().includes(lowerQuery)) {
          score += 5; // boost for exact phrase match
        }
      }

      // Check translated text match
      if (
        turn.translatedText &&
        (queryTokens.some((qt) => translatedTokens.some((tt) => tt.startsWith(qt))) ||
          (lowerQuery && turn.translatedText.toLowerCase().includes(lowerQuery)))
      ) {
        matchedFields.push('translated');
        score += 10;
        if (lowerQuery && turn.translatedText.toLowerCase().includes(lowerQuery)) {
          score += 5;
        }
      }

      // Check tags match
      if (turn.tags && turn.tags.some((t) => queryTokens.some((qt) => t.toLowerCase().includes(qt)))) {
        matchedFields.push('tags');
        score += 8;
      }

      if (queryTokens.length === 0) {
        score = 1; // Default score when matching purely on filters
      }

      results.push({
        turn,
        score,
        matchedFields,
      });
    }

    // Rank by descending score, then by recency (timestampMs)
    results.sort((a, b) => {
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      return (b.turn.timestampMs || 0) - (a.turn.timestampMs || 0);
    });

    if (options?.limit && options.limit > 0) {
      return results.slice(0, options.limit);
    }

    return results;
  }

  /**
   * Helper utility to split text into matching and non-matching segments
   * for UI highlighting (used by React components).
   */
  public static highlightSegments(
    text: string,
    query: string
  ): Array<{ text: string; isMatch: boolean }> {
    if (!text || !query.trim()) {
      return [{ text: text || '', isMatch: false }];
    }

    const tokens = NotesSearchEngine.tokenize(query);
    if (tokens.length === 0) {
      return [{ text, isMatch: false }];
    }

    // Build regex for prefix or exact matching of tokens
    const escaped = tokens.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    const regex = new RegExp(`(${escaped})`, 'gi');

    const parts = text.split(regex);
    return parts.map((part) => ({
      text: part,
      isMatch: regex.test(part),
    }));
  }
}
