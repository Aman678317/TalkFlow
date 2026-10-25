// English corrector / rephraser: deterministic rules + word-level LCS diff.
// No network, no Node imports.

// ≥50 common misspellings (lowercase keys; matched whole-word, case-insensitively).
const MISSPELLINGS = {
  alot: "a lot",
  recieve: "receive",
  recieved: "received",
  recieves: "receives",
  recieving: "receiving",
  definately: "definitely",
  definatly: "definitely",
  seperate: "separate",
  seperated: "separated",
  seperately: "separately",
  teh: "the",
  untill: "until",
  wierd: "weird",
  beleive: "believe",
  beleived: "believed",
  buisness: "business",
  calender: "calendar",
  goverment: "government",
  occured: "occurred",
  occuring: "occurring",
  occurence: "occurrence",
  accomodate: "accommodate",
  acheive: "achieve",
  acheived: "achieved",
  agressive: "aggressive",
  apparant: "apparent",
  arguement: "argument",
  begining: "beginning",
  beleif: "belief",
  cemetary: "cemetery",
  changable: "changeable",
  collegue: "colleague",
  comming: "coming",
  commited: "committed",
  concious: "conscious",
  dissapoint: "disappoint",
  embarass: "embarrass",
  enviroment: "environment",
  existance: "existence",
  experiance: "experience",
  finaly: "finally",
  foriegn: "foreign",
  freind: "friend",
  gaurd: "guard",
  harrass: "harass",
  immediatly: "immediately",
  independant: "independent",
  inevitible: "inevitable",
  knowlege: "knowledge",
  liason: "liaison",
  maintainance: "maintenance",
  millenium: "millennium",
  neccessary: "necessary",
  necesary: "necessary",
  noticable: "noticeable",
  occassion: "occasion",
  oppurtunity: "opportunity",
  pasttime: "pastime",
  persistant: "persistent",
  posession: "possession",
  prefered: "preferred",
  priviledge: "privilege",
  probly: "probably",
  proffesional: "professional",
  reciept: "receipt",
  recomend: "recommend",
  recomendation: "recommendation",
  refering: "referring",
  relevent: "relevant",
  religous: "religious",
  remeber: "remember",
  responsibilty: "responsibility",
  rythm: "rhythm",
  seige: "siege",
  succesful: "successful",
  succesfully: "successfully",
  supress: "suppress",
  tommorow: "tomorrow",
  tommorrow: "tomorrow",
  truely: "truly",
  unfortunatly: "unfortunately",
  vaccum: "vacuum",
  wether: "whether",
  writting: "writing",
  adress: "address",
  basicly: "basically",
  becuase: "because",
  completly: "completely",
  diferent: "different",
  diffrent: "different",
  excersize: "exercise",
  familar: "familiar",
  garantee: "guarantee",
  happend: "happened",
  intrest: "interest",
  langauge: "language",
  lenght: "length",
  libary: "library",
  mistery: "mystery",
  ninty: "ninety",
  publically: "publicly",
  realy: "really",
  sesion: "session",
  similiar: "similar",
  suprise: "surprise",
  thier: "their",
  threshhold: "threshold",
  usefull: "useful",
  wonderfull: "wonderful",
  // Un-apostrophised contractions are common spelling slips too.
  dont: "don't",
  doesnt: "doesn't",
  didnt: "didn't",
  isnt: "isn't",
  arent: "aren't",
  wasnt: "wasn't",
  werent: "weren't",
  hasnt: "hasn't",
  havent: "haven't",
  couldnt: "couldn't",
  wouldnt: "wouldn't",
  shouldnt: "shouldn't",
  youre: "you're",
  theyre: "they're",
  weve: "we've",
  ive: "I've",
  im: "I'm",
  cant: "can't",
  wont: "won't",
};

const BUSINESS_EXPANSIONS = {
  "won't": "will not",
  "can't": "cannot",
  "don't": "do not",
  "doesn't": "does not",
  "didn't": "did not",
  "isn't": "is not",
  "aren't": "are not",
  "wasn't": "was not",
  "weren't": "were not",
  "haven't": "have not",
  "hasn't": "has not",
  "hadn't": "had not",
  "couldn't": "could not",
  "wouldn't": "would not",
  "shouldn't": "should not",
  "mustn't": "must not",
  "i'm": "I am",
  "i've": "I have",
  "i'll": "I will",
  "i'd": "I would",
  "we're": "we are",
  "we've": "we have",
  "we'll": "we will",
  "they're": "they are",
  "they've": "they have",
  "you're": "you are",
  "you've": "you have",
  "it's": "it is",
  "that's": "that is",
  "there's": "there is",
  "let's": "let us",
};

const ACADEMIC_EXPANSIONS = {
  gonna: "going to",
  hafta: "have to",
  wanna: "want to",
  gotta: "have to",
  kinda: "kind of",
  sorta: "sort of",
};

const CASUAL_CONTRACTIONS = {
  "will not": "won't",
  "can not": "can't",
  "cannot": "can't",
  "do not": "don't",
  "does not": "doesn't",
  "did not": "didn't",
  "is not": "isn't",
  "are not": "aren't",
  "was not": "wasn't",
  "were not": "weren't",
  "have not": "haven't",
  "has not": "hasn't",
  "had not": "hadn't",
  "could not": "couldn't",
  "would not": "wouldn't",
  "should not": "shouldn't",
  "i am": "I'm",
  "i have": "I've",
  "i will": "I'll",
  "we are": "we're",
  "they are": "they're",
  "you are": "you're",
  "it is": "it's",
  "that is": "that's",
  "there is": "there's",
  "let us": "let's",
};

const WORD_TOKEN = /\b[A-Za-z]+(?:['’][A-Za-z]+)?\b/g;
const SPLIT_CONJUNCTION = ", and ";

function matchCase(word, replacement) {
  if (!word || !replacement) return replacement;
  if (word.length > 1 && word === word.toUpperCase() && /[A-Z]/.test(word)) {
    return replacement.toUpperCase();
  }
  if (/[A-Z]/.test(word[0])) {
    return replacement[0].toUpperCase() + replacement.slice(1);
  }
  return replacement;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function addChange(changes, type, before, after, description) {
  if (before !== after) changes.push({ type, before, after, description });
}

// Replace whole terms (single or multi word) case-insensitively, recording style changes.
function replaceTerms(text, map, changes, description) {
  const keys = Object.keys(map).sort((a, b) => b.length - a.length);
  if (!keys.length) return text;
  const pattern = keys
    .map((k) => escapeRegExp(k).replace(/['’]/g, "['’]"))
    .join("|");
  const re = new RegExp(`(?<![\\p{L}\\p{N}_])(?:${pattern})(?![\\p{L}\\p{N}_])`, "giu");
  return text.replace(re, (matched) => {
    const key = matched.toLowerCase().replace(/’/g, "'");
    const replacement = map[key];
    if (replacement == null) return matched;
    const fixed = matchCase(matched, replacement);
    addChange(changes, "style", matched, fixed, description);
    return fixed;
  });
}

function countWords(sentence) {
  return (sentence.match(/[\p{L}\p{N}]+(?:['’-][\p{L}\p{N}]+)*/gu) || []).length;
}

// Split >28-word sentences at "; " or ", and " for the "simple" style.
function simplifySentences(text, changes) {
  return text
    .split(/(\n)/)
    .map((line) => {
      if (line === "\n") return line;
      const sentences = line.split(/(?<=[.!?…])\s+/);
      const out = [];
      for (const sentence of sentences) {
        let current = sentence;
        for (let guard = 0; guard < 8 && countWords(current) > 28; guard++) {
          let split = null;
          const semicolon = current.indexOf(";");
          const conjunction = current.indexOf(SPLIT_CONJUNCTION);
          if (semicolon > 0) split = { index: semicolon, length: 1 };
          else if (conjunction > 0) {
            split = { index: conjunction, length: SPLIT_CONJUNCTION.length };
          }
          if (!split) break;
          const before = current
            .slice(0, split.index)
            .replace(/[;,]\s*$/, "")
            .trimEnd();
          let after = current.slice(split.index + split.length).trimStart();
          if (!before || !after) break;
          after = after[0].toUpperCase() + after.slice(1);
          addChange(
            changes,
            "style",
            current,
            `${before}. ${after}`,
            "Split a long sentence for a simple style",
          );
          out.push(`${before}.`);
          current = after;
        }
        out.push(current);
      }
      return out.join(" ");
    })
    .join("");
}

// Word-level LCS diff over whitespace-delimited tokens (punctuation stays attached).
function wordDiff(original, corrected) {
  const a = original.trim() ? original.trim().split(/\s+/) : [];
  const b = corrected.trim() ? corrected.trim().split(/\s+/) : [];
  if (!a.length && !b.length) return [];
  if (a.length * b.length > 250000) {
    return [
      ...a.map((value) => ({ kind: "del", value })),
      ...b.map((value) => ({ kind: "ins", value })),
    ];
  }
  const dp = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i][j] =
        a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "eq", value: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ kind: "del", value: a[i] });
      i++;
    } else {
      out.push({ kind: "ins", value: b[j] });
      j++;
    }
  }
  while (i < a.length) out.push({ kind: "del", value: a[i++] });
  while (j < b.length) out.push({ kind: "ins", value: b[j++] });
  return out;
}

export function correctEnglish(text, options = {}) {
  const mode = options.mode === "rephrase" ? "rephrase" : "correct";
  const style = ["business", "academic", "casual", "simple"].includes(options.style)
    ? options.style
    : "default";
  const original = typeof text === "string" ? text : "";
  const changes = [];
  let out = original;

  // 1) Spelling (case-preserving, whole word).
  out = out.replace(WORD_TOKEN, (word) => {
    const replacement = MISSPELLINGS[word.toLowerCase()];
    if (!replacement) return word;
    const fixed = matchCase(word, replacement);
    addChange(changes, "spelling", word, fixed, `Corrected spelling of "${word}"`);
    return fixed;
  });

  // 2) Pronoun "i".
  out = out.replace(/\bi\b(?!\.)/g, () => {
    addChange(changes, "grammar", "i", "I", 'Capitalized the pronoun "I"');
    return "I";
  });

  // 3) Duplicate consecutive words.
  const duplicate = /\b([A-Za-z]+(?:['’][A-Za-z]+)?)\s+\1\b/gi;
  for (let guard = 0; guard < 20; guard++) {
    const match = duplicate.exec(out);
    if (!match) break;
    const before = match[0];
    const after = match[1];
    out = out.slice(0, match.index) + after + out.slice(match.index + before.length);
    addChange(changes, "grammar", before, after, `Removed duplicate word "${after}"`);
    duplicate.lastIndex = 0;
  }

  // 4) Whitespace and punctuation spacing.
  out = out.replace(/[ \t]{2,}/g, (match) => {
    addChange(changes, "punctuation", match, " ", "Collapsed repeated spaces");
    return " ";
  });
  out = out.replace(/[ \t]+([,.;:!?])/g, (match, punct) => {
    addChange(changes, "punctuation", match, punct, "Removed space before punctuation");
    return punct;
  });
  out = out.replace(/([a-z]{2,}[.!?])([A-Za-z])/g, (match, punct, letter) => {
    const fixed = `${punct} ${letter}`;
    addChange(
      changes,
      "punctuation",
      match,
      fixed,
      "Added a space after sentence punctuation",
    );
    return fixed;
  });

  // 5) Rephrase styles.
  if (mode === "rephrase") {
    if (style === "business") {
      out = replaceTerms(
        out,
        BUSINESS_EXPANSIONS,
        changes,
        "Expanded contraction for a business tone",
      );
    } else if (style === "academic") {
      out = replaceTerms(
        out,
        ACADEMIC_EXPANSIONS,
        changes,
        "Replaced informal wording for an academic tone",
      );
    } else if (style === "casual") {
      out = replaceTerms(
        out,
        CASUAL_CONTRACTIONS,
        changes,
        "Collapsed formal phrasing for a casual tone",
      );
    } else if (style === "simple") {
      out = simplifySentences(out, changes);
    }
  }

  // 6) Terminal punctuation.
  const trimmed = out.trimEnd();
  if (trimmed && !/[.!?…:;]["'”’)\]]*$/.test(trimmed)) {
    out = `${trimmed}.`;
    addChange(changes, "punctuation", "", ".", "Added terminal punctuation");
  } else if (trimmed !== out) {
    out = trimmed;
  }

  // 7) Capitalize sentence starts.
  out = out.replace(/(^|[.!?…]\s+)(["'“‘(\[]*)([a-z])/gm, (match, lead, opener, letter) => {
    const fixed = lead + opener + letter.toUpperCase();
    addChange(
      changes,
      "grammar",
      match,
      fixed,
      "Capitalized the start of a sentence",
    );
    return fixed;
  });

  return { original, corrected: out, changes, diff: wordDiff(original, out) };
}
