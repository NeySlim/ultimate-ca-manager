import { BoxProps, ElementProps, Factory, MantineSpacing, StylesApiProps } from '../../core';
import { TreeController } from './use-tree';
export interface TreeNodeData {
    label: React.ReactNode;
    value: string;
    nodeProps?: Record<string, any>;
    children?: TreeNodeData[];
}
export interface RenderTreeNodePayload {
    /** Node level in the tree */
    level: number;
    /** `true` if the node is expanded, applicable only for nodes with `children` */
    expanded: boolean;
    /** `true` if the node has non-empty `children` array */
    hasChildren: boolean;
    /** `true` if the node is selected */
    selected: boolean;
    /** Node data from the `data` prop of `Tree` */
    node: TreeNodeData;
    /** Tree controller instance, return value of `useTree` hook */
    tree: TreeController;
    /** Props to spread into the root node element */
    elementProps: {
        className: string;
        style: React.CSSProperties;
        onClick: (event: React.MouseEvent) => void;
        'data-selected': boolean | undefined;
        'data-value': string;
        'data-hovered': boolean | undefined;
    };
}
export type RenderNode = (payload: RenderTreeNodePayload) => React.ReactNode;
export type TreeStylesNames = 'root' | 'node' | 'subtree' | 'label';
export type TreeCssVariables = {
    root: '--level-offset';
};
export interface TreeProps extends BoxProps, StylesApiProps<TreeFactory>, ElementProps<'ul'> {
    /** Data used to render nodes */
    data: TreeNodeData[];
    /** Horizontal padding of each subtree level, key of `theme.spacing` or any valid CSS value, `'lg'` by default */
    levelOffset?: MantineSpacing;
    /** Determines whether tree node with children should be expanded on click, `true` by default */
    expandOnClick?: boolean;
    /** Determines whether tree node with children should be expanded on space key press, `true` by default */
    expandOnSpace?: boolean;
    /** Determines whether tree node should be checked on space key press, `false` by default */
    checkOnSpace?: boolean;
    /** Determines whether node should be selected on click, `false` by default */
    selectOnClick?: boolean;
    /** Use-tree hook instance that can be used to manipulate component state */
    tree?: TreeController;
    /** A function to render tree node label */
    renderNode?: RenderNode;
    /** Determines whether selection should be cleared when user clicks outside of the tree, `false` by default */
    clearSelectionOnOutsideClick?: boolean;
    /** Determines whether tree nodes range can be selected with click when `Shift` key is pressed, `true` by default */
    allowRangeSelection?: boolean;
}
export type TreeFactory = Factory<{
    props: TreeProps;
    ref: HTMLUListElement;
    stylesNames: TreeStylesNames;
    vars: TreeCssVariables;
}>;
export declare const Tree: import("../../core").MantineComponent<{
    props: TreeProps;
    ref: HTMLUListElement;
    stylesNames: TreeStylesNames;
    vars: TreeCssVariables;
}>;
