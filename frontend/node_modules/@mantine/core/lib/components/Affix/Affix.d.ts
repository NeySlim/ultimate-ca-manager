import { BoxProps, ElementProps, Factory, MantineSize, StylesApiProps } from '../../core';
import { PortalProps } from '../Portal';
export type AffixStylesNames = 'root';
export type AffixCssVariables = {
    root: '--affix-z-index' | '--affix-top' | '--affix-left' | '--affix-bottom' | '--affix-right';
};
export interface AffixBaseProps {
    /** Root element `z-index` property, `200` by default */
    zIndex?: string | number;
    /** Determines whether component should be rendered within portal, `true` by default */
    withinPortal?: boolean;
    /** Props to pass down to the `Portal` component when `withinPortal` is set */
    portalProps?: Omit<PortalProps, 'children'>;
    /** Affix position on screen, defaults value is `{ bottom: 0, right: 0 }` */
    position?: {
        top?: MantineSize | (string & {}) | number;
        left?: MantineSize | (string & {}) | number;
        bottom?: MantineSize | (string & {}) | number;
        right?: MantineSize | (string & {}) | number;
    };
}
export interface AffixProps extends BoxProps, AffixBaseProps, StylesApiProps<AffixFactory>, ElementProps<'div'> {
}
export type AffixFactory = Factory<{
    props: AffixProps;
    ref: HTMLDivElement;
    stylesNames: AffixStylesNames;
    vars: AffixCssVariables;
}>;
export declare const Affix: import("../../core").MantineComponent<{
    props: AffixProps;
    ref: HTMLDivElement;
    stylesNames: AffixStylesNames;
    vars: AffixCssVariables;
}>;
