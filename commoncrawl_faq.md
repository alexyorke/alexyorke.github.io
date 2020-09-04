

# Generate list of all domain names without duplicates

This script is not finished because it will combine canocalized domains with non-canocalized ones (e.g. com.google and google.com.) It requires the `awscli` to be installed, but you do not need to have an AWS account.
```bash
# compute domain vertices for years which this data has not yet been computed
mkdir commoncrawl_domains; while read line; do sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\/crawl-data\//' | sed 's/$/\/cc-index\.paths\.gz/' | xargs -I{} sh -c 'curl {}' | gzip -d | sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\//' | xargs -I{} sh -c 'curl {} | gzip -d | cut -d " " -f 4 | cut -d "/" -f 3 | sort -u --compress-program=gzip >> commoncrawl_domains/domain_names_'"$line"'.txt'; sort -o "commoncrawl_domains/domain_names_$line.txt" "commoncrawl_domains/domain_names_$line.txt"; gzip "commoncrawl_domains/domain_names_$line.txt"; done < <(curl https://index.commoncrawl.org/collinfo.json | jq -r .[].id | tail -n 44);

# download domain vertex data as-is from years which it has been pre-computed
aws s3 --no-sign-request ls --recursive s3://commoncrawl/projects/hyperlinkgraph/ | grep -F "domain-vertices.txt.gz" | cut -d " " -f 5- | sed 's/^/https:\/\/commoncrawl.s3.amazonaws.com\//' | xargs -I{} sh -c 'curl -sL {} | gzip -d | cut -f 2 | sort -u --compress-program=gzip | gzip >> test/c_domain_names_$(basename {})';

# merge everything together and remove duplicates (warning: will combine canocalized and non-canocalized versions together)
zcat commoncrawl_domains/*.gz | sort -u --compress-program=gzip > all_domains.txt;
```
