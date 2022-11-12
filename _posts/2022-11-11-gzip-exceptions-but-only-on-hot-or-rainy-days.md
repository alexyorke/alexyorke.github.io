---
title: "GZIP exceptions, but only on hot or rainy days"
date: 2022-11-11
---

Want to get notified when part two (extended version) releases? Sign up to the mailing list here: http://eepurl.com/idzoGv

It was a hot summer day inside my apartment. At least not for long. I just got an air conditioner from my landlord and it was time to fire it up.

*A few weeks later*

I was in the middle of writing a program to decompress some gzip files in C# and I got a strange exception that indicated that the archive was corrupted:
```
Unhandled exception. System.IO.InvalidDataException: The archive entry was compressed using an unsupported compression method.

System.IO.Compression.Inflater.Inflate(FlushCode flushCode)
     at System.IO.Compression.Inflater.ReadInflateOutput(Byte* bufPtr, Int32 length, FlushCode flushCode, Int32& bytesRead)
     at System.IO.Compression.Inflater.ReadOutput(Byte* bufPtr, Int32 length, Int32& bytesRead)
     at System.IO.Compression.Inflater.InflateVerified(Byte* bufPtr, Int32 length)
     at System.IO.Compression.DeflateStream.ReadCore(Span`1 buffer)
     at System.IO.Compression.DeflateStream.Read(Byte[] array, Int32 offset, Int32 count)
     at System.IO.StreamReader.ReadBuffer()
     at System.IO.StreamReader.ReadLine()
     at MyApp.Program.ReadAllZippedLines(String filename)+MoveNext()
     at System.Linq.Enumerable.EnumerablePartition`1.MoveNext()
     at MyApp.Program.Main(String[] args)
     at MyApp.Program.<Main>(String[] args)
```

This was very strange, because the files were not normally corrupted. This was very concerning because I would have lost a lot of data if that were the case. Out of irrationality, I re-ran the program, and it worked? Weird, I thought. Maybe Windows had the file open with an anti-virus scanner for a second and I caught it at a bad time.

But nevertheless, the error returned again a few minutes later. I decided to turn off Windows Defender, rebooted my laptop, and tried again. No luck. The strange thing was the error was not predictable, sometimes it would work, other times not.

When I re-ran it again, Visual Studio waited on the line (due to an exception handler.) I was able to inspect the code at that point (located in `C:\Program Files\dotnet\shared\Microsoft.NETCore.App\3.1.16\System.IO.Compression.dll`):

```
internal int ReadCore(Span <byte> buffer) {

  this.EnsureDecompressionMode();

  this.EnsureNotDisposed();

  this.EnsureBufferInitialized();

  int start = 0;

  while (true) {

    do {

      int num = this._inflater.Inflate(buffer.Slice(start));

      start += num;

      if (start == buffer.Length || this._inflater.Finished() && (!this._inflater.IsGzipStream() || !this._inflater.NeedsInput()))

        goto label_7;

    }

    while (!this._inflater.NeedsInput());

    int count = this._stream.Read(this._buffer, 0, this._buffer.Length);

    if (count > 0) {

      if (count <= this._buffer.Length) < this conditional was false

      this._inflater.SetInput(this._buffer, 0, count);

      else

        break;

    } else

      goto label_7;

  }

  throw new InvalidDataException(SR.GenericInvalidData);

  label_7:

    return start;

}
```


This was strange, why was the buffer length greater than the count, but only sometimes? This would indicate that the buffer’s length or the count variable were being updated to an incorrect value. The file is the same and hasn't changed (according to its SHA1 hash.) Except, I couldn’t get the hash the second time due to a strange internal exception error in the plugin for File Explorer I was using.

Could I have discovered a race condition? It didn’t look like the gzip decompressor was multi-threaded. I continued to dig deeper down the callstack,

```
private ZLibNative.ErrorCode Inflate(ZLibNative.FlushCode flushCode) {

  ZLibNative.ErrorCode errorCode;

  try {

    errorCode = this._zlibStream.Inflate(flushCode);

  } catch (Exception ex) {

    throw new ZLibException(SR.ZLibErrorDLLLoadError, ex);

  }

  switch (errorCode) {

  case ZLibNative.ErrorCode.BufError:

    return errorCode;

  case ZLibNative.ErrorCode.MemError:

    throw new ZLibException(SR.ZLibErrorNotEnoughMemory, "inflate_", (int) errorCode, this._zlibStream.GetErrorMessage());

  case ZLibNative.ErrorCode.DataError:

    throw new InvalidDataException(SR.UnsupportedCompression);

  case ZLibNative.ErrorCode.StreamError:

    throw new ZLibException(SR.ZLibErrorInconsistentStream, "inflate_", (int) errorCode, this._zlibStream.GetErrorMessage());

  case ZLibNative.ErrorCode.Ok:

  case ZLibNative.ErrorCode.StreamEnd:

    return errorCode;

  default:

    throw new ZLibException(SR.ZLibErrorUnexpected, "inflate_", (int) errorCode, this._zlibStream.GetErrorMessage());

  }

}
```

It was returning a DataError or a StreamError, sometimes. This meant that there was something wrong with the data or the stream (yes, a bit obvious.)

To rule out if it was a coding error, I tried to decompress the gzip file with bash via gzip -dc file. bash threw a strange error, [“can’t seek file descriptor”](https://stackoverflow.com/questions/3838322/bash-read-write-file-descriptors-seek-to-start-of-file) when trying to read the file. This error is emitted from [bash.c here](https://github.com/bminor/bash/blob/f3a35a2d601a55f337f8ca02a541f8c033682247/input.c). I also tried decompressing several other gzip files, but they were unable to be decompressed.

At this point, I strongly suspected data corruption. I quickly checked CrystalDiskInfo for any reallocated sectors but could not find any. I then ran sfc.exe /SCANNOW, and I believe it did find errors and corrected them. I ran it again, and again, and again, and it kept fixing errors. At some point (maybe five times) it didn’t report any more errors.

Over the next few weeks, I began to have very strange issues with my laptop. Apps would take forever to load (and sometimes not at all), icons would be missing, and text would appear garbled. I figured my laptop was failing at this point. But one mystery remained: there was no incidents of strange behavior when on battery power. Only when plugged in. And why was my monitor, that I recently purchased, also having issues?
### Time to go deeper
What caught my attention was that the wrist-rest was very uncomfortable. It was an aging 2012 MacBook Pro, running Boot Camp, but there was no signs of wear on the aluminum. Again, the same pattern came up: the wrist-rest was only uncomfortable when running on AC power.

*Aside: at this point, I had to repair Visual Studio about two or three times due to strange ungoogle-able errors.*

It all clicked when I got a very bad shock when I touched my laptop’s frame: could it be an electrical issue?

### Electricity going where it shouldn’t
Let’s recap on what I found out so far:

\- There was a strange green and red noise on my brand new monitor.

\- There was a strange green and red noise on my old monitor.

\- The trackpad was spicy.

\- There (appeared to be) data corruption.

\- I got shocked by my laptop.

\- Sometimes my apartment lights turned on a little bit by themselves too after I turned them off.

It seems strange that, just out of coincidence, my old and new monitor both exhibited the exact same issue. I also upgraded my laptop’s battery earlier in the year, so perhaps I could have made a mistake?

What could cause things that shouldn’t conduct electricity to conduct it? There could be many issues:

\- A bad device that’s wired incorrectly.

\- Grounding issues.

\- Potentially more issues.

To rule out if it’s caused by another device, as everything was connected using a power strip, I unplugged everything and plugged my laptop directly into a GFCI outlet in the bathroom and turned on all devices and ran prime95 for about 15 minutes. It seemed to be ok. I then plugged everything else in and didn’t have any issues.

And then the issues came back. But only sometimes, or so I thought. The issues were correlated with if it was raining outside or if it was humid. Could it be too much humidity causing a short-circuit?

Apple says [“You should also use your Mac notebook where the relative humidity is between 0% and 95% (noncondensing)”](https://support.apple.com/en-us/HT201640#:~:text=You%20should%20also%20use%20your,and%2095%25%20\(noncondensing\).) and the ambient temperature was in-spec. Just to make sure, I turned on my air conditioning at full blast to lower the temperature and humidity. But that just made things worse.

Could it be that the air was too dry? I tried to increase the air conditioner’s temperature but that didn’t help.

But what I did notice was that the issues correlated with having the air conditioner on, which was correlated with humid conditions (because it was hot, so I turned on the AC.)

At this point I suspected an electrical issue. I contacted my landlord to send out an electrician. A service personnel came out and suggested I get an AVR UPS (auto-voltage regulator.)

These are fancy UPSes that automatically adjust the voltage to a desired level if it dips below a threshold (in my case, 120V.) This was because I noticed that the lights browned out sometimes, and he suspected my technical issues might be because of the voltage dips causing issues.

So, I got one. And I was pretty happy, because it was beeping a lot (which meant it was detecting issues and fixing them.)

It was beeping too much, actually. Beeping during calls, beeping during lunch, beeping during trying to sleep. It just kind of snuck up on me, drinking a glass of water and then…*beeeep!* Thankfully, I was just drinking water.

I decided to silence the beeps as they were getting distracting and waking me up in the night. I checked the stats and it fixed at least 20 power incidents in only a few days. Wow, it’s working pretty hard I thought.

Unfortunately, after a few more days, the issues reappeared.
### Grounding
The next order of business was to check if there was a grounding issue, according to my research. The “ground” is a path to earth to direct excess or unwanted electrical energy safely away. If there is an issue with the ground, then the unwanted electricity might not be dissipating (I probably butchered this term, I’m not an electrician, but if you have any suggestions on how to improve this let me know.)

A quick check with a $10.00 outlet tester confirmed that there was a grounding issue. The tester confirmed that there was no ground.

*Aside: At this point, my laptop was bordering on unusable, even on battery power. Random shutdowns and the screen would turn black. Many events appeared in the Event Log, related to APIC power issues. I bought a new laptop in the meantime.*

Armed with my new knowledge, I asked my landlord to send in an electrician this time. They asked lots of questions, and then recommended that my air conditioner stay on a different outlet because there were two circuits. I tried this for a few days, but the issues still reappeared.

I asked them to come again, and this time they installed a completely new outlet and the outlet was *correctly* grounded using my water heater as ground, according to my outlet tester.

At last, although one laptop was down, there were no more issues. No issues with strange colors on my monitor, no spicy trackpad, and no shocks.

Sometimes, debugging enters the real world.
