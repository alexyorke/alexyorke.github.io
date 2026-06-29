FROM ruby:4.0-bookworm AS build

WORKDIR /site

RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential git libssl-dev pkg-config \
  && rm -rf /var/lib/apt/lists/*

COPY Gemfile ./

RUN gem install bundler -v 2.3.25 \
  && bundle install

COPY . .

ENV JEKYLL_ENV=production

RUN bundle exec jekyll build

FROM nginx:alpine

COPY --from=build /site/_site /usr/share/nginx/html

EXPOSE 80
