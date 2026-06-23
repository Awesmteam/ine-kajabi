// Assembles the deployable static site into ./public.
// Keeps a single source of truth: kartra-full-page.html -> public/index.html.
import { mkdir, copyFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = join(root, "public");

await mkdir(outDir, { recursive: true });
await copyFile(join(root, "kartra-full-page.html"), join(outDir, "index.html"));

console.log("Built public/index.html");
