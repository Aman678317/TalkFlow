import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { IndicScript, TransliterateResult, NormalizeResult } from '../types/index.js';
import { INDIC_LANGUAGES } from '../data/language-registry.js';

export class IndicService {
  constructor(private client: DesiClient) {}

  public async transliterateText(
    text: string,
    targetScript: IndicScript = 'devanagari',
    sourceScript: IndicScript = 'latin'
  ): Promise<TransliterateResult[]> {
    return this.client.transliterate(text, targetScript, sourceScript);
  }

  public async normalizeText(
    text: string,
    cleanZwnj = true,
    fixNuktas = true
  ): Promise<NormalizeResult> {
    return this.client.normalize(text, cleanZwnj, fixNuktas);
  }

  public listIndicLanguages(): void {
    console.log(chalk.bold.cyan('\n=== 22 Official Eighth Schedule Indian Languages ===\n'));
    for (const lang of INDIC_LANGUAGES) {
      console.log(
        `${chalk.green(lang.code.padEnd(5))} ${chalk.bold(lang.name.padEnd(12))} (${lang.nativeName?.padEnd(16)})  Script: ${lang.script?.padEnd(14)} Formality: ${lang.supportsFormality ? '✅' : '—'}`
      );
    }
    console.log();
  }
}
