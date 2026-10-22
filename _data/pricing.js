const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

module.exports = function () {
  return yaml.load(fs.readFileSync(path.join(__dirname, "..", "content", "pricing.yml"), "utf8"));
};
