# Sorting files larger than your available disk space

Normally, the `sort` command will create temporary file(s) if the data to sort exceeds the amount it can fit into memory. However, this is an issue if your data is very large and two copies cannot exist simultaneously.

I just found out that `sort` has a `--compress-program` flag which will compress and decompress the temporary files it uses as needed. For example:

```
sort -u --compress-program=pigz
```

(`pigz` is a multi-threaded `gzip` compressor.)
