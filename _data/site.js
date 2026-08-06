const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const site = yaml.load(fs.readFileSync(path.join(__dirname, "..", "content", "site.yml"), "utf8"));
site.wednesday_racing.current_url = site.wednesday_racing[`${site.wednesday_racing.current_series}_url`];

module.exports = site;
