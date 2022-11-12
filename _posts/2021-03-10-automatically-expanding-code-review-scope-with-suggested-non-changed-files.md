---
title: "Automatically expanding code review scope with suggested non changed files"
date: 2021-03-10
---

Code review is important because it reduces coding errors when introducing new code into the codebase. It can also increase code quality. However, conventional diffs suffer from a flaw if they are solely used as code review tools: **they don't show what should have been changed.**

There's two main ways that files are changed together:

-   Through refactoring, renaming, or logic changes.

-   Renaming a string or term.

Renaming a string or a team in a string won't be covered by this post, and this approach isn't that great for solving it. This is because renaming strings may encompass many files at once but only once, and so there won't be enough data to correlate them together.

### Similar research

There has been research similar to this, including [[future-defective]{.ul}](https://sail.cs.queensu.ca/Downloads/MSR2015_InvestigatingCodeReviewPracticesInDefectiveFiles_AnEmpiricalStudyOfTheQtSystem.pdf) files and [[Who Should Review My Code? A File Location-Based Code-Reviewer Recommendation Approach for Modern Code Review]{.ul}](http://chakkrit.com/assets/papers/thongtanunam2015saner.pdf). What we need is the ability to find out what files are normally changed with other files, then flag those if they aren't changed as part of a PR. This article [[Temporal correlation in Git repositories]{.ul}](https://dzone.com/articles/temporal-correlation-git) shows a sample program written in PHP that correlates file paths with other file paths if they are changed together.

While that article is focused around avoiding [[Shotgun Surgery]{.ul}](https://michaelfeathers.typepad.com/michael_feathers_blog/2011/09/temporal-correlation-of-class-changes.html) (finding classes which are correlated together too much) it can also be used to find which files should be modified together. Sometimes it's not possible to fully decouple files (e.g. when adding a translation string when modifying the UI.)

### Getting started

Let's experiment. Clone [[Angular]{.ul}](https://github.com/angular/angular), create a directory called "commits", cd into angular, and run this command:

while read hash; do git show \--pretty=\'format:\' \--name-only \"\$hash\" \> ../commits/\$RANDOM\$RANDOM\$RANDOM.txt; done \< \<(git log \--oneline \| cut -d \" \" -f 1)

What this command does (it's from the original article) is get a list of all of the file paths that changed for each commit and create a new file with those file paths in it. The command isn't exactly optimal; the random file names aren't guaranteed to be perfectly random and so there might be a chance that one of the files gets overwritten. For demo purposes this is ok, as there's over 20k files so if one gets overwritten it's not the end of the world. I could use a counter next time.

Whipping up a quick C\# program, we can group the files by the other files that they've changed with. I don't want to release the source code just yet as it's an O(N\^2) algorithm and the code is super messy. Essentially what we're doing is reading each file with the file paths, creating a key-value pair with each path together with each other path (permutations), and then adding those pairs to a list.

With those pairs, we group by the first element and then group the values together. This is what we get:

Type = \"packages/router/src/url_tree.ts\" -\> \[0\] = { File = \"packages/router/src/router_state.ts\", Count = 15 }, \[1\] = { File = \"packages/router/src/shared.ts\", Count = 15 }, \[2\] = { File = \"packages/router/src/router.ts\", Count = 14 }, ...

### Parsing the output

How to read: out of all the PRs that the file at the path packages/router/src/url_tree.ts was changed, the file at the path packages/router/src/router_state.ts was also changed in the same PR 15 times this file was changed, the file at the path packages/router/src/shared.ts was changed 15 times, etc. If we change url_tree.ts without changing router_state.ts, then there might be a bug, because router_state.ts is usually changed when url_tree.ts is changed.

Note that there are some caveats with this approach. I'm not checking when url_tree.ts changes just by itself, and I don't know the percentage of how often router_state.ts changes in regards to the other files. Also, I'm not keeping track of renaming.

If we repeat this for all of the commits, we can get this structure for each file path. I did the first 100 files on Angular and got a 12MB JSON file; there's certainly a better way to store the database, however.

### What this means for you

What this means is that if you have a PR with file X changed, you can look it up in a dictionary whose value is a list of the other popular files that are usually changed with this file. If those files have a high probability of being changed (say, 90%), then you could warn the user that these files are usually changed together and that it was "missing" from the PR. Of course, the files aren't usually inextricably linked but it's good to do a double check.
