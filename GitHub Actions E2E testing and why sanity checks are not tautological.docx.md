End to end tests

E2E (end-to-end) tests. Angular. Yes, they're flaky. Yes, they're slow. But they are very useful and potentially under used. They're sometimes pushed off to run on end-developers devices because getting it to work on the CI is too finicky.

Why are E2E tests ignored? Well, they're a bit of a pain to get running in general, especially for newer users. (The command npm run test should be called npm run test-components, because it's just running the component tests, by default.)

Just a simple E2E test that checks a page title is incredibly useful. Sadly, it does need a lot of setup to just do a simple E2E test so oftentimes it goes ignored.

### Starting from scratch

Let's make a brand new Angular project. From scratch. From ng new my-app. Let's run npm install for good measure, then run npm run e2e.

ng new my-app

npm install

git init

git add .

git commit -m "Initial commit"

npm run e2e

You may think that Protractor is part of Angular. It's not\--it's a separate project. This means that the command npm run e2e doesn't work out of the box (yes, I have the Google Chrome browser installed):

\[19:33:27\] I/launcher - Running 1 instances of WebDriver

\[19:33:27\] I/direct - Using ChromeDriver directly\...

DevTools listening on ws://127.0.0.1:56681/devtools/browser/829c0ca6-bc1d-4f9c-aa8f-ba379fca9279

\[50252:41332:0309/193337.329:ERROR:device_event_log_impl.cc(214)\] \[19:33:37.329\] USB: usb_device_handle_win.cc:1056 Failed to read descriptor from node connection: A device attached to the system is not functioning. (0x1F)

\[50252:41332:0309/193337.362:ERROR:device_event_log_impl.cc(214)\] \[19:33:37.363\] USB: usb_device_handle_win.cc:1056 Failed to read descriptor from node connection: A device attached to the system is not functioning. (0x1F)

\[50252:41332:0309/193337.386:ERROR:device_event_log_impl.cc(214)\] \[19:33:37.386\] USB: usb_device_handle_win.cc:1056 Failed to read descriptor from node connection: A device attached to the system is not functioning. (0x1F)

Jasmine started

workspace-project App

× should display welcome message

\- Error: Timeout - Async callback was not invoked within timeout specified by jasmine.DEFAULT_TIMEOUT_INTERVAL.

internal/timers.js:549:17

jasmine-spec-reporter: unable to open \'internal/timers.js\'

Error: ENOENT: no such file or directory, open \'internal/timers.js\'

internal/timers.js:492:7

jasmine-spec-reporter: unable to open \'internal/timers.js\'

Error: ENOENT: no such file or directory, open \'internal/timers.js\'

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

\* Failures \*

\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*\*

1\) workspace-project App should display welcome message

\- Error: Timeout - Async callback was not invoked within timeout specified by jasmine.DEFAULT_TIMEOUT_INTERVAL.

Executed 1 of 1 spec (1 FAILED) in 35 secs.

\[19:34:36\] I/launcher - 0 instance(s) of WebDriver still running

\[19:34:36\] I/launcher - chrome \#01 failed 1 test(s)

\[19:34:36\] I/launcher - overall: 1 failed spec(s)

\[19:34:36\] E/launcher - Process exited with error code 1

npm ERR! code 1

npm ERR! path C:\\Users\\yorke\\Desktop\\angular-tour-of-heroes-master\\angular-tour-of-heroes-master

npm ERR! command failed

npm ERR! command C:\\WINDOWS\\system32\\cmd.exe /d /s /c ng e2e

npm ERR! A complete log of this run can be found in:

npm ERR! C:\\Users\\yorke\\AppData\\Local\\npm-cache\\\_logs\\2021-03-10T00_34_37_674Z-debug.log

Side-note: ok, so in this case I was "lucky" that it failed. Turns out if you have Docker running and a few other things running, your computer might get a bit slow (surprise surprise.) This causes the test to timeout. This is still an error though. Sometimes it works, sometimes it doesn't. On the CI though it was consistently failing, so we'll go with that.

Hmm, ok, maybe our setup is weird. Let's run it via GitHub actions instead (and add it manually to the build + test stage, since the first few in Google's search results don't contain E2E tests by default.) What happens now?

\[00:40:26\] I/launcher - Running 1 instances of WebDriver

\[00:40:26\] I/direct - Using ChromeDriver directly\...

\[00:40:29\] E/runner - Unable to start a WebDriver session.

\[00:40:29\] E/launcher - Error: WebDriverError: unknown error: Chrome failed to start: exited abnormally.

(unknown error: DevToolsActivePort file doesn\'t exist)

(The process started from chrome location /usr/bin/google-chrome is no longer running, so ChromeDriver is assuming that Chrome has crashed.)

(Driver info: chromedriver=89.0.4389.23 (61b08ee2c50024bab004e48d2b1b083cdbdac579-refs/branch-heads/4389@{\#294}),platform=Linux 5.4.0-1040-azure x86_64)

at Object.checkLegacyResponse (/home/runner/work/angular-tour-of-heroes/angular-tour-of-heroes/node_modules/selenium-webdriver/lib/error.js:546:15)

at parseHttpResponse (/home/runner/work/angular-tour-of-heroes/angular-tour-of-heroes/node_modules/selenium-webdriver/lib/http.js:509:13)

at /home/runner/work/angular-tour-of-heroes/angular-tour-of-heroes/node_modules/selenium-webdriver/lib/http.js:441:30

at processTicksAndRejections (internal/process/task_queues.js:97:5)

\[00:40:29\] E/launcher - Process exited with error code 100

npm ERR! code ELIFECYCLE

npm ERR! errno 1

npm ERR! angular-tour-of-heroes\@0.0.0 e2e: \`ng e2e\`

npm ERR! Exit status 1

npm ERR!

npm ERR! Failed at the angular-tour-of-heroes\@0.0.0 e2e script.

npm ERR! This is probably not a problem with npm. There is likely additional logging output above.

At this point you're likely to want to fix the error, so you'll do one or some of the following (potentially, unless you know where I'm going with this):

### Option one

Delete the E2E tests or delete the E2E test runner.

It can be tempting to snip the test that looks like it's just checking if one equals one\...

it(\'should display welcome message\', async () =\> {

**await page.navigateTo();**

**expect(await page.getTitleText()).toEqual(\'\<%= relatedAppName %\> app is running!\');**

});

\...Just remove the bolded statement and all of the errors magically disappear, except we're not running the E2E tests. But who cares? All it's checking is the page title. Right?

### Option two

Try to get the E2E tests working or die trying. I'm being a bit sarcastic, but I'll work through the problem as if I sequentially Googled each error message. It is surprisingly difficult.

Search Google for "Error: WebDriverError: unknown error: Chrome failed to start: exited abnormally." then...

-   Click on [[https://github.com/angular/webdriver-manager/issues/444]{.ul}](https://github.com/angular/webdriver-manager/issues/444), but that doesn't go anywhere

-   Click on [[https://github.com/actions/virtual-environments/issues/41]{.ul}](https://github.com/actions/virtual-environments/issues/41), which goes to [[https://github.com/actions/virtual-environments/issues/9]{.ul}](https://github.com/actions/virtual-environments/issues/9), which suggests to do "apt-get install chromium-chromedriver" first, so you squeeze in a "apt-get update && apt-get install chromium-chromedriver" before the npm build

-   That gives you the same error.

-   You go to [[https://github.com/heroku/heroku-buildpack-google-chrome/issues/56]{.ul}](https://github.com/heroku/heroku-buildpack-google-chrome/issues/56) which has seven ways to try to fix it with varying degrees of success.

-   You then search "E2E google chrome github actions".

-   The first five results are unrelated to anything to do with github actions.

-   You then find [[https://stackoverflow.com/questions/63651059/]{.ul}](https://stackoverflow.com/questions/63651059/) which says to run the same command that you tried except prefixed with sudo.

-   You then copy-and-paste the exact 12-line YAML part/blob of text of the E2E test from the answer into your workflow.

-   It doesn't work because it says permission denied.

-   You try to prefix every apt-get with sudo.

-   You get an error like "E: This command can only be used by root."

-   At this point you may delete the E2E test and just forget it. Or you could keep going and wonder if E2E tests were designed to be run.

-   You find [[https://askubuntu.com/questions/845534/this-command-can-only-be-used-by-root]{.ul}](https://askubuntu.com/questions/845534/this-command-can-only-be-used-by-root) and then prefix "apt-key" with sudo

-   Try it again.

-   You get a new error, "/home/runner/work/\_temp/878817f4-7ca2-4e31-8c02-092beb2da616.sh: line 5: /etc/apt/sources.list.d/google.list: Permission denied"

-   You add sudo to wget and to echo just in case.

-   Try again.

-   Get the same error.

-   Oops. Shouldn't have added sudo in front of echo.

-   Try again.

-   Still with me? Want to give up now?

-   Oh no, same error.

-   You do some more searching and find out that \>\> isn't as root. You then use "sudo tee -a" (because \>\> doesn't append as root). Try again.

-   The same error again this time around, "Error: WebDriverError: unknown error: Chrome failed to start: exited abnormally."

-   **Somehow you add this to your protractor.conf.js:**

-   chromeOptions: {

-   args: \[\'\--headless\'\]

-   }

All of a sudden it works!

\[20:31:04\] W/element - more than one element found for locator By(css selector, app-root .content span) - the first result will be used

workspace-project App

√ should display welcome message

Executed 1 of 1 spec SUCCESS in 2 secs.

\[20:31:05\] I/launcher - 0 instance(s) of WebDriver still running

\[20:31:05\] I/launcher - chrome \#01 passed

### Recap and final script

Let's recap what we did. Here's part of the original script, modified a little and commented a lot.

\# Update our apt repos, then install wget. You don't *need* wget (you could use curl); it doesn't matter though; you just need to download a signing key.

sudo apt-get update

sudo apt-get install -y wget

\# To get Google Chrome, you have to add the PPA for it. Google Chrome isn't in the default Ubuntu repo. You can run apt-get install wget because wget is in the repos.

wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub \| sudo apt-key add -

echo \"deb http://dl.google.com/linux/chrome/deb/ stable main\" \| sudo tee -a /etc/apt/sources.list.d/google.list

\# After adding in a repo, you have to tell apt to fetch the manifests. This includes Google Chrome.

sudo apt-get -y update

\# Install Chrome.

sudo apt-get install -y google-chrome-stable

\# "Run" Google Chrome, but with the version flag. This produces a version with a lot of verbose output. We just care about the first line and we can use a regex to extract just the version number.

VERSION=\`google-chrome \--version \| egrep -o \'\[0-9\]+.\[0-9\]+\' \| head -1\'

The script goes on to install webdriver-manager and a chrome package. Turns out that we don't need them as it "uses Chromedriver directly." It might have been for older Chrome versions. The test passes perfectly fine without them.

Just this isn't enough. We have to tell Protractor and Chrome that we're running in headless mode, which means that we can't run a UI. We also need to update Protractor. Let's add,

capabilities: {

browserName: \'chrome\',

chromeOptions: {

args: \[\'\--headless\'\]

}

},

[[To protractor.conf.js]{.ul}](https://www.protractortest.org/#/browser-setup). Pay attention to the "args" that we've added. We're adding these arguments because Chrome doesn't know we're running in a container. This means it tries to set up a UI and such and it can't do it because there isn't a UI.

**Why don't we need \--no-sandbox?** Some of the older issues mention it, but it seems there were some changes to chrome which allows chrome to run with the sandboxing enabled within a container. This stemmed from an [[error on Travis CI]{.ul}](https://docs.travis-ci.com/user/chrome#karma-chrome-launcher) about "The SUID sandbox helper binary was found, but is not configured correctly". Using \--no-sandbox is a quick band aid patch. The correct way is through [[setting the owner of the binary to root and the permissions correctly.]{.ul}](https://github.com/electron/electron/issues/17972)

**You don't need \--disable-dev-shm-usage anymore either.** You do need \--headless though, as Chrome doesn't know we're on a CI.

Now, \--no-sandbox, \--disable-dev-shm-usage and some other flags may be required for older versions of Chrome. Keep that in mind while testing.

### Why are E2E tests important?

Maybe this should have been the first section. If we were to snip our first E2E test that *appeared as though* it wasn't doing anything, we'd be missing out on a lot of testing opportunities. The first test isn't a tautology. This point two fold:

-   A single E2E test causes the afterEach function to run, which fails the tests if the console contains any errors. The afterEach function will not run if there are no tests. The console can contain errors (and still pass the component tests.) **Try adding some bad code to the main.po.ts file. The component tests will run fine, but your app will just be a blank page. npm run test isn't enough to check if your app works.**

-   "Breaks in" E2E testing. If you want to write another E2E test, go for it! You know that everything is in a somewhat sane state because you're able to run a single test and it works fine. Granted, there might be other problems down the line if you're working with flakier tests but otherwise the dependencies are installed.

### What if I want to test with extensions, including Chrome Web Store ones?

Chrome with the \--headless flag doesn't support extensions yet. You [[have to use xvfb]{.ul}](https://stackoverflow.com/questions/45372066/is-it-possible-to-run-google-chrome-in-headless-mode-with-extensions), which is a virtual frame buffer. You may also want to pass in the "-a" flag if you're [[running xvfb-run]{.ul}](https://manpages.debian.org/testing/xvfb/xvfb-run.1.en.html) with multiple concurrent instances on the same machine.

It'll want a path to your extension, so [[you'll have to download it first]{.ul}](https://superuser.com/questions/290280/how-to-download-chrome-extensions-for-installing-in-another-computer) to your computer from the Chrome Web Store, then add it to your Git repo.
