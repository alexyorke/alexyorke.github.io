When pulling new commits, sometimes package.json and/or package-lock.json (depending on your development workflow) changes. It can be difficult to know when it changes if there are a lot of files changed (although git diff will easily show you), or you might forget.

It may not appear to be that bad, missing either an npm install or an npm ci when package.json changes. When I try to build the project it'll say this weird error about some dependency, right? Then I'll just run npm install.

The issue is that some dependencies don't change enough for them to be incompatible. This means that your project may successfully compile and run, and maybe even pass the tests. You'll be writing code for the older version of the library. The new library change might have just fixed a security vulnerability for example and didn't make any user-facing API changes. This means that, when running it on the CI, it'll work just fine.

Or, it could have fixed a bug, changing behavior. You might not notice until the CI build pipeline or worse, it might go into production unnoticed.

It might be a small change, in which case it doesn't matter much. Or it could be a big enough change that is noticeable to the end user.

It might go unnoticed during code review if others only upgrade their dependencies when they get errors, which might not occur for all dependencies.

### Just running npm install or npm ci every pull

While this isn't necessarily a bad idea, it's a bit wasteful. If the package.json or package-lock.json hasn't changed and you're already up to date, then running npm install again might not do anything. Now, there are exceptions to this rule. The [[npm install command can update the package-lock.json file]{.ul}](https://stackoverflow.com/questions/45022048/why-does-npm-install-rewrite-package-lock-json), so if your team uses this method of development then there's less you can do to optimize it.

What we need is a better system, one that only runs npm ci or npm install when the package.json or the package-lock.json files change.

### A solution

Just concatenate package.json and package-lock.json and take the hash, right? Then check if the hashes differ when you run npm run start or npm run test and call npm install or npm ci as needed, right? Well, almost.

JSON syntax whitespace changes and different line endings don't mean that the actual files themselves changed, and rearranging the associative keys doesn't mean that something was added or deleted. Rebuilding on these cases is wasteful.

What we can do is use a command-line JSON parser called jq to help us. We can tell it to compress the JSON into one line and to sort the keys. This means that variations to whitespacing or key ordering won't affect the hash. The command to do this is:

echo \"\$(jq \--sort-keys -c . package.json package-lock.json)\" \| sha1sum

The reason I'm using echo and not echo -n is to preserve the hash of the individual files. For example, if I run jq -c . package-lock.json \| sha1sum it'd be the same hash as if I were to run the above command but delete package.json.

This command will work even if you:

-   Don't have either file.

-   Have one or the other.

-   Have both files.

If one of the files isn\'t found, it will complain (but still work); a cleaner command is the exercise for the reader.

### How would I implement this?

Here's what you can do:

-   Create a new npm script called needs-to-update.

-   Wrap the above script to check if a file called "npm-should-update.txt" exists. If it doesn't, then return false. If it does, return whether the hash matches that file.

-   Wrap all of your CLI scripts like start, test, and lint with needs-to-update. If needs-to-update returns true, then perform the update and call the wrapped script. If not, then just call the wrapped script.

-   Ensure you check needs-to-update.txt into a .gitignore. Other developers should not have your needs-to-update.txt file.

So, whenever you run npm run start, you'll be sure to have the right dependencies. This also works if you're git bisecting, too.

If you're concerned that npm install or npm ci will wipe something out unexpectedly, or if you have custom changes to the node_modules folder, **you could make it print an error message instead and stop the script, saying that the dependencies are out of date.**

If you do actually end up implementing it, I would recommend reading about **the differences between npm install and npm ci,** and whether your team has package-lock.json committed and its ramifications of it not being committed. This could mean the difference of whether this solution works or not.

### Caveats

-   If you're using git bisect (or checking out older commits), and you've run a script like npm link in the past, then this script won't know what script you've used to run in the past. This is more of a general issue when trying to run previous versions of an app and reproducibility concerns.

-   The command npm install can modify the package.json file in the past. Consider using npm ci instead to lock what you've had in the past. The issue however with npm ci is that if you have a very strange setup where you haven't updated in a very long time and you go back in time and try running npm ci, then it might not be the same state as what you've once had if you're not using reproducible builds. **This is only a concern if you don't use CI.**

-   If the needs-to-update.txt file is generated for every npm run start then it could make the working directory not clean which can make git prompt you asking to stash or save your files. You might have to modify your git bisect workflow or automatically stash and unstash your needs-to-update.txt file when checking out commits.

-   This command will only work on Bash and needs jq installed.

-   If needs-to-update.txt can't be created (e.g. permissions issues), then it will re-re-re-run the installation steps every time you run start or test. This could reduce productivity, so ensure you have the right permissions.

I'm sure there's someone who has already made something like this. My Google-Fu isn't fantastic and I couldn't find anything. Perhaps there is a huge caveat to using a method like this one. Then again, it's not much different from manually running it. Having a warning or an error message instead could be helpful, at least.
