const { defineConfig } = require("cypress");

module.exports = defineConfig({
  e2e: {
    specPattern: 'specs',
    supportFile: false,
    projectId: '11wp34',
    video: false,
    screenshotOnRunFailure: false
  },
  reporter: 'junit',
  reporterOptions: {
    mochaFile: 'reports/[hash].xml'
  }
});
