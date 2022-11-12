---
title: "How to mitigate long-term CI/CD pipeline issues"
date: 2021-02-21
---

We can use pipelines for multiple things in CI/CD, including acting as a buffer between developers and the master branch.

Sometimes, pipelines are treated as a set-it-and-forget-it; if it's green, then everything is ok. A successful pipeline doesn't mean it will always be successful. Since pipelines are the core of many CI/CD workflows, we should treat them‌ like that. If they break, then development ceases until we fix them.

Here are a few different pipeline gotchas and how to avoid them.

### "Boiling" the pipeline

#### Resource limits

One situation where "success" is misleading is when you're silently getting closer and closer to your resource limits without realizing it. Usually, this isn't an issue because the machines are usually so large that hitting your resource limits doesn't become an issue until you have a very complex pipeline or have a large project. When you ‌hit them, though, it's a big issue.

We monitor our Kubernetes clusters, our websites, our dashboards. Why don't we treat pipelines as the same?

If you don't have pipeline monitoring tools in place, you could be silently approaching:

-   The RAM, disk, or CPU limit.

-   The job time limit because of more and more dependencies and code takes longer and longer to compile and run.

-   The maximum number of processes permitted (the ulimit.)

If you don't have monitoring tools in place, the cause of errors could be:

-   A random occurrence (an edge case.)

-   A non-pinned dependency that has newer requirements. This newer dependency has more features and uses more resources.

-   Adding a new dependency.

-   Downloading an installation script or an operating system image with the "latest" tag and the version has changed.

-   A slow, measured progression of using more and more resources because the application is getting larger.

While there are some monitoring tools available, they don't have the fine-grained detail because they usually only monitor the container on the host and not the actual container itself. Or, they could be difficult to access, not easily visible, or are not enabled by default. Metrics such as:

-   Ulimit usage (how many processes can be created.)

-   Inode counts (how many files and directories can be created.)

-   Swap usage.

-   RAM usage (for some pipelines.)

Are rarely shown, even though exceeding them could cause pipeline failures.

Also, developers may not be aware of a pipeline taking longer and longer because of a combination of variabilities:

-   Pipelines take time to instantiate, and this could vary. For example, GitHub pipelines differentiates between billable time and total pipeline time. It takes time for the job to find a suitable runner.

-   If you have queued jobs, then it could take a very long time for a job to find a suitable pipeline to run.

-   The pipelines could use third-party dependencies or services, which take time to download or use. The third-party dependency's service might be slow.

-   Dependencies could be rate-limited or soft-rate-limited by throttling the download speed.

-   Developers don't watch the pipeline's completion; they have many other higher-priority tasks to complete. If they come back to it 30 minutes later, the pipeline could have taken 29 minutes or one minute to complete and they would not know.

Also,

-   Changing code in an unfamiliar programming language (such as Bash or GitHub Workflow files) can be difficult. Also, Bash has many pitfalls and edge-cases, which may not be clear if you don't spend a lot of time with the language. It follows the mantra of "If it's not broken, don't fix it." Tools such as a [[GitHub Workflow file validator extension]{.ul}](https://marketplace.visualstudio.com/items?itemName=cschleiden.vscode-github-actions) might not be used and instead use GitHub to validate the files after pushing it via trial and error.

-   DevOps is used to break down the barriers between developers and operations, but developers may not do operations work in their day-to-day. We may misjudge the operations philosophy as keep-trying-things-until-it-works to keep the lights on. Since Bash scripts are interpreted, there isn't a build-and-see-if-it-works function (there is a built-in syntax checker but might not be known), and so it turns into a guess-and-check. The guess-and-check method is an ops no-no.

-   The pipelines are in the cloud, so infrastructure is "automatically" handled. Pipelines normally run on VMs, and VMs are a certain size. For example, GitHub's pipelines run on DS Azure VMs. However, it's possible that other special types of pipelines could auto-scale. This means that resource limitations could be disregarded.

These pipeline timing variabilities mean that under normal circumstances the pipeline will be expected to take longer to run.

If a pipeline breaks (exceeds its resource limit), then sometimes these workarounds or debugging methods are used with varying degrees of success:

-   Trying to wrangle Java apps with the -Xmx and -Xms and other assortment of flags to limit memory usage.

-   Adding swap files. This can dramatically slow down memory accesses and can increase pipeline time.

-   Installing software with \--no-install-recommends to reduce disk usage. Not having recommended software could cause certain software features to break.

-   Aggressively deleting temporary files with liberal wildcards and/or missing quoted values at every step. This can cause other files to be erroneously deleted.

-   Regularly compressing files, but this can increase the job time and may not preserve symbolic links. If too many files are compressed, this could balloon artifact size, ‌hitting other limits.

-   Quitting apps with the "killall" command with liberal wildcards or using "kill -9" to force a program to quit immediately without allowing it to clean up. This could cause other processes to terminate, or cause corrupted data if it can't shutdown correctly.

-   Looking up best practices for Bash and pasting in commands like "set -e" as a debugging measure but not fully understanding their implications or how they change script behavior.

-   Interchanging -q (quiet) flags and \>/dev/null and removing them to see log output when they could have different behaviors depending on the application version.

-   Trying to read the logs, but the logs are difficult to parse because they contain ANSI color codes (making it hard to do a Ctrl+F search), contain interactive prompts or excessively verbose output (i.e. 3000 lines of a progress bar), write to temporary files which are erased after the pipeline finishes, or contain two or more programs' stdout simultaneously (i.e. mixed output lines.) The pipeline's logs weren't set up to be readable.

-   Parsing edge cases with more commands, but not considering adding more complexity and newer edge cases when simpler solutions exist.

-   Adding combinations of environment variables.

These aren't bad workarounds per se, but hastily adding them because the pipeline has to be fixed immediately means that other issues could occur down the road. They could have other consequences since little research is done---the goal is to fix it immediately because it is an emergency.

The pipeline could be "fixed" by simply throwing more resources at it. Again, sometimes this isn't a bad solution if it's needed (i.e. more dependencies and larger application sizes.) It can be useful for workarounds to prevent disruption while a root-cause analysis takes place. It isn't a panacea because:

-   Failures could occur because an app has an infinite loop and uses all available RAM. Upgrading the RAM will just make the app use more RAM until it fails. Also, upgrading the RAM can hide smaller memory leaks.

-   Upgrading the CPU means the app can run faster, but if it is in an infinite loop, no amount of CPU can make it run faster. Also, this could be a symptom of a spinlock.

-   Upgrading the disk's size to accommodate more files. Again, if there is an infinite disk writer then no amount of disk space will accommodate it. Also, it could allow for larger artifacts which can cause other resource limitations, especially if they have to be re-used between stages.

How do we overcome these issues?

-   Monitor how long it takes to run your pipeline. Create a chart and see how much it is increasing and when you will be approaching your limits.

-   Reduce the maximum pipeline time. You can take the 99th percentile of the pipeline runs and set it as the maximum time. Note, however, that this time should be reviewed periodically to ensure it is not too restrictive. This is because as your application grows, your pipeline might take longer to compile more and more code. A pipeline slowly taking more and more time to complete isn't necessarily bad.

-   Learn about Bash and other scripting languages, especially the pitfalls. I'll write a post about this soon.

-   For complex measurements like ulimits and inode counts, try logging it inside of the pipeline at the end before the cleanup steps or after any large operations. Then, tabulate these measurements periodically. Compare them with your ulimits in your pipeline.

-   Make the pipeline logs readable. Read through your pipeline logs and see if you can read them. Know how to remove or grep through ANSI color codes and ensure commands are producing output but CI-friendly output (i.e. no 3000 line progress bars.)

What are some other miscellaneous things that monitoring can help with?

-   It can allow easier transferring between CI systems

-   You can downsize your pipeline to save costs if you know how much resources your pipeline requires. Depending on how your pipeline works, downsizing could increase job throughput if they are queued based on pipeline size or credits per hour.

#### Listen to the warnings

Warnings are usually emitted when something isn't quite right.

-   Are you using a flag that's going to be deprecated soon? Hmm, that seems off. I hope they're not going to continue using it.

-   Using a feature in a way that could be a security issue? Hmm, I hope that they're being safe about it.

-   Server invoked with a default password? It *might* be fine for a CI pipeline (I don't think that's a great idea), but it's hard to say where it's being run.

Application developers put in development effort to create these warnings, including the conditions that cause them to be emitted. They wouldn't write them if there wasn't any use doing so; such development could be spent elsewhere.

Listening to warnings can help identify issues early on before they become emergencies. Granted, warnings don't necessarily have to be treated as emergencies but they should be tracked and resolved. If there isn't a reason for resolving them, then that should be documented.

#### The pipeline isn't successful, but it says it is

This is the most scary one. The pipeline says it's successful for a long time, but we're noticing some tests pass when they should have failed. How could that be?

There are several reasons for this:

-   A developer accidentally committed a test that shouldn't have been excluded (sometimes it is ok to exclude tests.) The test isn't run on the pipeline and the code should have failed.

-   A developer accidentally committed a test that is focused (i.e. run just this test and not the others.) This means that the other tests in the solution aren't being run.

-   Limited knowledge of Bash and shell scripts. By default, Bash scripts continue to run, even if one line fails. By default, Bash pipelines will return success and produce output even if one command failed. This could cause missing data to go unreported and tests to continue to pass if they are unfamiliar with how Bash scripting works. This is further compounded by developers not needing to work with shell scripts daily.

-   Shell and other scripts aren't syntax validated or linted. This can cause silent errors like invalid newlines that cause parts of the script to be un-runnable.

-   Dependencies are not pinned, which means incompatible code is silently injected or updated, which could yield success on different inputs. This could be caused by flags or features slowly being deprecated in combination with bad error handling.

-   Committing flaky tests, which only fail when run hundreds or thousands of times, or may not run at all and don't hit the "expectation". This can be an issue with Karma/Jasmine tests where this is just reported as a warning and not a failure.

-   The pipeline has to compile two projects, but compiles the second project twice because it contains the first part of the project's name and the project name was not quoted correctly.

-   Different locale settings which change sort order.

-   The pipeline is unintentionally running a no-op which always returns true.

How can we mitigate these?

-   You can make "fit" and "fdescribe" tests (for Karma/Jasmine) to fail on the CI/CD pipeline [[https://stackoverflow.com/questions/31304447/disable-jasmines-fdescribe-and-fit-based-on-environment]{.ul}](https://stackoverflow.com/questions/31304447/disable-jasmines-fdescribe-and-fit-based-on-environment) (but still allow them on developer's workstations for testing.)

-   Add Bash scripts to your development pipeline with tools such as Shellcheck.

-   Add a .editorconfig and .gitattributes file which will convert the line endings of Bash scripts to their correct endings. The same can be for Batch files (they need Windows line endings.)

-   Encourage reading and learning about Bash, the differences between Bash and sh, and how shell scripting works. Advice (especially best practices) may be tempting to follow as it is repeated many times in Google's search results. Always be critical about these best practices and do your research to see if they are the right fit. Know what the commands are doing before you add them.

-   For flaky tests, you could run the test stage in PRs multiple times. This prevents flaky tests, as they would have to fail less regularly for them to slip by.

-   Another point for flaky tests is to encourage developers to read about what flaky tests are and how to use asynchronous programming.

-   To prevent committing tests that don't run their "expected" statements (for Karma/Jasmine), install karma-no-spec-no-pass (a program of mine.) This program will cause a fail immediately once it encounters a test which doesn't run its expectation and is reported as finished.

-   Create a new pipeline which runs the master branch's tests a sufficient amount of times periodically to check for flaky tests. I am working on another post which addresses how many times your tests have to be run to have a certain confidence percentage that there aren't any flaky tests.

-   Pin your dependencies by installing a specific version of a library. The downside is that you have to modify your pipeline more often to upgrade the dependency and to receive security updates. This requires more development effort. You can adopt a hybrid approach by allowing the latest point release of a library/application to be installed. Be careful, as the maintainer has to follow the semver versioning system to prevent any breaking changes. Also, it isn't guaranteed that a point release won't break existing features; it could be unintentional.

-   Actively look for deprecated warnings in pipeline logs and your dependencies. You can use apt-get changelog \<package\> \| grep -i deprecat (on Ubuntu systems) to search for deprecation in dependency changelogs. The word "deprecat" is the stemmed version of "deprecate" which will match "deprecating", "deprecated", "deprecate", and "deprecatization". This isn't a panacea, however, as developers aren't forced to put this in their changelogs. Check newsletters and online resources regularly before and after upgrading to find any deprecated features you might be relying on. You can also check the manpages for the word "deprecated" between versions.

### Pipeline waste

"Pipeline waste" is when a pipeline runs, but its inputs will cause the pipeline to fail, or doesn't need to be re-run. This means that the pipeline was run wastefully. It also means that you have pipeline credits available (read: a lot of credits) at the end of your billing cycle that go unused.

While it might be financially inconsequential to worry about wasted pipeline credits, there are a few main reasons why this might not be the case:

-   Pipelines may have a very generous duration set, which means a pipeline **could take up to 12 hours to complete** (for example, there was a test that got stuck.) This can quickly eat through monthly credits.

-   **Having a large amount of monthly credits left over every month means you're wasting some of your credits.** You can schedule more tests such as soak tests, flaky test identification, or high-powered tests like large E2E tests which take time to run (and re-run if they are flaky and just have to pass at least once.) These types of tests can proactively increase productivity by identifying tech debt. With this approach, however, **make sure that you're not overcommitting your pipeline** with these types of optional tests because this can increase risk that you'll run out of credits if the developer's work exceeds the average pipeline utilization. You could try to run these tests close to the end of your billing cycle with a hard timebox if you have some spare credits left, as they are less likely to be used.

-   If the pipeline plan changes (read: increases in price), then being able to switch to another provider without large financial consequences or new budget approvals can save time.

As a side note, pipelines that have an excessive amount of CPU and RAM can decrease pipeline duration at the risk of not finding flaky tests because the tests run so fast that there might not be any opportunity for random delays that could reveal out-of-order execution. However, if the pipeline is too slow, then it might cause tests to timeout without being run, increasing artificial flakiness.

If you plan on adding additional pipelines or functionality, **ensure it brings value to your team and is not overcomplicating the pipeline for the sake of using free credits**. Creating a new pipeline or modifying an existing one is an investment and also requires maintenance.

#### Failing fast

You might think, "Well, that's what a pipeline is for! To catch these failures. How will I know if it fails if I don't have 20/20 hindsight?" While that is correct, it can be better to fail fast and use statistics to prevent failures.

Failing fast has a few advantages:

-   Developers know when a pipeline has failed and don't have to wait for it to finish when it's going to fail, anyway. This saves developers time and can make them more productive.

-   Saves costs because running a pipeline costs money. Not running it when it doesn't have to be run can save more money.

-   Allows other queued jobs to run sooner, thereby improving those developers' productivity.

-   Could reduce rate-limiting errors if those resources aren't requested as often.

-   Capping the pipeline length to shorter amounts avoids burning through generous 50000 minute (833 hour) credits per month (for example, GitHub Pipelines.) By default, some pipelines run for one hour up to 12 hours. If there are a few runaway pipelines, this could incur extra charges.

-   If you fail fast, then you have more time to run other jobs like flaky tests or soak tests which take a long time to run. You can use up more of your monthly minute credits without impacting developers and get more use out of your subscription.

Pipelines can be architected to fail fast by:

-   Moving the steps that are fast to run and do not depend on previous inputs to the beginning of the pipeline. For example, a linting step. If the linting fails, then the rest of the build will fail. It doesn't make sense to gather the dependencies and build the application if the linting will discard all previous work.

-   If the process is very fast, the process could be moved to a git pre-commit hook. This means that when a developer commits a change, a process runs and only allows the commit if the program passes. This could be a linter or a very fast syntax checker.

-   Architecting Bash scripts to be safer in CI/CD pipelines by adopting a fail-if-it-might-be-successful-but-not-guaranteed versus succeeding-when-it-should-have-failed philosophy. This will be a separate post.

The disadvantage of failing fast is that if you have multiple steps, it can be unclear what other steps would have failed if they are cancelled. This correlation can allow for easier debugging as other failure logs from different jobs would be generated.

#### Don't run it if you don't have to

If the pipeline contains files such as readme, then the pipeline doesn't have to be rerun when just those files change as part of a pull request (assuming they are not part of the build artifacts.)

These files could be .txt, .md, .adoc, binary files like .png's, .gifs, or .mp4's.

### Conclusion

In conclusion, there are many ways you can proactively maintain your pipeline against common pipeline failures. Being proactive means avoiding emergencies.

It's important to monitor and learn about Bash scripting because pipelines are the core part of the development workflow. If pipelines don't work, they have to be fixed in an emergency, and emergencies aren't where deep thoughtful work happens. Emergencies are fast fixes that could have wide-ranging effects which aren't immediately apparent, especially working in an unfamiliar language.

Finally, know when to not run your pipeline. Running your pipeline unnecessarily adds up over time, and this includes costs and potentially delaying others from running their jobs if the jobs are queued.
