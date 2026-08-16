# syntax=docker/dockerfile:1

FROM ruby:3.2-slim-bookworm

ENV BUNDLE_JOBS=4 \
    BUNDLE_RETRY=3 \
    JEKYLL_ENV=development

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        git \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/jekyll

COPY Gemfile ./
RUN bundle install

COPY . .

EXPOSE 4000 35729

CMD ["bundle", "exec", "jekyll", "serve", "--config", "_config.yml,_config.docker.yml", "--host", "0.0.0.0", "--port", "4000", "--livereload", "--livereload-port", "35729", "--drafts", "--future", "--force_polling"]
