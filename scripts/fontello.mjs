import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import AdmZip from "adm-zip";

export async function extractFontello(buffer, destination) {
  const root = path.resolve(destination);
  const entries = new AdmZip(buffer).getEntries();
  let size = 0;
  const files = [];
  if (entries.length > 500) throw new Error("Too many font archive entries");
  for (const entry of entries) {
    const parts = entry.entryName.split("/");
    if (
      parts.some(
        (part) => part === ".." || part.includes("\\") || part.includes(":"),
      )
    ) {
      throw new Error("Unsafe font archive path");
    }
    parts.shift(); // Fontello's top-level archive directory.
    if (entry.isDirectory || !parts.length) continue;
    const target = path.resolve(root, ...parts);
    if (!target.startsWith(root + path.sep))
      throw new Error("Unsafe font archive path");
    size += entry.header.size;
    if (size > 50 * 1024 * 1024) throw new Error("Font archive is too large");
    files.push([target, entry]);
  }
  // Validate every path before writing any file.
  for (const [target, entry] of files) {
    await mkdir(path.dirname(target), { recursive: true });
    await writeFile(target, entry.getData());
  }
}

export async function updateFontello(configFile, destination) {
  const form = new FormData();
  form.append(
    "config",
    new Blob([await readFile(configFile)], { type: "application/json" }),
    "config.json",
  );
  const response = await fetch("https://fontello.com/", {
    method: "POST",
    body: form,
    redirect: "error",
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) throw new Error(`Fontello returned ${response.status}`);
  const session = (await response.text()).trim();
  if (!/^[a-zA-Z0-9-]+$/.test(session))
    throw new Error("Invalid Fontello session");
  const archive = await fetch(`https://fontello.com/${session}/get`, {
    redirect: "error",
    signal: AbortSignal.timeout(30000),
  });
  if (!archive.ok) throw new Error(`Fontello returned ${archive.status}`);
  await extractFontello(Buffer.from(await archive.arrayBuffer()), destination);
}
