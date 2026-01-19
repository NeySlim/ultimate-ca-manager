export interface FocusTrapProps {
    /** Element at which focus should be trapped, should support ref prop */
    children: any;
    /** Determines whether focus should be trapped within child element */
    active?: boolean;
    /** Prop that should be used to access component ref */
    refProp?: string;
    /** Assigns element `ref` */
    innerRef?: React.ForwardedRef<any>;
}
export declare function FocusTrap({ children, active, refProp, innerRef, }: FocusTrapProps): React.ReactElement;
export declare namespace FocusTrap {
    var displayName: string;
    var InitialFocus: typeof FocusTrapInitialFocus;
}
export declare function FocusTrapInitialFocus(props: React.ComponentPropsWithoutRef<'span'>): import("react/jsx-runtime").JSX.Element;
export declare namespace FocusTrapInitialFocus {
    var displayName: string;
}
