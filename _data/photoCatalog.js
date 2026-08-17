const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const directory = path.join(__dirname, "..", "content", "photo-catalog");

module.exports = Object.fromEntries(
  fs.readdirSync(directory)
    .filter((filename) => /\.ya?ml$/i.test(filename))
    .map((filename) => [
      path.basename(filename, path.extname(filename)),
      yaml.load(fs.readFileSync(path.join(directory, filename), "utf8"))
    ])
);
