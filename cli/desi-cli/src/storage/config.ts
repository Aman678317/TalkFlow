import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { AppConfig, DesiCliError } from '../types/index.js';

export class ConfigManager {
  private configDir: string;
  private configFilePath: string;

  constructor(customConfigDir?: string) {
    if (customConfigDir) {
      this.configDir = customConfigDir;
    } else if (process.env.DESI_CONFIG_DIR) {
      this.configDir = process.env.DESI_CONFIG_DIR;
    } else {
      const xdgConfig = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
      this.configDir = path.join(xdgConfig, 'desi-cli');
    }
    this.configFilePath = path.join(this.configDir, 'config.json');
  }

  public getConfigDir(): string {
    return this.configDir;
  }

  public getConfigFilePath(): string {
    return this.configFilePath;
  }

  public loadConfig(): AppConfig {
    let fileConfig: AppConfig = {};

    if (fs.existsSync(this.configFilePath)) {
      try {
        const raw = fs.readFileSync(this.configFilePath, 'utf8');
        fileConfig = JSON.parse(raw);
      } catch (err: any) {
        throw new DesiCliError(
          `Configuration error: Failed to parse ${this.configFilePath}: ${err.message}`,
          7,
          'Run "desi config reset" or edit the config file manually.'
        );
      }
    }

    // Environment variables take precedence over file settings
    const envApiKey =
      process.env.DESI_API_KEY ||
      process.env.GLOBAL_TALK_API_KEY ||
      process.env.DEEPL_API_KEY;

    const envApiUrl =
      process.env.DESI_API_URL ||
      process.env.GLOBAL_TALK_API_URL ||
      process.env.DEEPL_API_URL;

    return {
      apiUrl: envApiUrl || fileConfig.apiUrl || 'https://api.globaltalk.ai',
      apiKey: envApiKey || fileConfig.apiKey,
      defaultTargetLang: fileConfig.defaultTargetLang || 'hi',
      defaultHonorific: fileConfig.defaultHonorific || 'formal',
      enableCache: fileConfig.enableCache !== undefined ? fileConfig.enableCache : true,
      maxRetries: fileConfig.maxRetries || 3,
      timeoutMs: fileConfig.timeoutMs || 30000,
    };
  }

  public saveConfig(newConfig: Partial<AppConfig>): void {
    const existing = this.loadConfig();
    const merged: AppConfig = { ...existing, ...newConfig };

    if (!fs.existsSync(this.configDir)) {
      fs.mkdirSync(this.configDir, { recursive: true, mode: 0o700 });
    }

    fs.writeFileSync(this.configFilePath, JSON.stringify(merged, null, 2), {
      encoding: 'utf8',
      mode: 0o600,
    });
  }

  public setKey(key: string, value: any): void {
    const validKeys: (keyof AppConfig)[] = [
      'apiKey',
      'apiUrl',
      'defaultTargetLang',
      'defaultHonorific',
      'enableCache',
      'maxRetries',
      'timeoutMs',
    ];

    if (!validKeys.includes(key as keyof AppConfig)) {
      throw new DesiCliError(
        `Invalid configuration key: "${key}". Valid keys: ${validKeys.join(', ')}`,
        6
      );
    }

    const update: any = {};
    if (key === 'enableCache') {
      update[key] = value === 'true' || value === true;
    } else if (key === 'maxRetries' || key === 'timeoutMs') {
      update[key] = parseInt(value, 10);
    } else {
      update[key] = value;
    }

    this.saveConfig(update);
  }

  public resetConfig(): void {
    if (fs.existsSync(this.configFilePath)) {
      fs.unlinkSync(this.configFilePath);
    }
  }
}
