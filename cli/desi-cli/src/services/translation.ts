import fs from 'node:fs';
import path from 'node:path';
import Table from 'cli-table3';
import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { CacheManager } from '../storage/cache.js';
import { TranslateOptions, TranslationResult, DesiCliError } from '../types/index.js';

export class TranslationService {
  constructor(
    private client: DesiClient,
    private cache: CacheManager
  ) {}

  public async translateText(
    text: string,
    options: TranslateOptions
  ): Promise<Map<string, TranslationResult>> {
    const results = new Map<string, TranslationResult>();

    for (const targetLang of options.targetLangs) {
      const cacheKey = this.cache.getCacheKey(
        text,
        targetLang,
        options.sourceLang,
        options.honorific,
        options.glossaryId
      );

      if (!options.noCache) {
        const cached = this.cache.get(cacheKey);
        if (cached) {
          results.set(targetLang, cached);
          continue;
        }
      }

      const [res] = await this.client.translate({
        text,
        targetLang,
        sourceLang: options.sourceLang,
        honorific: options.honorific,
        respectfulSuffix: options.respectfulSuffix,
        domain: options.domain,
        glossaryId: options.glossaryId,
        glossaryIds: options.glossaryIds,
        modelType: options.modelType,
        tagHandling: options.tagHandling,
        context: options.context,
      });

      if (res) {
        results.set(targetLang, res);
        this.cache.set(cacheKey, res);
      }
    }

    return results;
  }

  public async translateFile(
    filePath: string,
    options: TranslateOptions
  ): Promise<void> {
    if (!fs.existsSync(filePath)) {
      throw new DesiCliError(`File not found: ${filePath}`, 6);
    }

    const content = fs.readFileSync(filePath, 'utf8');
    const results = await this.translateText(content, options);

    if (options.output) {
      // Determine if output is a directory or file
      const isDir =
        fs.existsSync(options.output) && fs.statSync(options.output).isDirectory();

      for (const [lang, res] of results.entries()) {
        let targetPath = options.output;
        if (isDir || options.targetLangs.length > 1) {
          const ext = path.extname(filePath);
          const base = path.basename(filePath, ext);
          targetPath = path.join(
            isDir ? options.output : path.dirname(options.output),
            `${base}.${lang}${ext}`
          );
        }
        fs.writeFileSync(targetPath, res.text, 'utf8');
      }
    } else {
      this.renderOutput(results, 'text', options.showBilledCharacters);
    }
  }

  public renderOutput(
    results: Map<string, TranslationResult>,
    format: 'text' | 'json' | 'table' = 'text',
    showBilledCharacters = false
  ): void {
    if (format === 'json') {
      const output: Record<string, any> = {};
      for (const [lang, res] of results.entries()) {
        output[lang] = res;
      }
      console.log(JSON.stringify(output, null, 2));
      return;
    }

    if (format === 'table' || (results.size > 1 && format !== 'text')) {
      const head = ['Language', 'Translation'];
      if (showBilledCharacters) {
        head.push('Billed Chars');
      }

      const table = new Table({
        head: head.map((h) => chalk.cyan(h)),
        wordWrap: true,
      });

      for (const [lang, res] of results.entries()) {
        const row = [chalk.green(lang.toUpperCase()), res.text];
        if (showBilledCharacters) {
          row.push(String(res.billedCharacters ?? res.text.length));
        }
        table.push(row);
      }

      console.log(table.toString());
      return;
    }

    // Default plain text output
    for (const [lang, res] of results.entries()) {
      if (results.size > 1) {
        console.log(chalk.bold(`[${lang.toUpperCase()}]:`));
      }
      console.log(res.text);
      if (showBilledCharacters && res.billedCharacters) {
        console.log(chalk.dim(`(Billed characters: ${res.billedCharacters})`));
      }
    }
  }
}
