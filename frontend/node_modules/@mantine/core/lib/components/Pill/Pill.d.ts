import { BoxProps, ElementProps, Factory, MantineRadius, MantineSize, StylesApiProps } from '../../core';
import { CloseButtonProps } from '../CloseButton';
import { PillGroup } from './PillGroup/PillGroup';
export type PillStylesNames = 'root' | 'label' | 'remove';
export type PillVariant = 'default' | 'contrast';
export type PillCssVariables = {
    root: '--pill-fz' | '--pill-radius' | '--pill-height';
};
export interface PillProps extends BoxProps, StylesApiProps<PillFactory>, ElementProps<'div'> {
    /** Controls pill `font-size` and `padding`, `'sm'` by default */
    size?: MantineSize;
    /** Determines whether the remove button should be displayed, `false` by default */
    withRemoveButton?: boolean;
    /** Called when the remove button is clicked */
    onRemove?: () => void;
    /** Props passed down to the remove button */
    removeButtonProps?: CloseButtonProps & React.ComponentPropsWithoutRef<'button'>;
    /** Key of `theme.radius` or any valid CSS value to set border-radius. Numbers are converted to rem. `'xl'` by default. */
    radius?: MantineRadius;
    /** If pill is disabled it has higher contrast to be visible on the disabled input background and the remove button is hidden */
    disabled?: boolean;
}
export type PillFactory = Factory<{
    props: PillProps;
    ref: HTMLDivElement;
    stylesNames: PillStylesNames;
    vars: PillCssVariables;
    variant: PillVariant;
    ctx: {
        size: MantineSize | (string & {}) | undefined;
    };
    staticComponents: {
        Group: typeof PillGroup;
    };
}>;
export declare const Pill: import("../../core").MantineComponent<{
    props: PillProps;
    ref: HTMLDivElement;
    stylesNames: PillStylesNames;
    vars: PillCssVariables;
    variant: PillVariant;
    ctx: {
        size: MantineSize | (string & {}) | undefined;
    };
    staticComponents: {
        Group: typeof PillGroup;
    };
}>;
