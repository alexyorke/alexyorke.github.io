# Download entire archive from 2011 until 2020

Note: the script will have a lot of 404 errors initially because the first few months of 2011 have not been archived. Requires `aria2` to be installed. As of 2020, the archive is about 1.1TB compressed.

```bash
echo -en https://data.gharchive.org/{2011..2020}-{01..12}-{01..31}-{0..23}.json.gz\\n| sed 's/^ *//g' | aria2c -x 16 -i -
```
