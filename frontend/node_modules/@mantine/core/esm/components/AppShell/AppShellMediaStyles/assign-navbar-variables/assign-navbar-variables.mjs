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
  if (isPrimitiveSize(navbarWidth)) {
    const baseSize = rem(getBaseSize(navbarWidth));
    baseStyles["--app-shell-navbar-width"] = baseSize;
    baseStyles["--app-shell-navbar-offset"] = baseSize;
    if (mode === "static") {
      baseStyles["--app-shell-navbar-grid-width"] = baseSize;
    }
  }
  if (isResponsiveSize(navbarWidth)) {
    if (typeof navbarWidth.base !== "undefined") {
      baseStyles["--app-shell-navbar-width"] = rem(navbarWidth.base);
      baseStyles["--app-shell-navbar-offset"] = rem(navbarWidth.base);
      if (mode === "static") {
        baseStyles["--app-shell-navbar-grid-width"] = rem(navbarWidth.base);
      }
    }
    keys(navbarWidth).forEach((key) => {
      if (key !== "base") {
        minMediaStyles[key] = minMediaStyles[key] || {};
        minMediaStyles[key]["--app-shell-navbar-width"] = rem(navbarWidth[key]);
        minMediaStyles[key]["--app-shell-navbar-offset"] = rem(navbarWidth[key]);
        if (mode === "static") {
          minMediaStyles[key]["--app-shell-navbar-grid-width"] = rem(navbarWidth[key]);
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
    const breakpointValue = getBreakpointValue(navbar.breakpoint, theme.breakpoints) - 0.1;
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

export { assignNavbarVariables };
//# sourceMappingURL=assign-navbar-variables.mjs.map
