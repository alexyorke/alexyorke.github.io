# How to quickly download thousands of config or program files to test parsers, compilers, and fuzzers

When developing certain applications, it can be helpful to have a set of
example files to use. For example, when designing a compiler, there
might be some edge cases that you might not be aware about and so having
example files helps find these issues faster. Some uses for example
files could be for fuzzers, compilers, parsers, and more. For example,
there is the Excel spreadsheet dataset which contains a million or so
Excel files used for testing programs that deal with Excel files.

In this blog post I will be going over on how to download a set of
Gradle files used for testing a fictional Gradle parser. This technique
could be extended to download files of any type, however (such as
configuration files.)

Where do we go to get example files? Well, GitHub has a lot of code.
GitHub at the time of this writing GitHub has about 100 million
repositories with 40 million users. Google has a lot as well, but the
results are more focused on blogs than actual raw programming files.
While not impossible to get raw files (e.g. using the inurl attribute to
get the filename), the signal to noise ratio is low for what we want.

Let’s use the GitHub search to find some sample files. Searching for
".gradle" finds a lot of files, and we can write a script to download
them, right? Well, we are limited to the first 100 pages of search
results, and even if we search on the file type’s language, we only get
1000 sample files and a lot of them are exact duplicates. That’s a lot,
but it’s not enough for our purposes. What can we do if GitHub’s search
restricts us to the first 1000 results?

We can search for random dictionary words with the language as the
filetype so that we can get more search results by coincidentally
finding a word that is contained in the comments of a file. The issue is
that this takes a very very long time, a lot of words just return zero
results, and there are a lot of duplicates. We could try searching for
"aaa", "aab", "aac", ... (since GitHub forces the query to be at least
three characters long.) This would net us 26\^3 = 17576 searches, many
of those return zero search results. Is there a better way?

The website GHArchive.com has been collecting public GitHub event data
since about 2011. This event data consists of when new repos are
created, user comments’ on PRs, and more importantly, pushes to all
public repos. The "PushEvent" contains the message and URL of the
commit. We can search for the word that we want in the commit message,
then find and download the files that correspond to that word.

It’s not perfect though: the word that corresponds to the filetype isn’t
guaranteed to be in the commit message. When is the last time you wrote
"Adding a C\# file" for a commit? Thankfully though, this approach works
well enough for our purposes and we are able to get a very sizable chunk
of files.

The following script downloads all event data from 2015 through 2020
from GHArchive.com. Since there are \~44640 files (assuming every month
has 31 days), and each file is \~10MB, then this will download \~44GB.
If that’s too much, then the years can be adjusted to get a smaller
slice in time. The "sponge" utility is required because gharchive.com
doesn’t like having long-lived server connections when streaming the
file (and will disconnect us); to get it, install the moreutils package.
Also, install the jq package to parse json files. The following script
will go to gharchive.com, and extract the commit URLs from the
PushEvents:

```
\#!/bin/bash

for Y in {2015..2020}; do

for M in {01..12}; do

for D in {01..31}; do

for H in {0..23}; do

while read -r line; do echo "\$line" | LC\_ALL=C grep -F
"\\"type\\":\\"PushEvent\\"" | grep -i "gradle" | jq
.payload.commits\[\].url | cut -d "\\"" -f 2 &gt;&gt;
\~/gradle\_urls.txt; done &lt; &lt;(curl
"https://data.gharchive.org/\$Y-\$M-\$D-\$H.json.gz" | gunzip | sponge);

done;

done;

done;

done;
```
Replace "gradle" with your search term. I recommend using a very generic
term so that you can cast the net as large as possible. If you want to
search for multiple terms (i.e. OR), write "term1\\|term2\\|term3"
(where term1, term2, and term3 are your keywords) as the grep query.

For the inexpensive \$5/month VPS that I used, I predicted this would
take about two months to download and parse all of the data from 2015 to
2020. The limiting factor was CPU because the file expands to \~6x
larger and each line has to be parsed individually. To speed this up, it
could be run on multiple nodes (i.e. each one downloads a single year or
a month) and then the URLs are aggregated at the end.

If you get errors every 30th or 31st file, don’t worry because these
days in that month doesn’t exist. It’s possible to skip over those but
it could make the code a bit more complicated.

## Aside: using Google’s BigQuery to avoid having to spend two months downloading data

If you have \~\$30 CAD to spend, you can get the first half of the data
a lot faster. You get 1TB of data free to process every month, but if
you have a **billing account setup it will charge you without warning if
you go over. The dataset is a few TB’s, so you will get auto-charged.
Run the query on a single day first to make sure that the query is
correct.** Go to
[*https://console.cloud.google.com/bigquery?project=githubarchive&page=project*](https://console.cloud.google.com/bigquery?project=githubarchive&page=project)
and run the following query:

```
SELECT type, payload FROM \`githubarchive.year.2015\` where payload like
‘%gradle%’
```

Repeat for each year up to 2020, exporting the results each time both to
Google Drive and "manual" 10000 row download (downloading will take the
first 10000 rows, Google Drive will take the first GB. Doing both will
get you more data, since downloading 10000 rows might be more than a GB,
and vice-versa.) There is probably a smarter way to export the entire
query to a downloadable file but I don’t know how to do it.

Download all of the CSV files from Drive, decompress all of them and put
them into a folder. Move all of the manually downloaded files into the
same folder and decompress them. Folder hierarchy doesn’t matter; they
can be nested. Duplicates don’t matter either as those will be filtered
out.

Run this command in the CSV directory to extract the URLs:

```
grep -Ero
"https:\\/\\/api\\.github\\.com\\/repos\\/\[A-Za-z0-9\\-\]+\\/\[A-Za-z0-9\\-\]+\\/commits\\/\[a-f0-9\]+"
| cut -d ":" -f 2- | sort -u &gt; \~/gradle\_urls.txt
```

Now you have a list of URLs in the fraction of the time. Continue onto
the next step.

(Aside, done.)

Why am I not parsing the data from 2011? I tried to parse it, but it
seems like it was in a different schema and I didn’t get any URLs after
about a day, whereas starting from 2015 I got results in about 30
minutes. Your experience may vary.

This will output a list of URLs which correspond to a single commit
(which can contain many files) whose commit messages contain the word
"gradle". GitHub’s API is rate-limited, which is why they are saved to a
file called "gradle\_urls.txt" for further processing at a slower speed.
There are ways around the rate-limit in this API, but they will not be
discussed in this post.

To extract the file URLs in each commit, run:

```
while read -r line; do curl "\$line" | jq .files\[\].raw\_url | cut -d
'"' -f 2 | sort -u &gt; \~/gradle\_sample\_file\_urls.txt; done &lt;
\~/gradle\_urls.txt
```

This will output a list of URLs that point directly to the files in each
commit, aggregated by commit. At this point you could filter the URLs
(e.g. find all ones that end with ".gradle") and download those files.
To get some inspiration on what extensions or filenames it *could* have
(but not guaranteed), go through
[*https://github.com/github/linguist/blob/master/lib/linguist/languages.yml*](https://github.com/github/linguist/blob/master/lib/linguist/languages.yml),
find your language, and see how the grammar is applied. You might find
some filenames that you didn’t know about that you can match against. If
you want a *lot* of files, you could download all of them and check them
individually but the signal to noise ratio is very low.

To download all of the URLs (but you probably want to filter them
first), run:

```
wget -i \~/gradle\_sample\_file\_urls.txt
```

This will download all of the sample files. You could say you’re done,
but there is a bit of cleanup that you might want to do afterwards.

## Cleanup time

I have a few bonus tips on how to clean up the resulting downloaded
files and how to get *even more*.

After downloading the files (e.g. wget -i urls.txt), you’ll have a bunch
of files which are duplicates, a lot of them very similar, some might be
empty, some might have invalid syntax, and some are totally random and
don’t correspond to your file type at all.

The first step is to remove exact duplicates. I used the fdupes utility
to automatically delete all duplicates, preserving a random file in the
set. To delete all duplicates, run fdupes -dN . in the directory with
the downloaded files. **NOTE: this will remove all duplicates with no
warnings, so take a backup first.**

Next, to filter out files which do not correspond to the language that
you wanted, GitHub has a tool called Linguist which is used for
detecting the programming language for repositories. They have a command
line tool available here:
[*https://github.com/github/linguist*](https://github.com/github/linguist).

```
for i in \*; do if (github-linguist "\$i" | grep -F "language:" | grep
-q "Gradle"); then echo "\$i"; fi; done;
```

This will print out all filenames that github-linguist has identified as
a Gradle file. Unfortunately, with the sample data that I downloaded it
was too restrictive and misclassified a lot of files as generic text
files; I only got a handful of files from my thousands of files
downloaded as it seems that it forces the filename to match; when wget
downloads the files it adds a ".numeric" suffix which could cause this
check to fail.

Fortunately, there is a workaround. **Note: take a backup of the
directory before running this command.** Since the filename has to be
matched, then in order to have the filename pre-approved, it has to be
in github-linguist’s filename set. Check this file to find out how the
filenames have to match:
[*https://github.com/github/linguist/blob/master/lib/linguist/languages.yml*](https://github.com/github/linguist/blob/master/lib/linguist/languages.yml).
Each file must be in a different directory, but with the pre-approved
filename. This script will move each file into a randomly-generated
directory with the pre-approved filename:

```
for i in \*; do
UUID=\$(cat /proc/sys/kernel/random/uuid);
mkdir "\$UUID";
mv "\$i" "\$UUID/build.gradle";
done;
```

Where "build.gradle" is a github-linguist pre-approved filename. Then,
in the directory with the gradle files, run:

```
find . -type f -print0 |
while IFS= read -r -d '' line; do
if (github-linguist "\$line" | grep -F "language:" | grep -q "Gradle");
then echo "\$line"; fi;
done
```

This will print out a list of file paths that github-linguist thinks are
Gradle files. I got a *lot* more results after doing it like this. It
will take a while to process, however.

You could stop here if you have sufficient sample data, or if you are
unsatisfied you can continue to get even more files.

## Let’s get greedy

(This section will be cleaned up at some point, as while it is possible
to perform using a script, I haven’t made one yet for it.)

Notice that earlier I said that the URLs corresponded to commits, which
mean that they are part of a series and can be linked together. The
entire file’s history can be tracked and so we can find more examples of
this file by downloading it at each point in history.

In the \~/gradle\_url\_sample\_files.txt file, a URL might look like
this:

[*https://raw.githubusercontent.com/github/linguist/a5df9a00ab7c9828bd7038bb9f9bd5e56d325dc9/samples/Gradle/build.gradle*](https://raw.githubusercontent.com/github/linguist/a5df9a00ab7c9828bd7038bb9f9bd5e56d325dc9/samples/Gradle/build.gradle)

Replace the word "raw.githubusercontent.com" with "github.com":

```
sed 's/raw\\.githubusercontent\\.com/github\\.com/g'
```

Add "commits" after the repo name:

[*https://github.com/github/linguist/commits/a5df9a00ab7c9828bd7038bb9f9bd5e56d325dc9/samples/Gradle/build.gradle*](https://raw.githubusercontent.com/github/linguist/a5df9a00ab7c9828bd7038bb9f9bd5e56d325dc9/samples/Gradle/build.gradle)

If you open this in your web browser, you will get the entire change
history for this file on an HTML page. Fortunately, we can parse this
HTML page and extract the commit URLs at each point in time. Note: this
only gets the first page of the results; getting each page is outside
the scope of this blog post.

This is a quick and dirty way to do it. HTML should not be parsed by
regex, but this was sufficient enough for my purposes. The next step is
to download the HTML page, extract the URLs, and print them:

```
curl
"https://github.com/github/linguist/commits/a5df9a00ab7c9828bd7038bb9f9bd5e56d325dc9/samples/Gradle/build.gradle"
| sed -n 's/.\*href="\\(.\*\\)".\*/\\1/p' | grep -oE
"\\/commit\\/\[0-9a-e\]+"
```

One of the outputs from this command looks like:

```
/commit/4ed58c743d
```

Append the text
"[*https://api.github.com/repos/github/linguist*](https://api.github.com/repos/github/linguist)":
[*https://api.github.com/repos/github/linguist/commits/4ed58c743d*](https://api.github.com/repos/github/linguist/commits/4ed58c743d)

Download that URL:

```
curl
"[*https://api.github.com/repos/github/linguist/commits/4ed58c743d*](https://api.github.com/repos/github/linguist/commits/4ed58c743d)"
| jq .files\[\].raw\_url | cut -d ‘"‘ -f 2
```

Each of those URLs will point directly to a raw file, including the
filename. Grep for the filenames that you want, and download each of
those files. Tada! You have a few more files to work with.
