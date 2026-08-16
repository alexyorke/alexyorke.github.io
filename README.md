Welcome to my website.

Currently, not much is on the homepage yet. You can go to my Blog in the nav bar.

Disclaimer: The views and opinions expressed on this blog are my own and do not necessarily reflect those of my employer, past or present.

## Local preview with Docker

Install Docker Desktop, then run:

```shell
docker compose up --build
```

Open <http://localhost:4000>. The preview includes drafts and future-dated posts, watches the bind-mounted repository for changes, and reloads the browser automatically.

Stop the server with `Ctrl+C`. To render the site once without starting the preview server, run:

```shell
docker compose run --rm site bundle exec jekyll build --config _config.yml,_config.docker.yml --drafts --future
```
