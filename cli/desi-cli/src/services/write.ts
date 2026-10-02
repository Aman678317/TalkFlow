import fs from 'node:fs';
import * as diff from 'diff';
import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { DesiCliError } from '../types/index.js';

export class WriteService {
  constructor(private client: DesiClient) {}

  public async rephrase(params: {
    text: string;
    targetLang?: string;
    style?: string;
    tone?: string;
  }) {
    return this.client.writeRephrase(params);
  }

  public async correct(text: string) {
    return this.client.writeCorrect(text);
  }

  public async processFile(
    filePath: string,
    mode: 'write' | 'correct',
    options: {
      style?: string;
      tone?: string;
      targetLang?: string;
      check?: boolean;
      fix?: boolean;
      backup?: boolean;
      showDiff?: boolean;
    }
  ): Promise<void> {
    if (!fs.existsSync(filePath)) {
      throw new DesiCliError(`File not found: ${filePath}`, 6);
    }

    const originalText = fs.readFileSync(filePath, 'utf8');
    let improvedText = originalText;

    if (mode === 'correct') {
      const res = await this.client.writeCorrect(originalText);
      improvedText = res.correctedText;
    } else {
      const res = await this.client.writeRephrase({
        text: originalText,
        style: options.style,
        tone: options.tone,
        targetLang: options.targetLang,
      });
      improvedText = res.improvements[0]?.text || originalText;
    }

    const hasChanges = originalText.trim() !== improvedText.trim();

    if (options.showDiff && hasChanges) {
      this.renderDiff(originalText, improvedText);
    }

    if (options.check) {
      if (hasChanges) {
        console.log(chalk.yellow(`Improvements suggested for ${filePath}`));
        process.exitCode = 8;
        return;
      } else {
        console.log(chalk.green(`No changes needed for ${filePath}`));
        process.exitCode = 0;
        return;
      }
    }

    if (options.fix && hasChanges) {
      if (options.backup) {
        fs.writeFileSync(`${filePath}.desi.bak`, originalText, 'utf8');
      }
      fs.writeFileSync(filePath, improvedText, 'utf8');
      console.log(chalk.green(`Updated ${filePath} in place.`));
      return;
    }

    if (!options.check && !options.fix) {
      console.log(improvedText);
    }
  }

  public renderDiff(original: string, improved: string): void {
    const changes = diff.diffWords(original, improved);
    let output = '';

    for (const part of changes) {
      if (part.added) {
        output += chalk.green(part.value);
      } else if (part.removed) {
        output += chalk.red.strikethrough(part.value);
      } else {
        output += chalk.dim(part.value);
      }
    }

    console.log(output);
  }
}
