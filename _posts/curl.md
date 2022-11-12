# An interesting feature in curl on powershell

Something I just found out was that curl has a `-usebasicparsing` flag which shows information about an HTTP request. For example,

`curl https://example.com -usebasicparsing` gives:

```
StatusCode        : 200
StatusDescription : OK
Content           : <!doctype html>
                    <html>
                    <head>
                        <title>Example Domain</title>

                        <meta charset="utf-8" />
                        <meta http-equiv="Content-type" content="text/html; charset=utf-8" />
                        <meta name="viewport" conten...
RawContent        : HTTP/1.1 200 OK
                    Age: 34688
                    Vary: Accept-Encoding
                    X-Cache: HIT
                    Content-Length: 1256
                    Cache-Control: max-age=604800
                    Content-Type: text/html; charset=UTF-8
                    Date: Tue, 15 Sep 2020 01:35:58 GMT
                    Expi...
Forms             :
Headers           : {[Age, 34688], [Vary, Accept-Encoding], [X-Cache, HIT], [Content-Length, 1256]...}
Images            : {}
InputFields       : {}
Links             : {@{outerHTML=<a href="https://www.iana.org/domains/example">More information...</a>; tagName=A;
                    href=https://www.iana.org/domains/example}}
ParsedHtml        :
RawContentLength  : 1256
```

Sadly, I can't seem to get it to work on Ubuntu.
