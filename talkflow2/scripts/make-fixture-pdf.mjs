// Generates tests/fixtures/hello.pdf — minimal single-page PDF with a FlateDecode content stream.
import zlib from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");
fs.mkdirSync(dir, { recursive: true });

const content =
  "BT /F1 24 Tf 72 720 Td (Hello PDF world.) Tj 0 -28 Td (Translation test sentence two.) Tj ET";
const deflated = zlib.deflateSync(Buffer.from(content, "latin1"));

const objs = {
  1: "<< /Type /Catalog /Pages 2 0 R >>",
  2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
  3: "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
  4: `<< /Length ${deflated.length} /Filter /FlateDecode >>`,
  5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
};

const chunks = [];
const offsets = { 0: 0 };
let pos = 0;
const push = (s) => { chunks.push({ s }); pos += Buffer.byteLength(s, "latin1"); };
const pushBuf = (b) => { chunks.push({ buf: b }); pos += b.length; };
const flush = (from) => {
  for (const c of chunks.slice(from)) {
    const bytes = c.buf ? c.buf : Buffer.from(c.s, "latin1");
    toWrite.push(bytes);
  }
};

push("%PDF-1.4\n");
for (let i = 1; i <= 5; i++) {
  offsets[i] = pos;
  push(`${i} 0 obj\n${objs[i]}\nendobj\n`);
}
offsets[4] = pos;
push("4 0 obj\n" + objs[4] + "\nstream\n");
pushBuf(deflated);
push("\nendstream\nendobj\n");

const xrefPos = pos;
let xref = "xref\n0 6\n";
xref += "0000000000 65535 f\n";
for (let i = 1; i <= 5; i++) xref += String(offsets[i]).padStart(10, "0") + " 00000 n\n";
push(xref);
push(`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);

const toWrite = [];
for (const c of chunks) toWrite.push(c.buf ? c.buf : Buffer.from(c.s, "latin1"));
const out = Buffer.concat(toWrite);
fs.writeFileSync(path.join(dir, "hello.pdf"), out);

// Roundtrip verification
const raw = out.toString("latin1");
const m = raw.match(/stream\n([\s\S]*?)\nendstream/);
const inflated = zlib.inflateSync(Buffer.from(m[1], "latin1")).toString("latin1");
console.log("bytes:", out.length);
console.log("inflated ok:", inflated.trim().slice(0, 80));
