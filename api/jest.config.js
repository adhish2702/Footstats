/** @type {import('jest').Config} */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/tests"],
  // Creates the schema in TEST_DATABASE_URL and loads the fixture players (tests/seed.ts).
  globalSetup: "<rootDir>/tests/globalSetup.ts",
  testTimeout: 15000,
};
