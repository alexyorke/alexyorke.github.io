*This article is about tests that can't be run asynchronously, don't have callbacks or other ways to notify when it is safe to return from a result. These tests are "polling" or "waiting" tests.*

People are very adaptable. They can change their environment to make things more livable and know how to solve complex problems. People are good for a lot of things. They're also good for manually running flaky test suites. Too good, in fact. They might not know they are flaky because we're so adaptable.

### People aren't computers, and vice versa

People aren't good at being computers. They operate on feelings, emotions, and intuition. They don't have millisecond accuracy on what time it is. They can override what they are told if it is unsafe, makes little sense, or needs to make minor adaptations to achieve a goal. Computers don't have an abstract concept of what a goal means. Sure, machine learning has goals, but these are just mathematical equations.

When you ask a computer to run a test, it'll do *exactly* what you say. In some ways this is good: you want reproducibility. But it can go the other way as well. Sometimes you have to give computers a time limit to run a test. If it's past a certain time limit, then there's something wrong with the test and ‌stop and report a failure.

**The issue is computers don't have a concept of what a goal is.** Here, the goal is to run the test and report if it failed or succeeded within a period. Computers don't know if waiting 10 more milliseconds could have caused the test to succeed. Even if they did, it wasn't in their instructions. Humans ‌wouldn't think twice about it; if I asked them to wait 10 seconds, then they may just by human variability, wait slightly longer. Or, if I have asked them to wait 10 seconds but the test in the past actually takes 11 or 12 seconds, then they'll probably wait ‌longer. It might be subconscious.

This is because people are achieving a goal: wait until the button appears on the screen and then click it. These instructions are guidelines and not rules.

The other difference is that people don't have all the information a computer has, nor do they need that information. A computer is given instructions to "know" when to click on the button. This could be that the HTML for the button is inserted into the DOM, or its enabled attribute is set to true. People don't care about HTML or DOM elements, they look at the screen and if the button looks clickable, then they will click on it. If it's disabled and they click on it by accident, they'll click on it again when it's enabled. If the button says "Don't click me" for a few seconds and then says "You can click me now", people will adapt. Computers don't know until they are programmed.

### Making computers more like people

How can we bring some people's properties to computers? Well, for starters, programming intuition or common sense into computers would be almost impossible. But what we can do is give computers more information, like how long previous test runs took. There's a little something in statistics called percentiles that could be useful. Testing with percentiles **almost certainly isn't a new concept**, but it's an interesting one to explore.

Percentiles are a measurement for determining what percent of numbers are below or above a certain number. When you hear the phrase "99th percentile", it means 99% of the measured values are ‌below or above a certain number. How can percentiles help us when testing?

Let's go back to giving the computer more information. The computer is now given some numbers that correspond to how long the test took to run in the past. Let's say the tests ran **successfully** 50 times and their standard deviation for how long the tests took to run in seconds is three seconds. Standard deviation is a measurement for how "spread out" numbers are.

The computer now knows that the numbers are spread out by three seconds. What can it do with that information? Well, computers are good with math, and they're *decent* at making pseudo-random values. What we can do instead is tell the computer "Wait until the 99th percentile, or wait until the fourth standard deviation, and if the tests still aren't running, then add a random delay, check again, and if they still don't work, report a failure."

What does this mean? Well, now the computer is automatically adjusting how long it is waiting before it is reporting a failure. It's more human-like because it is using its previous experiences to determine how long a test will take to run. If the test gets just a few milliseconds longer, then it will be within the range of the percentile and the computer will log a success and how long it took to run that test. It'll then use its previous results to calculate how long it should wait in the future, which will include this data point.

This sounds great, right? People can write tests and not have to set really large timeouts (which can waste time) or really short ones, and the computer will know how long to run the test. But there are a few caveats:

-   If the tests are slowly getting longer and longer, this could mean there are performance issues. Or, it could result from more features and code being added. It's important to monitor how long the tests are taking to ensure they are not taking too long. This is especially an issue as the tests are automatically being run longer and longer with little to no human intervention and so they might not realize any issues.

-   If the tests are rewritten or partially rewritten, it can be unclear how long to wait for the tests to pass. This could be mitigated by automatically resetting the time ‌to run the test (and set it to a very large value), and then as the test runs in subsequent invocations, it would narrow down its acceptable values.

### On acceptable values

It can be unclear how long to wait for a test to pass if there isn't any data on how long it took to run in the past. There are a few guidelines you can use to calculate how long you should wait:

-   If all tests in the solution took this long to pass, would it exceed the pipeline timeout?

-   If the pipeline is comparable to the customer's device (e.g. a mobile device), how long would they wait before giving up? This may not be representative because testing could run un-optimized code or run multiple tests in parallel, ‌slowing down execution time.

-   If I were to run this test, how long until I would stop the test if it was still running and didn't pass?

-   What are my team's performance goals?

### Conclusion

In conclusion, people don't make great computers. Many of people's values, intuitions, and variability allow for adaptability to achieve a goal but isn't normally translated to computers who follow instructions to the letter.

Applying some people principals such as variability to tests to accommodate for random delays can increase test success.
