import { BoxProps, ElementProps, ExtendComponent, Factory, MantineRadius, MantineThemeComponent, StylesApiProps } from '../../core';
import { AccordionChevronPosition, AccordionHeadingOrder, AccordionValue } from './Accordion.types';
import { AccordionChevron } from './AccordionChevron';
export type AccordionStylesNames = 'root' | 'content' | 'item' | 'panel' | 'icon' | 'chevron' | 'label' | 'itemTitle' | 'control';
export type AccordionVariant = 'default' | 'contained' | 'filled' | 'separated';
export type AccordionCssVariables = {
    root: '--accordion-transition-duration' | '--accordion-chevron-size' | '--accordion-radius';
};
export interface AccordionProps<Multiple extends boolean = false> extends BoxProps, StylesApiProps<AccordionFactory>, ElementProps<'div', 'value' | 'defaultValue' | 'onChange'> {
    /** Determines whether multiple items can be opened at a time, `false` by default */
    multiple?: Multiple;
    /** Value for controlled component */
    value?: AccordionValue<Multiple>;
    /** Default value for uncontrolled component */
    defaultValue?: AccordionValue<Multiple>;
    /** Called when value changes */
    onChange?: (value: AccordionValue<Multiple>) => void;
    /** Determines whether arrow key presses should loop though items (first to last and last to first), `true` by default */
    loop?: boolean;
    /** Transition duration in ms, `200` by default */
    transitionDuration?: number;
    /** Determines whether chevron rotation should be disabled, `false` by default */
    disableChevronRotation?: boolean;
    /** Position of the chevron relative to the item label, `right` by default */
    chevronPosition?: AccordionChevronPosition;
    /** Size of the chevron icon container, `24` by default */
    chevronSize?: number | string;
    /** Heading order, has no effect on visuals */
    order?: AccordionHeadingOrder;
    /** Custom chevron icon that will be used in all items */
    chevron?: React.ReactNode;
    /** Key of `theme.radius` or any valid CSS value to set border-radius. Numbers are converted to rem. `theme.defaultRadius` by default. */
    radius?: MantineRadius;
}
export type AccordionFactory = Factory<{
    props: AccordionProps;
    ref: HTMLDivElement;
    stylesNames: AccordionStylesNames;
    vars: AccordionCssVariables;
    variant: AccordionVariant;
}>;
export declare function Accordion<Multiple extends boolean = false>(_props: AccordionProps<Multiple>): import("react/jsx-runtime").JSX.Element;
export declare namespace Accordion {
    var extend: (c: ExtendComponent<AccordionFactory>) => MantineThemeComponent;
    var withProps: (props: Partial<AccordionProps<false>>) => AccordionProps<false>;
    var classes: any;
    var displayName: string;
    var Item: import("../../core").MantineComponent<{
        props: import("./AccordionItem/AccordionItem").AccordionItemProps;
        ref: HTMLDivElement;
        stylesNames: import("./AccordionItem/AccordionItem").AccordionItemStylesNames;
        compound: true;
    }>;
    var Panel: import("../../core").MantineComponent<{
        props: import("./AccordionPanel/AccordionPanel").AccordionPanelProps;
        ref: HTMLDivElement;
        stylesNames: import("./AccordionPanel/AccordionPanel").AccordionPanelStylesNames;
        compound: true;
    }>;
    var Control: import("../../core").MantineComponent<{
        props: import("./AccordionControl/AccordionControl").AccordionControlProps;
        ref: HTMLButtonElement;
        stylesNames: import("./AccordionControl/AccordionControl").AccordionControlStylesNames;
        compound: true;
    }>;
    var Chevron: typeof AccordionChevron;
}
