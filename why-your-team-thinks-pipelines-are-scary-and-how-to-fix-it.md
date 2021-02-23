Pipelines can be scary. Why is that? Well, they are central to many CI/CD development workflows. They are the window to pushing code into production.

Once they break or start having issues, the entire development team has to stop and fix it.

However, there are some reasons ‌a pipeline might break more often than it should, or why it incurs more technical debt than other parts of the project:

-   Central to many parts of the development pipeline, so it's high risk if you break it.

-   Pipelines might be written in Bash, a scripting language that many developers might be unfamiliar with or don't use in their day-to-day. Or they could use YAML files.

-   Consequently, developers probably don't have IDE syntax checking or other development tools used to test the scripts before committing them. They might not know of some Bash debuggers or Bash linters available. They might not have the CI image cloned locally to test the scripts. If they work with GitHub pipelines, they might not use the JSON schema to validate the YAML files before committing them.

-   This means that scripts could be run via trial-and-error, using the CI pipeline to run and validate the scripts.

-   This can be very frustrating and slow because there is a long turnaround time between commits. Pipelines have to clone and run all the code which takes on the order of minutes. When developing locally, it can take a few seconds or milliseconds to build code.

-   It's difficult to debug remotely, as you normally don't have a debugger with Bash scripts. While you can use set -x to show what the commands are taking in as arguments, it doesn't show the whole picture. Debugging tools like CPU usage (which can be helpful for diagnosing hangs) might not be available.

-   Developers then turn to Google or Stack Overflow, where they might get conflicting solutions or many upvoted comments describing the caveats for some solutions. They might be confused about what POSIX means and whether they need POSIX compatibility. Sometimes the commenters don't understand Bash and criticize the answer for not working when in fact the commands work as intended.

-   This means developers could choose other less popular solutions that have different side-effects. While they might not work as well, they might be more clearly written and so don't have as much criticism. Or, they could be less popular and since many people haven't used those commands, then there will be less criticism as a side-effect.

-   Sometimes the commands might not work for the edge cases that the developer's solution needs. The developer may choose the question because it's close enough to what they're looking for.

-   The commands may only work on certain versions of Bash, or require commands from different operating systems. This might not be clear in the answer. This means that a command might not work and might be ambiguous ‌why. It might be because of the syntax or because the command wasn't the right one for the job, or the command isn't installed or is not in their \$PATH variable.

-   If developers do their day-to-day work in a procedural language with exceptions, they might be confused with Bash scripts. Normally, if a line fails, then the program aborts. Bash is different, as by default, it keeps executing if one line fails. If the line doesn't print an error message, then it could be confusing ‌why it was skipped.

-   This creates a continually stressful environment which entices developers to get the job done as soon as possible. Stress isn't great for long-term decision making. This also reinforces negative experiences.

This leads to:

-   Trying to fix the mistakes by following highly touted Bash best practices when not considering the side-effects or how the flags change the language's behavior.

-   This means that when using others' code, which does indeed work on their machine, it might not work in their script because of the flags added which change Bash's behavior.

-   This can lead to code debt and not-touching-it-if-it-doesn't-need-to-be-fixed mentality. Code is just maintained and not refactored out of fear of breaking something.

That sounds terrible. What can we do to mitigate these effects?

-   Learn Bash and shell scripting. Not just the snippets\--all of it. Learn the edge cases. Learn it from a reputable source, like a book, that lays out the language fundamentals. It'll also have some gotchas too. Try to avoid the first edition of the book if you can, unless it's highly rated. While you can learn it on the internet, there's a lot of bad or unintentionally dangerous advice, unfortunately.

-   While it can be a tongue-and-cheek gesture to threaten team members for having to babysit the pipeline until someone else breaks it, it can be stressful for those who are not familiar with Bash. Ensure they take part when fixing the pipeline, but know that they can ask for help.

-   Try to replicate the CI environment locally. Try running some scripts locally as well so that you can get instant or near-instant feedback. This will make you more productive.

-   Try using tools like Shellcheck to find out some issues with your shell scripts. While Shellcheck is amazing, it isn't a replacement for syntax checking your shell scripts (although it does ‌a pretty good job.) Use bash -n for that. I'll go into why in another post.
