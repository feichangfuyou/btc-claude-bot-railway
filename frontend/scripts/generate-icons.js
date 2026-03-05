#!/usr/bin/env node
import { readFileSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { Resvg } from "@resvg/resvg-js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const publicDir = join(__dirname, "..", "public");
const svgPath = join(publicDir, "icon.svg");

const sizes = [
  { name: "icon-192", size: 192 },
  { name: "icon-512", size: 512 },
  { name: "favicon-196", size: 196 },
  { name: "favicon-32", size: 32 },
];

const svg = readFileSync(svgPath);

for (const { name, size } of sizes) {
  const resvg = new Resvg(svg, { fitTo: { mode: "width", value: size } });
  const rendered = resvg.render();
  const png = rendered.asPng();
  const outPath = join(publicDir, `${name}.png`);
  writeFileSync(outPath, png);
  console.log(`Generated ${name}.png (${size}x${size})`);
}

console.log("Done.");
