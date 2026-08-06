const fs = require("fs");
const path = require("path");

const source = fs.readFileSync(path.join(__dirname, "..", "content", "wednesday-races.md"), "utf8");

module.exports = [...source.matchAll(/^\- \[([^\]]+)\]\(([^)]+)\)$/gm)].map((match) => ({
  label: match[1],
  url: match[2]
}));
