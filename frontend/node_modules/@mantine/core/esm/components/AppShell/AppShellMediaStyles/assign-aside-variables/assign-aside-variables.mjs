'use client';
import { keys } from '../../../../core/utils/keys/keys.mjs';
import { rem } from '../../../../core/utils/units-converters/rem.mjs';
import 'react';
import 'react/jsx-runtime';
import { getBreakpointValue } from '../../../../core/utils/get-breakpoint-value/get-breakpoint-value.mjs';
import '@mantine/hooks';
import 'clsx';
import '../../../../core/MantineProvider/Mantine.context.mjs';
import '../../../../core/MantineProvider/default-theme.mjs';
import '../../../../core/MantineProvider/MantineProvider.mjs';
import '../../../../core/MantineProvider/MantineThemeProvider/MantineThemeProvider.mjs';
import '../../../../core/MantineProvider/MantineCssVariables/MantineCssVariables.mjs';
import '../../../../core/Box/Box.mjs';
import '../../../../core/DirectionProvider/DirectionProvider.mjs';
import { getBaseSize } from '../get-base-size/get-base-size.mjs';
import { isPrimitiveSize } from '../is-primitive-size/is-primitive-size.mjs';
import { isResponsiveSize } from '../is-responsive-size/is-responsive-size.mjs';

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
  if (isPrimitiveSize(asideWidth)) {
    const baseSize = rem(getBaseSize(asideWidth));
    baseStyles["--app-shell-aside-width"] = baseSize;
    baseStyles["--app-shell-aside-offset"] = baseSize;
  }
  if (isResponsiveSize(asideWidth)) {
    if (typeof asideWidth.base !== "undefined") {
      baseStyles["--app-shell-aside-width"] = rem(asideWidth.base);
      baseStyles["--app-shell-aside-offset"] = rem(asideWidth.base);
    }
    keys(asideWidth).forEach((key) => {
      if (key !== "base") {
        minMediaStyles[key] = minMediaStyles[key] || {};
        minMediaStyles[key]["--app-shell-aside-width"] = rem(asideWidth[key]);
        minMediaStyles[key]["--app-shell-aside-offset"] = rem(asideWidth[key]);
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
    const breakpointValue = getBreakpointValue(aside.breakpoint, theme.breakpoints) - 0.1;
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

export { assignAsideVariables };
//# sourceMappingURL=assign-aside-variables.mjs.map
