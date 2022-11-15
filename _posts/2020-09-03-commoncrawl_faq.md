---
title: "Generate list of all domain names and IP addresses without duplicates"
date: 2020-09-03
---

This script is not finished because it will combine canocalized domains with non-canocalized ones (e.g. com.google and google.com.) It requires the `awscli` to be installed, but you do not need to have an AWS account. Domains and IP addresses might contain ports (such as google.com:1234)

```bash
# compute domain vertices for years which this data has not yet been computed
while read -r cdx; do
    curl "$cdx" | gzip -d | cut -d " " -f 1 | cut -d ")" -f 1 | sort -u --compress-program=gzip | tr "," "." | gzip >> commoncrawl_domains_$(echo "$cdx" | cut -d "/" -f 6).txt.gz;
	done < <(\
		while read -r ccindexpath; do
			curl "$ccindexpath" | gzip -d | sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\//' | grep "\.gz$" | sponge;
			done < <(\
				while read -r collinfo; do \
					sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\/crawl-data\//;s/$/\/cc-index\.paths\.gz/' | grep "\.gz$"; \
				done < <(curl https://index.commoncrawl.org/collinfo.json | jq -r .[].id | tail -n 44 | sponge)\
		)\
)

# download domain vertex data as-is from years which it has been pre-computed
aws s3 --no-sign-request ls --recursive s3://commoncrawl/projects/hyperlinkgraph/ | grep -F "domain-vertices.txt.gz" | cut -d " " -f 5- | sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\//' | xargs -I{} sh -c 'curl -sL {} | gzip -d | cut -f 2 | sort -u --compress-program=gzip | gzip >> c_domain_names_$(basename {})';

# merge everything together and remove duplicates (warning: will combine canocalized and non-canocalized versions together)
zcat commoncrawl_domains/*.gz | sort -u --compress-program=gzip > all_domains.txt;
```
