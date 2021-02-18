**This post is a draft. There might be significant edits.**

In this post, I set out to do some data analysis with tight real-world and financial constraints. No BigQuery, no Amazon EC2, and no easy solutions allowed. My budget is \$2.50 CAD. Can I do it? Well, let's find out.

I wanted to do some fuzzing for a parser that I was making, but I couldn't find enough sample files as the files are hard to find. I tried googling (and got about 70 or so), and did a few GitHub searches which got me a 1000 more, but a lot were duplicates.

The parser can't be fuzzed traditionally using an automatic generator\--I didn't know what to generate. I needed real-world examples of the files so that I knew what features of the language that had to be prioritized to support, and some potentially non-standard things that some people might do that aren\'t immediately clear in the docs.

GitHub has a lot of repositories, and a lot of potential sample files even though the search doesn't give all the results. GHArchive, a website that stores links to all the files on GitHub, is about 1.1TB compressed, about 7TB uncompressed. It doesn't store the content or the filenames, but stores metadata that can provide clues about what file(s) are contained in that link (and so can download those directly.)

This is a classic ML problem: we have an input X which maps to Y, but we want to find a function that approximates f(X) = Y. To make this more concrete, say I want a bunch of gradle files. I have a list of metadata `{X1, X2, X3, ..., Xn}` which maps to `{Y1, Y2, Y3, ..., Yn}` but not all of Y are gradle files. We need to find given an X how likely it is to map to a valid Y. This is important for a few reasons: if we make f(X) too restrictive, then we won't get enough sample files and similarly if we make it too permissive we will run out of our 5000 hourly request API key limit to resolve the files (and find out that they aren't the ones that we are looking for) and it will take forever to find our files.

The goal is to be able to type in a search query and get back the files (a lot more than the regular search can produce) that match it. It would be self-reinforcing, as it would download the search results (1000 results) to train itself on what files match the criteria that the user enters. As a bit of a spoiler, using a super naïve method (searching the commit messages for a keyword), I got a terrible 0.2% match rate (5000 queries/hour \* 0.2% = 10 successful files per hour), so this is our lower bound; anything above this is considered "more" successful.

The ML process will take in a truncated version of the commit message plus two integers that correspond to the number of files and the file sizes. My hypothesis is that this information will be a bit better than the naïve search, but not by much.

Oh, and our budget is \$2.50 CAD, 1TB of bandwidth, 1GB of ram, and 13.5GB of storage.

I do not intend this post to be a guide to accomplish this task as fast as possible. I could have done it on BigQuery and had it 90% done in about 20 seconds for about \~\$250 CAD. It's meant to push bash to the extreme to see how much ML pre-processing is possible on a very tight budget with a lot of planning.

Is this viable?

Let's download a file from GHArchive and see.

`zcat 2018-01-01-0.json.gz \| jq -c \'\[.payload.commits\[0\].message, .payload.commits\[0\].sha\]\' \| grep -vF \"null,null\" \| grep gradle`

To estimate the amount of content that we have to download:
```
for Y in {2011..2020}; do
for M in {01..12}; do
for D in {01..31}; do
for H in {0..23}; do
echo -n \"\$Y-\$M-\$D \$H \"; curl \"https://data.gharchive.org/\$Y-\$M-\$D-\$H.json.gz\" \--location \--silent \--write-out \'%{size_download} %{http_code}\\n\' \--output /dev/null;
done;
done;
done;
done;
```
To run, save it in a file called estimate_download.sh. Then, run bash estimate_download.sh. Unfortunately, this takes a while:

`time bash estimate_download.sh`

(output)\...

real: 6.269s

...

Ouch. Since there are data from 2011 through until 2020.5ish, then (2020.5-2011) \* 365 \* 24 = 83220 items to download, so if it takes 6.269s to download 24 items, then it will take 6.269s/24 = 0.26120s per item, and there are 83220 items so 83220 \* 0.26120 = 21737s or about 6 hours. This could be parallelized, but since we just need an estimate we don't need to download all the files.

How many files do we need to download to get a good estimate? What is a good estimate? Well, since we are constrained by time (i.e. we only have 360 hours left), we should leave a lot of time to the actual data process itself, but we also don't want to undershoot it and have to do a lot of costly last-minute fixes. Fortunately, there are some statistics that we can use to help us figure this out.

Using a margin of error calculator with a confidence interval of 95%, we get a 10% sampling error for a sample size of 100 and population size of 83220. Whatever mean we calculate, there is a 95% chance it will be off by +-10%, and a 5% chance it will be off by more than that amount in either direction. The 95% figure is an industry standard. Since we will be sampling 100 times, then it will take 0.26120 \* 100 = 26.12s to calculate an approximate mean.

The number of times that we sample to get a smaller confidence interval depends on how close we get to our bandwidth cap of 1TB.
```
touch archive_sizes.tsv;
(for Y in {2011..2020}; do
    for M in {01..12}; do
        for D in {01..31}; do
            for H in {0..23}; do
                echo "https://data.gharchive.org/$Y-$M-$D-$H.json.gz";
            done;
        done;
    done;
done) \
| grep -Fvxf <(awk '{print $1}' archive_sizes.tsv) \
| shuf \
| (while read -r line; do \
   curl "$line" --location --silent --write-out '%{url_effective}    %{size_download}    %{http_code}\n' --output /dev/null \
   | awk '{ if ($3 == 200) { print } }' \
   | cat || exit; done) \
| head -n $1 >> archive_sizes.tsv;
 
awk '{ sum += $2 } END { if (NR > 0) print "Average MB/file: "((sum / NR) / 1024) / 1024 }' archive_sizes.tsv;

```
This gives us the following results in archive_sizes.tsv:

(add stuff here)

This script that I quickly whipped up grabs a random selection of files and gets their size (it does not download the files; just the HTTP headers that indicate how large the file is), ignores the 404 ones (because not all months have 31 days), and saves it to a file. When the script is re-run, it emulates sampling without replacement by not redownloading the sizes which have already been downloaded previously. You can run it by saving it in a file called estimator.sh, then running bash estimator.sh 100 to get a sampling of 100 files.

A bit of a side-note. Some of the files are empty (not sure why), even after redownloading. So, a size of an empty gzip file can be found via:

`echo | gzip -1 | wc -c`

Which gives the byte count of 21. So, any files less than or equal to this value are empty. We could generously round this up to 1024 (i.e. a KB) because the gzip file might contain other metadata which inflates the file size even if it is empty. Plus, any files smaller than 1KB probably don't have many events anyway.

Running estimator.sh 100 twice, we get an average MB/file of 14.1637 for 200 samples. Recall that we have about 83220 items to download (assuming no 404's), so 14.1637MB/file \* 83220 files = 1.124TB+-6.92% for a 95% confidence interval. If we are unlucky and we are at the edge of the 95% percentile, then we will have to download 1.202TB. Our bandwidth is 1TB, so we might go over 202GB. Since it costs \$0.0093132/GB to go over, then 202GB \* \$0.0093132/GB = \$1.88 in overages. On average, it will be about 124 \* \$0.0093132 = \$1.15 in overages. If we wanted to, we could keep increasing the sample size to get a more accurate estimate into how much overages we will have, but for now this is ok.

Alright, so now we have an estimate of how much data that we have to download. However, we can't afford storing \~1TB of data on-disk, so we have to stream it. Since it is gzipped, it has to be decompressed and we can't exceed the amount of memory in our VPS (1GB of RAM.) Additionally, our droplet only has 1 vCPU, so if a connection is open for too long then the server might prematurely close our connection and cause issues with our script.

Let's download 100 random sample files, which will take up about 14.1637 \* 100 = 1.38GB of bandwidth. Since we have to download them anyway, this is ok.

We can use the output from the estimator script to grab a selection of files:

`mkdir sample_files; head -n 100 archive_sizes.tsv | awk '{print $1}' | wget -P sample_files -i -`

Which will download the first 100 files from archive_sizes.tsv into a folder called "sample_files". Note: change 100 to your desired sample size.

Before we decompress the files, we should figure out what we want first so that we don't have to decompress the files multiple times. We would like to find the compression ratio, the amount of PushEvents in bytes, and peek at a few lines in one of the files to see what we want.

We need to find the compression ratio. Run du -s . in the sample_files directory to get the total size for all of the files in bytes. Then, run zcat \* \| wc -c to get the total bytes of the decompressed files. I got 1.456GB and 11.623GB respectively, so a ratio of \~1:8. Upon inspection of a few files, they appear to be compressed using gzip -9, which is important as you will see why later on.

Fortunately, we only care about PushEvents, so this means that we can discard some of the data. To see how much of the files are PushEvents, run:

`zcat * | grep -F "\"type\":\"PushEvent\"" | wc -c`

(While it is better to parse JSON properly, this approximation is very fast as it is unlikely that this exact text is in a PR commit message.) This gives 2.4356GB, which means that we only need \~21% of each file. Since each file is \~14.1637MB, then 14.1637MB \* 8 \* 0.21 = \~23.8MB/file needed to store in RAM. There is some overhead for storing strings in memory, but this is a good start.

In order to prepare the database, we will have to write *something* to disk at some point. Our droplet has 25GB of storage, but 10GB are for the operating system. So, we have 15GB left, minus the 1GB we used to download sample files so more like 14GB. We shouldn't squeeze the OS right up to 0 bytes remaining, so we should allow 500MB for temp storage. So we have about 13.5GB to actually write to.

What do we need to make the database? Well, we need to see what is inside of a PushEvent.

`{"id":"3588679312","type":"PushEvent","actor":{"id":9129006,"login":"goldenbull","gravatar_id":"","url":"https://api.github.com/users/goldenbull","avatar_url":"https://avatars.githubusercontent.com/u/9129006?"},"repo":{"id":50581553,"name":"goldenbull/ManagedXZ","url":"https://api.github.com/repos/goldenbull/ManagedXZ"},"payload":{"push_id":957216132,"size":1,"distinct_size":1,"ref":"refs/heads/master","head":"04861c96a3fa1402a7f36ae298dfdc804c0a9650","before":"b73f992f626c429ab921c26ce38202489d871dd0","commits":[{"sha":"04861c96a3fa1402a7f36ae298dfdc804c0a9650","author":{"email":"566643c3c2e54f8db1c3c28a443e0cafab329ef8@gmail.com","name":"goldenbull"},"message":"change icon setting for nuget","distinct":true,"url":"https://api.github.com/repos/goldenbull/ManagedXZ/commits/04861c96a3fa1402a7f36ae298dfdc804c0a9650"}]},"public":true,"created_at":"2016-01-31T06:00:00Z"}`

A PushEvent is a package of one or more commits. A PushEvent contains several fields, but the fields that interest us are the commit URLs, the commit messages (for each URL), the number of files in the push and the size in bytes of the push.

To make it easier for ML, it has to be unwrapped into individual rows. Each commit message, URL, \# files and \# bytes needs to be on a row. If we were just to extract the PushEvents, parse them (generously assuming we can remove 50% of the data), and save them then it would take about (23.8/2) = 11.9MB per file, and there are 83220 items so \~967GB. Ut oh. Assuming a generous 1:8 compression ratio, we get 120GB compressed. That's a lot more than the 13.5GB that we have to work with. Using the xz compressor with the -9e option (highest compression available), it gives a 1:16 ratio which gives us 60GB, but it takes forever to compress and it's still too large.

We need "goldenbull/ManagedXZ", "04861c96a3fa1402a7f36ae298dfdc804c0a9650", \"change icon setting for nuget\", size, and distinct_size (two relatively small integers.) The username and repo will have a lot of redundancy, so we will let the compression algorithm take care of the repetition for us. How can we estimate how much information we have to store?

First, we can estimate the average length of the repo + username, the commit message length, the range for the size and distinct_size, and since the hashes are all the same size we don't need to estimate the length, but we need to know how many there are.

(provide estimates for all fields)

`zcat 2015* 2016* 2017* 2018* | grep -F "\"type\":\"PushEvent\"" | jq '.payload.commits[].sha' | wc -l`

This gives us 1247955 for 37 files, so \~33728 hashes/file. If each hash is 160 bits, then it will take up \~675KB/file, or 83220 files \* 675KB = 53.57GB just to store the hashes uncompressed.

Fortunately, we don't have to store the entire hash. GitHub's API is nice enough to still return a response if the hash is truncated, provided that the hash prefix that we send is unique to that repo, otherwise we get a 404.

To find the upper bound of the hash length, we can calculate the probability of a collision given a hash size.

![](media/image2.png){width="1.609375546806649in" height="0.6753062117235346in"}

([[https://preshing.com/20110504/hash-collision-probabilities/]{.ul}](https://preshing.com/20110504/hash-collision-probabilities/)) http://davidjohnstone.net/pages/hash-collision-probability

Plugging in N = 2\^160 and k = (\~33728 hashes/file \* 83220 files) = 2806844160 we get 2.695301×10^-30^ probability of a collision, or E(X) = \~0. If we have a collision, it's not the end of the world in our case as that just means that the file is unavailable. If we truncate the hash to 80 bits, then we get a 3.258414×10^-6^ probability of a collision, or E(X) = 9145 collisions globally, or 0.0003% of our data. This is the worst-case scenario because since each repo has their own hash group, having two hashes that are the same globally isn't necessarily a problem as long as they belong to separate repos.

Some repos have a lot of commits, others not so much. We can approximate this by finding how many repos there are, and then split the hashes for each one and re-calculate the probabilities. It's not a great approximation but it gets us closer.

`zcat 2011\* 2012\* 2013\* 2014\* \| jq -r \'.repo.name\' \>\> hashes.txt;`

`zcat 2015\* 2016\* 2017\* 2018\* \| grep -F \"\\\"type\\\":\\\"PushEvent\\\"\" \| jq -r \'.payload.commits\[0\].url\' \| cut -d \"/\" -f 5-6 \>\> hashes.txt;`

`sort -u hashes.txt \| wc -l;`

This command gives us 361453 for 37 files, so 9769 repos/file or 83220 \* 9769\... hold on a sec\... equals 812976180 repos in total. No no no. This calculation may have to be checked.

Since we are sampling from a stream that contains duplicates (412812 to be exact), then the increase in repos is not linear or exponential; it mimics a logarithmic distribution a bit more. Let's see how.

Find the number of unique items in a sliding window. We want 100 windows, and the file is 1142058 lines long so we need to sample with a sample size of 1142058/100 = 11420 items. We can do so in a loop:
```
size=0;
while [[ $size < [1142058] ]]; do
head -n $size hashes.txt | sort -u | wc -l;
((size+=11420));
done > hash_calc.txt;
```
This is pretty inefficient (something like O(n\^2)) but it works okish. Let's plot the result of hash_calc.txt:

(results)

The line of best fit gives us -399 + 2.01x + (4.57\*10\^-7) x\^2 = 1741468467, which means that x is about... 60 million. Not the greatest of estimates. We forgot about 2011 through 2014, which seems that this would reduce the estimate by about half, so therefore we get about 30 million, which is close to our 28 million result from Google.

![Chart](media/image1.png){width="6.5in" height="3.8333333333333335in"}

This isn't a great approximation because the number of repos are likely to repeat, increasing logarithmically and not linearly, thus it might be better to go to Google to get a more accurate figure. Google says there are at least 28 million public repos, so we were off by quite a bit here. Let's use 28 million instead.

It's impossible to store all of the data in its current form, even with the highest compression options available. We will need to do lossy compression. Let's remove all of the other events that we don't need, compress it, and see how much space it takes up:

`for i in \*.gz; do LC_ALL=C zgrep -F \"\\\"type\\\":\\\"PushEvent\\\"\" \"\$i\" \| jq -c \'\[\[.payload.commits\[\].message, .payload.size, .payload.distinct_size\], .payload.commits\[\].url\]\' \>\> out.txt; done;`

This gives us lines that look like:

\[\[\"Can be run from outside of bin. Fixed multi-line issue\",1,1\],\"[[https://api.github.com/repos/jmoon018/rshell-unit-tester/commits/56688cc528224d40679b7e83c105b27367443a8c]{.ul}](https://api.github.com/repos/jmoon018/rshell-unit-tester/commits/56688cc528224d40679b7e83c105b27367443a8c)\"\]

(pretend that we downloaded all of the files to a pseudo-directory), then this gives us an uncompressed 20GB file which represents 73GB of downloaded compressed data. The compression ratio for out.txt can be approximated by taking the first 100mb and compressing it:

`head -c 100000000 out.txt \| gzip - \| wc -c`

Which gives us 34589853 bytes, or \~35MB, which is a 2.86x compression rate, which would give us a \~7GB file for the year 2015. This won't fit in our 13.5GB as we still have to deal with 2011, 2012, ..., and 2020. Can we do better?

Well, we could get rid of the "[[https://api.github.com/repos/]{.ul}](https://api.github.com/repos/jmoon018/rshell-unit-tester/commits/56688cc528224d40679b7e83c105b27367443a8c)" text, remove the word "/commits/" (since we know from the length of the hash where the username starts), which would save 38 bytes per line. We have XYZ lines in that file, so 38 bytes per line is 38 \* XYZ =

So, 28 million repos and 2806844160 hashes, so there are 2806844160/28000000 = \~100 hashes/repo. Our sample space has increased by about 100 times because each hash has a repo prefix. Therefore, we can represent this by decreasing the amount of hashes by 100 times, because each repo has 100 so it effectively has a prefix. So, 2806844160/100 = 28068441, which means that a rate of collision for an 80 bit hash (50% of the size) is 3.258418×10^-10^, so E(X) = \~1 hashes. Not too bad.

What about 60 bits? This gives a collision probability of 3.416116×10^-4^, so E(X) = 958850 collisions, or 0.03% of our hashes will collide. How low do we go? If we went to one extreme and just stored 1bit per hash, then there is a 99.999\...99% collision for a single repo, as unless they have a handful of commits, each one will probably collide. We wouldn't be able to get much data. Similarly, if we stored it too long, then we are wasting space.

Switching to a 60bit hash gives us 2.66x savings in data, so we only need about 20GB to store the hashes. That's getting closer to our 13.5GB that we have, plus don't forget we have to store the commit messages, usernames and repos, and a couple integers. How much commit text do we have?

`zcat 2015\* 2016\* 2017\* 2018\* 2019\* 2020\* \| jq \'.payload.commits\[\].message\' 2\> /dev/null \| wc -c`

`zcat 2015\* 2016\* 2017\* 2018\* 2019\* 2020\* \| jq \'.payload.commits\[\].message\' 2\> /dev/null \| gzip -9 \| wc -c`

This gives us 182014216 uncompressed bytes, and 61707559 compressed using gzip -9, a ratio of about 1:3 compression. So, (61707559/37) \* 83220 = 138GB compressed + 20GB = 158GB.

Would lowercasing the text and removing quotes help?

`zcat 2015\* 2016\* 2017\* 2018\* 2019\* 2020\* \| jq -r \'.payload.commits\[\].message\' 2\> /dev/null \| tr \'\[:upper:\]\' \'\[:lower:\]\' \| gzip -9 \| wc -c`

This gives us 57691173 bytes, which is 3.15x compression which is just 0.15x more than our previous run. Not terribly efficient.

Hmm, that doesn't help a lot. Let's graph the size and frequency of each commit message to see if there are a few long ones that are taking up most of the space:

`while read line; do echo \"\$line\" \| wc -c; done \< \<(zcat 2015\* 2016\* 2017\* 2018\* 2019\* 2020\* \| jq -r \'.payload.commits\[\].message\' 2\> /dev/null) \> histo.txt`

Feel free to stop it when you get around a few thousand points. It'll take forever otherwise as it is starting a new jq process for every line.

The histogram looks like this:

(add histogram)

How long can the commit messages be compressed so that they fit in under 10GB? Well, there are 2806844160 hashes so there are 2806844160 commits for each hash. Therefore,

((x \* 2806844160) / 3) / 1024 / 1024 / 1024 = 10 so x = 11.476 bytes, or 11 bytes. That would give us a string of "abcdefghijk", or 11 characters. A bit short. Can we do better?

If we only allow a-z (and spaces and maybe punctuation), then it would be 27 characters, or 5 bits/character, so 0.625 bytes/character. Using this, we can store 1.6x as much info, so 11.476 \* 1.6 = 18 characters. A bit better. The 50th percentile is 29 bytes (characters-ish), the 30th percentile is 15, so this could squeeze in some of them without truncation.

At this point you might say why didn't you just run ML on the small sample to determine the viability? Well, I need the finalized data either way, so I figured that I might as well try to salvage as much as I can.

We can PCA-esque the commit messages by removing the most common words which will save on space and pre-process the data a bit more. For those unfamiliar with how PCA works, it is removing dimensions from the data which are ineffective predictors from the final result. In this case, if a word occurs in a lot of commit messages, chances are it isn't "doing" anything; it is not adding to the variance.

I am becoming increasingly worried that this isn't enough info for our ML pipeline to make an accurate guess on. So, we could add commit dates per repo to find repos that are more likely to contain our search results. This could narrow down our search results: find repos that might contain it, then from those search the commits in them. We have the repo + username but we need the date. We are so close to running out of space that we can't add the date for every commit. We will have to add them as checkpoints in certain locations which minimize variance (i.e. the spaces in between are linear-ish.) This will add a few KB's to our total which is ok.

The dates can be interpolated for each data point to get a commit frequency for each repo which is another data point we can use for our ML pipeline. We also have the email address; we could grab the domain portion and quantize it to a few bits (i.e. one for gmail, hotmail, outlook, other) for each commit. This would add a few megabytes.

Another stat that we can use in our ML pipeline is pre-filtering our results based on repository language. Depending on what your search term is, it might have a high correlation to the repository's language. For example, searching or our gradle file [[https://github.com/search?l=Gradle&q=filename%3Agradle&type=Code]{.ul}](https://github.com/search?l=Gradle&q=filename%3Agradle&type=Code) shows that it primarily exists in repositories whose detected language is primarily Java. We can then scrape those 28 million repository HTML pages and only save the repos whose main language is Java. This will reduce the intensive file-detection stage later on.

We need a file listing from each repository. How do we do this?

We could scrape each individual HTML repo page, but it would be very slow.

We could clone every repo with git clone, but that would take a while as well as there are many individual files and we'd get the entire repository history, which we don't want. We could use a shallow clone to just get the most recent revision which saves on cloning time and disk space, but it is still slow.

We could download the auto-generated zip from master, store it as a temp file, then do zip -l on it to get the file listing, which would allow us to quickly get the entire repository without the overhead of creating each individual file, plus the benefit of compression. We still haven't solved the problem of downloading the entire repository though. Unfortunately, this does not have a Content-Length header so we can't do anything fancy like reading the end of the ZIP file to get the TOC and therefore the file listing. We could stream the ZIP file into memory and try to decompress it to save on disk space, but still, we have to download the entire thing and that eats up a lot of bandwidth we could use to download more files in parallel.

What to do? The "git archive" command is able to list remote repositories without downloading the files themselves, but GitHub does not support the git archive command for git repos. Interestingly though, svn supports it:

svn ls -R [[https://github.com/gtque/GoaTE.git]{.ul}](https://github.com/gtque/GoaTE.git)

This gives us the file listing for a repo, doesn't use up a lot of bandwidth, but it is very slow:
```
real 2m36.286s

user 0m0.344s

sys 0m0.375s
```
Ouch. We're stuck in the fast, cheap, and quality triangle. We've gotten the files cheaper, the same quality, but not as fast. Can we have all three? We can. There is a project called "fast svn crawler" which does just that: crawls svn faster. ./svn-crawler [[https://github.com/mithro/fastsvncrawler]{.ul}](https://github.com/mithro/fastsvncrawler).git. These are the stats after using fastsvncrawler:

```
real 0m13.718s

user 0m1.078s

sys 0m0.297s
```

That's about a \~10x speedup! Can we go even faster? Yes. We only need the trunk (and not the other branches.) Therefore, we can run time ./svn-crawler [[https://github.com/gtque/GoaTE.git/trunk]{.ul}](https://github.com/gtque/GoaTE.git/trunk) and get the following output:

```
real 0m3.372s

user 0m0.313s

sys 0m0.141s
```

That's about a \~4x speedup from our 10x speedup! Can we go EVEN FASTER? Well, if we run the command through strace we get a bunch of gettimeofday calls. We don't care about file modification dates, so if we avoided this call it could reduce our CPU usage. Trying to avoid the HTTP overhead through ssh fails, as it fails to connect to the server after authentication (I presume that GitHub does not support this.)

Since we don't need *all* of the file paths that match (we just need to know if one of them matches), we can terminate early. Let's say we needed to grab a sample .java file:

```
time ./svn-crawler https://github.com/gtque/GoaTE.git/trunk \| grep -m 1 -F \".java\" \| head -n 1
```

```
real 0m1.120s

user 0m0.016s

sys 0m0.109s
```

Wow! That's about a \~3.2x speedup from our 4x speedup, or \~128x faster overall! Can we squeeze it out just a bit more? Yes, sort of. We don't care what grep outputs; we just need to know that it matches. Therefore, we can use the quiet option:
```
time ./svn-crawler https://github.com/gtque/GoaTE.git/trunk \| grep -q -m 1 -F \".java\"

real 0m1.035s

user 0m0.000s

sys 0m0.078s
```
This gives us a speedup of \~0.82x, but since network conditions change a bit it is hard to get a good estimate. It can only help as grep doesn't need to print anything.

Let's go back to our original problem. We want to download all files of a certain type from GitHub. We have several indicators to do this, such as filename, extension, size, etc. but GitHub's search and API does not show us all of those files. We have to create a model which allows us to predict which repos contain these files, so that when we go to those repos to check if the files do indeed exist then we don't need to check 28 million, we just need to check a handful.

When we do a search, we know how many repos which contain the search term are of a certain language, but B does not imply A. We don't know if there are lots of Java repos that don't contain Gradle files, we just know that there are a lot of Gradle files that are in Java repos. We need to find P(B \| A'), or in English, what is the probability that a repo is in Java and does not contain any gradle files? We want this number (hopefully) to as close as zero as possible, so that if we search for Java repos then we will get back a strong signal that there are indeed the files that we are looking for.

We have A = probability that repo is Java (0.30337942857), B = repo contains a gradle file, and P(B \| A), but we want to find P(B' \| A) which is the same as P(A \| B').

P(A \| B) = (P(B \| A)P(A))/P(B) (Bayes Theorem)

![](media/image3.png){width="3.3802088801399823in" height="2.280557742782152in"}

We just need to find P(A) \* (1- P(B\|A))/(1-P(B)), since these are all known we just have to substitute. Let's do some *very* approximate math. GitHub search says there is about 9,035,441 Gradle files total [[https://github.com/search?q=filename%3Abuild+extension%3Agradle&type=Code]{.ul}](https://github.com/search?q=filename%3Abuild+extension%3Agradle&type=Code) but each repo could have multiple gradle files. Therefore, we have to find the average number of gradle files per repo, then we can divide the total number of files by that amount to get the number of repos, which can then be added to the probability estimate from the 28 million. GitHub only gives us 1000 search results, so we will have a very high error bound.

We have to crawl these repo search results to get the author name and repo name, then do a svn list on each repo to see how many ".gradle" extensions we can find, then take the average, which will take at least 1000 seconds to compute, or about 17 minutes single threaded.

Put all of the repo links into a file, then run this command:

while read line; do ./svn-fast-crawler "\$line".git/trunk \| grep -F ".gradle" \| wc -l; done \< gradle_repo_list.txt \| awk \'{ sum += \$1 } END { print sum }\'

Then just divide by 1000.

To see how many repos have a certain language, go to [[https://api.github.com/search/repositories?q=language:java+fork:false]{.ul}](https://api.github.com/search/repositories?q=language:java+fork:false) and then the "total_count" number will say how many repos match. This metric appears to be computed by the language that is 50% or greater in the repository. So for example if the Java percentage is 55%, then it will be classified as Java.

If we are to download the GitHub repo page to get the language stats, it takes about 0.5 seconds per repo. It's about 0.15mb/page, or 0.027mb/page gzip compressed (super approximate.) If we have 100mbits/second bandwidth, how many pages can we download per second which would saturate our connection? The pages are 1.2mbits each (0.216 compressed), so 83 pages/second (or 463/second compressed.) We are constrained by process overhead as well as decompressing the gzip response, so 463 pages/second is the upper limit which sounds a bit optimistic. If we were able to download 463 pages/second, it'd take about 17 hours, which is a lot.

To be continued in part 2\...
