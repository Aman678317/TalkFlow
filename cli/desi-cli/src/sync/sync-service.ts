import fs from 'node:fs';
import path from 'node:path';
import yaml from 'yaml';
import fg from 'fast-glob';
import pLimit from 'p-limit';
import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { getFormatParserForFile, ParsedEntry } from '../formats/index.js';
import { DesiCliError, FormalityTier } from '../types/index.js';

export interface SyncConfig {
  version: number;
  source_locale: string;
  target_locales: string[];
  honorific?: FormalityTier;
  respectful_suffix?: boolean;
  buckets?: Array<{
    name: string;
    format: string;
    source_path: string;
    target_path_pattern: string;
    concurrency?: number;
  }>;
}

export class SyncService {
  private configPath: string;
  private lockPath: string;

  constructor(
    private client: DesiClient,
    projectRoot = process.cwd()
  ) {
    this.configPath = path.join(projectRoot, '.desi-sync.yaml');
    if (!fs.existsSync(this.configPath)) {
      // Backwards-compatible check for .deepl-sync.yaml
      const legacyPath = path.join(projectRoot, '.deepl-sync.yaml');
      if (fs.existsSync(legacyPath)) {
        this.configPath = legacyPath;
      }
    }
    this.lockPath = path.join(projectRoot, '.desi-sync.lock');
  }

  public loadConfig(): SyncConfig {
    if (!fs.existsSync(this.configPath)) {
      throw new DesiCliError(
        `Sync configuration not found (${this.configPath})`,
        7,
        'Run "desi sync init" to create a configuration file.'
      );
    }
    const content = fs.readFileSync(this.configPath, 'utf8');
    return yaml.parse(content);
  }

  public async runSync(options: { dryRun?: boolean; force?: boolean } = {}): Promise<void> {
    const config = this.loadConfig();
    console.log(chalk.cyan(`Starting Desi Continuous Localization Sync...`));
    console.log(`Source locale: ${chalk.bold(config.source_locale)}`);
    console.log(`Target locales: ${chalk.bold(config.target_locales.join(', '))}\n`);

    const buckets = config.buckets || [
      {
        name: 'default',
        format: 'json',
        source_path: 'locales/en/**/*.json',
        target_path_pattern: 'locales/{locale}/{filename}.json',
      },
    ];

    let totalTranslated = 0;

    for (const bucket of buckets) {
      console.log(chalk.bold(`Bucket: ${bucket.name}`));
      const sourceFiles = fg.sync(bucket.source_path);

      if (sourceFiles.length === 0) {
        console.log(chalk.yellow(`  No source files matching "${bucket.source_path}"`));
        continue;
      }

      for (const sourceFile of sourceFiles) {
        console.log(`  Processing ${chalk.blue(sourceFile)}...`);
        const parser = getFormatParserForFile(sourceFile);
        const sourceContent = fs.readFileSync(sourceFile, 'utf8');
        const entries = parser.parse(sourceContent);

        for (const targetLocale of config.target_locales) {
          const filename = path.basename(sourceFile, path.extname(sourceFile));
          const targetFile = bucket.target_path_pattern
            .replace('{locale}', targetLocale)
            .replace('{filename}', filename);

          let targetEntries: ParsedEntry[] = [];
          if (fs.existsSync(targetFile)) {
            const targetContent = fs.readFileSync(targetFile, 'utf8');
            targetEntries = parser.parse(targetContent);
          }

          const targetMap = new Map(targetEntries.map((e) => [e.key, e.sourceText]));
          const toTranslate = entries.filter((e) => !targetMap.has(e.key) || options.force);

          if (toTranslate.length === 0) {
            console.log(`    [${targetLocale}] Up to date.`);
            continue;
          }

          console.log(
            `    [${targetLocale}] Translating ${toTranslate.length} keys...`
          );

          if (options.dryRun) {
            console.log(chalk.dim(`      (Dry run: skipped translation call)`));
            continue;
          }

          const limit = pLimit(bucket.concurrency || 4);
          const translatedEntries: ParsedEntry[] = [];

          await Promise.all(
            toTranslate.map((item) =>
              limit(async () => {
                const [res] = await this.client.translate({
                  text: item.sourceText,
                  targetLang: targetLocale,
                  sourceLang: config.source_locale,
                  honorific: config.honorific || 'formal',
                  respectfulSuffix: config.respectful_suffix,
                });

                if (res) {
                  translatedEntries.push({
                    key: item.key,
                    sourceText: item.sourceText,
                    translatedText: res.text,
                  });
                  totalTranslated++;
                }
              })
            )
          );

          // Merge translated entries into target
          const merged = entries.map((entry) => {
            const match = translatedEntries.find((t) => t.key === entry.key);
            if (match) {
              return match;
            }
            const existing = targetEntries.find((t) => t.key === entry.key);
            return existing || entry;
          });

          const serialized = parser.serialize(
            fs.existsSync(targetFile) ? fs.readFileSync(targetFile, 'utf8') : sourceContent,
            merged
          );

          fs.mkdirSync(path.dirname(targetFile), { recursive: true });
          fs.writeFileSync(targetFile, serialized, 'utf8');
          console.log(chalk.green(`    [${targetLocale}] Wrote ${targetFile}`));
        }
      }
    }

    console.log(chalk.bold.green(`\n✓ Sync complete! (${totalTranslated} keys translated)\n`));
  }
}
