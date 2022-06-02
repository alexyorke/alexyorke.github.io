# Quickly estimating allocated-but-unused filesystem blocks

If you delete a file from a filesystem, it is removed from the index but usually stays on disk until a newer file overwrites it.

It is hard to determine how much data is deleted because file systems usually do not separate zeros from overwritten areas.

Both Testdisk and PhotoRec can restore deleted files (to estimate how much data has been lost but not yet reallocated); however, they can only do this if the file system&#39;s index about that file is intact. Also, it operates block by block, so while it is slow as an approximation, it&#39;s fantastic for recovering deleted files. Additionally, it takes time to recover other parts of the file, such as the filename, which, again, is valuable for recovering files, but not necessary for an estimate.

One might be concerned with how many files can be undeleted, when sending a disk over a network, and when reassigning those sectors in a server or maintenance environment.

### Terminology

In this post, a "zeroed block" is a block which just contains zeros on the file system that we&#39;re using. In this case, we&#39;re mounting an XFS filesystem file, so a "zero block" is one which is pure zeros on that virtual file system; we&#39;re not concerned about the physical file system which contains that file.

A free block (defined by XFS) is a block that the file system can use to write data to. It might contain zeros, or it might have deleted file data.

### Getting started

Here&#39;s an XFS filesystem, approximately 256GB in size, and contains about 80 million files. Let&#39;s find out how much data is deleted.

First, let&#39;s get the block size.
```
$ xfs_info xfspart.img

meta-data=xfspart.img isize=512 agcount=4, agsize=16777088 blks

= sectsz=4096 attr=2, projid32bit=1

= crc=1 finobt=1, sparse=1, rmapbt=0

= reflink=1

data = bsize=4096 blocks=67108352, imaxpct=25

= sunit=0 swidth=0 blks

naming =version 2 bsize=4096 ascii-ci=0, ftype=1

log =internal log bsize=4096 blocks=32767, version=2

= sectsz=4096 sunit=1 blks, lazy-count=1

realtime =none extsz=4096 blocks=0, rtextents=0
```

The data's block size is 4096.How many free blocks are there?

```
$ xfs_db -r -f -c 'freesp -s' xfspart.img

from to extents blocks pct

1 1 2546152 2546152 7.49

2 3 911501 2041822 6.01

4 7 135254 623605 1.83

8 15 17445 190110 0.56

16 31 77858 2142232 6.30

32 63 14970 552755 1.63

64 127 1390 123298 0.36

128 255 750 126097 0.37

256 511 231 73905 0.22

512 1023 40 26820 0.08

1024 2047 25 35063 0.10

2048 4095 16 48302 0.14

4096 8191 20 128915 0.38

8192 16383 42 524281 1.54

16384 32767 43 1075196 3.16

32768 65535 46 2342649 6.89

65536 131071 41 3947378 11.61

131072 262143 7 1108540 3.26

262144 524287 5 2231234 6.56

524288 1048575 1 687478 2.02

4194304 8388607 3 13416832 39.47

total free extents 3705840

total free blocks 33992664

average free extent size 9.17273
```

About 50% of the disk is free, which means 50% of the space is reserved. According to the du command, this is correct. This means that "total free blocks" refer to blocks that are available for reallocation, not necessarily zeroed ones.

We could look at the free space extents:

```
$ xfs_db -r -f -c 'freesp -d' xfspart.img | wc -l

3703532
```

We would need to convert the agbno&#39;s into blocks, and then write a script to sample the intervals uniformly. Is there an alternative way that isn&#39;t XFS specific?

Let&#39;s start at the block level. We&#39;ll print out a few blocks from our file:

```
$ xfs_logprint -D -f xfspart.img

[...]

BLKNO: 1505

0 a5355de4 e325a5f5 54cd9df6 6506fc89 ca52b9ff 6ace79d7 ef9eb46f 4c7de7b6

8 426c52d0 439ace42 7dcce422 8042584f ffd90e7e 3c645921 49c1e0e1 92788e42

10 9923bc96 8ec69d91 62e7d648 1a08a9ac a496ba08 b650c6d cbf97496 486d0fee

18 caad8832 8bb79812 773960e9 6fb5aa62 dfcc301b 3ea437f2 28d47707 8caddb2b

20 c3ef6603 e7408c96 d6cf8054 33fded0e fb7ddd8d 4ebb95a0 fb23bf04 93b891c

28 fee01d7b b7e665b5 57fcb8b6 730cd271 c63304d1 abc746be 97384437 c94802f3

30 af38b5d5 888f264f a7a164d2 6665cdbb 49a600f3 368435a4 db25a652 e58cab38

38 1e55f7fb 44708a45 9be66a16 619afffd 6c7c859f 9eb8a9f0 541df29c a3f83150

40 257fe38f 9fce9fa8 be74d00 24b7e1af 7d6666af a8ffc4bb 67e2771a 64810a3e

48 2aa638d1 2e19e242 a0a2d696 3aac42b5 fb05685c bd61ec5c 4fdc662f 856f106c

50 67992c1b 8b2e7579 75adf95 61d1162 2fafd42c b737a2c3 ff23c6aa 39b1f81e

58 b6629743 e0a477bd f07c9065 3776fd0 1ddb6213 61eb5aa3 ff3f736e af1c2fd9

60 d48e6a72 c6ad2e6b cc7ca116 9a5d52d7 c25029c4 7c9f03a4 4bd71895 6bbbfb0e

68 5fc5f9a5 8ff25f73 312d3af3 659cf372 7af223ec 85cca734 1c45febe 99017b68

70 3693035 b3097096 e14e5950 56c6a840 20ca7ab3 db70f6e9 236334c4 ad2a6100

78 fc760869 6ebafb95 a496146 9724741d b00f359a c8ade661 417ef62f 10765443

[...]
```

Let&#39;s make sure that this maps to a physical block[0]:

```
$ dd if=xfspart.img bs=512 count=1 skip=1505 | od -t x4 -w32

0000000 a5355de4 e325a5f5 54cd9df6 6506fc89 ca52b9ff 6ace79d7 ef9eb46f 4c7de7b6

0000040 426c52d0 439ace42 7dcce422 8042584f ffd90e7e 3c645921 49c1e0e1 92788e42

0000100 9923bc96 8ec69d91 62e7d648 1a08a9ac a496ba08 0b650c6d cbf97496 486d0fee

0000140 caad8832 8bb79812 773960e9 6fb5aa62 dfcc301b 3ea437f2 28d47707 8caddb2b

0000200 c3ef6603 e7408c96 d6cf8054 33fded0e fb7ddd8d 4ebb95a0 fb23bf04 093b891c

0000240 fee01d7b b7e665b5 57fcb8b6 730cd271 c63304d1 abc746be 97384437 c94802f3

0000300 af38b5d5 888f264f a7a164d2 6665cdbb 49a600f3 368435a4 db25a652 e58cab38

0000340 1e55f7fb 44708a45 9be66a16 619afffd 6c7c859f 9eb8a9f0 541df29c a3f83150

0000400 257fe38f 9fce9fa8 0be74d00 24b7e1af 7d6666af a8ffc4bb 67e2771a 64810a3e

0000440 2aa638d1 2e19e242 a0a2d696 3aac42b5 fb05685c bd61ec5c 4fdc662f 856f106c

0000500 67992c1b 8b2e7579 075adf95 061d1162 2fafd42c b737a2c3 ff23c6aa 39b1f81e

0000540 b6629743 e0a477bd f07c9065 03776fd0 1ddb6213 61eb5aa3 ff3f736e af1c2fd9

0000600 d48e6a72 c6ad2e6b cc7ca116 9a5d52d7 c25029c4 7c9f03a4 4bd71895 6bbbfb0e

0000640 5fc5f9a5 8ff25f73 312d3af3 659cf372 7af223ec 85cca734 1c45febe 99017b68

0000700 03693035 b3097096 e14e5950 56c6a840 20ca7ab3 db70f6e9 236334c4 ad2a6100

0000740 fc760869 6ebafb95 0a496146 9724741d b00f359a c8ade661 417ef62f 10765443
```

Looks like we&#39;re on the right track.

We can print out if a block is empty via checking if the hex representation of it is just zeros. We&#39;re temporarily using the 512 byte block size (for inodes) so that we can cross-check our work with xfs\_db:

```
$ dd if=xfspart.img bs=512 count=1 skip=1505 status=none | hexdump -v -e '/4 "%02x"' | grep -c '^[0]\*$'

0
```

Let&#39;s manually go to a block we know is free (block 15) and see if grep returns 1.

```
$ dd if=xfspart.img bs=512 count=1 skip=15 status=none | hexdump -v -e '/4 "%02x"' | grep -c '^[0]\*$'

1
```

As we want to total all of the blocks that are zeros, we return one if there is a match, and zero otherwise.

Recall that we have 67108352 blocks in total, so for a conf. interval of 99% and a margin of error of 1%, we have to sample 16637 blocks. The sample size is approximately 68.15MB.

While the amount of data isn&#39;t particularly large for an HDD, random accesses slow down the data transfer. Using CrystalDiskMark, we measure the performance of random 4KiB reads. Q1T1 (one queue, one thread to simulate how the data will be accessed) indicates we can read at 0.41MB/s.

As a best case scenario, this will take about a minute and 37 seconds. Since we&#39;re running it through WSL2, performance might be impacted further, however.

Let&#39;s use 4096 as our data block size, and sample 16637 random blocks:

```
$ for i in $(shuf -i0-67108351 -n16637 | sort -n); do dd if=xfspart.img bs=4096 count=1 skip=$i status=none | hexdump -v -e '/4 "%02x"' | grep -c '^[0]\*$'; done | pv -l -s 16637 | awk '{s+=$1} END {printf "%.0f", s}'

4759
```

_We don&#39;t need PV, but it gives us a progress bar and ETA. To make reading more sequential, I&#39;m sorting the sectors in increasing order._

_It took two minutes and 46 seconds, which was not close to what we expected. As well as running WSL2, I had a lot of apps and backup software running, which could have caused the estimation to be off._

So, out of 16637 blocks, 4759 were zeros, which is about 28.60% of zero blocks or 78.61GB.

Since zero blocks are free space[1], then we can subtract them from the reported free space to get the non-zeroed out blocks. We know that 33992664/67108352 blocks or 50.653% is reported as free by XFS from our xfs\_info command earlier.

So, reported free space - zero blocks = 50.653% - 28.60% = 22.053% of the disk is non-zeroed blocks.

This means that 22.053% of 67108352 blocks is about **60.62GB of deleted files**. So, our free space is composed of 60.62GB of deleted files and 78.61GB of zeroed blocks, or 139.23GB of free space total.

Is this accurate?

### Checking our work

#### Cross checking with zeroed out filesystem

I happened to have a copy of the exact filesystem, except that I&#39;ve zeroed out the free space, defragged it, then re-zeroed out the free space again. Let&#39;s rerun the script on that filesystem.

We get 8493, which means that out of 16637 blocks, 8493 were free, or about 51.04%.

So, reported free space - zero blocks = 50.653% - 51.04% = -0.387% of our disk contains deleted files.

Why is it negative? Well, it&#39;s in our 1% margin of error and 99% confidence interval. For all intents and purposes, this is essentially zero.

We&#39;re expecting the zeroed out volume to not have any recoverable deleted files so this matches up with our expectations.

##### What does PhotoRec recover?

After running PhotoRec on the partition, it recovered 45GB of data ("du" apparent size.) This is the same order of magnitude of what we estimated, however, it is less because we are working at a file system block level rather than a file level. This means that even if a file occupied only one byte of data, we would have counted it as 512 bytes.

#### Compressing both disks

Compressing the zeroed out disk using zstd with default options gives us a ratio of 16.84 (15.2GB), while the non-zeroed out disk is 6.26 (40.9GB); each disk was 256GB on-disk.

The difference between these two compressed files is 25.7GB. We have 60.62GB of deleted files, so let&#39;s go to the first disk.

The non-zeroed out disk had 128GB of data, plus 60.62GB of deleted data which gives 188.62GB of data to compress. Consequently, the zeroed out disk only had 128GB of data to compress.

The adjusted compression ratio for the compressed disk is 188.62GB/40.9GB is 4.61, while the zeroed out disk is 128GB/15.2GB = 8.421.

This doesn&#39;t tell us a whole lot, but confirms that the disk with deleted files doesn&#39;t compress as well as the one with just zeros. Since the deleted file was a subsection of the files (potentially gzipped), it makes sense that the compression ratio would be smaller.

### Areas for improvement

- 1.2x-2x faster 4k random reads using multiple threads from CrystalDiskMark (Q32T16.) Unclear if this will be a performance improvement under WSL2.

- The sampling method also includes the internal log, which is 32767 blocks or about 17MB. We probably shouldn&#39;t include the log in our sampling because that&#39;s not considered a deleted file. While the internal log is very small compared to our entire disk, larger disks might have a larger log and could affect sampling.

- I zeroed the disk using cat /dev/zero \&gt; zeros then deleted the file; this means that each block doesn&#39;t have a special header because if it did, then that header should be intact for all of the blocks. Since deleting the file was instantaneous, a header couldn&#39;t have been on every block, and this would have caused our free block count to be close to zero. This means that a single large file with just zeros that was deleted would not count towards the deleted files.

- Consequently, if a file has zero blocks that align with the filesystem&#39;s blocks, then that part of the file won&#39;t be counted towards the deleted data total.

- fstrim could improve the performance of discarding unused blocks [https://man7.org/linux/man-pages/man8/fstrim.8.html](https://man7.org/linux/man-pages/man8/fstrim.8.html). It has a minimum option that could be used in conjunction with the free space extents histogram discussed earlier to determine a tradeoff between how many unused blocks will be discarded compared to how long sequential writes will take.

### Areas to explore in the future

A drive does not have to contain pure zeros for it to have been wiped. It is possible for a drive to contain any amount of random data, a random pattern, or a predictable pattern, as long as it is not sensitive information. The method described in this post can&#39;t be adapted to work in the general case because it works on blocks of content rather than finding sensitive information.

While these are interesting questions, they are outside the scope of this post.

### Conclusion

Using block-level analysis, we determined how many unused blocks there are compared to those that have already been discarded. We were able to estimate how much data had been deleted but had not yet been reallocated.

We found out that our first filesystem had about 60.62GB ± 1% of deleted data, and the identical filesystem which was zeroed out and defragged had about 0.26MB ± 1% of deleted data. While I don&#39;t know for certain whether these are actually deleted files, the two measurements are different enough to warrant a conclusion.

While the apparent size of the recovered files by "du" was about 45GB, it gives us the same order of magnitude as to how many files were deleted. Additionally, it is unclear if photorec does not recover files that don&#39;t have a valid file header (as it uses file types to determine what files to recover.)

This measurement is important because of:

- Potential security concerns (deleted files can be salvaged.) This method should not be used in and of itself for checking if any deleted files remain because it is stochastic, but it is helpful in preemptively prioritizing what drives have many deleted files or large quantities of deleted data.
- Determining when or what threshold to zero out a disk&#39;s free space. Doing it too often is wasteful, but not often enough means the underlying storage may be occupying unnecessary data. This is especially relevant for dynamic disks.
- How compressible your disk is if you&#39;re sending it over a network. Getting the average compressibility of all files may not be a good estimator of disk compressibility because the deleted files may still take up space.

### Footnotes

0: This data is from `/dev/urandom`.

1: In the context of this post, zero blocks are free space.
