// Validate every TeX expression in the built site with the vendored KaTeX.
// Usage: node .tools/check_math.js            (from the project root)
const path = require('path');
const fs = require('fs');
const root = path.resolve(__dirname, '..');
const katex = require(path.join(__dirname, 'site_assets', 'katex', 'katex.min.js'));
function* html(dir) {
  for (const e of fs.readdirSync(dir, {withFileTypes: true})) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) yield* html(p); else if (p.endsWith('.html')) yield p;
  }
}
let n = 0, bad = 0;
for (const f of html(path.join(root, 'site'))) {
  const text = fs.readFileSync(f, 'utf8');
  const re = /<(span|div) class="math (inline|block)">([\s\S]*?)<\/\1>/g;
  let m;
  while ((m = re.exec(text))) {
    const tex = m[3].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&amp;/g, '&');
    n++;
    try { katex.renderToString(tex, {displayMode: m[2] === 'block', throwOnError: true}); }
    catch (e) { bad++; console.log(path.relative(root, f), '::', e.message.slice(0, 150)); }
  }
}
console.log(`${n} expressions, ${bad} errors`);
process.exit(bad ? 1 : 0);
