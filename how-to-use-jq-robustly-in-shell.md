Jq is a command-line JSON parser. It is very powerful and can even parse messy JSON. However, it has a few useful features to ensure output correctness and safety. As with all commands, it has some behaviors on failure which may or may not be desirable.

Knowing about the pitfalls and workarounds allow you to use jq more robustly and avoid changing it with other commands which can cause parsing issues later on that are difficult to debug.

### Use jq -r if you don't want quotes; don't use tr -d

Say you have a value in a JSON string that has quotes but you want to remove the quotes. You could do:

echo \"{\\\"x\\\":\\\"3\\\"}\" \| jq .x \| tr -d \'\"\' which returns 3.

The issue is that you're assuming that the JSON will have no quoted values. For example, this returns the wrong value:

echo \"{\\\"x\\\": \\\"\\\\\\\"Three\\\\\\\"\\\" }\" \| jq .x \| tr -d \'\"\' returns \\Three\\ instead of just the word "Three" (with quotes.) This was probably not intended.

If you use -r:

echo \"{\\\"x\\\": \\\"\\\\\\\"Three\\\\\\\"\\\" }\" \| jq -r .x

The output is "Three" (with quotes) which probably was intended.

### If the JSON isn't valid, jq will stop parsing and will print incomplete output

Be careful when parsing documents that could be invalid JSON because jq will print the first part that parsed correctly. If you're piping it, it may appear that it was parsed in its entirety. Always check status codes to ensure that the entire JSON block was parsed.

For example, I have a JSON document with one syntactically invalid entry but several entries before it are valid.

I run jq .\[\].friends test and get:

\...

\[

{

\"id\": 0,

\"name\": \"Rosario Melendez\"

},

{

\"id\": 1,

\"name\": \"Melendez Brennan\"

},

{

\"id\": 2,

\"name\": \"Vincent Spence\"

}

\]

parse error: Expected separator between values at line 448, column 7

I get output, but that output is incomplete. Ensure you check the status code from jq (in this case it was 4.) If I stored it in a variable, I would get a string but that string would be invalid because the parsing error didn't parse the entire file. If I just checked if the variable's length wasn't zero, then I wouldn't be getting the right output.

#### Just use set -e\...right? Right?

You may think that set -e will help. It can, if the output isn't piped. If it is piped, then the receiving program could line-buffer the input and start processing it when it could be invalid or incomplete.

It's easy to test this. Simply run:

\#!/bin/bash

set -e

true \| jq invalid \| echo test

echo \"I am still running\"

The output is "test" followed by "I am still running" (although some errors), even though the command jq invalid failed (because the file doesn't exist.) The script still continued to run even though one of the lines returned a failure code. Also, the exit code from the script is 0, indicating success even though it was unsuccessful.

#### Considerations

Use jq's empty filter to validate the file before parsing, or check the error code after parsing the JSON.

### Be careful with jq -r and newlines

Let's go back to an example file. You run cat test \| jq -c .\[\].friends and get the following output:

\[{\"id\":0,\"name\":\"Cherie\\nFrederick\"},{\"id\":1,\"name\":\"Mcclure Howell\"},{\"id\":2,\"name\":\"Skinner Leon\"}\]

\[{\"id\":0,\"name\":\"Dana Stout\"},{\"id\":1,\"name\":\"Stacy Irwin\"},{\"id\":2,\"name\":\"Everett Paul\"}\]

\[{\"id\":0,\"name\":\"Billie Douglas\"},{\"id\":1,\"name\":\"Ebony Acosta\"},{\"id\":2,\"name\":\"Hunt Strickland\"}\]

\[{\"id\":0,\"name\":\"Mcclain Roberts\"},{\"id\":1,\"name\":\"Frankie Wynn\"},{\"id\":2,\"name\":\"Mckay Sanders\"}\]

\[{\"id\":0,\"name\":\"Rosario Melendez\"},{\"id\":1,\"name\":\"Melendez Brennan\"},{\"id\":2,\"name\":\"Vincent Spence\"}\]

Each friend is on a line by themselves. This means I can loop over the lines and parse each JSON line individually, right? Well, in this example yes. If the names contain newlines, though, then you'll have broken JSON:

cat test \| jq -c .\[\].friends \| jq -r .\[\].name

**Cherie**

**Frederick**

Mcclure Howell

Skinner Leon

Dana Stout

...

Here, Cherie and Frederick are on two seperate lines. If you were to parse them, then the names wouldn't match.

#### Considerations

Use jq -0 instead of -r to delimit using null characters.

### Don't quote the output yourself, use -R

Wrapping the output in double quotes doesn't guarantee that the characters will be escaped correctly if the input contains double quotes.

### Use -a for escaping unicode characters

Depending on the JSON parser or other parsers in the pipeline, it might not expect non-ASCII chars.

If you are logging to a file and the logger doesn't expect UTF-8 output (and parses it as ASCII), then some characters could become corrupted.

For example,

echo \"Á\" \| jq -R yields \"Á" (with quotes.)

The -a switch changes this behavior and replaces them with escape sequences:

echo \"Á\" \| jq -a -R yields \"\\u00c1\" (with quotes.)

#### Considerations

Use -a when you need unicode safety.

### Use \@filters instead of \$(\...) when concatenating strings

Running this command produces the right output,

echo \"{\\\"page\\\": 3}\" \| echo \"https://example.com/search?id=\$(jq .page)\" (outputs [[https://example.com/search?id=3]{.ul}](https://example.com/search?id=3)).

But it gets dangerous if the number turns into text that contains non-URI safe characters:

echo \"{\\\"page\\\": \\\"\[3-2\]\\\"}\" \| echo \"https://example.com/search?id=\$(jq .page)\" which returns [[https://example.com/search?id=\"\[3]{.ul}](https://example.com/search?id=%22%5B3)-2\]\" . If you were to pipe this URL into curl, curl interprets the square brackets as a URL range. Curl fails to download that URL with the error, "curl: (3) \[globbing\] bad range in column 26".

However, running:

echo \"{\\\"page\\\": \\\"\[3-2\]\\\"}\" \| jq \'\@uri \"[[https://www.google.com/search?q=\\(.page)]{.ul}](https://www.google.com/search?q=%5C(.page))\"\' which returns \"[[https://www.google.com/search?q=%5B3-2%5D]{.ul}](https://www.google.com/search?q=%5B3-2%5D)\". This is URL safe.

#### Considerations

Use jq's filters when concatenating inputs from multiple sources. Look into the \@sh filter for creating shell compatible output to ensure command interoperability.
