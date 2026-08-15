const fs = require("fs");
const path = require("path");

const results = (filename) => [...fs.readFileSync(path.join(__dirname, "..", "content", filename), "utf8").matchAll(/^\- \[([^\]]+)\]\(([^)]+)\)$/gm)].map((match) => ({
  label: match[1],
  url: match[2]
}));

module.exports = {
  spring: results("spring-regatta-results.md"),
  fall: results("fall-regatta-results.md")
};
