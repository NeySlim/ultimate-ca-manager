interface HoverCardContext {
    openDropdown: () => void;
    closeDropdown: () => void;
}
export declare const HoverCardContextProvider: ({ children, value }: {
    value: HoverCardContext;
    children: React.ReactNode;
}) => import("react/jsx-runtime").JSX.Element, useHoverCardContext: () => HoverCardContext;
export {};
