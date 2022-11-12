---
title: "Avoiding npm install whack-a-mole"
date: 2021-02-22
---

When pulling new commits, sometimes package.json and/or package-lock.json (depending on your development workflow) changes. It can be difficult to know when it changes if there are a lot of files changed (although git diff will easily show you), or you might forget.

It may not appear to be that bad, missing either an npm install or an npm ci when package.json changes that is. When I try to build the project it&#39;ll say this weird error about some dependency, right? Then I&#39;ll just run npm install.

The issue is that some dependencies don&#39;t change enough for them to be incompatible. This means that your project may successfully compile and run, and maybe even pass the tests. You&#39;ll be writing code for the older version of the library. The new library change might have just fixed a security vulnerability for example and didn&#39;t make any user-facing API changes. This means that, when running it on the CI, it&#39;ll work just fine.

Or, it could have fixed a bug, changing behavior. You might not notice until the CI build pipeline or worse, it might go into production unnoticed.

It might be a small change, in which case it doesn&#39;t matter much. Or it could be a big enough change that is noticeable to the end user.

It might go unnoticed during code review if others only upgrade their dependencies when they get errors, which might not occur for all dependencies.

### Just running npm install or npm ci every pull

While this isn&#39;t necessarily a bad idea, it&#39;s a bit wasteful. If the package.json or package-lock.json hasn&#39;t changed and you&#39;re already up to date, then running npm install again might not do anything. Now, there are exceptions to this rule. The [npm install command can update the package-lock.json file](https://stackoverflow.com/questions/45022048/why-does-npm-install-rewrite-package-lock-json), so if your team uses this method of development then there&#39;s less you can do to optimize it.

What we need is a better system, one that only runs npm ci or npm install when the package.json or the package-lock.json files change.

### A solution

Just concatenate package.json and package-lock.json and take the hash, right? Then check if the hashes differ when you run npm run start or npm run test and call npm install or npm ci as needed, right? Well, almost.

JSON syntax whitespace changes and different line endings don&#39;t mean that the actual files themselves changed, and rearranging the associative keys doesn&#39;t mean that something was added or deleted. Rebuilding on these cases is wasteful.

What we can do is use a command-line JSON parser called jq to help us. We can tell it to compress the JSON into one line and to sort the keys. This means that variations to whitespacing or key ordering won&#39;t affect the hash. The command to do this is:

echo &quot;$(jq --sort-keys -c . package.json package-lock.json)&quot; | sha256sum

The reason I&#39;m using echo and not echo -n is to preserve the hash of the individual files. For example, if I run jq -c . package-lock.json | sha256sum it&#39;d be the same hash as if I were to run the above command but delete package.json.

This command will work even if you:

- Don&#39;t have either file.
- Have one or the other.
- Have both files.

If one of the files isn&#39;t found, it will complain (but still work); a cleaner command is the exercise for the reader.

### How would I implement this?

Here&#39;s what you can do:

- Create a new npm script called needs-to-update.
- This script would hash the package.json and package-lock.json file and check if it matches the hash in node-modules-hash.txt.
- If the hash doesn&#39;t match, or the file doesn&#39;t exist, then it will run npm ci, then set the contents of node-modules-hash.txt to the hash of package.json and package-lock.json.
- Additionally, you must wrap _all_ npm scripts (except for ci) such as npm run lint, npm run start to call the needs-to-update script first.
- Ensure you check node-modules-hash.txt into a .gitignore or a local .gitattributes file. Other developers should not have your node-modules-hash.txt file because each developer may or may not have updated their node\_modules folder.

So, whenever you run npm run start, needs-to-update will check if your dependencies need to be updated. If they do, then it&#39;ll update them for you then call npm start. You&#39;ll always be sure you&#39;ll have the right dependencies. This also works if you&#39;re git bisecting because the contents of node-modules-hash.txt won&#39;t change on disk, and will reflect the hash of the node\_modules folder.

If you&#39;re concerned that npm install or npm ci will wipe something out unexpectedly, or if you have custom changes to the node\_modules folder, **you could make it print an error message instead and halt, saying that the dependencies are out of date.**

If you do actually end up implementing it, I would recommend reading about **the differences between npm install and npm ci,** and whether your team has package-lock.json committed and its ramifications of it not being committed. This could mean the difference of whether this solution works or not.

### Caveats

- If you&#39;re using git bisect (or checking out older commits), and you&#39;ve run a script like npm link in the past, then this script won&#39;t know what script you&#39;ve used to run in the past. This is more of a general issue when trying to run previous versions of an app and reproducibility concerns.
- The command npm install can modify the package.json file in the past. Consider using npm ci instead to lock what you&#39;ve had in the past. The issue however with npm ci is that if you have a very strange setup where you haven&#39;t updated in a very long time and you go back in time and try running npm ci, then it might not be the same state as what you&#39;ve once had if you&#39;re not using reproducible builds. **This is only a concern if you don&#39;t use CI.**
- This command will only work on Bash and needs jq installed.
- If node-modules-hash.txt can&#39;t be created (e.g. permissions issues), then it will re-re-re-run the installation steps every time you run start or test. Ensure you have correct permissions.
