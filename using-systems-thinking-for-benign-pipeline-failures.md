Pipeline failures, at a high level, are misaligned assumptions. The developer assumes that the code is ready to go but the CI tool disagrees.

This could be for a variety of reasons:

-   The developer makes a trivial change and erroneously believes that it won't break the build.

-   They forget to build it locally or forget to run some of the commands like linting.

-   There are temporal issues on the pipeline, like a resource that can't be accessed.

-   The pipeline's environment is slightly different from the developer's. For example, the linting is set slightly differently, or different versions of packages are installed.

-   Some of the tests might be flaky and fail sometimes.

-   The pipeline contains hardware and resources that the developer doesn't have access to, like building on a Windows computer.

-   API rate limits.

-   Maximum execution time exceeded.

-   Working with unfamiliar files like YAML and XML.

-   Different installed dependencies.

I've probably caused hundreds of temporary pipeline failures so far. Nobody is perfect and we shouldn't expect developers to be, either. Pipelines are there as a safety net.

What we can do, however, is analyze, from a high-level what recurring issues developers are experiencing. Each pipeline failure doesn't merely represent a few minutes of waiting, it represents a data point.

Say you have a CI build that fails 5% of the time because of linting or configuration files with invalid syntax or invalid schemas. I don't think any developer wants to purposefully wait a few minutes to find out that whatever they've written was broken. They want a tight feedback loop.

This can show what developers might find useful: better build processes, easier linting, and an early warning system before committing files that are not going to pass the build. Auto-formatters. Linting rules that automatically reformat the code.

The small issues, especially the subtle ones that take time to debug, can help find discrepancies between the pipelines and developer's workstations. This could be different from where the application is deployed, so knowing how the pipelines or code was fixed in these situations is essential. If you have logs enabled, you could go to an earlier commit and find the diff that fixed it. If there are many similar issues, you can use this information to help others.

Other developers may be experiencing similar issues, even if their pipelines are passing. They might be using complicated workarounds to get it to pass or different environment settings.
