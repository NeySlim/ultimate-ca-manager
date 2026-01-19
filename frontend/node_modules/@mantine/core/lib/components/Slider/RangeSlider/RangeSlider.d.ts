import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
import { TransitionOverride } from '../../Transition';
import { SliderCssVariables, SliderStylesNames } from '../Slider.context';
export type RangeSliderValue = [number, number];
export interface RangeSliderProps extends BoxProps, StylesApiProps<RangeSliderFactory>, ElementProps<'div', 'onChange' | 'value' | 'defaultValue'> {
    /** Key of `theme.colors` or any valid CSS color, controls color of track and thumb, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, numbers are converted to rem, `'xl'` by default */
    radius?: MantineRadius;
    /** Controls size of the track, `'md'` by default */
    size?: MantineSize | (string & {}) | number;
    /** Minimal possible value, `0` by default */
    min?: number;
    /** Maximum possible value, `100` by default */
    max?: number;
    /** Number by which value will be incremented/decremented with thumb drag and arrows, `1` by default */
    step?: number;
    /** Number of significant digits after the decimal point */
    precision?: number;
    /** Controlled component value */
    value?: RangeSliderValue;
    /** Uncontrolled component default value */
    defaultValue?: RangeSliderValue;
    /** Called when value changes */
    onChange?: (value: RangeSliderValue) => void;
    /** Called when user stops dragging slider or changes value with arrows */
    onChangeEnd?: (value: RangeSliderValue) => void;
    /** Hidden input name, use with uncontrolled component */
    name?: string;
    /** Marks displayed on the track */
    marks?: {
        value: number;
        label?: React.ReactNode;
    }[];
    /** Function to generate label or any react node to render instead, set to null to disable label */
    label?: React.ReactNode | ((value: number) => React.ReactNode);
    /** Props passed down to the `Transition` component, `{ transition: 'fade', duration: 0 }` by default */
    labelTransitionProps?: TransitionOverride;
    /** Determines whether the label should be visible when the slider is not being dragged or hovered, `false` by default */
    labelAlwaysOn?: boolean;
    /** Determines whether the label should be displayed when the slider is hovered, `true` by default */
    showLabelOnHover?: boolean;
    /** Content rendered inside thumb */
    thumbChildren?: React.ReactNode;
    /** Disables slider */
    disabled?: boolean;
    /** Thumb `width` and `height`, by default value is computed based on `size` prop */
    thumbSize?: number | string;
    /** A transformation function to change the scale of the slider */
    scale?: (value: number) => number;
    /** Determines whether track values representation should be inverted, `false` by default */
    inverted?: boolean;
    /** Minimal range interval, `10` by default */
    minRange?: number;
    /** Maximum range interval, `Infinity` by default */
    maxRange?: number;
    /** First thumb `aria-label` */
    thumbFromLabel?: string;
    /** Second thumb `aria-label` */
    thumbToLabel?: string;
    /** Props passed down to the hidden input */
    hiddenInputProps?: React.ComponentPropsWithoutRef<'input'>;
    /** Determines whether the selection should be only allowed from the given marks array, `false` by default */
    restrictToMarks?: boolean;
    /** Props passed down to thumb element based on the thumb index */
    thumbProps?: (index: 0 | 1) => React.ComponentPropsWithoutRef<'div'>;
}
export type RangeSliderFactory = Factory<{
    props: RangeSliderProps;
    ref: HTMLDivElement;
    stylesNames: SliderStylesNames;
    vars: SliderCssVariables;
}>;
export declare const RangeSlider: import("../../../core").MantineComponent<{
    props: RangeSliderProps;
    ref: HTMLDivElement;
    stylesNames: SliderStylesNames;
    vars: SliderCssVariables;
}>;
