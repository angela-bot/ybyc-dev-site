const markdownIt = require("markdown-it");
const markdown = markdownIt({ html: true });

const escapeHtml = (value) => String(value)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;")
  .replace(/\"/g, "&quot;")
  .replace(/'/g, "&#39;");

function renderNavigation(items, activeSection) {
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

  return `<nav class="navbar navbar-expand-lg main-nav sticky-top" aria-label="Primary navigation"><div class="container-xl px-4"><a class="navbar-brand d-lg-none serif fw-bold" href="index.html">YBYC</a><button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#mainNav" aria-controls="mainNav" aria-expanded="false" aria-label="Toggle navigation"><span class="navbar-toggler-icon"></span></button><div class="collapse navbar-collapse" id="mainNav"><ul class="navbar-nav">${links(items)}</ul></div></div></nav>`;
}

function raceDate(value, format = "long") {
  const date = (dateValue) => new Date(`${dateValue}T12:00:00`);
  const parts = (dateValue) => {
    const current = date(dateValue);
    return {
      weekday: current.toLocaleDateString("en-US", { weekday: "long" }),
      month: current.toLocaleDateString("en-US", { month: "long" }),
      day: current.getDate(),
      year: current.getFullYear()
    };
  };
  const range = (start, end) => {
    const first = parts(start);
    const last = parts(end);
    if (first.year === last.year && first.month === last.month) return `${first.month} ${first.day}–${last.day}, ${first.year}`;
    if (first.year === last.year) return `${first.month} ${first.day}–${last.month} ${last.day}, ${first.year}`;
    return `${first.month} ${first.day}, ${first.year}–${last.month} ${last.day}, ${last.year}`;
  };

  if (format === "range" || format === "schedule") {
    const valueRange = range(value.start, value.end);
    return format === "schedule" ? `${valueRange} schedule` : valueRange;
  }

  const current = parts(value);
  if (format === "day") return current.day;
  if (format === "month") return current.month;
  if (format === "month-day-year") return `${current.month} ${current.day}, ${current.year}`;
  if (format === "weekday-year") return `${current.weekday} · ${current.year}`;
  return `${current.weekday}, ${current.month} ${current.day}, ${current.year}`;
}

module.exports = function (eleventyConfig) {
  eleventyConfig.addPassthroughCopy("assets");
  eleventyConfig.addPassthroughCopy("assets/wednesday-races");
  eleventyConfig.addPassthroughCopy("images");
  eleventyConfig.addLiquidFilter("markdown", (source) => markdown.render(source));
  eleventyConfig.addLiquidFilter("navigation", (source, activeSection) => renderNavigation(source, activeSection));
  eleventyConfig.addLiquidFilter("raceDate", raceDate);

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
