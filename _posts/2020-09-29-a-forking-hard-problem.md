---
title: "Caveats when measuring pipeline optimizations"
date: 2020-09-29
---

One day I couldn’t log into my linux VPS. When I tried to log in I got an error message saying that the shell could not be created. Hmm, strange. I was able to log into Digital Ocean’s management page and didn’t see any issues; the CPU was at 1%, the memory at 70%, and the disk and network activity were about 2%. Disk space was pretty high with a few GBs available.

I logged into the recovery console and immediately started seeing messages like:

bash: could not fork process

Oh, it looks like there’s a process that got out of control and started making a bunch of other processes. So I tried to see what process it was by running htop, but I got the same error “bash; could not fork process” and so couldn’t run it. After googling for a bit, someone suggested prefixing the command with exec, which replaces the running shell with the command (so that I don’t use up another process slot.) After running exec htop, htop reported normal values too; the CPU was low, memory was ok, and there were a lot of processes running (about 80) but that’s not too unusual. I decided to quit the 10 copies of a program that I had running (which I believed to be the cause of the slowdown) but I couldn’t, as exec killall <program name> didn’t do anything that I could see as running it with exec immediately drops me back to the login screen and I can’t see the output. I tried to pgrep it but was unsuccessful in killing the process. I decided to do a graceful reboot via exec /sbin/shutdown -r now as I was out of options.

The server took a while to restart but came up normally. I was able to log into ssh again. I waited a few hours to see if the server was going to hang again and it didn’t, so I was thinking it had to do with the program that I was running.

So, I tried running 10 copies of the program again. It seemed to be ok for a few minutes so I let it go for a few hours. A few hours later I had the same issue: I couldn’t fork any processes. Thankfully I left myself logged into ssh so I still had some opportunity to debug.

I ran htop and saw no issues: cpu was very low, swap was not used very much, memory was a little high, but I still couldn’t fork any other processes. Since I wasn’t able to open up vnstat but was able to load htop, I suspected it had to do with TCP connections because vnstat is a network monitor and if it couldn’t open up a connection then there must not be any connections left.

Ok, it has to do with my application. I suspected some sort of resource leak in terms of TCP connections, since it makes a lot of them. I found a few instances of where I wasn’t releasing the resources (forgot to use the “using” statement) on some IDisposable classes, recompiled and a few hours later, same error.

I did some math and figured that my app used about 1632 TCP connections maximum. That doesn’t sound like a lot given that there are 65535 ports per application process space, so I should be under that. I did some research and found out that the kernel holds open the sockets for two minutes after they are closed, so I began to think that it was generating so many connections that it was holding a lot of closed ones open for a very long time. I went back through the program again to see if I forgot any using statements and I couldn’t find any; since the TCP connections are closed by my app it should be ok, as the limit is for TCP connections that are open, and my app closes them, I hoped.

However, if I had a lot of TCP connections opened why did my bandwidth completely stop for many hours given that the old sockets time out after a few minutes? Also, the main loop in my app will restart itself if it encounters an exception, and given that insufficient ports will throw an exception I wasn’t sure why it was not throwing an exception. I decided to test this by running my app in Visual Studio’s .NET object allocator to see if I could spot a large influx of objects that were being generated and not being released (i.e. TCP connections.)

No dice. Nothing out of the ordinary. It used up a lot of “objects” but nothing that could explain an excessive amount.

I decided to run just one copy of my app to see if it was just one app going out of control, or if it was the ensemble together that was causing issues. I ran one for a while on my local PC and didn’t see any large resource consumption issues (I should have run it on the linux box, however.) I concluded that it had to do with running them together. Given that they were only reading from 10 files total and writing to 10 files (giving 20 file handles total) I didn’t think that would exceed any file system limits; 20 files seems to be pretty small. I uninstalled clamav (an anti-virus scanner for linux) as that opens up a lot of files but that didn’t seem to change anything. I checked with ulimit and got 8192 file handles possible, so I had to try something else.

Then I remembered that my app makes a lot of threads; about 1632 to be exact, multiplied by a few because each WebClient might take up some internally. If I’m running 10 copies, I’m running at least 16320 threads. That’s a lot of threads. Each thread takes up a bit of memory, but because I wasn’t out of memory that seemed strange. If it were due to context-switching I’d expect it to be super slow but that wouldn’t explain why fork wouldn’t allow new processes to be created.

I went back to htop and saw that I had about 54 threads running idle. So, 54 + 16320 = 16374, and coincidentally log2(16374) = 13.99911918 (almost 14), and so 16384 - 16374 = 10 “left”, which is interesting. It is almost a power of two which prompted another investigation: given that there are a few process limits that are in powers of two, could this be a ulimit setting? Can the total number of threads be restricted?

It turns out that the number of threads was set much lower after running a program from stackoverflow which shows the number of threads that can be instantiated before encountering that exception. I decided to increase it to 20000, but then only got to about 3800 threads. I then found another setting, pending signals and max user processes, which were set to 3859 which was suspiciously close to the 3800 threads, minus the number of threads I already had running at idle.

After increasing it, rebooting, and checking again via ulimit it didn’t show my changes. Strange. However, I remembered that a soft limit was set to the previous limit, so I changed that via ulimit -sU 20000.

Unfortunately, that didn’t work and I still got the same error. I’ll update this post with more information as I go along.
