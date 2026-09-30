// Google Apps Script that starts the simulate workflow every 30 minutes, because GitHub's own
// schedule often starts runs hours late or skips them. Runs are idempotent, so extra starts are harmless.
//
// Setup: paste into a new project at https://script.new, add a script property GITHUB_TOKEN holding a
// fine-grained token with only "Actions: read and write" on this repository, then run setup() once.

var REPO = 'ttannu/coindcx-paper-bots';
var WORKFLOW = 'simulate.yml';

function setup() {
  stop();
  ScriptApp.newTrigger('dispatch').timeBased().everyMinutes(30).create();
  dispatch();
}

function dispatch() {
  var token = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!token) {
    console.log('No GITHUB_TOKEN script property; nothing to do.');
    return;
  }
  var response;
  try {
    response = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + WORKFLOW + '/dispatches', {
      method: 'post',
      contentType: 'application/json',
      headers: {
        Authorization: 'Bearer ' + token,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      },
      payload: JSON.stringify({ref: 'main'}),
      muteHttpExceptions: true
    });
  } catch (err) {
    // A network hiccup; the next trigger tries again. Throwing would email a failure notice.
    console.log('GitHub unreachable: ' + err);
    return;
  }
  var code = response.getResponseCode();
  var body = response.getContentText();
  if (code === 204) return;
  var rateLimited = code === 429 || (code === 403 && /rate limit/i.test(body));
  // 401: token expired or revoked. 404: repository or access gone. 422: the workflow switched itself off
  // after the final report. None of these recover on their own, so the trigger removes itself.
  if (!rateLimited && (code === 401 || code === 403 || code === 404 || code === 422)) {
    console.log('Stopping the trigger after HTTP ' + code + ': ' + body);
    stop();
    return;
  }
  console.log('HTTP ' + code + ', will retry on the next trigger: ' + body);
}

function stop() {
  ScriptApp.getProjectTriggers().forEach(function (trigger) {
    ScriptApp.deleteTrigger(trigger);
  });
}
