# Download entire Chrome Extension Webstore

Downloads all `.crx` extensions to current directory, with the filename as the extension's id. It takes about 15 minutes for the script to generate the URLs because it is very inefficient and creates ~200000 `sed` processes (one for each line.) After the URL generation is finished it goes pretty fast though.

It's a lot of data, so you might want to save the URLs to a file first so that you can restart the download later.

```bash
curl https://chrome.google.com/webstore/sitemap | sed -n 's/^.*<loc>\(.*\)<\/loc>.*$/\1/p' | recode html..ascii | aria2c -i -;
(while read line; do echo "$line" | sed 's/^/https:\/\/clients2.google.com\/service\/update2\/crx\?response=redirect\&os=win\&arch=x64\&os_arch=x86_64\&nacl_arch=x86-64\&prod=chromiumcrx\&prodchannel=beta\&prodversion=79.0.3945.53\&lang=ru\&acceptformat=crx3\&x=id%3D/g;s/$/%26installsource%3Dondemand%26uc\n out='"$line"'\.crx/'; done < <(cat sitemap* | sed -n 's/^.*<loc>\(.*\)<\/loc>.*$/\1/p' | awk -F / '{print $NF}' | sort -u | shuf)) | aria2c -x 16 -i -;
```
