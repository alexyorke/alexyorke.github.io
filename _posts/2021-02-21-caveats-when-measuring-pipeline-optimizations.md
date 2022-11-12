---
title: "Caveats when measuring pipeline optimizations"
date: 2021-02-21
---

Pipelines are the core of many CI/CD workflows. Having pipelines optimized means that the core of the CI/CD workflow can be completed faster or use fewer resources, and this can also yield cost savings.

### Why optimizations are hard to measure

Optimizations, especially when taken together (even though small) can yield large performance impacts over time. However, it can be complex to assess how much these improvements meet the end result.

This is because:

-   Developers may not check a pipeline regularly after creating PRs and the review process may take time to complete (having a faster pipeline isn't a bottleneck.) So, increasing the performance by a few minutes in the average case may not have as wide ranging effects as one may have thought. Or, it could decrease, for example, the 99^th^ percentile or situations where code must be expedited. These cases may not occur often but are important.

-   Decreasing a pipeline's duration could be exponentially effective, especially if the jobs are queued. This is important during deadlines where multiple jobs can be queued, potentially exponentially increasing waiting time.

-   Each dependency takes time to download, and this can vary. Measuring smaller performance impacts may not appear statistically significant when summed together with all other changes, but the sum of these changes in isolation matters.

-   Dependencies could be rate-limited which can cause failures or very slow downloads. This can become apparent when trying to optimize a pipeline and running it much more than it is usually run to see if the optimizations are statistically significant.

-   Performance impacts like less data written to the disk can be difficult to measure, especially if multiple jobs are running simultaneously on the same pipeline. This can cause inter-job variability which makes measuring statistical significance more difficult because an identical job depends on environmental factors outside of its control.

-   Other VMs running on the same server could have higher process priorities or CPU credits, causing other invisible variabilities.

Throwing more hardware and increasing the queue size can work, but there are financial and resource limitations to doing so. Sometimes, resources like a specialized server can't be replicated and so ensuring you have enough throughput is important.

Pipelines can be separated into multiple steps which can run in parallel, but there's a limit to their ability to be separated.

### Small improvements can be exponentially effective

If the pipeline is queued and is "slow", then small improvements can be exponentially effective.

For example, if we can model the pipeline as a M/M/1 (essentially means a queue with one server that can run just one job at a time) queue (ignoring other factors), then we can model the waiting time for jobs as a simple equation. This isn't a perfect model as there could be several other factors and your pipeline queue might be queued differently.

Let's assume that it takes 30 seconds to process a job and the pipeline can process *x* jobs per 30 seconds. The pipeline is pretty slow right now and can only process 0.25 jobs per 30 seconds, or one job per 120 seconds.

There's a bit of math involved but don't worry about the smaller details. This equation is called the [["Simple two-equation queue"]{.ul}](https://en.wikipedia.org/wiki/Queueing_theory). Waiting time = (1/x) \* ln(30/x), which equals 19.15 seconds for waiting time.

What if we doubled the jobs per second? Say we found an efficiency gain. Then, we could process 0.5 jobs per 30 seconds, or one job every 60 seconds. This would mean we'd have a waiting time of about 8.19 seconds, which is about a 2.4 times improvement!

What if we doubled the throughput again to 1? Well, we'd get a waiting time of 3.4 seconds, which is another 2.4 times improvement! But wait a second, there's only a difference of about five seconds. The first time we improved it by about 11 seconds, now it's only five, even though we doubled the throughput.

This shows that diminishing returns can result as the pipeline is continually optimized, but is exponentially more effective when it is "slow".

#### On making small improvements

As an aside, you can also try rearranging a set of commands in a Bash pipeline to perform the faster commands first as long as it would yield the same results. For example, if you're filtering a file for lines that contain certain words then performing an expensive step on those results, then filtering the results (which contain the original line for more words), try running the filters together or combine them together before running the expensive process.

### Become familiar with Bash to prevent subtle optimization bugs

Optimizations can be negative if they subtly introduce bugs or ignore edge cases. When dealing with an unfamiliar language, optimizing something that you're not familiar with means that you could be ignoring some edge cases to make something negligibly faster.

If you're not familiar with the Bash or shell scripting languages, familiarise yourself first, including some of the idiosyncrasies, edge cases, gotchas, and better practices. This will allow you and your team to modify the code more efficiently.

Don't be too risk-averse, however, as this means you might avoid changing the pipeline for the risk of breaking it. Sometimes there are safer or equivalent ways to write a script that may or may not increase performance, and those require changing the scripts. Sometimes the optimizations are safer and also give performance improvements; a win-win.

### Performing measurements

To perform more accurate measurements, try running it on a private custom runner many times. Also, prefix the Bash commands and scripts which don't perform network accesses with the "time" command to find how much CPU time they are using.

While this isn't 100% perfect, it can reduce other variabilities and increase statistical confidence.

### Conclusion

In closing, optimizing a pipeline and determining if it is statistically significant can be challenging. Only large-scale optimizations can be easily viewed as optimizations but smaller optimizations may not appear to be optimizing the pipeline. This doesn't mean that small optimizations are not effective, rather, the language and more theoretical understandings of dataflow between commands has to be analyzed.
