import { Factory } from '../../core';
export interface PortalProps extends React.ComponentPropsWithoutRef<'div'> {
    /** Portal children, for example, custom modal or popover */
    children: React.ReactNode;
    /** Element inside which portal should be created, by default a new div element is created and appended to the `document.body` */
    target?: HTMLElement | string;
    /** If set, all portals are rendered in the same DOM node, `false` by default */
    reuseTargetNode?: boolean;
}
export type PortalFactory = Factory<{
    props: PortalProps;
    ref: HTMLDivElement;
}>;
export declare const Portal: import("../../core").MantineComponent<{
    props: PortalProps;
    ref: HTMLDivElement;
}>;
