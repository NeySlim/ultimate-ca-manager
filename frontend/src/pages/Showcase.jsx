import React, { useState } from 'react';
import { ThemeToggle } from '../design-system/themes';
import { 
  Button, Input, Badge, Checkbox, Radio, Switch, Select, TextArea,
  Container, Stack, Grid, Inline, Flex, Divider,
  Spinner, Alert, Skeleton, Progress, EmptyState, Toast,
  Modal, Tooltip, Drawer, Popover, Dropdown,
  Tabs, Breadcrumbs, Pagination
} from '../design-system';
import './Showcase.css';

export default function Showcase() {
  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('primitives');
  const [currentPage, setCurrentPage] = useState(1);
  
  const tabs = [
    { id: 'primitives', label: 'Primitives (8)' },
    { id: 'layout', label: 'Layout (6)' },
    { id: 'feedback', label: 'Feedback (6)' },
    { id: 'overlays', label: 'Overlays (5)' },
    { id: 'navigation', label: 'Navigation (4)' }
  ];

  const breadcrumbItems = [
    { label: 'Home', href: '/' },
    { label: 'Design System', href: '/showcase' },
    { label: 'Components' }
  ];

  return (
    <Container>
      <div className="showcase-header">
        <div>
          <h1>UCM Design System v3.0</h1>
          <Breadcrumbs items={breadcrumbItems} />
        </div>
        <ThemeToggle />
      </div>

      <Tabs tabs={tabs} defaultTab="primitives" onChange={setActiveTab} />

      <Stack spacing="lg" className="showcase-content">
        {activeTab === 'primitives' && (
          <>
            <section>
              <h2>Buttons (5 variants × 5 sizes)</h2>
              <Grid cols={3} gap="md">
                <Button variant="primary">Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="danger">Danger</Button>
                <Button loading>Loading</Button>
                <Button size="xs">Tiny</Button>
                <Button size="sm">Small</Button>
                <Button size="lg">Large</Button>
                <Button size="xl">Extra Large</Button>
              </Grid>
            </section>

            <Divider />

            <section>
              <h2>Form Inputs</h2>
              <Stack spacing="md">
                <Input placeholder="Text input..." />
                <TextArea placeholder="Textarea with multiple lines..." rows={3} />
                <Select>
                  <option>Select option...</option>
                  <option>Option 1</option>
                  <option>Option 2</option>
                </Select>
              </Stack>
            </section>

            <Divider />

            <section>
              <h2>Checkboxes, Radios, Switches</h2>
              <Stack spacing="md">
                <Checkbox>Accept terms and conditions</Checkbox>
                <Radio name="demo">Option A</Radio>
                <Radio name="demo">Option B</Radio>
                <Switch>Enable notifications</Switch>
              </Stack>
            </section>

            <Divider />

            <section>
              <h2>Badges</h2>
              <Inline spacing="sm">
                <Badge variant="default">Default</Badge>
                <Badge variant="primary">Primary</Badge>
                <Badge variant="success">Success</Badge>
                <Badge variant="warning">Warning</Badge>
                <Badge variant="danger">Danger</Badge>
                <Badge variant="info">Info</Badge>
                <Badge size="sm">Small</Badge>
                <Badge size="lg">Large</Badge>
              </Inline>
            </section>
          </>
        )}

        {activeTab === 'layout' && (
          <>
            <section>
              <h2>Container</h2>
              <Container size="md">
                <div className="demo-box">Content in container (max-width: 768px)</div>
              </Container>
            </section>

            <section>
              <h2>Stack (vertical)</h2>
              <Stack spacing="sm">
                <div className="demo-box">Item 1</div>
                <div className="demo-box">Item 2</div>
                <div className="demo-box">Item 3</div>
              </Stack>
            </section>

            <section>
              <h2>Grid</h2>
              <Grid cols={4} gap="md">
                <div className="demo-box">1</div>
                <div className="demo-box">2</div>
                <div className="demo-box">3</div>
                <div className="demo-box">4</div>
              </Grid>
            </section>

            <section>
              <h2>Inline (wraps)</h2>
              <Inline spacing="sm">
                {Array.from({ length: 20 }, (_, i) => (
                  <Badge key={i}>Tag {i + 1}</Badge>
                ))}
              </Inline>
            </section>

            <section>
              <h2>Flex</h2>
              <Flex justify="space-between" align="center">
                <div className="demo-box">Left</div>
                <div className="demo-box">Center</div>
                <div className="demo-box">Right</div>
              </Flex>
            </section>

            <section>
              <h2>Divider</h2>
              <div>Content above</div>
              <Divider />
              <div>Content below</div>
            </section>
          </>
        )}

        {activeTab === 'feedback' && (
          <>
            <section>
              <h2>Spinners</h2>
              <Inline spacing="lg">
                <Spinner size="xs" />
                <Spinner size="sm" />
                <Spinner size="md" />
                <Spinner size="lg" />
                <Spinner size="xl" />
              </Inline>
            </section>

            <section>
              <h2>Alerts</h2>
              <Stack spacing="md">
                <Alert variant="info">This is an informational message</Alert>
                <Alert variant="success">Operation completed successfully!</Alert>
                <Alert variant="warning">Please review this warning</Alert>
                <Alert variant="error" onDismiss={() => {}}>Critical error occurred</Alert>
              </Stack>
            </section>

            <section>
              <h2>Progress Bars</h2>
              <Stack spacing="md">
                <Progress value={25} showLabel />
                <Progress value={50} variant="success" showLabel />
                <Progress value={75} variant="warning" showLabel />
                <Progress value={90} variant="error" size="lg" showLabel />
              </Stack>
            </section>

            <section>
              <h2>Skeleton Loaders</h2>
              <Stack spacing="sm">
                <Skeleton width="100%" height={24} />
                <Skeleton width="80%" height={24} />
                <Skeleton width="60%" height={24} />
              </Stack>
            </section>

            <section>
              <h2>Empty State</h2>
              <EmptyState
                icon="📭"
                title="No items found"
                description="Try adjusting your filters or create a new item"
                action={<Button>Create Item</Button>}
              />
            </section>

            <section>
              <h2>Toast Notification</h2>
              <Button onClick={() => setToastOpen(true)}>Show Toast</Button>
              <Toast isOpen={toastOpen} onClose={() => setToastOpen(false)} variant="success">
                Action completed successfully!
              </Toast>
            </section>
          </>
        )}

        {activeTab === 'overlays' && (
          <>
            <section>
              <h2>Modal</h2>
              <Button onClick={() => setModalOpen(true)}>Open Modal</Button>
              <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Example Modal" size="md">
                <p>This is a modal dialog with some content inside.</p>
                <Stack spacing="md">
                  <Input placeholder="Email address" />
                  <TextArea placeholder="Message" />
                  <Flex justify="flex-end" gap="sm">
                    <Button variant="ghost" onClick={() => setModalOpen(false)}>Cancel</Button>
                    <Button onClick={() => setModalOpen(false)}>Submit</Button>
                  </Flex>
                </Stack>
              </Modal>
            </section>

            <section>
              <h2>Drawer</h2>
              <Button onClick={() => setDrawerOpen(true)}>Open Drawer</Button>
              <Drawer isOpen={drawerOpen} onClose={() => setDrawerOpen(false)} title="Settings">
                <Stack spacing="md">
                  <Input placeholder="Name" />
                  <Select>
                    <option>Choose option...</option>
                  </Select>
                  <Switch>Enable feature</Switch>
                </Stack>
              </Drawer>
            </section>

            <section>
              <h2>Tooltip</h2>
              <Inline spacing="md">
                <Tooltip content="Top tooltip" position="top">
                  <Button variant="secondary">Hover (Top)</Button>
                </Tooltip>
                <Tooltip content="Bottom tooltip" position="bottom">
                  <Button variant="secondary">Hover (Bottom)</Button>
                </Tooltip>
              </Inline>
            </section>

            <section>
              <h2>Popover</h2>
              <Popover trigger={<Button variant="secondary">Open Popover</Button>}>
                <Stack spacing="sm">
                  <h4 style={{ margin: 0 }}>Popover Content</h4>
                  <p style={{ margin: 0, fontSize: '14px' }}>This is a popover with custom content.</p>
                </Stack>
              </Popover>
            </section>

            <section>
              <h2>Dropdown</h2>
              <Dropdown
                trigger={<Button variant="secondary">Open Menu ▾</Button>}
                items={[
                  { label: 'Profile' },
                  { label: 'Settings' },
                  { label: 'Logout' }
                ]}
                onSelect={(item) => alert(`Selected: ${item.label}`)}
              />
            </section>
          </>
        )}

        {activeTab === 'navigation' && (
          <>
            <section>
              <h2>Breadcrumbs</h2>
              <Breadcrumbs items={breadcrumbItems} />
            </section>

            <section>
              <h2>Tabs</h2>
              <Tabs 
                tabs={[
                  { id: 'tab1', label: 'First Tab' },
                  { id: 'tab2', label: 'Second Tab' },
                  { id: 'tab3', label: 'Third Tab' }
                ]}
              />
            </section>

            <section>
              <h2>Pagination</h2>
              <Pagination
                currentPage={currentPage}
                totalPages={10}
                onPageChange={setCurrentPage}
              />
              <p style={{ marginTop: '16px', fontSize: '14px', color: 'var(--color-text-secondary)' }}>
                Current page: {currentPage} / 10
              </p>
            </section>
          </>
        )}
      </Stack>
    </Container>
  );
}
