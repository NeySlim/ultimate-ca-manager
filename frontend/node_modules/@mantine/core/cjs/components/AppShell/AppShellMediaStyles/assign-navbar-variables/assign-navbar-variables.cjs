'use client';
'use strict';

var keys = require('../../../../core/utils/keys/keys.cjs');
var rem = require('../../../../core/utils/units-converters/rem.cjs');
require('react');
require('react/jsx-runtime');
var getBreakpointValue = require('../../../../core/utils/get-breakpoint-value/get-breakpoint-value.cjs');
require('@mantine/hooks');
require('clsx');
require('../../../../core/MantineProvider/Mantine.context.cjs');
require('../../../../core/MantineProvider/default-theme.cjs');
require('../../../../core/MantineProvider/MantineProvider.cjs');
require('../../../../core/MantineProvider/MantineThemeProvider/MantineThemeProvider.cjs');
require('../../../../core/MantineProvider/MantineCssVariables/MantineCssVariables.cjs');
require('../../../../core/Box/Box.cjs');
require('../../../../core/DirectionProvider/DirectionProvider.cjs');
var getBaseSize = require('../get-base-size/get-base-size.cjs');
var isPrimitiveSize = require('../is-primitive-size/is-primitive-size.cjs');
var isResponsiveSize = require('../is-responsive-size/is-responsive-size.cjs');

function assignNavbarVariables({
  baseStyles,
  minMediaStyles,
  maxMediaStyles,
  navbar,
  theme,
  mode
}) {
  const navbarWidth = navbar?.width;
  const collapsedNavbarTransform = "translateX(calc(var(--app-shell-navbar-width) * -1))";
  const collapsedNavbarTransformRtl = "translateX(var(--app-shell-navbar-width))";
  if (navbar?.breakpoint && !navbar?.collapsed?.mobile) {
    maxMediaStyles[navbar?.breakpoint] = maxMediaStyles[navbar?.breakpoint] || {};
    maxMediaStyles[navbar?.breakpoint]["--app-shell-navbar-offset"] = "0px";
    maxMediaStyles[navbar?.breakpoint]["--app-shell-navbar-width"] = "100%";
    if (mode === "static") {
      maxMediaStyles[navbar?.breakpoint]["--app-shell-navbar-grid-width"] = "0px";
    }
  }
  if (isPrimitiveSize.isPrimitiveSize(navbarWidth)) {
    const baseSize = rem.rem(getBaseSize.getBaseSize(navbarWidth));
    baseStyles["--app-shell-navbar-width"] = baseSize;
    baseStyles["--app-shell-navbar-offset"] = baseSize;
    if (mode === "static") {
      baseStyles["--app-shell-navbar-grid-width"] = baseSize;
    }
  }
  if (isResponsiveSize.isResponsiveSize(navbarWidth)) {
    if (typeof navbarWidth.base !== "undefined") {
      baseStyles["--app-shell-navbar-width"] = rem.rem(navbarWidth.base);
      baseStyles["--app-shell-navbar-offset"] = rem.rem(navbarWidth.base);
      if (mode === "static") {
        baseStyles["--app-shell-navbar-grid-width"] = rem.rem(navbarWidth.base);
      }
    }
    keys.keys(navbarWidth).forEach((key) => {
      if (key !== "base") {
        minMediaStyles[key] = minMediaStyles[key] || {};
        minMediaStyles[key]["--app-shell-navbar-width"] = rem.rem(navbarWidth[key]);
        minMediaStyles[key]["--app-shell-navbar-offset"] = rem.rem(navbarWidth[key]);
        if (mode === "static") {
          minMediaStyles[key]["--app-shell-navbar-grid-width"] = rem.rem(navbarWidth[key]);
        }
      }
    });
  }
  if (navbar?.breakpoint && mode === "static") {
    minMediaStyles[navbar.breakpoint] = minMediaStyles[navbar.breakpoint] || {};
    minMediaStyles[navbar.breakpoint]["--app-shell-navbar-position"] = "sticky";
    minMediaStyles[navbar.breakpoint]["--app-shell-navbar-grid-row"] = "2";
    minMediaStyles[navbar.breakpoint]["--app-shell-navbar-grid-column"] = "1";
    minMediaStyles[navbar.breakpoint]["--app-shell-main-column-start"] = "2";
  }
  if (navbar?.collapsed?.desktop) {
    const breakpointValue = navbar.breakpoint;
    minMediaStyles[breakpointValue] = minMediaStyles[breakpointValue] || {};
    minMediaStyles[breakpointValue]["--app-shell-navbar-transform"] = collapsedNavbarTransform;
    minMediaStyles[breakpointValue]["--app-shell-navbar-transform-rtl"] = collapsedNavbarTransformRtl;
    if (mode === "fixed") {
      minMediaStyles[breakpointValue]["--app-shell-navbar-offset"] = "0px !important";
    } else {
      minMediaStyles[breakpointValue]["--app-shell-navbar-width"] = "0px";
      minMediaStyles[breakpointValue]["--app-shell-navbar-display"] = "none";
      minMediaStyles[breakpointValue]["--app-shell-main-column-start"] = "1";
    }
  }
  if (navbar?.collapsed?.mobile) {
    const breakpointValue = getBreakpointValue.getBreakpointValue(navbar.breakpoint, theme.breakpoints) - 0.1;
    maxMediaStyles[breakpointValue] = maxMediaStyles[breakpointValue] || {};
    maxMediaStyles[breakpointValue]["--app-shell-navbar-width"] = "100%";
    maxMediaStyles[breakpointValue]["--app-shell-navbar-offset"] = "0px";
    if (mode === "static") {
      maxMediaStyles[breakpointValue]["--app-shell-navbar-grid-width"] = "0px";
    }
    maxMediaStyles[breakpointValue]["--app-shell-navbar-transform"] = collapsedNavbarTransform;
    maxMediaStyles[breakpointValue]["--app-shell-navbar-transform-rtl"] = collapsedNavbarTransformRtl;
  }
}

exports.assignNavbarVariables = assignNavbarVariables;
//# sourceMappingURL=assign-navbar-variables.cjs.map
