import fs from 'node:fs';
import WebSocket from 'ws';
import chalk from 'chalk';
import { DesiClient } from '../api/desi-client.js';
import { DesiCliError } from '../types/index.js';

export class VoiceService {
  constructor(private client: DesiClient) {}

  public async streamAudio(
    audioSource: string | Buffer,
    targetLangs: string[],
    options: {
      sourceLang?: string;
      contentType?: string;
      noStream?: boolean;
      chunkSize?: number;
      chunkIntervalMs?: number;
    }
  ): Promise<void> {
    const meetingId = `cli_voice_${Date.now()}`;
    const primaryTarget = targetLangs[0] || 'hi';

    // 1. Obtain ephemeral session token and WebSocket URL
    const session = await this.client.requestVoiceSession(
      meetingId,
      options.sourceLang || 'en',
      primaryTarget
    );

    return new Promise((resolve, reject) => {
      const ws = new WebSocket(session.websocketUrl);

      ws.on('open', async () => {
        if (!options.noStream) {
          console.log(chalk.cyan(`[Connected to Desi Voice Gateway - Meeting ${meetingId}]`));
        }

        let audioBuffer: Buffer;
        if (typeof audioSource === 'string') {
          if (!fs.existsSync(audioSource)) {
            ws.close();
            return reject(new DesiCliError(`Audio file not found: ${audioSource}`, 6));
          }
          audioBuffer = fs.readFileSync(audioSource);
        } else {
          audioBuffer = audioSource;
        }

        const chunkSize = options.chunkSize || 3200; // 100ms of 16kHz 16-bit mono PCM
        const interval = options.chunkIntervalMs || 100;
        let offset = 0;

        const intervalId = setInterval(() => {
          if (offset >= audioBuffer.length) {
            clearInterval(intervalId);
            // Send end of media signal
            ws.send(JSON.stringify({ end_of_source_media: {} }));
            return;
          }

          const chunk = audioBuffer.subarray(offset, offset + chunkSize);
          offset += chunkSize;

          ws.send(
            JSON.stringify({
              source_media_chunk: {
                data: chunk.toString('base64'),
              },
            })
          );
        }, interval);
      });

      ws.on('message', (data: WebSocket.Data) => {
        try {
          const msg = JSON.parse(data.toString());

          if (msg.source_transcript_update) {
            const concluded = msg.source_transcript_update.concluded || [];
            for (const seg of concluded) {
              process.stdout.write(chalk.dim(`[Source ${seg.language || ''}]: `) + seg.text + '\n');
            }
          }

          if (msg.target_transcript_update) {
            const concluded = msg.target_transcript_update.concluded || [];
            for (const seg of concluded) {
              console.log(chalk.bold.green(`[Translation ${msg.target_transcript_update.language || ''}]: `) + seg.text);
            }
          }

          if (msg.end_of_stream) {
            ws.close();
            resolve();
          }

          if (msg.error) {
            console.error(chalk.red(`Voice Stream Error: ${msg.error.error_message}`));
            ws.close();
            reject(new DesiCliError(msg.error.error_message, 9));
          }
        } catch {
          // Ignore parse errors on binary frames
        }
      });

      ws.on('error', (err) => {
        reject(new DesiCliError(`WebSocket connection error: ${err.message}`, 9));
      });
    });
  }
}
