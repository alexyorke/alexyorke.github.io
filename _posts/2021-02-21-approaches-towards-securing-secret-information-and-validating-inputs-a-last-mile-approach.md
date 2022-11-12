---
title: "Approaches towards securing secret information and validing inputs, a last mile approach"
date: 2021-02-21
---

When developing applications, chances are you'll have to deal with passwords, API keys, or other sensitive information. Or, it could be untrusted information like user input.

### Last mile approach to user input validation and protection

It's clear that if you're inserting data into a database, you have to use parameterized queries and/or sanitize user input. While there are many pieces of security software which can prevent accidently using user input in non-parameterized queries, it could be even better to make it difficult to do the wrong thing to start with. It can also be ambiguous if the user input is mixed with other strings, which may or may not be safe.

There's nothing stopping you from concatenating a string in a MySQL query with user input, for example. Sure, you know better, but it's even *better* to not let it happen to start with. Perhaps you've missed your morning coffee or have an emergency push to production.

Imagine a new class called UserInput which contains the user's input from a form. It's just a class with a string containing the user's input and a set of methods for accessing it securely (by passing it through a sanitizer.) There could be a few accessor methods: one for SQL queries, another for displaying the data on an HTML page, and another for, say, checking if the string is just whitespace or empty.

This hypothetical framework produces UserInput objects when a user submits a form. You now are dealing with a UserInput object rather than a raw string.

What does this mean?

-   If I pass it to a MySQL parameterized query, the query parameterizer will call the MySQL query sanitizer on the UserInput object and use that. It has to call it to get the user's input. The object is just an object.

-   If I try to concatenate a UserInput object with the MySQL query, my application won't build. That's a good thing.

-   Similarly, if I try to print it to the screen (e.g. on an HTML page), the framework will call the internal sanitizeHtml method on the UserInput object.

This isn't a new concept per-se, Perl has a similar methodology.

### Last mile approach to passwords

There's many, many, ways to deal with passwords. There's Azure KeyVault, Hashicorp Vault, and many others. Kubernetes has sealed secrets. You can put it in a separate file that's not included in your build. Sometimes they can make use of a TPM and encrypt the secrets. But at some point you'll need to *access* the secret. If it's an API key, you'll have to pass it to a method, or if it's a password it'll have to be passed to a method to do a login.

But here's the problem: you've done all of the work securing the values, now they're sitting in a string when you have to pass it to another method. And you're trusting that that method doesn't accidentally leak it, or that that password string doesn't go anywhere else or isn't accessed by any other methods. Or isn't logged. Or isn't accidently serialized.

There are many services to warn you if you've leaked an API key, and countless others that will regex the logs to find for secrets. While that's good to have, it's too late. It's already been logged to disk. There's latency between scanning the keys and when they've been leaked. What if they've been leaked to the user?

Let's start with the properties of passwords. Where and how are passwords used?

-   They usually need to be used once and then you're logged in. The server doesn't need to keep the password around sitting in memory or floating around in an application scope. It's usually in a database or in a vault, hashed.

-   Depending on how large the application is, they might have to be used in several locations. So, they have to flow through the system securely.

If I have a login function that calls an authentication function, the login function doesn't need to know what the password is. It needs to pass it to the authentication function. The authentication function might pass it to another function, in which case it doesn't care what the password is. Nor should it.

What if we could turn the password into an opaque blob? What if we could also limit its scope and tell it to self destruct when it leaves the scope? Well, we might be able to get close to doing that.

**The following is a hypothetical concept which *prevents* accidentally logging passwords. Since it does not encrypt the credentials, it is not 100% safe but it is *better* than simply using a string. This concept is useful when you have no other choice to pass around credentials, or have to temporarily convert it to a string.**

Imagine a class called Credentials that held the username and password. This object is created from a hypothetical framework's special credential form. Internally, the framework would create this object and then seal it (so that we can't change the contents.) Credentials would also implement IDisposable which means that if we use it in a "using" statement, then the Dispose() method can erase the credentials for us. Then the framework would give the Credentials object to us.

What's the purpose of making Credentials an object? There are several reasons:

-   By default, trying to log an object just produces its memory location, not the contents. If you want to be safer you could override ToString() with an empty string.

-   You can't usually easily mix objects together. You can't append an object to another one like you can do with string concatenation.

-   With objects, you can only allow access to the inside data through special methods. These methods can call other methods or trigger events. Granted, it's not safe from reflection.

What this means is you're given a Credentials object, your login function can't see what's inside it. It doesn't have to. If it tries to log it by accident nothing will happen. The last layer however can unwrap it and get the value. That last layer could be a system-level call, for example.

There's also some other benefits:

-   The framework could only accept Credentials objects in its public methods. This means that all layers down until the final layer can't log the credentials by accident.

#### Wait, this just sounds like .NET's deprecated SecureString!

It's similar, but not exactly. SecureString aimed to also encrypt the string in memory, but on other systems it couldn't be guaranteed. Also, Microsoft warns not to use it anymore.

This solution doesn't guarantee to encrypt anything, but instead makes the credentials more difficult to log. Calling Dispose may not guarantee that the string is actually erased, either.

### Caveats

-   These are pushes to make your application *slightly* more secure, but they are not a panacea. Application security is very complicated.

-   It's still possible to access the protected information. It's still a string, just less accessible to everyone.

-   To be effective, it would require a major framework overhaul.
