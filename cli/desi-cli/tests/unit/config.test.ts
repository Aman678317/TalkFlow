import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { ConfigManager } from '../../src/storage/config.js';

describe('ConfigManager', () => {
  let tempDir: string;
  let originalEnv: NodeJS.ProcessEnv;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'desi-config-test-'));
    originalEnv = { ...process.env };
    // Clear out any external env vars that could bleed into tests
    delete process.env.DESI_API_KEY;
    delete process.env.GLOBAL_TALK_API_KEY;
    delete process.env.DEEPL_API_KEY;
    delete process.env.DESI_API_URL;
    delete process.env.GLOBAL_TALK_API_URL;
    delete process.env.DEEPL_API_URL;
    delete process.env.DESI_CONFIG_DIR;
  });

  afterEach(() => {
    process.env = originalEnv;
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  it('should use custom config directory when provided', () => {
    const configManager = new ConfigManager(tempDir);
    expect(configManager.getConfigDir()).toBe(tempDir);
    expect(configManager.getConfigFilePath()).toBe(path.join(tempDir, 'config.json'));
  });

  it('should use DESI_CONFIG_DIR environment variable when set', () => {
    const customPath = path.join(tempDir, 'custom-env-dir');
    process.env.DESI_CONFIG_DIR = customPath;

    const configManager = new ConfigManager();
    expect(configManager.getConfigDir()).toBe(customPath);
  });

  it('should load default configuration when config file does not exist', () => {
    const configManager = new ConfigManager(tempDir);
    const config = configManager.loadConfig();

    expect(config.apiUrl).toBe('https://api.globaltalk.ai');
    expect(config.apiKey).toBeUndefined();
    expect(config.defaultTargetLang).toBe('hi');
    expect(config.defaultHonorific).toBe('formal');
    expect(config.enableCache).toBe(true);
    expect(config.maxRetries).toBe(3);
    expect(config.timeoutMs).toBe(30000);
  });

  it('should save and load persistent configuration values', () => {
    const configManager = new ConfigManager(tempDir);

    configManager.saveConfig({
      apiKey: 'gtk_live_test_key_12345',
      defaultTargetLang: 'te',
      defaultHonorific: 'familiar',
    });

    const loaded = configManager.loadConfig();
    expect(loaded.apiKey).toBe('gtk_live_test_key_12345');
    expect(loaded.defaultTargetLang).toBe('te');
    expect(loaded.defaultHonorific).toBe('familiar');
  });

  it('should give precedence to environment variables over config file', () => {
    const configManager = new ConfigManager(tempDir);
    configManager.saveConfig({
      apiKey: 'file_key_123',
      apiUrl: 'https://file.api.desi.ai',
    });

    // Native DESI_API_KEY override
    process.env.DESI_API_KEY = 'env_desi_key_456';
    process.env.DESI_API_URL = 'https://custom.api.desi.ai';

    const loaded = configManager.loadConfig();
    expect(loaded.apiKey).toBe('env_desi_key_456');
    expect(loaded.apiUrl).toBe('https://custom.api.desi.ai');
  });

  it('should support backwards-compatible DEEPL_API_KEY environment variable fallback', () => {
    const configManager = new ConfigManager(tempDir);
    process.env.DEEPL_API_KEY = 'deepl_legacy_key_789';

    const loaded = configManager.loadConfig();
    expect(loaded.apiKey).toBe('deepl_legacy_key_789');
  });

  it('should correctly set individual keys with type conversions', () => {
    const configManager = new ConfigManager(tempDir);

    configManager.setKey('timeoutMs', '45000');
    configManager.setKey('enableCache', 'false');
    configManager.setKey('defaultTargetLang', 'bn');

    const loaded = configManager.loadConfig();
    expect(loaded.timeoutMs).toBe(45000);
    expect(loaded.enableCache).toBe(false);
    expect(loaded.defaultTargetLang).toBe('bn');
  });

  it('should throw error when attempting to set an invalid key', () => {
    const configManager = new ConfigManager(tempDir);

    expect(() => {
      configManager.setKey('unsupportedKey', 'value');
    }).toThrow('Invalid configuration key');
  });

  it('should reset configuration by deleting config file', () => {
    const configManager = new ConfigManager(tempDir);
    configManager.saveConfig({ apiKey: 'to_be_deleted' });
    expect(fs.existsSync(configManager.getConfigFilePath())).toBe(true);

    configManager.resetConfig();
    expect(fs.existsSync(configManager.getConfigFilePath())).toBe(false);
  });
});
