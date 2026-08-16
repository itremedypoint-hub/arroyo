// Slice marked blocks out of site/index.html and evaluate them in an
// isolated VM. Tests therefore exercise the EXACT shipped code, not a copy.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const here = dirname(fileURLToPath(import.meta.url));
export const HTML_PATH = join(here, "..", "site", "index.html");
export const html = readFileSync(HTML_PATH, "utf8");

export function slice(name) {
  const a = html.indexOf(`/*${name}_START*/`);
  const b = html.indexOf(`/*${name}_END*/`);
  if (a === -1 || b === -1) throw new Error(`marker ${name} not found`);
  return html.slice(a, b);
}

// Engine + validator + training data + strings, evaluated together in one
// clean context (validator references ARROYO; nothing touches the DOM).
export function loadCore() {
  const src = [slice("ARROYO_ENGINE"), slice("ARROYO_SHA256"),
    slice("ARROYO_STRINGS"), slice("ARROYO_TRAINING_DATA"), slice("ARROYO_VALIDATE"),
    "({ARROYO, sha256Hex, STRINGS, TRAINING_DATA, validateDataset})"].join("\n;");
  const ctx = { Math, Number, Array, Object, JSON, isFinite, TextEncoder, Uint8Array, Int32Array, DataView };
  return vm.runInNewContext(src, ctx);
}

export function loadVectors() {
  return JSON.parse(readFileSync(join(here, "..", "verify", "golden_vectors.json"), "utf8"));
}
