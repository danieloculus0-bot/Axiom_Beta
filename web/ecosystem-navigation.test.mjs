import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const read = path => readFileSync(new URL(path, import.meta.url), "utf8");
const PROJECTS = "https://danieloculus0-bot.github.io/BEAN/portfolio/";
const BEAN = "https://danieloculus0-bot.github.io/BEAN/";

test("every Axiom public entry point offers a way back to the ecosystem", () => {
  for (const file of ["./index.html", "./erp/index.html", "./ewi/index.html", "./lab/index.html"]) {
    const html = read(file);
    assert.ok(html.includes('href="' + PROJECTS + '"'), file + " needs the canonical directory");
    assert.ok(html.includes('href="' + BEAN + '"'), file + " needs the BEAN home");
  }
});

test("the ERP remains the primary interactive application", () => {
  const html = read("./erp/index.html");
  assert.match(html, /id="module-nav"/);
  assert.match(html, /id="menu-search"/);
  assert.match(html, /<script type="module" src="\.\/app\.mjs"><\/script>/);
  assert.match(html, /href="\.\.\/ewi\/"/);
});

test("operator and evidence labs preserve their native workflow controls", () => {
  const ewi = read("./ewi/index.html");
  assert.match(ewi, /id="job-select"/);
  assert.match(ewi, /id="nav-workbench"/);
  assert.match(ewi, /src="\.\/app\.mjs"/);
  const lab = read("./lab/index.html");
  assert.match(lab, /data-view="passport"/);
  assert.match(lab, /data-view="inspection"/);
});

test("the root redirect still reaches ERP, with visible fallback navigation", () => {
  const html = read("./index.html");
  assert.match(html, /location\.replace\("\.\/erp\/"/);
  assert.match(html, /href="\.\/erp\/"/);
});

test("ecosystem navigation is not misrepresented as an integration API", () => {
  for (const file of ["./erp/index.html", "./ewi/index.html", "./lab/index.html"]) {
    const html = read(file);
    assert.ok(/not connected|No enterprise server|No server/i.test(html));
    assert.ok(!html.includes('href="' + PROJECTS + '#'), "cross-site nav must not invent record context");
  }
});

test("ERP cross-project return links are prominent and remain available on mobile", () => {
  const html = read("./erp/index.html");
  const css = read("./erp/style.css");
  const sidebar = html.split('<aside class="sidebar">')[1]?.split("</aside>")[0];
  assert.ok(sidebar, "ERP must retain its sidebar");
  const visibleNav = sidebar.split('<nav class="ecosystem-entry"')[1]?.split("</nav>")[0];
  assert.ok(visibleNav, "prominent project navigation must exist outside the footer");
  assert.match(visibleNav, /All Projects/);
  assert.ok(visibleNav.includes('href="' + PROJECTS + '"'));
  assert.ok(visibleNav.includes('href="' + BEAN + '"'));
  assert.ok(sidebar.indexOf('<nav class="ecosystem-entry"') < sidebar.indexOf('class="environment"'), "return path should appear before the ERP menu");
  assert.match(css, /\.ecosystem-entry\{display:flex/);
  assert.match(css, /\.sidebar-footer\{display:none\}/);
  assert.doesNotMatch(css, /\.ecosystem-entry\s*\{[^}]*display\s*:\s*none/i);
});
