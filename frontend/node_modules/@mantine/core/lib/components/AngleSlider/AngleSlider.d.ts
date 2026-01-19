import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
export type AngleSliderStylesNames = 'root' | 'thumb' | 'label' | 'marks' | 'mark';
export type AngleSliderCssVariables = {
    root: '--slider-size' | '--thumb-size';
};
export interface AngleSliderProps extends BoxProps, StylesApiProps<AngleSliderFactory>, ElementProps<'div', 'onChange'> {
    /** Step between values, used when the component is controlled with keyboard, `1` by default */
    step?: number;
    /** Value of the controlled component */
    value?: number;
    /** Default value for uncontrolled component */
    defaultValue?: number;
    /** Called on value change */
    onChange?: (value: number) => void;
    /** Called after the selection is finished */
    onChangeEnd?: (value: number) => void;
    /** Called in `onMouseDown` and `onTouchStart` events */
    onScrubStart?: () => void;
    /** Called in `onMouseUp` and `onTouchEnd` events */
    onScrubEnd?: () => void;
    /** Determines whether the label should be displayed inside the slider, `true` by default */
    withLabel?: boolean;
    /** Array of marks that are displayed on the slider */
    marks?: {
        value: number;
        label?: string;
    }[];
    /** Slider size in px, `60px` */
    size?: number;
    /** Size of the thumb in px, by default is calculated based on the `size` value */
    thumbSize?: number;
    /** Formats label based on the current value */
    formatLabel?: (value: number) => React.ReactNode;
    /** Disables interactions */
    disabled?: boolean;
    /** Determines whether the selection should be only allowed from the given marks array, `false` by default */
    restrictToMarks?: boolean;
    /** Props passed down to the hidden input */
    hiddenInputProps?: React.ComponentPropsWithoutRef<'input'>;
    /** Hidden input name, use with uncontrolled component */
    name?: string;
}
export type AngleSliderFactory = Factory<{
    props: AngleSliderProps;
    ref: HTMLDivElement;
    stylesNames: AngleSliderStylesNames;
    vars: AngleSliderCssVariables;
}>;
export declare const AngleSlider: import("../../core").MantineComponent<{
    props: AngleSliderProps;
    ref: HTMLDivElement;
    stylesNames: AngleSliderStylesNames;
    vars: AngleSliderCssVariables;
}>;
