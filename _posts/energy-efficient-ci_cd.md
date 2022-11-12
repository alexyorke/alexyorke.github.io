---
title: "Energy efficient CI/CD"
date: 2021-02-21
---

CI/CD pipelines are the core of many development workflows today. However, they require energy to run. Since energy may come from non-renewable resources, there might be concerns regarding the environment.

There are a few ways you can optimize your pipeline to increase energy efficiency while minimizing developer impact.

### Coalesce jobs

Coalescing is an energy-efficiency technique commonly used in mobile devices such as laptops or smartphones to save battery power by batching multiple jobs together to avoid intermittent wake-ups.

Here are a few tips:

-   If your jobs are small and don't exceed a pipeline's resource requirements, you could ‌put multiple jobs together on one runner. This could save energy only if multiple machines would have been instantiated or started up to run multiple jobs.

-   If your pipeline has multiple stages, try putting them together in one stage. This could increase pipeline time, but could reduce the number of computers required to return the result.

#### Advanced tips

These tips are theoretical and don't appear to have any concrete implementations yet. They are more suited for large teams.

-   If you have jobs that have to be run periodically (e.g. cron jobs) but don't have to be run at a specific time (just run it today at some point), then a job scheduler could use these ranges or larger intervals to calculate when other jobs could run at the same time. This allows multiple machines to run simultaneously which means fewer spurious wakeups and allows for more opportunities for machines to turn off or go into a very low power state. It also allows for other jobs which have flexible schedules to be batched together when power is cheaper, for example.

-   Pause or slowdown the pipeline during meetings or during breaks such as lunch and then resume it just before the meeting ends. If you're in an hour long meeting, chances are you might not be checking the status of your PR until the end. This means that the PR could be delayed until a few minutes after the meeting so that it completes but is able to be batched with other jobs or with jobs of the other people in the meeting.

-   Run pipelines in five or ten minute increments for the entire team. This allows for multiple jobs to be batched and machines to have time to warm up to accept jobs. This does mean that the pipeline results will be delayed, however.

-   Consider adding a pipeline "cooldown" phase. This means that if a developer quickly pushes multiple commits a few minutes apart the pipeline won't run until a specified duration after the last commit. This can prevent frequent pipeline false starts and premature cancellations.

### Other tips

-   Reduce pipeline failures by using a client-side Git post-commit hook that checks for syntax errors or linting errors that can be optionally overridden. Since the developer already has the dependencies installed and code cloned locally, linting is much faster on the developer's computer. This also means that the pipelines are less likely to fail if the linting stages have already been completed. Ensure that the linting steps, if done as a pre-commit hook, are ultra fast or have a strict timeout of a few seconds (and succeed if it exceeded the deadline.) These pre-linters don't have to be perfect; they could just check the files that have been committed. It's to prevent the CI from failing.

-   If a project is very large, consider breaking it into smaller projects. This means that long-running tests may have to be run less often.

-   Use containers with the software that you need pre-installed. Choose containers that have a minimal base image, build on that image, then use that image in your CI workflow. Ensure that you keep the Dockerfile so that the builds are reproducible. This can reduce the time re-re-re-re-downloading dependencies over and over.

-   If you plan to run your pipelines locally, consider running them on bare-metal. This reduces the number of virtualization layers, potentially reducing idle power usage and increasing job throughput.

-   Have a tentative job-is-successful message by incorporating IDE integration. This means that when a developer creates a pull request, your IDE will send its compile status to the pipeline. The CI pipeline would show a tentative build pass or failure depending on the IDE's status. Each subsequent commit can only show the tentative build pass if the push was done through the IDE (which compiled the code.) When the PR is merged, it can go into a queue, be built, and then merge into master. This means that the pipeline isn't run for every subsequent commit but instead once per merge.

-   Consider reducing the maximum disk allocation per container. This could allow for more containers to run per host if disk-space is an issue. It can also allow for smaller disk sizes to be used.

-   Run Selenium tests in a [[separate VM]{.ul}](https://www.selenium.dev/documentation/en/remote_webdriver/remote_webdriver_server/) and each container would share that VM to start up new browsers. This may or may not save energy.

-   Use \--tmp-fs to mount a RAM disk to store your CI's build files if your pipeline runner doesn't do that by default. Docker will [[write to its own internal filesystem]{.ul}](https://stackoverflow.com/questions/35313763/are-docker-artifacts-when-running-a-container-stored-in-host-fs-or-memory) (which writes to the container's layer which "writes" to the host.) Writing to a conventional disk could slow down build times, meaning that your runner will be running for longer. Writing to a RAM disk could be faster, especially if the files will be deleted the next run. This could use additional RAM, so make sure you size your containers correctly. Ensure this is right for you by doing additional research.

-   Run tests that fail often as a pre-test step. This will prevent having to wastefully run the entire test suite if these tests fail. However, ensure you also run the entire test suite (including those tests which fail often) as you normally do. This can add overhead (running a few tests twice), so additional research is required to see how it impacts your testing.

-   Avoid running the pipeline on draft PRs or WIP PRs if the pipeline's status is irrelevant.

Again, these are mostly theoretical points and are mainly points to stimulate discussions. Some points may reduce reproducibility for every step, so you might want to incorporate a hybrid approach and do full builds from scratch every fourth or nth build or a build everyday. They could involve a lot of administration which would negate the energy-efficiency savings.
