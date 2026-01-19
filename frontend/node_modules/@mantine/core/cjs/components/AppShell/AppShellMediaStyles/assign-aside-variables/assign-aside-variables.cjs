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

function assignAsideVariables({
  baseStyles,
  minMediaStyles,
  maxMediaStyles,
  aside,
  theme,
  mode
}) {
  const asideWidth = aside?.width;
  const collapsedAsideTransform = "translateX(var(--app-shell-aside-width))";
  const collapsedAsideTransformRtl = "translateX(calc(var(--app-shell-aside-width) * -1))";
  if (aside?.breakpoint && !aside?.collapsed?.mobile) {
    maxMediaStyles[aside?.breakpoint] = maxMediaStyles[aside?.breakpoint] || {};
    if (mode === "fixed") {
      maxMediaStyles[aside?.breakpoint]["--app-shell-aside-width"] = "100%";
      maxMediaStyles[aside?.breakpoint]["--app-shell-aside-offset"] = "0px";
    } else {
      maxMediaStyles[aside?.breakpoint]["--app-shell-aside-width"] = "0px";
      maxMediaStyles[aside?.breakpoint]["--app-shell-aside-offset"] = "0px";
    }
  }
  if (isPrimitiveSize.isPrimitiveSize(asideWidth)) {
    const baseSize = rem.rem(getBaseSize.getBaseSize(asideWidth));
    baseStyles["--app-shell-aside-width"] = baseSize;
    baseStyles["--app-shell-aside-offset"] = baseSize;
  }
  if (isResponsiveSize.isResponsiveSize(asideWidth)) {
    if (typeof asideWidth.base !== "undefined") {
      baseStyles["--app-shell-aside-width"] = rem.rem(asideWidth.base);
      baseStyles["--app-shell-aside-offset"] = rem.rem(asideWidth.base);
    }
    keys.keys(asideWidth).forEach((key) => {
      if (key !== "base") {
        minMediaStyles[key] = minMediaStyles[key] || {};
        minMediaStyles[key]["--app-shell-aside-width"] = rem.rem(asideWidth[key]);
        minMediaStyles[key]["--app-shell-aside-offset"] = rem.rem(asideWidth[key]);
      }
    });
  }
  if (aside?.breakpoint && mode === "static") {
    minMediaStyles[aside.breakpoint] = minMediaStyles[aside.breakpoint] || {};
    minMediaStyles[aside.breakpoint]["--app-shell-aside-position"] = "sticky";
    minMediaStyles[aside.breakpoint]["--app-shell-aside-grid-row"] = "2";
    minMediaStyles[aside.breakpoint]["--app-shell-aside-grid-column"] = "3";
    minMediaStyles[aside.breakpoint]["--app-shell-main-column-end"] = "3";
  }
  if (aside?.collapsed?.desktop) {
    const breakpointValue = aside.breakpoint;
    minMediaStyles[breakpointValue] = minMediaStyles[breakpointValue] || {};
    minMediaStyles[breakpointValue]["--app-shell-aside-transform"] = collapsedAsideTransform;
    minMediaStyles[breakpointValue]["--app-shell-aside-transform-rtl"] = collapsedAsideTransformRtl;
    if (mode === "fixed") {
      minMediaStyles[breakpointValue]["--app-shell-aside-offset"] = "0px !important";
    } else {
      minMediaStyles[breakpointValue]["--app-shell-aside-width"] = "0px";
      minMediaStyles[breakpointValue]["--app-shell-aside-display"] = "none";
      minMediaStyles[breakpointValue]["--app-shell-main-column-end"] = "-1";
    }
    minMediaStyles[breakpointValue]["--app-shell-aside-scroll-locked-visibility"] = "hidden";
  }
  if (aside?.collapsed?.mobile) {
    const breakpointValue = getBreakpointValue.getBreakpointValue(aside.breakpoint, theme.breakpoints) - 0.1;
    maxMediaStyles[breakpointValue] = maxMediaStyles[breakpointValue] || {};
    if (mode === "fixed") {
      maxMediaStyles[breakpointValue]["--app-shell-aside-width"] = "100%";
      maxMediaStyles[breakpointValue]["--app-shell-aside-offset"] = "0px";
    } else {
      maxMediaStyles[breakpointValue]["--app-shell-aside-width"] = "0px";
    }
    maxMediaStyles[breakpointValue]["--app-shell-aside-transform"] = collapsedAsideTransform;
    maxMediaStyles[breakpointValue]["--app-shell-aside-transform-rtl"] = collapsedAsideTransformRtl;
    maxMediaStyles[breakpointValue]["--app-shell-aside-scroll-locked-visibility"] = "hidden";
  }
}

exports.assignAsideVariables = assignAsideVariables;
//# sourceMappingURL=assign-aside-variables.cjs.map
