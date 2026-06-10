---
title: Alex Yorke (Alex York)
description: Personal website of Alex Yorke, also known as Alex York. Writing on CI/CD, testing, reliability, shell tooling, and functional programming.
permalink: /
---
<section class="home-intro">
  <p class="eyebrow">Software engineering writing</p>
  <h1>Alex Yorke</h1>
  <p>
    <strong>Alex Yorke</strong>, also known as <strong>Alex York</strong>, writes practical articles on CI/CD, testing, debugging, shell tooling, reliability, and functional programming.
  </p>
  <p>This is the personal website of Alex Yorke, with long-form technical notes, investigations, and essays for working software engineers.</p>
  <p class="home-links">
    <a href="{{ '/about/' | relative_url }}">About Alex Yorke</a>
    <span>/</span>
    <a href="{{ '/blog/' | relative_url }}">Browse the blog</a>
    <span>/</span>
    <a href="{{ '/feed.xml' | relative_url }}">RSS</a>
  </p>
</section>

<section class="section-heading">
  <div>
    <p class="eyebrow">Recent writing</p>
    <h2>Latest posts</h2>
  </div>
  <a class="text-link" href="{{ '/blog/' | relative_url }}">See the full archive</a>
</section>

<div class="home-post-list">
  {% assign recent_posts = site.posts | slice: 0, 3 %}
  {% for post in recent_posts %}
    <article class="home-post-item">
      <p class="post-card-meta">
        <time datetime="{{ post.date | date_to_xmlschema }}">{{ post.date | date: "%B %-d, %Y" }}</time>
      </p>
      <h3><a href="{{ post.url | relative_url }}">{{ post.title }}</a></h3>
      <p>{{ post.description | default: post.excerpt | strip_html | normalize_whitespace | escape | truncatewords: 36 }}</p>
      <a class="text-link" href="{{ post.url | relative_url }}">Read article</a>
    </article>
  {% endfor %}
</div>
