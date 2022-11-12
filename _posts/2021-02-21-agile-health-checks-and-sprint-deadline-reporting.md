---
title: "Agile health checks and sprint deadline reporting"
date: 2021-02-21
---

Sometimes when completing a sprint, the sprint may have exceeded its velocity and your team has got much more done. Other times, it may have failed short of its velocity, and sometimes it may have hit the goal right on.

If sprints do not hit their velocity goal (within a certain margin of error), especially serially, it's common to perform an investigation to find out why the goals aren't being met. Deadline slipping can cause project delays and loss of revenue, so delays are not welcome.

However, completing a project early is anomalous too. It's certainly not a bad thing---getting more work done means the project can be completed before the deadline. That's not usually considered being a bad thing, and so investigations don't occur.

I would argue that a sprint being early should be explained just as ones that don't meet expectations (within a margin of error.) It shouldn't be posed as a negative investigation, though.

Knowing why a sprint is early means you can identify issues before they become long-term issues. Or you can identify high-impact process improvements and investigate related ones.

### Categorization

There are two categories of reasons ‌a sprint could be early (these categories aren't necessarily bad or good):

-   Short-term reasons, such as developers pushing to meet deadlines or de-scoping a user story.

-   Long-term, such as developers only working on user stories they are familiar with or technological efficiency improvements that can be carried over to other sprints.

-   A mix of both.

Also, there are several reasons ‌a sprint might be early:

-   Developers expending extra effort to meet deadlines. Depending on how hard and how long they strive to meet deadlines, it could cause more bugs and rework later on.

-   Technological advancements such as a faster build system or better IDEs or software.

-   Less tangible process improvements like fewer approvals needed.

-   Different team compositions (if some team members have to go on leave or are available during a sprint.)

-   Developers working on tasks that they are familiar with. This isn't inherently bad, but it could create knowledge islands.

-   Task parallelizability is different. I say differently because having highly parallelizable tasks does not mean tasks will be completed faster. The tasks might rely on several sub-components completed by different team members and would need lots of communication.

-   Clearer priorities.

-   Different ‌meetings or different amounts of meetings.

-   Less context switching.

-   Different communication patterns.

-   Technological issues like flaky internet (especially during winter months.)

-   Different weather patterns or societal effects.

It's important to gather team-level metrics and identify patterns to maintain a constant velocity because it de-risks the deliverable's deadlines. Also, it can prevent longer-term surprise issues like knowledge islands.

Your team might not know why the sprint was faster or slower. If you ‌ask them, ensure it is as a positive rather than a negative.

Metrics by themselves isn't a panacea. If there were delays, they could be multidimensional, but only one dimension manifests itself statistically. For example, if tasks take longer to complete, making them go faster might not be the best approach. There could be blockers, for example, which prevent tasks from‌.

### Methods to create metrics

How can you create metrics for seemingly intangible items?

-   To find knowledge islands, tabulate what files each team member is changing and in which repository, including co-authors. Assess the ‌files (e.g. tests, features, bug fixes.) Git has several commands to use for this purpose. However, this metric could be unreliable because team members who are unfamiliar with certain tasks may produce more verbose code or update the documentation, which would register as a file change. If pair programming, one author may not be the co-author of a PR. If there are large, long-term discrepancies, then ensure that knowledge islands aren't being created.

-   Record who isn't and is available for sprints.

-   Take notes of how often pair programming occurs during stand up.

-   Depending on the project management software used, it could be possible to generate a Gantt-style chart for tasks with explicit dependencies. This could ‌generate dependency depth or task parallelizability.

-   Project management software can also show context-switching. If priorities change frequently, then developers may have to stop and start new tasks. This can hurt productivity. I could record this in project management software as task state changes. You can also check for stale or outdated branches. These may have to be merged later on as they become more and more out of date, and resolving merge conflicts can reduce developer productivity.

-   For assessing communication patterns, some software like Slack and Teams can show team-level message statistics like number of messages sent or phone calls per day. Again, this metric could be unreliable, as of course it doesn't show the content of the messages or how concise the messages are, as this would be a privacy issue.

-   Identify task-level topics or themes. Some developers may have more interest or experience working with these types of tasks, even if they span user stories.

-   Use a burndown chart to determine when user stories are moved into different stages but are not necessarily done. This could help untangle the review process (which could be delayed because of other factors) and how fast the user stories are being completed.

-   Identify when developers might get overwhelmed by monitoring how many points they complete each sprint and find periodicity. If there is a lot of periodicity, then developers might be extending themselves too much one sprint and have little energy for the next.

-   Use websites like downdetector to monitor outages. Use its heat map to identify geographical outages that may not be reported on the main chart.

-   Record historical weather data.

It is also important to know about statistical significance. People aren't robots and can't be expected to perform precisely the same every time, and there might be variabilities that are because of random chance. You can assess statistical significance through many statistical analysis softwares.

### Conclusion

In conclusion, knowing why a project is early is equally important as knowing if it is behind schedule. While metrics are important, it is important to know if they are statistically significant and to use systems thinking to ensure you're measuring the right things.
