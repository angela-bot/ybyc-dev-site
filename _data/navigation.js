const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "content", "navigation.md"), "utf8");
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

module.exports = items;
