# PostCSS Mixins

<img align="right" width="135" height="95"
     title="Philosopher’s stone, logo of PostCSS"
     src="https://postcss.org/logo-leftp.svg">

[PostCSS] plugin for mixins.

Note, that you must set this plugin before [postcss-simple-vars]
and [postcss-nested].

```css
@define-mixin icon $network, $color: blue {
    .icon.is-$(network) {
        color: $color;
        @mixin-content;
    }
    .icon.is-$(network):hover {
        color: white;
        background: $color;
    }
}

@mixin icon twitter {
    background: url(twt.png);
}
@mixin icon youtube, red {
    background: url(youtube.png);
}
```

```css
.icon.is-twitter {
    color: blue;
    background: url(twt.png);
}
.icon.is-twitter:hover {
    color: white;
    background: blue;
}
.icon.is-youtube {
    color: red;
    background: url(youtube.png);
}
.icon.is-youtube:hover {
    color: white;
    background: red;
}
```

[postcss-utilities] collection is better for `clearfix` and other popular hacks.
For simple cases you can use [postcss-define-property].

[postcss-define-property]: https://github.com/daleeidd/postcss-define-property
[postcss-utilities]:       https://github.com/ismamz/postcss-utilities
[postcss-simple-vars]:     https://github.com/postcss/postcss-simple-vars
[postcss-nested]:          https://github.com/postcss/postcss-nested
[PostCSS]:                 https://github.com/postcss/postcss

<a href="https://evilmartians.com/?utm_source=postcss-mixins">
  <img src="https://evilmartians.com/badges/sponsored-by-evil-martians.svg"
       alt="Sponsored by Evil Martians" width="236" height="54">
</a>


## Docs
Read full docs **[here](https://github.com/postcss/postcss-mixins#readme)**.
