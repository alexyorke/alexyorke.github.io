---
title: "Methods to reduce flaky tests"
date: 2021-02-15
---

### What are flaky tests?

In programming, flaky tests are tests that don’t pass some times. There are many reasons a test might not pass sometimes:

-   It is non-deterministic (relies on a random number generator) and the test isn’t prepared to use some values from this generator. For example, creating an array of a random length and getting the first item. If the array’s length is zero, then there isn’t a first item.

-   It relies on a resource that might not be available or take longer to start up than usual. For example, an HTTP server or downloading a file from a remote host.

-   It uses a shared resource which might be in use. This could be a file, port, or shared data structure.

-   The order of the returned elements changes, but the test checks if they are ordered a certain way.

-   It uses the latest-and-greatest version of a software (for example, the latest tag.) This means that if the software updates, the test suite might get different results because the software version changed.

-   It uses dates or times which, of course, are subject to change depending on the time of day.

-   The environment that the test is running on is different. For example, there might not be enough memory to cache a file or the storage might be too slow and cause timeouts.

Flaky tests can also occur if the tests are too granular or not granular enough.

### Why are flaky tests problematic?

Flaky tests have to be re-run to pass or, depending on the environment, might not be able to run at all. This means that developers may have to re-run their tests multiple times to pass a continuous integration (CI) test before their code can be merged. This reduces productivity as re-running a test suite can take time.

It also reduces confidence in the test. If it’s flaky, it means that it isn’t running some times. Or it might not be testing the right thing.

### Why are flaky tests hard to identify?

Flaky tests might not fail often in isolation because they could depend on different environments or by a random chance.

It is also unclear how many times to run the test suite to ensure that there aren’t any flaky tests, because:

-   The total possibilities for a random number might not be easily identifiable.

-   It requires statistical knowledge to calculate how likely failures could occur, and a confidence interval.

#### How many times do I have to run my tests?

How many times you run your tests depends on how important identifying and finding flaky tests are. You can use the formulas below to determine what probability of success (when it should have been a failure) is right for you. Log the test suite seed after the tests fail so that you can reproduce it.

Let’s consider a test which generates a number from 0 to 400 inclusive, but when it generates a zero, then it fails. So, there are 401 values total.

Let’s run the test suite “a lot”. Here, 100 times. Running the test once means that there is a 400/401 chance of it succeeding, or a 99.75% or so chance. How about running it a 100 times? If each trial succeeds 400/401, then (400/401)^100 is about a 77.9% chance of succeeding when it should have failed.

What if we run it 10000 times? Well, there’s a 0.00000000143% chance of it succeeding when it should have failed. It might not be workable to run the test suite 10000 times, especially if it is very resource intensive.

### Test granularity

Test granularity describes how detailed your tests are and what they are testing. Use different levels of granularity depending on the test. It is important to know what level of granularity to use because not knowing will cause flaky tests. Each decreasing level of granularity implicity checks each previous level.

A granular test can succeed when it should fail, and a fine-grained test fails when it should succeed.

A **hyper granular** test implicity checks if a function is not throwing an exception. It just runs the function. If the function returns anything other than exception, say null or false or garbage data, it is irrelevant.

A **very granular** test checks if a function is not throwing an exception of a certain type. If the function returns anything other than an exception of a certain type, say null or false or garbage data, it is irrelevant.

A **granular** test would just check that a function is returning x elements, but wouldn’t check what the elements are. Their contents are irrelevant.

A **fine-grained** test would check if a function is returning a precise set of elements, and those element schemas must match a defined schema. If the elements are out of order, it doesn’t matter.

A **very fine-grained** test would check if a function is returning a precise set of elements in a precise order, and those elements must match another set of elements exactly.

A **hyper fine-grained** test would check if a function is returning a precise set of elements in a precise order, and those elements and their presentation must match another set of elements exactly.

Here are some more concrete examples:

-   A function returns three elements, and the granular test checks if it returns three elements. The granular test passes. However, those elements are all empty, but they shouldn’t be empty. The granular test checks if there are three elements, not what’s inside of them.

-   A function returns three elements asynchronously, and the fine-grained test checks if it returns those elements in a certain order. The order of the elements doesn’t matter, so the fine-grained test fails when the elements are not in the order it expects. The fine-grained test should have passed because all the elements had the right information but weren’t in the right order.

### It’s more likely than you think

#### Probability that a random byte array is a valid UTF-8 string

There’s a 4% chance that your randomly generated byte array is a valid UTF-8 string [<u>https://math.stackexchange.com/questions/750551/probability-that-random-byte-array-is-a-valid-utf-8-string</u>](https://math.stackexchange.com/questions/750551/probability-that-random-byte-array-is-a-valid-utf-8-string) . These cause issues when dynamically assuming the type of variables, such as in dynamic languages. If the array is treated as a string, then some operations on the string won’t work.

#### There’s a 19% chance that an English word is a valid base64 string

Be careful when deserializing random strings that are randomly generated into base64. Try it for yourself. while read line; do base64 -d &lt;&lt;&lt; "$line" &gt;/dev/null 2&gt;/dev/null && echo "$line"; done &lt; /usr/share/dict/words \| wc -l . In fact, any alphanumeric string whose length is divisible by four is a valid base64 string.

Reference: [<u>'changeme' is valid base64 (blog.3fx.ch)</u>](https://3fx.ch/blog/2019/12/09/changeme-is-valid-base64/)

### Language-specific tips and tricks to reduce flakyness

#### Shell

-   ShellCheck is a program which checks your shell script against common bad practices, like not quoting globs. Not quoting globs means that some commands might fail, depending on what files are in the directory or if the path contains spaces.

-   Watch out for race conditions when reading from all of the files in a directory and writing to a file in the same directory. For example, cat ./\* &gt; file.txt. This could cause an infinite loop because it is reading from the file that it is writing to. You can use the sponge command to buffer the output and then write it all at once.

-   Ensure that it has the correct dependencies and that the bash version on the host is compatible. You can use bashreqs, a program of mine, to check what dependencies your bash script needs.

-   Ensure that the line endings are LF. If they are not, then your script might not run or might suddenly stop at a certain line. You can convert to LF line endings by using a program such as dos2unix, and by setting [<u>auto LF line conversions in your .gitattributes file</u>](https://techblog.dorogin.com/case-of-windows-line-ending-in-bash-script-7236f056abe). This doesn’t prevent uncommitted files from having the wrong line endings. Create a .editorconfig file and set the line endings there, too.

-   When sorting large files, ensure you have enough disk space. You can pass the --compress-program flag to sort to compress the temporary files.

-   By default, bash will keep executing your script if one line fails. This is contrary to many programming languages. You can change this behavior by adding [<u>set -e to the top of your shell scripts</u>](https://stackoverflow.com/questions/19622198/what-does-set-e-mean-in-a-bash-script), but make sure that it is ok to stop at any point in your script and that any cleanups will occur if so.

-   Ensure that the script has execute permissions (so that you can run it), and that the script has permissions to access any files it needs.

-   Ensure that custom command aliases are ported with your script.

-   Ensure that commands are installed using the “command” command.

#### Jasmine

-   If the test fails, does it clean up after itself? Does it have anything to clean up? Does it call ngOnDestroy only if it called ngOnInit?

-   If expecting a boolean, use toBe rather than toBeTruthy or toBeFalsy because toBeTruthy succeeds if the value tests to a true value, so “1” is a valid output. The toBe function checks if it is equal to the boolean true.

-   Ensure you know what you expect from an observable.

    -   Do I need all of the items, just the first one, the second one, or the last one?

    -   Do I need to count how many items are coming out of it, or do I need to keep getting items until it completes?

    -   If the first one is ok, is it safe to say the test passed even if the second item causes an error?

-   Use DoneFn as callbacks for async functions such as subscribe(). Otherwise, the test could keep running and not expect the output.

-   Different operating systems and different browsers can empty the [<u>micro events queue differently</u>](https://jakearchibald.com/2015/tasks-microtasks-queues-and-schedules/). Make sure that you test those browsers.

-   Research whether GetElementByText vs XPaths makes sense for your project.

#### Golang

-   Use Go’s race condition detector: go build -race.

### How to deal with flaky tests

There are many ways to deal with flaky tests.

-   If a flaky test cannot be easily resolved, quarantine it. This will prevent other developers from being blocked. The test should be fixed quickly to ensure that new code runs the test. Don’t quarantine too many tests simultaneously because this means more and more code might not be correct and can cause an avalanche effect.

-   If a test can’t be easily improved or requires additional research, consider adding a flaky annotation. This keeps track of the flaky tests and can allow automatic rerunning those tests. Some test frameworks can create a flaky test report, including how many times the flaky test failed to run and how many are currently running. The test can still run, but won’t fail the entire test suite unless it cannot run a certain amount of times.

-   Consider deleting the test if it no longer serves its purpose, or a set of other tests cover it.

-   Consider refactoring or rewriting the test if there are too many changes to make it non-flaky.

### The flaky test checklist

When programming, we have to make assumptions to create code. Assuming nothing means that the code becomes bloated with cases that will never happen. Assuming too little can cause flaky tests.

Here’s a checklist of what assumptions you are making and whether they are ok:

#### Transformation of outputs

-   Does the order of the returned objects matter? The order might change depending on the test suite environment. If the order doesn’t matter, then sort the elements before comparing or use a non-variant equal method. This applies to lists and database results.

-   Does the presentation of the returned object matter? If the JSON syntax element ended with a space, is it still considered the same object? Does the property ordering matter?

-   Does the output have to be transformed? For example, is the output case sensitive? Deserialize objects before comparing them, if not.

-   Make sure that the number still fits within the casted data type. For example, ints and bigints.

-   Use ranges when the value’s precision is flexible or use value-smoothing or rounding.

-   Make sure that the invalid data can’t accidentally be valid. For example, if random padding is added to an output string, could one of the random padding combinations be divisible by a certain number?

-   When using environment-specific info like CPU percent, ensure that ranges are used if the CPU could change.

-   Randomizing an array means that the output array could be the same. Depending on the size of your array, it could be a high probability. If it can’t be the same, then make sure that the array is re-shuffled.

-   Use regex or URL matching if the text needs to match a pattern rather than an exact string. Use URL parsing libraries if a parameter from a URL needs to be matched, rather than checking if the parameter as a string exists in the URL.

#### Race conditions and asynchronous processing

-   Does the test assume that the shared state is clean?

-   Are you assuming an asynchronous process finishes quickly? It might not. Use callbacks for expectations.

-   Getting the time multiple times means that some instances aren’t at the same time. Ensure that you store the time once if all objects require the same time.

-   When generating random numbers, do the minimum and maximum values still pass the tests? If retrieving a random element from an array, use the built-in function to get a random element from an array (or make one) rather than a bare array index to prevent array out of bounds bugs.

-   Does your code depend on something else which you don’t have control over, for example, an HTTP web service? Use polling to check for updated values, and timeout after a specified period.

-   When comparing representations of two dates, make sure that you have the right time zone and are considering if a date ends with a numeric digit that that digit might not have padding.

-   Wait for sockets or other resources to become available. This could be used for E2E testing (checking if an element is visible) or if a file is ready. Remember to use timeouts to prevent waiting forever if the resource never becomes available.

-   Flush storage after tests.

-   Don’t read and write from a shared state unless you’re sure that it’s safe.

-   Deleting empty vs non-empty directories might be different, depending on your programming language. The tests might write more than one file to a directory and so the regular clean up commands might not work.

-   Ensure that the port you’re trying to access isn’t in use and you have enough privileges to access it.

-   Use library functions when making temporary folders and files. It will make them with a random name, put them in the right location depending on the environment so that they are writable, and have a unique name.

-   When making database calls, try using transactions when possible.

#### Fuzzing

-   Random numbers can be the minimum and maximum values within the range. Make sure your code can handle these values.

-   Ensure random strings don’t contain invalid UTF-8 characters. Make sure that the random string function is what your user can enter, such as alpha-numeric characters. That’s not to say we can never test them, rather, they should be tested separately.

-   Check keep-alive HTTP settings when making long-running calls.

-   Understand the probability that a flaky test will occur.

#### Consistent environment

-   Ensure the correct level of granularity. Are you checking if we received x events, or are we checking if those x events are precisely a certain value?

-   When writing files, make sure you have privileges to write them.

-   Avoid tagging dependencies as latest as they could change at any time.

-   Clean up temporary files.

-   Databases have enough buffer size to handle requests if using manual timeouts.

-   Remove old versions of libraries (such as Go) if they are unsupported.

-   Be careful when writing to and deleting from NFS file systems. The file system could be slow or suddenly disconnect.

-   Try running it on different OSes like Windows.

-   Consider using a package.lock.json file to lock dependencies and prevent silent upgrades.

-   Ensure that scripts don’t have invisible zero-width Unicode characters. These could cause strings that look identical to be different when compared by a computer.

-   Does the test depend on its environment, for example, using a certain port? If so, store it in an environment variable and input it at test time rather than hard coding it.

-   Creating many test files? Consider creating a sub-directory per test to make sure that the results are isolated.

-   When creating directory structures and filenames, make sure that they comply with the OSes restrictions on filenames, allowed filename characters, and maximum path length. Use path joining utilities to combine two paths together.

-   Some files, like those on HTTP servers might not be available or are rate-limited. Make sure you can catch and handle these errors and retry.
