import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { TranslationResult } from '../types/index.js';

export class CacheManager {
  private cacheDir: string;
  private cacheFile: string;
  private memoryCache: Map<string, { result: TranslationResult; timestamp: number }> = new Map();
  private enabled: boolean;

  constructor(customCacheDir?: string, enabled = true) {
    this.enabled = enabled;
    if (customCacheDir) {
      this.cacheDir = customCacheDir;
    } else if (process.env.DESI_CONFIG_DIR) {
      this.cacheDir = path.join(process.env.DESI_CONFIG_DIR, 'cache');
    } else {
      const xdgCache = process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
      this.cacheDir = path.join(xdgCache, 'desi-cli');
    }
    this.cacheFile = path.join(this.cacheDir, 'translations.json');
    this.loadDiskCache();
  }

  private loadDiskCache(): void {
    if (!this.enabled || !fs.existsSync(this.cacheFile)) {
      return;
    }
    try {
      const content = fs.readFileSync(this.cacheFile, 'utf8');
      const parsed = JSON.parse(content);
      if (typeof parsed === 'object' && parsed !== null) {
        for (const [key, value] of Object.entries(parsed)) {
          this.memoryCache.set(key, value as any);
        }
      }
    } catch {
      // Corrupt cache file, start fresh
      this.memoryCache.clear();
    }
  }

  private persistDiskCache(): void {
    if (!this.enabled) {
      return;
    }
    try {
      if (!fs.existsSync(this.cacheDir)) {
        fs.mkdirSync(this.cacheDir, { recursive: true, mode: 0o700 });
      }
      const data: Record<string, any> = {};
      for (const [key, val] of this.memoryCache.entries()) {
        data[key] = val;
      }
      fs.writeFileSync(this.cacheFile, JSON.stringify(data), {
        encoding: 'utf8',
        mode: 0o600,
      });
    } catch {
      // Graceful fallback if filesystem cannot be written
    }
  }

  public getCacheKey(
    text: string,
    targetLang: string,
    sourceLang?: string,
    honorific?: string,
    glossaryId?: string
  ): string {
    const raw = `${text}|${targetLang}|${sourceLang || 'auto'}|${honorific || 'default'}|${glossaryId || ''}`;
    return crypto.createHash('sha256').update(raw).digest('hex');
  }

  public get(key: string): TranslationResult | undefined {
    if (!this.enabled) {
      return undefined;
    }
    const item = this.memoryCache.get(key);
    if (!item) {
      return undefined;
    }
    return item.result;
  }

  public set(key: string, result: TranslationResult): void {
    if (!this.enabled) {
      return;
    }
    this.memoryCache.set(key, { result, timestamp: Date.now() });
    this.persistDiskCache();
  }

  public clear(): void {
    this.memoryCache.clear();
    if (fs.existsSync(this.cacheFile)) {
      fs.unlinkSync(this.cacheFile);
    }
  }

  public getStats(): { totalEntries: number; cachePath: string; enabled: boolean } {
    return {
      totalEntries: this.memoryCache.size,
      cachePath: this.cacheFile,
      enabled: this.enabled,
    };
  }
}
