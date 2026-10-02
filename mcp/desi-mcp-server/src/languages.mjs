// --------------------------------------------------------------------------------------------------
// Copyright (c) 2026 GlobalTalk AI Authors. All rights reserved.
// Licensed under the MIT License.
// --------------------------------------------------------------------------------------------------

export class LanguagesList {
  static countryDefaults = {
    en: "en-US",
    pt: "pt-BR",
    zh: "zh-Hans",
  };

  constructor(list, direction = null) {
    this.list = list;
    this.codesList = list.map((lang) => (lang.language || lang.code).toLowerCase()).join(", ");
    this.direction = direction;
  }

  static async create(client, direction) {
    if (direction !== "source" && direction !== "target") {
      throw new Error('LanguagesList needs to be called with "target" or "source"');
    }

    const method = direction === "source" ? "getSourceLanguages" : "getTargetLanguages";
    const langs = await client[method]();
    const normalized = langs.map((lang) => ({
      name: lang.name,
      code: (lang.language || lang.code).toLowerCase(),
    }));
    return new LanguagesList(normalized, direction);
  }

  normalize(code) {
    if (!code) return "";
    const lowerCode = code.toLowerCase();
    let countryDefault;

    if (
      this.direction === "target" &&
      (countryDefault = LanguagesList.countryDefaults[lowerCode])
    ) {
      return countryDefault;
    }

    if (this.list.some((lang) => lang.code === lowerCode)) {
      return lowerCode;
    }

    const baseCode = lowerCode.split("-")[0];
    if (this.direction === "source" && this.list.some((lang) => lang.code === baseCode)) {
      return baseCode;
    }

    return lowerCode;
  }
}

export class LanguageCache {
  #client;
  #pending = new Map();

  constructor(client) {
    this.#client = client;
  }

  async get(direction) {
    let pending = this.#pending.get(direction);

    if (!pending) {
      pending = LanguagesList.create(this.#client, direction).catch((error) => {
        this.#pending.delete(direction);
        throw error;
      });
      this.#pending.set(direction, pending);
    }

    return pending;
  }
}
