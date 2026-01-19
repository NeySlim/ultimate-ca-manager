import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
export type TypographyStylesProviderStylesNames = 'root';
export interface TypographyStylesProviderProps extends BoxProps, StylesApiProps<TypographyStylesProviderFactory>, ElementProps<'div'> {
}
export type TypographyStylesProviderFactory = Factory<{
    props: TypographyStylesProviderProps;
    ref: HTMLDivElement;
    stylesNames: TypographyStylesProviderStylesNames;
}>;
export declare const TypographyStylesProvider: import("../../core").MantineComponent<{
    props: TypographyStylesProviderProps;
    ref: HTMLDivElement;
    stylesNames: TypographyStylesProviderStylesNames;
}>;
