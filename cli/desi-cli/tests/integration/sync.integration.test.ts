import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {
  JsonFormatParser,
  YamlFormatParser,
  AndroidXmlFormatParser,
  getFormatParserForFile,
} from '../../src/formats/index.js';
import { SyncService } from '../../src/sync/sync-service.js';
import { DesiClient } from '../../src/api/desi-client.js';

describe('Sync & Format Parsers Integration', () => {
  let tempDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'desi-sync-test-'));
  });

  afterEach(() => {
    fs.rmSync(tempDir, { recursive: true, force: true });
  });

  describe('Format Parsers', () => {
    it('JsonFormatParser: should parse nested JSON and serialize translations preserving structure', () => {
      const parser = new JsonFormatParser();
      const originalJson = JSON.stringify(
        {
          navbar: {
            title: 'Multilingual Hub',
            logout: 'Log Out',
          },
          count: 42,
        },
        null,
        2
      );

      const parsed = parser.parse(originalJson);
      expect(parsed).toHaveLength(2);
      expect(parsed.find((p) => p.key === 'navbar.title')?.sourceText).toBe('Multilingual Hub');
      expect(parsed.find((p) => p.key === 'navbar.logout')?.sourceText).toBe('Log Out');

      // Update translated values
      parsed[0]!.translatedText = 'हब';
      parsed[1]!.translatedText = 'लॉग आउट';

      const serialized = parser.serialize(originalJson, parsed);
      const reParsed = JSON.parse(serialized);

      expect(reParsed.navbar.title).toBe('हब');
      expect(reParsed.navbar.logout).toBe('लॉग आउट');
      expect(reParsed.count).toBe(42); // Non-string numbers preserved!
    });

    it('YamlFormatParser: should parse and serialize YAML key structures', () => {
      const parser = new YamlFormatParser();
      const yamlContent = `
app:
  name: GlobalTalk AI
  tagline: Breaking language barriers
`;

      const parsed = parser.parse(yamlContent);
      expect(parsed).toHaveLength(2);
      expect(parsed.find((p) => p.key === 'app.name')?.sourceText).toBe('GlobalTalk AI');

      parsed[1]!.translatedText = 'भाषा की बाधाओं को तोड़ना';
      const serialized = parser.serialize(yamlContent, parsed);

      expect(serialized).toContain('भाषा की बाधाओं को तोड़ना');
    });

    it('AndroidXmlFormatParser: should parse and replace Android XML string elements', () => {
      const parser = new AndroidXmlFormatParser();
      const xmlContent = `<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">GlobalTalk</string>
    <string name="welcome_message">Welcome User</string>
</resources>`;

      const parsed = parser.parse(xmlContent);
      expect(parsed).toHaveLength(2);
      expect(parsed[0]?.key).toBe('app_name');
      expect(parsed[0]?.sourceText).toBe('GlobalTalk');
      expect(parsed[1]?.key).toBe('welcome_message');
      expect(parsed[1]?.sourceText).toBe('Welcome User');

      parsed[1]!.translatedText = 'उपयोगकर्ता का स्वागत है';
      const serialized = parser.serialize(xmlContent, parsed);

      expect(serialized).toContain('<string name="welcome_message">उपयोगकर्ता का स्वागत है</string>');
      expect(serialized).toContain('<string name="app_name">GlobalTalk</string>');
    });

    it('getFormatParserForFile: should return correct parser based on file extension', () => {
      expect(getFormatParserForFile('locales/en.json')).toBeInstanceOf(JsonFormatParser);
      expect(getFormatParserForFile('locales/en.yaml')).toBeInstanceOf(YamlFormatParser);
      expect(getFormatParserForFile('locales/en.yml')).toBeInstanceOf(YamlFormatParser);
      expect(getFormatParserForFile('res/values/strings.xml')).toBeInstanceOf(AndroidXmlFormatParser);
    });
  });

  describe('SyncService Workflow', () => {
    it('should scan source locale, detect untranslated keys, and translate into target locale', async () => {
      // Setup file structure
      const localesDir = path.join(tempDir, 'locales');
      const enDir = path.join(localesDir, 'en');
      const hiDir = path.join(localesDir, 'hi');
      fs.mkdirSync(enDir, { recursive: true });
      fs.mkdirSync(hiDir, { recursive: true });

      const enFile = path.join(enDir, 'messages.json');
      fs.writeFileSync(
        enFile,
        JSON.stringify(
          {
            greeting: 'Hello, world!',
            farewell: 'Goodbye!',
          },
          null,
          2
        ),
        'utf8'
      );

      // Setup .desi-sync.yaml
      const configYaml = `
version: 1
source_locale: en
target_locales:
  - hi
honorific: formal
respectful_suffix: true
buckets:
  - name: messages
    format: json
    source_path: ${enFile.replace(/\\/g, '/')}
    target_path_pattern: ${path.join(localesDir, '{locale}', 'messages.json').replace(/\\/g, '/')}
`;
      fs.writeFileSync(path.join(tempDir, '.desi-sync.yaml'), configYaml, 'utf8');

      // Setup Mock Client
      const mockClient = {
        translate: jest.fn().mockImplementation((opts: any) => {
          if (opts.text === 'Hello, world!') {
            return Promise.resolve([{ text: 'नमस्ते, दुनिया!' }]);
          }
          if (opts.text === 'Goodbye!') {
            return Promise.resolve([{ text: 'अलविida!' }]);
          }
          return Promise.resolve([{ text: opts.text }]);
        }),
      } as unknown as jest.Mocked<DesiClient>;

      const syncService = new SyncService(mockClient, tempDir);
      await syncService.runSync();

      const hiFile = path.join(hiDir, 'messages.json');
      expect(fs.existsSync(hiFile)).toBe(true);

      const hiContent = JSON.parse(fs.readFileSync(hiFile, 'utf8'));
      expect(hiContent.greeting).toBe('नमस्ते, दुनिया!');
      expect(hiContent.farewell).toBe('अलविida!');
    });

    it('should respect --dry-run and not write translated files to disk', async () => {
      const sourceFile = path.join(tempDir, 'source.json');
      const targetFile = path.join(tempDir, 'target.json');

      fs.writeFileSync(sourceFile, JSON.stringify({ key: 'Dry run test' }), 'utf8');

      const configYaml = `
version: 1
source_locale: en
target_locales:
  - de
buckets:
  - name: test
    format: json
    source_path: ${sourceFile.replace(/\\/g, '/')}
    target_path_pattern: ${targetFile.replace(/\\/g, '/')}
`;
      fs.writeFileSync(path.join(tempDir, '.desi-sync.yaml'), configYaml, 'utf8');

      const mockClient = {
        translate: jest.fn(),
      } as unknown as jest.Mocked<DesiClient>;

      const syncService = new SyncService(mockClient, tempDir);
      await syncService.runSync({ dryRun: true });

      expect(mockClient.translate).not.toHaveBeenCalled();
      expect(fs.existsSync(targetFile)).toBe(false);
    });
  });
});
