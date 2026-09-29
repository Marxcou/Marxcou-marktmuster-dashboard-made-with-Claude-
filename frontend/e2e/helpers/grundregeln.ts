// Grundregeln für die Oberflächenprüfung. Die Liste verbotener Begriffe kommt aus dem Backend (einzige Quelle).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const source = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), "../../../backend/app/grundregeln.py"), "utf-8");

export const DISCLAIMER = /DISCLAIMER = \(([\s\S]*?)\)\n/.exec(source)![1]
  .split("\n").map((l) => /"(.*)"/.exec(l)?.[1] ?? "").join("");

const terms = /FORBIDDEN_TERMS = \[([\s\S]*?)\]/.exec(source)![1].match(/"([^"]+)"/g)!.map((t) => t.slice(1, -1));
export const FORBIDDEN = new RegExp(`(?<![\\p{L}\\d])(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})(?![\\p{L}\\d])`, "iu");

/** Erste verbotene Empfehlungsvokabel im Text oder null (Grundregel 1). */
export function findForbidden(text: string): string | null {
  return FORBIDDEN.exec(text)?.[1] ?? null;
}
