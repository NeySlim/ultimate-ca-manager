export interface MenuTargetProps {
    /** Target element */
    children: React.ReactNode;
    /** Key of the prop that should be used to get element ref */
    refProp?: string;
}
export declare const MenuTarget: import("react").ForwardRefExoticComponent<MenuTargetProps & import("react").RefAttributes<HTMLElement>>;
