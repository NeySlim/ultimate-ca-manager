import { ButtonProps, GroupProps } from '@mantine/core';
import { ConfirmLabels } from './context';
export interface ConfirmModalProps {
    id?: string;
    children?: React.ReactNode;
    onCancel?: () => void;
    onConfirm?: () => void;
    closeOnConfirm?: boolean;
    closeOnCancel?: boolean;
    cancelProps?: ButtonProps & React.ComponentPropsWithoutRef<'button'> & Record<`data-${string}`, string>;
    confirmProps?: ButtonProps & React.ComponentPropsWithoutRef<'button'> & Record<`data-${string}`, string>;
    groupProps?: GroupProps;
    labels?: ConfirmLabels;
}
export declare function ConfirmModal({ id, cancelProps, confirmProps, labels, closeOnConfirm, closeOnCancel, groupProps, onCancel, onConfirm, children, }: ConfirmModalProps): import("react/jsx-runtime").JSX.Element;
