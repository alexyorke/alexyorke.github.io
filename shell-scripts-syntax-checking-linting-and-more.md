# Shell scripts, syntax checking, linting, line breaks, CI/CD, and more

Shell scripts are the glue that holds many systems together. They&#39;re also great for system utilities among many other things. However, they have a few thorns that can cause hours of debugging, especially in remote teams with different environments and software. Fortunately, there are a few ways to prevent them.

Here are the main issues:

- Line breaks and converting them at every step in the process.
- Syntax validation.
- Linting (and why linting isn&#39;t syntax checking.)
- UTF-8 ignorables that aren&#39;t (usually) ignorable.
- What shebang should I use?

### Line breaks, syntax validation, and linting

Bash scripts (I&#39;m using &quot;shell script&quot; pejoratively) need LF line breaks. If they have CRLF then executing them on the shell via `./script.sh` means you&#39;ll get weird errors.

[52 Are shell scripts sensitive to encoding and line endings?](https://stackoverflow.com/questions/39527571/are-shell-scripts-sensitive-to-encoding-and-line-endings)

[The case of Windows line-ending in bash-script](https://techblog.dorogin.com/case-of-windows-line-ending-in-bash-script-7236f056abe)

This could cause hours of debugging as the errors are non-intuitive and worse, sometimes the line breaks are added on lines that _haven&#39;t been changed,_ which means that _if that line is executed as part of an if-statement, it won&#39;t work but the rest of the script will._

Wrong line breaks need to be converted at many stages:

- While editing (so that you don&#39;t have to re-convert them when you run the script.)
- After committing (so that you don&#39;t share the wrong line breaks with everyone, and if your editor doesn&#39;t support a `.editorconfig`.)
- Before running CI/CD (if you uploaded the file directly from file upload to GitHub.)
- Renormalizing the line endings for everyone else.

#### While editing

Use a `.editorconfig` to automatically convert the file endings to LF on save. See [Visual Studio Code, line endings and a bash script](https://blog.thecraftingstrider.net/posts/tech/2019.09/vscode-line-endings-and-bash-script/) on how to do this.

#### After committing

Use a `.gitattributes` file and add the line `*.sh text eol=lf` to it. Also add in `Makefile text eol=lf` if you want Makefiles to work as well. You can also add a crlf rule for .cmd and .bat files, but that&#39;s a bit out of scope for this blog post.

#### Before running CI/CD

Bash files (usually) don&#39;t have any syntax validation before CI/CD. We build C#, Java, Python, and oodles of other files, why don&#39;t we check Bash files?

Set up a script to run [shellcheck](https://www.shellcheck.net/), a program that lints Bash files. It finds many common programming errors, including incorrectly quoted variables. Also, run bash -n on the file during CI/CD because shellcheck isn&#39;t 100% perfect at detecting syntax errors.

Also get your team members to run shellcheck before they push to CI/CD so that CI/CD doesn&#39;t fail unnecessarily.

Shellcheck says this script is fine, but `bash -n` says it is invalid (it is invalid):

```
#!/bin/bash
(scp -r s/!(t) test:/test)
```

That doesn&#39;t mean shellcheck is useless. Shellcheck is meant to find linting errors such as possible errors that cause unintended script execution errors. `Bash -n` is _just_ for syntax checking. You&#39;ll be hard-pressed to find any other articles about CI/CD and `bash -n` and as such I couldn&#39;t add any references to it.

Also, check the line endings by running dos2unix on the file (through CI/CD) and then comparing it with the input file. If they differ, then the line endings might be different. **Don&#39;t rewrite the file just on the CI/CD with dos2unix.** It will cause the files to slowly become out of sync with the teams&#39; versions. If you must, run it locally then push the changes if any.

#### Renormalizing it for everyone else

Run `git add --renormalize .`

[Git: how to renormalize line endings in all files in all revisions?](https://stackoverflow.com/questions/7156694/git-how-to-renormalize-line-endings-in-all-files-in-all-revisions)

### UTF-8 ignorables that aren&#39;t (usually) ignorable

See my other post [https://github.com/alexyorke/alexyorke.github.io/blob/master/utf-8-default-ignorables-you-should-not-ignore.md](https://github.com/alexyorke/alexyorke.github.io/blob/master/utf-8-default-ignorables-you-should-not-ignore.md) on how to identify invisible characters and why they cause issues.

### What shebang should I use?

Use `#!/usr/bin/env bash`. It&#39;ll be the same thing 99% of the time as `#!/bin/bash` except those cases where a different version of Bash is installed or preferred. This could mean having access to newer features that your script uses.

[Why is #!/usr/bin/env bash superior to #!/bin/bash?](https://stackoverflow.com/questions/21612980/why-is-usr-bin-env-bash-superior-to-bin-bash)
