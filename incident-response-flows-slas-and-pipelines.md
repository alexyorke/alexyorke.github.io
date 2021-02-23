Many organizations are adopting Agile and Agile-based processes. Agile's motto is "move fast and break things." While I agree that at some point you have to "Ship It", chances are there will be issues in production that have to be fixed, well, immediately.

It can be ok to move fast and break things, but at some point you have to fix them. You could have thousands or millions of users who you have an SLA with. Every second that your services are down could be costing your company lots of money, or using up your SLA downtime "credits" very quickly, making future disasters more costly.

There are thousands of different ways a company could prepare their incident response teams. Hotfixes could be pushed directly on the nodes themselves, or if development is complicated, pipelines could be used. Pipelines in this situation may not be the optimal choice, but could be useful if the SLAs need to be met but aren't a life-or-death situation. Maybe you don't have an incident response plan yet or are in the process of developing one. Maybe sometimes you need to get a push out very quickly to hit a deadline.

In these situations, pipelines are the window to deployment but also the bottleneck. When your production server is down, pushing code via a pipeline might be too slow.

You can expedite it by emergency merging when some of the checks have passed. But if your pipeline is complicated, how do you know what checks are optional and which ones are required? What if you hit merge when the code is half-way through compiling but doesn't actually compile when it hits master?

Pipelines with required and optional steps aren\'t new. When you make a PR on GitHub for example, the merge button will turn white and enabled when all of the required steps pass but there are still optional ones pending or running. It'll turn green once everything is done.

There's some issues with that approach, though. In normal development, all steps might be required. You might not want developers skipping some of the linting steps to save time, for example. In an emergency though linting is irrelevant.

What we can do is add in another priority level: absolutely-required.

For example, we could assign the absolutely-required priority to code compilation. You could assign the tests as an absolutely-required step, depending on how long they usually take to run. During an emergency situation, if you try to merge while an absolutely-required step is running, you'll have to click through perhaps a few confirmation dialogues. This is to prevent you from making bad decisions when you're stressed.

If the code doesn't compile, you could be extending your downtime by having to re-run the entire pipeline. This way, you can know immediately when it's safe to merge.

The day-to-day development will be unaffected; developers will still be required to do the linting and other tasks. The optional tasks can still be optional.

Another benefit with using this approach is that you can log when you've used it. This is so that, when the dust settles and the emergency is over, you can go back and find what code needs to go through the extra stages like linting and spell checking. Everything could be automatically flagged and so it'd be easy to spot.
