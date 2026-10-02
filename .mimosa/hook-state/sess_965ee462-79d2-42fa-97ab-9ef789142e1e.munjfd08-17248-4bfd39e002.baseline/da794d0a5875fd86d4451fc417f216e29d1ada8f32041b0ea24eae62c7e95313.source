#!/usr/bin/env node

import { Command } from 'commander';
import chalk from 'chalk';
import readline from 'node:readline';
import { VERSION } from '../version.js';
import { ConfigManager } from '../storage/config.js';
import { CacheManager } from '../storage/cache.js';
import { DesiClient } from '../api/desi-client.js';
import { TranslationService } from '../services/translation.js';
import { IndicService } from '../services/indic.js';
import { WriteService } from '../services/write.js';
import { VoiceService } from '../services/voice.js';
import { DocumentService } from '../services/document.js';
import { SyncService } from '../sync/sync-service.js';
import { DesiCliError, FormalityTier, IndicScript } from '../types/index.js';

const program = new Command();
const configManager = new ConfigManager();
const appConfig = configManager.loadConfig();
const cacheManager = new CacheManager(undefined, appConfig.enableCache);
const desiClient = new DesiClient(appConfig);

const translationService = new TranslationService(desiClient, cacheManager);
const indicService = new IndicService(desiClient);
const writeService = new WriteService(desiClient);
const voiceService = new VoiceService(desiClient);
const documentService = new DocumentService(desiClient);
const syncService = new SyncService(desiClient);

program
  .name('desi')
  .description('Desi Language AI & GlobalTalk AI CLI: 100+ World Languages, 22 Indic Languages, Cultural Honorifics, Continuous Sync & Voice Streaming')
  .version(VERSION);

// Global options
program
  .option('--api-key <key>', 'Override API Key for this request')
  .option('--api-url <url>', 'Override API Endpoint URL')
  .option('--no-cache', 'Bypass local translation cache')
  .hook('preAction', (thisCommand) => {
    const opts = thisCommand.opts();
    if (opts.apiKey) {
      appConfig.apiKey = opts.apiKey;
    }
    if (opts.apiUrl) {
      appConfig.apiUrl = opts.apiUrl;
    }
  });

// 1. translate
program
  .command('translate [input]')
  .description('Translate text, files, or standard input across 100+ global and 22 Indic languages')
  .requiredOption('-t, --to <langs>', 'Target language codes (comma-separated, e.g. hi,es,de)')
  .option('-f, --from <lang>', 'Source language code (auto-detected if omitted)')
  .option('--honorific <tier>', 'Formality tier: formal, familiar, intimate, respectful, neutral', 'formal')
  .option('--respectful-suffix', 'Append respectful suffix (-ji, -garu, -avargal)', false)
  .option('-o, --output <path>', 'Output file or directory path')
  .option('--format <type>', 'Output format: text, json, table', 'text')
  .option('--show-billed-characters', 'Show billed character counts', false)
  .option('--preserve-code', 'Preserve markdown code fences', false)
  .action(async (input, options) => {
    try {
      const targetLangs = options.to.split(',').map((l: string) => l.trim().toLowerCase());

      let textToTranslate = input;
      if (!textToTranslate && !process.stdin.isTTY) {
        // Read from stdin
        const rl = readline.createInterface({ input: process.stdin });
        const lines: string[] = [];
        for await (const line of rl) {
          lines.push(line);
        }
        textToTranslate = lines.join('\n');
      }

      if (!textToTranslate) {
        throw new DesiCliError('Please provide text or pipe from stdin', 6);
      }

      const results = await translationService.translateText(textToTranslate, {
        targetLangs,
        sourceLang: options.from,
        honorific: options.honorific as FormalityTier,
        respectfulSuffix: options.respectfulSuffix,
        showBilledCharacters: options.showBilledCharacters,
        preserveCode: options.preserveCode,
        output: options.output,
        noCache: !program.opts().cache,
      });

      translationService.renderOutput(results, options.format, options.showBilledCharacters);
    } catch (err: any) {
      handleError(err);
    }
  });

// 2. transliterate
program
  .command('transliterate [text]')
  .description('Phonetically convert Latin/Romanized text (Hinglish/Tanglish) to native Brahmic scripts')
  .option('--to <script>', 'Target script (devanagari, bengali, tamil, telugu, etc.)', 'devanagari')
  .option('--from <script>', 'Source script', 'latin')
  .action(async (text, options) => {
    try {
      if (!text && !process.stdin.isTTY) {
        const rl = readline.createInterface({ input: process.stdin });
        for await (const line of rl) {
          const [res] = await indicService.transliterateText(line, options.to as IndicScript, options.from as IndicScript);
          console.log(res?.transliteratedText);
        }
        return;
      }
      if (!text) {
        throw new DesiCliError('Please provide text to transliterate', 6);
      }
      const [res] = await indicService.transliterateText(text, options.to as IndicScript, options.from as IndicScript);
      console.log(res?.transliteratedText);
    } catch (err: any) {
      handleError(err);
    }
  });

// 3. normalize
program
  .command('normalize [text]')
  .description('Sanitize Indic Unicode text, cleaning ZWNJ/ZWJ anomalies and composed nuktas')
  .action(async (text) => {
    try {
      if (!text) {
        throw new DesiCliError('Please provide text to normalize', 6);
      }
      const res = await indicService.normalizeText(text);
      console.log(res.normalizedText);
    } catch (err: any) {
      handleError(err);
    }
  });

// 4. write
program
  .command('write [input]')
  .description('Rephrase and polish text style/tone with Desi Write')
  .option('--style <style>', 'Writing style (academic, business, casual, simple, creative)', 'business')
  .option('--tone <tone>', 'Tone (confident, diplomatic, enthusiastic, friendly, neutral)', 'diplomatic')
  .option('--lang <lang>', 'Target language code', 'en')
  .option('--check', 'Check if improvements are suggested (exit code 8 if changes needed)', false)
  .option('--fix', 'Apply improvements in place', false)
  .option('--backup', 'Create .desi.bak file when applying in place', false)
  .option('--diff', 'Display colorful visual diff', false)
  .action(async (input, options) => {
    try {
      if (!input) {
        throw new DesiCliError('Please provide text or a file path', 6);
      }
      if (input.endsWith('.txt') || input.endsWith('.md')) {
        await writeService.processFile(input, 'write', options);
        return;
      }
      const res = await writeService.rephrase({
        text: input,
        targetLang: options.lang,
        style: options.style,
        tone: options.tone,
      });
      const improved = res.improvements[0]?.text || input;
      if (options.diff) {
        writeService.renderDiff(input, improved);
      } else {
        console.log(improved);
      }
    } catch (err: any) {
      handleError(err);
    }
  });

// 5. correct (alias: c)
program
  .command('correct [input]')
  .alias('c')
  .description('Correct grammar and spelling without changing phrasing')
  .option('--check', 'Check if errors exist', false)
  .option('--fix', 'Fix in place', false)
  .action(async (input, options) => {
    try {
      if (!input) {
        throw new DesiCliError('Please provide text or a file path', 6);
      }
      const res = await writeService.correct(input);
      console.log(res.correctedText);
    } catch (err: any) {
      handleError(err);
    }
  });

// 6. voice
program
  .command('voice [file]')
  .description('Real-time streaming audio translation via Desi Voice WebSocket')
  .requiredOption('-t, --to <langs>', 'Target translation languages (e.g. hi,en)')
  .option('-f, --from <lang>', 'Source audio language', 'en')
  .option('--content-type <mime>', 'Audio MIME format', 'audio/pcm;encoding=s16le;rate=16000')
  .option('--no-stream', 'Buffer output until complete')
  .action(async (file, options) => {
    try {
      const targetLangs = options.to.split(',').map((l: string) => l.trim().toLowerCase());
      await voiceService.streamAudio(file || process.stdin, targetLangs, {
        sourceLang: options.from,
        contentType: options.contentType,
        noStream: options.stream === false,
      });
    } catch (err: any) {
      handleError(err);
    }
  });

// 7. document
program
  .command('document <file>')
  .description('Translate documents preserving layouts (PDF, DOCX, PPTX, XLSX, HTML, TXT)')
  .requiredOption('-t, --to <lang>', 'Target language code')
  .option('-f, --from <lang>', 'Source language code')
  .option('-o, --output <path>', 'Destination output path')
  .action(async (file, options) => {
    try {
      await documentService.translateDocument(file, options.to, {
        sourceLang: options.from,
        outputPath: options.output,
      });
    } catch (err: any) {
      handleError(err);
    }
  });

// 8. sync
const syncCmd = program.command('sync').description('Continuous localization sync engine');

syncCmd
  .command('run', { isDefault: true })
  .description('Scan project, translate untranslated keys, and update project files')
  .option('--dry-run', 'Preview changes without executing translations', false)
  .option('--force', 'Force re-translation of all keys', false)
  .action(async (options) => {
    try {
      await syncService.runSync(options);
    } catch (err: any) {
      handleError(err);
    }
  });

// 9. languages
program
  .command('languages')
  .description('List supported languages (global + 22 Eighth Schedule Indic languages)')
  .option('--indic', 'List only 22 official Indian languages', false)
  .action(async (options) => {
    try {
      if (options.indic) {
        indicService.listIndicLanguages();
        return;
      }
      indicService.listIndicLanguages();
      const langs = await desiClient.getLanguages('target');
      console.log(chalk.bold.cyan('=== Global World Languages ===\n'));
      for (const l of langs) {
        console.log(`- ${chalk.green(l.code)}: ${l.name} ${l.supportsFormality ? chalk.dim('(Supports Formality)') : ''}`);
      }
      console.log();
    } catch (err: any) {
      handleError(err);
    }
  });

// 10. usage
program
  .command('usage')
  .description('Display account character quotas and translation volume')
  .action(async () => {
    try {
      const usage = await desiClient.getUsage();
      console.log(chalk.bold.cyan('\n=== Desi & GlobalTalk AI Account Quota ===\n'));
      console.log(`Billed Characters: ${chalk.bold(usage.characterCount.toLocaleString())} / ${usage.characterLimit.toLocaleString()}`);
      console.log(`Documents Translated: ${chalk.bold(usage.documentCount.toLocaleString())} / ${usage.documentLimit.toLocaleString()}\n`);
    } catch (err: any) {
      handleError(err);
    }
  });

// 11. auth
const authCmd = program.command('auth').description('Manage API authentication');

authCmd
  .command('show')
  .description('Show current API key status')
  .action(() => {
    if (appConfig.apiKey) {
      const masked = `${appConfig.apiKey.slice(0, 4)}...${appConfig.apiKey.slice(-4)}`;
      console.log(chalk.green(`API Key configured: ${masked}`));
    } else {
      console.log(chalk.yellow('No API Key configured. Run "desi init" or set DESI_API_KEY.'));
    }
  });

authCmd
  .command('set-key')
  .description('Set API key via standard input')
  .option('--from-stdin', 'Read key from standard input', true)
  .action(async () => {
    const rl = readline.createInterface({ input: process.stdin });
    for await (const line of rl) {
      const key = line.trim();
      if (key) {
        configManager.saveConfig({ apiKey: key });
        console.log(chalk.green('API Key saved successfully.'));
        return;
      }
    }
  });

// 12. cache
const cacheCmd = program.command('cache').description('Manage local translation cache');

cacheCmd
  .command('stats')
  .description('Display cache statistics')
  .action(() => {
    const stats = cacheManager.getStats();
    console.log(chalk.cyan(`\nCache Entries: ${stats.totalEntries}`));
    console.log(`Cache Path: ${stats.cachePath}`);
    console.log(`Cache Enabled: ${stats.enabled ? chalk.green('Yes') : chalk.red('No')}\n`);
  });

cacheCmd
  .command('clear')
  .description('Purge all cached translations')
  .action(() => {
    cacheManager.clear();
    console.log(chalk.green('Cache cleared successfully.'));
  });

// 13. config
const configCmd = program.command('config').description('Inspect and update CLI settings');

configCmd
  .command('list')
  .description('List all configuration values')
  .action(() => {
    console.log(JSON.stringify(appConfig, null, 2));
  });

configCmd
  .command('set <key> <value>')
  .description('Set a configuration setting')
  .action((key, value) => {
    try {
      configManager.setKey(key, value);
      console.log(chalk.green(`Configuration updated: ${key} = ${value}`));
    } catch (err: any) {
      handleError(err);
    }
  });

configCmd
  .command('reset')
  .description('Reset all stored configurations')
  .action(() => {
    configManager.resetConfig();
    console.log(chalk.green('Configuration reset to defaults.'));
  });

// Error handling helper
function handleError(err: any): void {
  const exitCode = err.exitCode || 1;
  console.error(chalk.red(`Error: ${err.message}`));
  if (err.suggestion) {
    console.error(chalk.yellow(`Suggestion: ${err.suggestion}`));
  }
  process.exit(exitCode);
}

program.parse(process.argv);
