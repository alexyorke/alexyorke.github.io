---
title: "Using 'agrep' to search for typos"
date: 2021-03-10
---

If you have a typo in your codebase, it might be tempting to reach for spell check. While spell check is useful, it doesn't know how words should be spelled outside of its own internal dictionary. If this is US English, then the word "javascript" isn't a word and so would be marked as invalid by spell check.

While it is possible to generate a team-driven spellcheck with a custom dictionary of words, sometimes this might not be practical. What if I just need to search the codebase for a single, potentially misspelled word?

Enter '[[agrep]{.ul}](https://linux.die.net/man/1/agrep)' (not 'grep'.) The agrep command stands for approximate grep, and uses the edit distance between words to calculate how many characters would need to be added, removed, or modified to make your original word. A popular algorithm to calculate this is the Levenstein distance.

### How do you use 'agrep'?

Let's clone Angular and see if there are any misspellings of "angular".

First, clone Angular: git clone github.com/angular/angular Then, cd into angular.

In that directory, run agrep -2 -ir -w \"angular\" . \| cut -d \":\" -f 2- \| grep -aviF \"angular\" \| grep -avi \"regular\"

That command will recursively search all files in the angular repo, find all lines that contain a word whose edit distance between angular is at most two, and then hide all lines with the word "angular". We have to filter out a few other words, because "angular" with two characters removed can also make the word "regular". This has the caveat of not finding misspellings of "angular" on lines that contain the word "regular", so be warned.

We get a few results:

```
input.nativeElement.value = \'angul\';

// (\`angul\`) has a length \> 3, the validation is successful

// Login form control is valid. However, the form control is invalid because \`angul\` does

it(\'should place initial, multi, singular and application followed by attribute style instructions in the template code in that order\',

it(\'should place initial, multi, singular and application followed by attribute class instructions in the template code in that order\',

\"description\": \"should place initial, multi, singular and application followed by attribute style instructions in the template code in that order\",

\"description\": \"should place initial, multi, singular and application followed by attribute class instructions in the template code in that order\",

\*\*Do\*\* create a new service once the service begins to exceed that singular purpose.

\* \*\*bazel:\*\* Hide Bazel files in Bazel builder (\[\#29110\]([[https://github.com/angul]{.ul}](https://github.com/angul)
```

We get the word "singular" too; we could have filtered that out but since we didn't get too many results it's easy to look through them.

Here we've matched "angul" for "angular" too. It just so happens that the two letters were removed from the end; it doesn't matter where in the word they can be modified, added, or deleted. For example, the word "angzzular" matches too.

If we wanted to search for words that can be up to three characters away, we could use agrep -3 instead. If we do that though we start to quickly get more matches, in this case 204 lines of matches. This might be too many to look through.

### Preventing false positives

Some words, especially shorter ones, also match many dictionary words. You can find which dictionary words will match by searching the dictionary beforehand, and then noting any words that appear:

agrep -2 -ir -w \"angular\" /usr/share/dict/words

In this case it returned 19 words that are at most two characters away from "angular".

This could be more useful in the case of translation files, where words might be misspelled. Or, you can pre filter your strings in your code (through a regex) and then search through just those.
