// The core-emoji pack, read straight from the repo so Studio never drifts from what Purple ships.
import coreEmoji from "../../../../packs/core-emoji/content/emoji.json";
import coreSynonyms from "../../../../packs/core-emoji/content/synonyms.json";
import coreRankings from "../../../../packs/core-emoji/content/rankings.txt?raw";

export const CORE_EMOJI: Record<string, string> = coreEmoji;
export const CORE_SYNONYMS: Record<string, string> = coreSynonyms;

export const CORE_RANKED_WORDS: string[] = coreRankings
  .split("\n")
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith("#"));

const RANKED = new Set(CORE_RANKED_WORDS);

export const isCoreWord = (word: string) => word in CORE_EMOJI || word in CORE_SYNONYMS;
export const isCoreRanked = (word: string) => RANKED.has(word);
