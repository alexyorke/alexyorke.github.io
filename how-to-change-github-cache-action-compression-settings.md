The [GitHub cache action](https://github.com/actions/cache) is an action that allows you to cache files in between CI runs. However, there isn&#39;t a publicly documented way to modify the compression settings (i.e. to increase or decrease the compression ratio.)

However, changing the [ZSTD\_CLEVEL](http://zstd/README.md%20at%20cefafc0b6efc1cf31b57c8f7f99a7aa88344644d%20%C2%B7%20facebook/zstd%20(github.com)) environment variable allows you to modify the compression level.

For example, in your GitHub actions YAML file, add the `env` stanza:

```
- name: Cache
uses: actions/cache@v2.1.6
env:
ZSTD_CLEVEL: 19
with:
[...]
```
...To change the compression level.

### Does this actually work?

As of zstd v1.5.0 on September 20th, 2021 on the ubuntu-latest image, it works. If I cache a [100mb test file from Cachefly](http://cachefly.cachefly.net/speedtest/?ref=driverlayer.com/web), GitHub says the cache size is 416162 B. Consequently, after setting the environment variable to 19, GitHub says the cache size is only 38709 B.

The higher-compressed file is 10.75 times smaller than not setting the environment variable, which means that the environment variable did have an effect.

### Levels higher than 19

This doesn&#39;t work with levels higher than 19 because the --ultra flag wasn&#39;t specified. If you try to do it anyway, you&#39;ll get a message saying &quot;Warning : compression level higher than max, reduced to 19&quot;.

It doesn&#39;t appear to be possible to manipulate the --ultra flag through the GitHub cache action, but is &quot;possible&quot; if you create your own caching mechanism (i.e. upload the file directly to the cache.)

If you must use GitHub&#39;s cache action and still want to compress higher than 19, you can first pre-compress the file using --ultra and level 21, then set the ZSTD\_CLEVEL to 1 for the GitHub cache action. This is just a workaround as there is overhead when compressing a file twice, and in some cases could make the file slightly larger.
