import { BoxProps, StylesApiProps } from '../../core';
import { __BaseInputProps } from './Input';
interface BaseProps extends __BaseInputProps, BoxProps, StylesApiProps<{
    props: any;
    stylesNames: string;
}> {
    __staticSelector?: string;
    __stylesApiProps?: Record<string, any>;
    id?: string;
}
export declare function useInputProps<T extends BaseProps, U extends Partial<T>>(component: string, defaultProps: U, _props: T): Omit<T & { [Key in Extract<keyof T, never>]-?: {}[Key] | NonNullable<T[Key]>; }, "size" | "variant" | "style" | "label" | "className" | "id" | "wrapperProps" | "required" | "description" | "error" | "__staticSelector" | "__stylesApiProps" | "withAsterisk" | "labelProps" | "descriptionProps" | "errorProps" | "inputContainer" | "inputWrapperOrder" | "mod" | "unstyled" | "classNames" | "styles" | "vars"> & {
    classNames: Partial<Record<string, string>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, string>>) | undefined;
    styles: Partial<Record<string, import("../../core").CSSProperties>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, import("../../core").CSSProperties>>) | undefined;
    unstyled: boolean | undefined;
    wrapperProps: {
        label: import("react").ReactNode;
        description: import("react").ReactNode;
        error: import("react").ReactNode;
        required: boolean | undefined;
        classNames: Partial<Record<string, string>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, string>>) | undefined;
        className: string | undefined;
        __staticSelector: string | undefined;
        __stylesApiProps: Record<string, any>;
        errorProps: Record<string, any> | undefined;
        labelProps: Record<string, any> | undefined;
        descriptionProps: Record<string, any> | undefined;
        unstyled: boolean | undefined;
        styles: Partial<Record<string, import("../../core").CSSProperties>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, import("../../core").CSSProperties>>) | undefined;
        size: import("../../core").MantineSize | (string & {}) | undefined;
        style: import("../../core").MantineStyleProp;
        inputContainer: ((children: React.ReactNode) => React.ReactNode) | undefined;
        inputWrapperOrder: ("input" | "label" | "description" | "error")[] | undefined;
        withAsterisk: boolean | undefined;
        variant: string | undefined;
        id: string | undefined;
        mod: import("../../core").BoxMod | undefined;
    } & BoxProps;
    inputProps: {
        required: boolean | undefined;
        classNames: Partial<Record<string, string>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, string>>) | undefined;
        styles: Partial<Record<string, import("../../core").CSSProperties>> | ((theme: import("../../core").MantineTheme, props: any, ctx: unknown) => Partial<Record<string, import("../../core").CSSProperties>>) | undefined;
        unstyled: boolean | undefined;
        size: import("../../core").MantineSize | (string & {}) | undefined;
        __staticSelector: string | undefined;
        __stylesApiProps: Record<string, any>;
        error: import("react").ReactNode;
        variant: string | undefined;
        id: string | undefined;
    };
};
export {};
