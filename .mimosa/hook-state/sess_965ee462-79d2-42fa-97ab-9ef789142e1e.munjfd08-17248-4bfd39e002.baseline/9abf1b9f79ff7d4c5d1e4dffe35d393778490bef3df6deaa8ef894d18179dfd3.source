import fs from 'node:fs';
import path from 'node:path';
import ora from 'ora';
import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { DesiCliError } from '../types/index.js';

export class DocumentService {
  constructor(private client: DesiClient) {}

  public async translateDocument(
    filePath: string,
    targetLang: string,
    options: {
      sourceLang?: string;
      formality?: string;
      outputPath?: string;
    }
  ): Promise<void> {
    if (!fs.existsSync(filePath)) {
      throw new DesiCliError(`Document file not found: ${filePath}`, 6);
    }

    const filename = path.basename(filePath);
    const fileBuffer = fs.readFileSync(filePath);

    const spinner = ora(`Uploading ${filename} for translation...`).start();

    try {
      const { documentId, documentKey } = await this.client.uploadDocument(
        fileBuffer,
        filename,
        targetLang,
        options.sourceLang,
        options.formality
      );

      spinner.text = `Translating ${filename} to ${targetLang.toUpperCase()}...`;

      // Poll until done or error
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        const status = await this.client.checkDocumentStatus(documentId, documentKey);

        if (status.status === 'done') {
          spinner.text = `Downloading translated document...`;
          const translatedBuffer = await this.client.downloadDocument(documentId, documentKey);

          const ext = path.extname(filePath);
          const base = path.basename(filePath, ext);
          const defaultOutput = path.join(
            path.dirname(filePath),
            `${base}.${targetLang}${ext}`
          );
          const finalOutput = options.outputPath || defaultOutput;

          fs.writeFileSync(finalOutput, translatedBuffer);
          spinner.succeed(
            chalk.green(
              `Translated document saved to ${finalOutput} (Billed characters: ${status.billedCharacters || 0})`
            )
          );
          break;
        }

        if (status.status === 'error') {
          spinner.fail(chalk.red(`Document translation failed: ${status.errorMessage}`));
          throw new DesiCliError(`Document translation failed: ${status.errorMessage}`, 1);
        }

        if (status.secondsRemaining !== undefined && status.secondsRemaining > 0) {
          spinner.text = `Translating ${filename} (est. ${status.secondsRemaining}s remaining)...`;
        }
      }
    } catch (err: any) {
      spinner.fail(err.message);
      throw err;
    }
  }
}
