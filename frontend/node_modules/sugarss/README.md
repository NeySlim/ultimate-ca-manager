# SugarSS

<img align="right" width="120" height="155"
     title="SugarSS logo by Maria Keller"
     src="http://postcss.github.io/sugarss/logo.svg">

Indent-based CSS syntax for [PostCSS].

```sass
a
  color: blue

.multiline,
.selector
  box-shadow: 1px 0 9px rgba(0, 0, 0, .4),
              1px 0 3px rgba(0, 0, 0, .6)

// Mobile
@media (max-width: 400px)
  .body
    padding: 0 10px
```

As any PostCSS custom syntax, SugarSS has source map, [stylelint]
and [postcss-sorting] support out-of-box.

It was designed to be used with [postcss-simple-vars] and [postcss-nested].
But you can use it with any PostCSS plugins
or use it without any PostCSS plugins.
With [postcss-mixins] you can use `@mixin` syntax as in Sass.

<a href="https://evilmartians.com/?utm_source=sugarss">
  <img src="https://evilmartians.com/badges/sponsored-by-evil-martians.svg"
       alt="Sponsored by Evil Martians" width="236" height="54">
</a>

[postcss-mixins]:              https://github.com/postcss/postcss-mixins
[postcss-nested]:              https://github.com/postcss/postcss-nested
[postcss-simple-vars]:         https://github.com/postcss/postcss-simple-vars
[postcss-sorting]:             https://github.com/hudochenkov/postcss-sorting
[stylelint]:                   http://stylelint.io/
[PostCSS]:                     https://github.com/postcss/postcss


## Docs
Read full docs **[here](https://github.com/postcss/sugarss#readme)**.
