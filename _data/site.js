const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

module.exports = yaml.load(fs.readFileSync(path.join(__dirname, "..", "content", "site.yml"), "utf8"));
