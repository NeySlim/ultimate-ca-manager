import { Factory, MantineSpacing } from '../../core';
import { PaginationIcon } from './Pagination.icons';
import { PaginationControl } from './PaginationControl/PaginationControl';
import { PaginationDots } from './PaginationDots/PaginationDots';
import { PaginationFirst, PaginationLast, PaginationNext, PaginationPrevious } from './PaginationEdges/PaginationEdges';
import { PaginationItems } from './PaginationItems/PaginationItems';
import { PaginationRoot, PaginationRootCssVariables, PaginationRootProps, PaginationRootStylesNames } from './PaginationRoot/PaginationRoot';
export type PaginationStylesNames = PaginationRootStylesNames;
export type PaginationCssVariables = PaginationRootCssVariables;
export interface PaginationProps extends PaginationRootProps {
    /** Determines whether first/last controls should be rendered, false by default */
    withEdges?: boolean;
    /** Determines whether next/previous controls should be rendered, true by default */
    withControls?: boolean;
    /** Adds props to next/previous/first/last controls */
    getControlProps?: (control: 'first' | 'previous' | 'last' | 'next') => Record<string, any>;
    /** Next control icon component */
    nextIcon?: PaginationIcon;
    /** Previous control icon component */
    previousIcon?: PaginationIcon;
    /** Last control icon component */
    lastIcon?: PaginationIcon;
    /** First control icon component */
    firstIcon?: PaginationIcon;
    /** Dots icon component */
    dotsIcon?: PaginationIcon;
    /** Key of `theme.spacing`, gap between controls, `8` by default */
    gap?: MantineSpacing;
    /** Determines whether the pagination should be hidden when only one page is available (`total={1}`), `false` by default */
    hideWithOnePage?: boolean;
    /** Determines whether pages controls should be displayed, `true` by default */
    withPages?: boolean;
}
export type PaginationFactory = Factory<{
    props: PaginationProps;
    ref: HTMLDivElement;
    stylesNames: PaginationStylesNames;
    vars: PaginationCssVariables;
    staticComponents: {
        Root: typeof PaginationRoot;
        Control: typeof PaginationControl;
        Dots: typeof PaginationDots;
        First: typeof PaginationFirst;
        Last: typeof PaginationLast;
        Next: typeof PaginationNext;
        Previous: typeof PaginationPrevious;
        Items: typeof PaginationItems;
    };
}>;
export declare const Pagination: import("../../core").MantineComponent<{
    props: PaginationProps;
    ref: HTMLDivElement;
    stylesNames: PaginationStylesNames;
    vars: PaginationCssVariables;
    staticComponents: {
        Root: typeof PaginationRoot;
        Control: typeof PaginationControl;
        Dots: typeof PaginationDots;
        First: typeof PaginationFirst;
        Last: typeof PaginationLast;
        Next: typeof PaginationNext;
        Previous: typeof PaginationPrevious;
        Items: typeof PaginationItems;
    };
}>;
