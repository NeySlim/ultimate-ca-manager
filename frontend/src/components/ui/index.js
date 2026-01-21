// UI Components - Headless UI Based
// Replaces Mantine components with pure CSS + Headless UI

export { Button } from './Button';
export { Text } from './Text';
export { Badge } from './Badge';
export { Input, PasswordInput } from './Input';
export { Stack, Group, Card, Divider } from './LayoutUtils';
export { Menu, MenuItem, MenuDivider } from './Menu';
export { Modal } from './Modal';
export { Tabs, TabsList, TabsTab, TabsPanels, TabsPanel } from './Tabs';
export { Select } from './Select';
export { MultiSelect } from './MultiSelect';
export { Pagination } from './Pagination';
export { SegmentedControl } from './SegmentedControl';
export { SimpleGrid } from './SimpleGrid';
export { Tooltip } from './Tooltip';
export { ActionIcon } from './ActionIcon';
export { Container } from './Container';
export { Textarea, NumberInput, Switch, Radio, Alert, Box } from './MoreComponents';
export { CopyButton as GridCopyButton } from './Grid';
export { Avatar, Title, Anchor, Loader, ScrollArea, ThemeIcon, Paper, Center, Code } from './MoreComponents2';

// New intelligent components
export { StatusBadge } from './StatusBadge';
export { SearchToolbar } from './SearchToolbar';
export { CodeBlock } from './CodeBlock';
export { CopyButton } from './CopyButton';

// Grid - Import, assign nested properties, then export
import GridComponent, { GridCol } from './Grid';
GridComponent.Col = GridCol;
export { GridComponent as Grid };
export default GridComponent; // For backward compat with Layout/index.js

// Table - Import, assign nested properties, then export
import { Table as TableComponent, Stepper as StepperComponent, Loader } from './MoreComponents2';
TableComponent.Thead = TableComponent.Thead;
TableComponent.Tbody = TableComponent.Tbody;
TableComponent.Tr = TableComponent.Tr;
TableComponent.Th = TableComponent.Th;
TableComponent.Td = TableComponent.Td;
StepperComponent.Step = StepperComponent.Step;
export { TableComponent as Table, StepperComponent as Stepper };

// Layout components (for backward compatibility)
export { default as PageHeader } from './Layout/PageHeader';
export { default as Widget } from './Layout/Widget';
