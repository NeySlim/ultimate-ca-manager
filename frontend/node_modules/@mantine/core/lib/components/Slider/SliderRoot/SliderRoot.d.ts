import { BoxProps, ElementProps, MantineColor, MantineRadius, MantineSize } from '../../../core';
export interface SliderRootProps extends BoxProps, ElementProps<'div'> {
    size: MantineSize | (string & {}) | number;
    children: React.ReactNode;
    color: MantineColor | undefined;
    disabled: boolean | undefined;
    variant?: string;
    thumbSize: string | number | undefined;
    radius: MantineRadius | undefined;
}
export declare const SliderRoot: import("react").ForwardRefExoticComponent<SliderRootProps & import("react").RefAttributes<HTMLDivElement>>;
