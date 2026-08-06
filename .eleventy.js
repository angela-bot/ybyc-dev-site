const markdownIt = require("markdown-it");
const markdown = markdownIt({ html: true });

const escapeHtml = (value) => String(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/\"/g, "&quot;")
  .replace(/'/g, "&#39;");

function navigationItems(source) {
  const items = [];
  let parent;

  for (const line of source.split("\n")) {
    const match = line.match(/^(\s*)-\s+\[([^\]]+)\]\(([^)]+)\)\s*$/);
    if (!match) continue;
    const item = { label: match[2], href: match[3], children: [] };
    if (match[1].length) parent?.children.push(item);
    else {
      items.push(item);
      parent = item;
    }
  }

  return items;
}

function renderNavigation(source, activeSection) {
  const sections = {
    "index.html": "home",
    "about.html": "club",
    "sailing.html": "sailing",
    "events.html": "events",
    "clubhouse.html": "clubhouse",
    "shop.html": "shop"
  };
  const links = (items) => items.map((item) => {
    const label = escapeHtml(item.label);
    const href = escapeHtml(item.href);
    const isActive = activeSection === sections[item.href];
    if (!item.children.length) {
      return `<li class="nav-item"><a class="nav-link${isActive ? " active" : ""}" href="${href}">${label}</a></li>`;
    }
    return `<li class="nav-item dropdown"><a class="nav-link dropdown-toggle${isActive ? " active" : ""}" href="${href}" role="button" data-bs-toggle="dropdown" aria-expanded="false">${label}</a><ul class="dropdown-menu">${item.children.map((child) => `<li><a class="dropdown-item" href="${escapeHtml(child.href)}">${escapeHtml(child.label)}</a></li>`).join("")}</ul></li>`;
  }).join("");

  return `<nav class="navbar navbar-expand-lg main-nav sticky-top" aria-label="Primary navigation"><div class="container-xl px-4"><a class="navbar-brand d-lg-none serif fw-bold" href="index.html">YBYC</a><button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNav" aria-controls="mainNav" aria-expanded="false" aria-label="Toggle navigation"><span class="navbar-toggler-icon"></span></button><div class="collapse navbar-collapse" id="mainNav"><ul class="navbar-nav">${links(navigationItems(source))}</ul></div></div></nav>`;
}

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.addPassthroughCopy("images");
  eleventyConfig.addLiquidFilter("markdown", (source) => markdown.render(source));
  eleventyConfig.addLiquidFilter("navigation", (source, activeSection) => renderNavigation(source, activeSection));

  return {
    dir: {
      input: ".",
      includes: "_includes",
      output: "_site"
    },
    htmlTemplateEngine: "liquid",
    markdownTemplateEngine: "liquid"
  };
};
