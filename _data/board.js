const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");

const board = yaml.load(fs.readFileSync(path.join(__dirname, "..", "content", "board.yml"), "utf8"));
const labels = {
  commodore: "Commodore", "vice-commodore": "Vice Commodore", "rear-commodore": "Rear Commodore",
  treasurer: "Treasurer", secretary: "Secretary", house: "House", fleet: "Fleet", membership: "Membership",
  race: "Race & Cruise", hospitality: "Hospitality", newsletter: "Newsletter", webmaster: "Webmaster",
  education: "Education", publicity: "Publicity", youth_sailing: "Youth Sailing", nominating: "Nominating",
  historical: "Historical", ships_store: "Ship’s Store", planning: "Planning"
};

board.groups = [
  { title: "Officers", keys: ["commodore", "vice-commodore", "rear-commodore", "treasurer", "secretary"] },
  { title: "Committee Chairs", keys: ["house", "fleet", "membership", "race", "hospitality", "newsletter", "webmaster", "education", "publicity", "youth_sailing"] },
  { title: "Support Committee Chairs", keys: ["nominating", "historical", "ships_store", "planning"] }
].map((group) => ({
  ...group,
  members: group.keys.map((key) => ({ role: labels[key], ...board.current_board[key] }))
}));

module.exports = board;
