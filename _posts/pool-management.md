---
title: "Simple pool management algorithm"
date: 2020-09-08
---

In programming, there are some situations where an application needs a resource or a handle, and it doesn’t matter what type it is, as long as it is valid and not in use. Examples of where pools are used are in threads (thread pools), database connection pools, connection pools, and more. Connection pools remove the dependency of the application from the connections; it doesn’t care what connection it gets, as long as it works.

Consider the case where there is a pool of connections but with a few restrictions: if a connection is used too much it needs to cooldown for a while, and we don’t know how much is too much before it needs to be cooled down. Sometimes the connections can’t be used at all and need to cooldown. Our application is a multithreaded application, and it withdraws connections randomly from the connection pool. The connections shouldn’t be “overheated” in that if a bunch of threads use a connection (e.g. when the pool is initially small) it could burn it out whereas using it over a period would have made it last for longer. How can this be implemented without a lot of logic?

First, assign each connection a unique id. This id never changes and will be used to identify each connection. Next, put all of them into a pool called “to test”; this pool could have invalid, valid, or partially working connections; we want all of them. The ordering of this doesn’t matter; in C# this could be a ConcurrentBag for example. Create another initially empty pool called the valid pool which holds the connections which are currently active. The ordering doesn’t matter, as long as a random item can be selected from it and, preferably, no duplicates can be added.

Next, withdraw n connections at a time from this pool and check them. If the connection is valid, add it to the valid pool if it doesn’t exist there. Otherwise, delete it from the valid pool if it doesn’t exist.

The application should withdraw a random connection from the connection pool, blocking if the pool is less than r connections (to prevent burning out a small pool.) This could be achieved with a facade to stop accessing the pool directly.

When there aren’t any more connections to check, wait for a bit, and start from the beginning.

## A more complicated example

This works, however if a connection is permanently dead, or dead for a long time, it will continually check the dead connections. This might not be a problem if there aren’t a lot of dead connections, or connections that are in cooldown, but it will slow down the connection checking. Also, if there are a lot of connections to check, the connection might be severely burned out before the connection checker finds out.

Let’s assume that if a connection is beginning to get worn out it has a slower response time. Then, each connection could have a list of s values which contain the response times. When the thread is done with the connection, it appends the latency to the end of the circular buffer of response times. The connection pool would now be a connection list ordered by the average of the list, so in effect this is a moving average of response times. The connections that are getting slower and slower over time pushes the connection further and further back so that it is chosen less often, and then when it is chosen, the moving average will slowly move it back into the forefront. If the connection either works or doesn’t, then the values 0 (works) and 1 (does not work) can be used instead of latency metrics; the score of pure ones will move it back in the queue and zeros will move it forward.

The issue (or potentially desirable) effect is that the durable connections that can withstand a lot of load will be used a lot, maybe exponentially more than the other connections and the other ones will be used exponentially less. Since the ones at the beginning are proven to work it uses those and doesn’t bother trying to use something that might not work; it takes a very risk-averse approach.
