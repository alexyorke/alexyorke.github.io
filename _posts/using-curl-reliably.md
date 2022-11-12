---
title: "Using curl reliably"
date: 2021-02-16
---

Curl is a useful command which downloads or uploads data to a remote resource. While it is very useful, it\'s important to consider the slight-but-very-important differences between very similar flags. Certain combinations of flags and redirects, when used together, can cause security issues or unintended consequences like tests that report as passing when in fact they failed.

### "curl -o file" and "\>" have *slightly* different side-effects

On first glance, curl -o file and running curl \> file do the same thing. They both write to a file. Why does it matter if one uses -o and the other uses the shell?

The command curl -o proactively makes a request before it checks if the file it\'s trying to write to can be written to. The redirect operator does not.

#### Making a GET vs not making one

Its differences are apparent in failure modes.

-   curl -o /dev/full "https://example.com" will send a GET request.

-   curl "https://example.com" \> /dev/full does not send any HTTP requests.

This has many implications:

-   If you're trying to warm up a server and are writing the pid of the server to a file, the first command will send a request even though the file couldn't be written to.

-   If you're running curl in a loop and trying to download a file (and retry on failure), the second option won't DoS the server if the file isn't writable. This could cause issues with rate limited APIs.

This can be flaky because the server may only expect to get a single request, but it could receive over one if the curl command "failed" but it sent a request.

#### Different exit codes

The command curl -o will proactively try to make an HTTP connection before it saves to a file.

If curl fails, it could return error code 1, 3, 6, 7, [among many others](https://curl.se/libcurl/c/libcurl-errors.html).

If the command curl "https://example.com" \> /dev/full fails, then it will return exit code 1, regardless of whether the host was found. This is because it doesn't make any HTTP requests, and so the redirect operator fails.

#### Considerations

-   Exit codes depend on how you are invoking curl. Ensure that you are handling those codes correctly.

-   The -o flag and the pipe redirection operator (\>) operate differently. Ensure you know how they behave under different failure conditions.

### "curl \--data-binary \@file" and "curl -X POST -T file" aren't the same; they have *vastly* different memory considerations

When using curl \--data-binary, [the file is stored](https://stackoverflow.com/questions/51222398/using-curl-data-binary-option-out-of-memory) in memory. If the file is large, then there might not be enough memory available and curl might crash.

The command curl -X POST -T file doesn't load the entire file into memory, however, it is not identical to curl \--data-binary \@file.

Create a file named "test" in the current directory with the contents "test-text". Then run:

curl -X POST -T test [https://pie.dev/post](https://pie.dev/post)

{

\"args\": {},

**\"data\": \"test-text\\n\",**

\"files\": {},

\"form\": {},

\"headers\": {

\"Accept\": \"\*/\*\",

\"Accept-Encoding\": \"gzip\",

\"Cdn-Loop\": \"cloudflare\",

\"Cf-Connecting-Ip\": \"\<my ip\>\",

\"Cf-Ipcountry\": \"CA\",

\"Cf-Ray\": \"\<id\>\",

\"Cf-Request-Id\": \"\<id\>\",

\"Cf-Visitor\": \"{\\\"scheme\\\":\\\"https\\\"}\",

\"Connection\": \"Keep-Alive\",

\"Content-Length\": \"10\",

\"Host\": \"pie.dev\",

\"User-Agent\": \"curl/7.58.0\"

},

\"json\": null,

\"origin\": \"\<my-ip\>\",

\"url\": \"https://pie.dev/post\"

}

While curl \--data-binary \@test https://pie.dev/post gives:

{

\"args\": {},

\"data\": \"\",

\"files\": {},

\"form\": {

**\"test-text\\n\": \"\"**

},

\"headers\": {

\"Accept\": \"\*/\*\",

\"Accept-Encoding\": \"gzip\",

\"Cdn-Loop\": \"cloudflare\",

\"Cf-Connecting-Ip\": \"\<my-ip\>\",

\"Cf-Ipcountry\": \"CA\",

\"Cf-Ray\": \"\<id\>\",

\"Cf-Request-Id\": \"\<id\>\",

\"Cf-Visitor\": \"{\\\"scheme\\\":\\\"https\\\"}\",

\"Connection\": \"Keep-Alive\",

\"Content-Length\": \"10\",

\"Content-Type\": \"application/x-www-form-urlencoded\",

\"Host\": \"pie.dev\",

\"User-Agent\": \"curl/7.58.0\"

},

\"json\": null,

\"origin\": \"\<my-ip\>\",

\"url\": \"https://pie.dev/post\"

}

#### Considerations

The server *might* respond the same way to both requests, but it can determine which method was used. Make sure that your server supports the -X POST method if you plan to use it.

### Use \--retry, \--connect-timeout, and other switches to retry on failure

Curl has [many flags](https://stackoverflow.com/questions/42873285/curl-retry-mechanism) that are useful when you need to retry a request. A request could fail for many reasons, so retrying it prevents having to re-run the entire test.

#### Considerations

-   Don't retry an infinite number of times.

-   Be careful when retrying internal APIs. This could indicate that they are flaky if it is a production endpoint. If it is used for checking if a server has finished warming up then it is usually ok.

### Use -L to follow redirects

By default, curl doesn't follow HTTP redirects. If a file is moved or redirects to a new URL, curl won't download the file like your browser will. Use the -L flag to follow redirects.

### Be careful when using -J and -O

These options automatically download to a file whose name is specified from the server. If the server changes its filename, then the download filename could change. Scripts that depend on a certain filename could break.

Also, if the server stops specifying a filename one day, you'll get an error like "Warning: Remote filename has no length!" and no files will be downloaded. This is most certainly an issue.

### Let curl parse the status codes; use the -w flag like -w \'%{http_code}\'

Curl has a -w flag which corresponds to parameters in the output. This is a much better alternative than parsing the CLI output by hand.

#### Considerations

Don't parse the CLI output unless it's absolutely required. This is because the CLI output could change, and also adds additional complexity, including having to program for edge cases. Use the -w flag instead to get clean, consistent output.

### Preventing accidental globs with \--globoff

Curl has a special syntax for fetching multiple files; it uses square brackets and curly braces. If you don't plan to use those, then it makes sense to turn them off in-case your URL requires using those unescaped. For example, inserting variables within URLs and those variables are from a set of test cases that contain those characters. For example, \[1-2\] can be interpreted as downloading two files. This can cause unintended consequences.

### Prevent unintended connections with \--proto=http,https

If a protocol in a URL isn't specified curl will try to guess what it is. It could guess FTP or SMTP, among many other protocols. This could lead to unintended side effects like connecting to the wrong server.

Only allowing the protocols that you use will prevent this side-effect. You can also use \--proto=https to only allow https and block http.

### Be very careful with -k, or \--insecure

This disables SSL cert verification and can allow a MITM attack. This option should only be used for local testing/debugging and not used in production.

### The status code for a multi-file transfer is just the last file, use \--fail-early to fail once one has failed

If you transfer multiple files using curl and are checking the status of the output (as you should), you might be surprised to find that the status of the command is successful even if one of the files failed to transfer. This is because curl just returns the status of the last file transferred, not any subsequent ones. So if all files failed to transfer except the last one, then the command will report a success.

This can cause havoc while testing because you might assume that the other requests were successful when in fact they were not. Use the \--fail-early flag to stop and return an error code once a transfer was unsuccessful.

### When piping curl's output, be careful about getting disconnected

Sometimes you may want to execute a script and pipe it to bash from curl. Or, it could be another command which reads line-by-line. The pattern is usually curl ... \| bash. However, there are some issues with this:

-   If there is a long delay in the script (a sleep command or taking a long time to run a command), then the pipe will block. This means that curl has to pause downloading. If the downloading paused for too long, the server might disconnect you. If the script takes 20 minutes to run, it could mean a connection to the server for 20 minutes. **This means that your script might not download and thus won't run.**

-   The server also will have hints that you are running curl and could switch your request's contents. This could be a security issue.

#### Considerations

Download the script first before executing it. That way you can check the script's hash before running it (to make sure that it hasn't been tampered with), and won't depend on a constant connection to the server. Try using the -N flag, which stands for \--no-buffer.
