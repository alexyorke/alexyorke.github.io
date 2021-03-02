### UTF-8 Default Ignorables you shouldn&#39;t ignore

This finds pesky invisible UTF-8 characters. They normally don&#39;t cause problems but they can cause strings to not equal even though they look exactly the same. They can prevent some files from being parsed, or weird errors when importing CSV files.

They can cause parsers to choke on data that contains these characters. Or they could cause [failed Kubernetes deployments](https://www.instana.com/blog/how-a-slack-zero-width-space-character-broke-a-kubernetes-deployment/). Not fun if you ask me.

They can prevent Ctrl+F from finding a word, so they&#39;re kinda annoying. They can cause weird syntax errors too, depending on your programming language. Or they can just be a hassle when you try to hit delete and nothing happens. They can also be used to encode secret data.

C# regex (for all character-based languages like English): `[\u0000-\u0008]|[\u000E-\u001F]|[\u007F-\u009F]|[\u0085]|[\u00AD]|[\u06DD]|[\u070F]|[\u180B-\u180E]|[\u2000-\u200C]|[\u2029-\u202F]|[\u205F-\u206F]|[\u3000]|[\uFEFF]|[\uFFF0-\uFFFC]`

Finds 120 unique invisible characters. Not _all_ of them, but the ones that usually cause issues.

C# regex without 200B and 3000 (for all other languages): `[\u0000-\u0008]|[\u000E-\u001F]|[\u007F-\u009F]|[\u0085]|[\u00AD]|[\u06DD]|[\u070F]|[\u180B-\u180E]|[\u2000-\u200A]|[\u200C]|[\u2029-\u202F]|[\u205F-\u206F]|[\uFEFF]|[\uFFF0-\uFFFC]`

U+200B and U+3000 show up frequently in non-English languages. U+200B is a really large space, and U+3000 is a really long tab.

U+2003 are for trees&#39; indenting. You might want to exclude it if you use a lot of filesystem trees in your docs.

There&#39;s a zero-width separator for emojis. A lot of people use emojis so I left that out of the regex.

How did I make this regex? Well, I compiled a list of the default ignorables from [http://www.unicode.org/L2/L2002/02368-default-ignorable.pdf](http://www.unicode.org/L2/L2002/02368-default-ignorable.pdf), trial and error finding which characters were benign (line breaks, space bar, tab key, etc.) Then I downloaded a list of readme&#39;s, ran them through and found which characters were false positives (some emojis that needed a zero-width space to separate them for example.)

From there, I ran it through thousands of readmes and audited the matches to see if they were not false positives. If they were, I refined the character sets and repeated again and again.

After that, I optimized the regex by combining the ranges together. I also may have found a bug in another program I was using to match these regexes but that&#39;s for another time.

There&#39;s a few more that I don&#39;t have, mostly because I used the official PDF instead [Network.IDN.blacklist chars - MozillaZine Knowledge Base](http://kb.mozillazine.org/Network.IDN.blacklist_chars). I didn&#39;t include a lot of them as they showed up too many times on almost all documents I tried or they interfered with an emoji.

There are other solutions but they don&#39;t match as many invisibles.

I used this website extensively to cross-check my work [https://www.soscisurvey.de/tools/view-chars.php](https://www.soscisurvey.de/tools/view-chars.php)
