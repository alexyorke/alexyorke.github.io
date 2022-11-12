---
title: "How to download entire GHArchive"
date: 2020-09-03
---

Note: the script will have a lot of 404 errors initially because the first few months of 2011 have not been archived. Requires `aria2` to be installed. As of 2020, the archive is about 1.1TB compressed.

```bash
echo -en https://data.gharchive.org/{2011..2020}-{01..12}-{01..31}-{0..23}.json.gz\\n| sed 's/^ *//g' | aria2c -x 16 -i -
```

# Download entire archive with deleted repo data

GHArchive stores created and deleted repository events, which means that it is possible to reconstruct a somewhat consistent snapshot of the repositories which are currently on GitHub. In order to reconstruct the snapshot, the deleted events have to be processed after the created events. However, this is very time-consuming so there is a slightly less accurate but much faster way to do it.

To find out which repositories are live on GitHub, concatenate all of the downloaded files together from this script and just delete all repositories which appear an even number of times, then remove all duplicates preserving the first occurence. This works because, for the most part, if a repository is created, then the next event must be a deleted event, which is two events and so is even. If a repository is created, deleted, and then created, there are three events and so is odd. Note: this is an approximate method because it does not account for repos which are made private, repos which were outside of the boundaries of the scan, and some GHArchive data is not available.

```bash
echo -en https://data.gharchive.org/{2011..2020}-{01..12}-{01..31}-{0..23}.json.gz\\n| sed 's/^ *//g' | xargs -P 128 bash gharchive_downloader.sh
```

Then, create a file called `gharchive_downloader.sh` with the following contents:

```bash
curl --connect-timeout 10 --retry 10 "$1" | zgrep "\"type\":\"CreateEvent\"\|\"type\":\"DeleteEvent\"" | jq -c '[.repo.name, .payload.ref_type]' | grep "\"repository\"" | sort -f | jq -r .[0] > $(basename "$1")
```
