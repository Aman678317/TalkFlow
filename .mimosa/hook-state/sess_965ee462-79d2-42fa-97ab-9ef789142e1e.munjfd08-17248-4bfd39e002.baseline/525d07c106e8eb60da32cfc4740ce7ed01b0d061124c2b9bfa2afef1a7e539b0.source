import fs from 'node:fs';
import path from 'node:path';
import yaml from 'yaml';

export interface ParsedEntry {
  key: string;
  sourceText: string;
  translatedText?: string;
}

export interface FormatParser {
  parse(content: string): ParsedEntry[];
  serialize(originalContent: string, entries: ParsedEntry[]): string;
}

/**
 * Nested JSON Parser preserving non-string types and original indentation.
 */
export class JsonFormatParser implements FormatParser {
  public parse(content: string): ParsedEntry[] {
    const data = JSON.parse(content);
    const entries: ParsedEntry[] = [];

    const traverse = (obj: any, prefix = '') => {
      for (const key of Object.keys(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const val = obj[key];
        if (typeof val === 'string') {
          entries.push({ key: fullKey, sourceText: val });
        } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
          traverse(val, fullKey);
        }
      }
    };

    traverse(data);
    return entries;
  }

  public serialize(originalContent: string, entries: ParsedEntry[]): string {
    const data = JSON.parse(originalContent);
    const map = new Map(entries.map((e) => [e.key, e.translatedText || e.sourceText]));

    const setNested = (obj: any, pathParts: string[], value: string) => {
      const part = pathParts[0];
      if (!part) {
        return;
      }
      if (pathParts.length === 1) {
        obj[part] = value;
        return;
      }
      if (!obj[part] || typeof obj[part] !== 'object') {
        obj[part] = {};
      }
      setNested(obj[part], pathParts.slice(1), value);
    };

    for (const [key, val] of map.entries()) {
      setNested(data, key.split('.'), val);
    }

    // Detect indentation
    const match = originalContent.match(/^[ \t]+/m);
    const indent = match ? match[0] : 2;

    return JSON.stringify(data, null, indent) + '\n';
  }
}

/**
 * YAML Parser preserving comments and key structure.
 */
export class YamlFormatParser implements FormatParser {
  public parse(content: string): ParsedEntry[] {
    const doc = yaml.parseDocument(content);
    const entries: ParsedEntry[] = [];

    const traverse = (node: any, prefix = '') => {
      if (!node || typeof node !== 'object') {
        return;
      }
      for (const [key, val] of Object.entries(node)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        if (typeof val === 'string') {
          entries.push({ key: fullKey, sourceText: val });
        } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
          traverse(val, fullKey);
        }
      }
    };

    traverse(doc.toJSON());
    return entries;
  }

  public serialize(originalContent: string, entries: ParsedEntry[]): string {
    const doc = yaml.parseDocument(originalContent);
    for (const entry of entries) {
      if (entry.translatedText) {
        doc.setIn(entry.key.split('.'), entry.translatedText);
      }
    }
    return doc.toString();
  }
}

/**
 * Android XML Strings Parser (`<string name="key">Text</string>`).
 */
export class AndroidXmlFormatParser implements FormatParser {
  public parse(content: string): ParsedEntry[] {
    const entries: ParsedEntry[] = [];
    const regex = /<string\s+name=["']([^"']+)["'][^>]*>(.*?)<\/string>/gs;
    let match;
    while ((match = regex.exec(content)) !== null) {
      const key = match[1]!;
      const text = match[2]!;
      entries.push({ key, sourceText: text });
    }
    return entries;
  }

  public serialize(originalContent: string, entries: ParsedEntry[]): string {
    let result = originalContent;
    const map = new Map(entries.map((e) => [e.key, e.translatedText || e.sourceText]));

    for (const [key, translated] of map.entries()) {
      const regex = new RegExp(`(<string\\s+name=["']${key}["'][^>]*>)(.*?)(<\\/string>)`, 'gs');
      result = result.replace(regex, `$1${translated}$3`);
    }
    return result;
  }
}

export function getFormatParserForFile(filePath: string): FormatParser {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === '.json') {
    return new JsonFormatParser();
  }
  if (ext === '.yaml' || ext === '.yml') {
    return new YamlFormatParser();
  }
  if (ext === '.xml') {
    return new AndroidXmlFormatParser();
  }
  return new JsonFormatParser();
}
