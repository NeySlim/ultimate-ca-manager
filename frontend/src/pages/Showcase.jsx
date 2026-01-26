import React, { useState } from 'react';
import { ThemeToggle } from '../design-system/themes';
import { 
  Button, Input, Badge, Checkbox, Select,
  Container, Stack, Grid,
  Spinner, Alert, Skeleton,
  Modal, Tooltip,
  Tabs
} from '../design-system';
import './Showcase.css';

export default function Showcase() {
  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('primitives');
  
  const tabs = [
    { id: 'primitives', label: 'Primitives' },
    { id: 'layout', label: 'Layout' },
    { id: 'feedback', label: 'Feedback' },
    { id: 'overlays', label: 'Overlays' }
  ];

  return (
    <Container>
      <div className="showcase-header">
        <h1>UCM Design System</h1>
        <ThemeToggle />
      </div>

      <Tabs tabs={tabs} defaultTab="primitives" onChange={setActiveTab} />

      <Stack spacing="lg" className="showcase-content">
        {activeTab === 'primitives' && (
          <>
            <section>
              <h2>Buttons</h2>
              <Grid cols={3} gap="md">
                <Button variant="primary">Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="danger">Danger</Button>
                <Button size="sm">Small</Button>
                <Button size="lg">Large</Button>
                <Button loading>Loading</Button>
              </Grid>
            </section>

            <section>
              <h2>Inputs & Forms</h2>
              <Stack spacing="md">
                <Input placeholder="Enter text..." />
                <Select>
                  <option>Option 1</option>
                  <option>Option 2</option>
                </Select>
                <Checkbox>Accept terms</Checkbox>
              </Stack>
            </section>

            <section>
              <h2>Badges</h2>
              <Grid cols={3} gap="sm">
                <Badge variant="primary">Primary</Badge>
                <Badge variant="success">Success</Badge>
                <Badge variant="warning">Warning</Badge>
                <Badge variant="danger">Danger</Badge>
                <Badge variant="info">Info</Badge>
              </Grid>
            </section>
          </>
        )}

        {activeTab === 'layout' && (
          <>
            <section>
              <h2>Stack (Vertical)</h2>
              <Stack spacing="sm">
                <div className="demo-box">Item 1</div>
                <div className="demo-box">Item 2</div>
                <div className="demo-box">Item 3</div>
              </Stack>
            </section>

            <section>
              <h2>Grid</h2>
              <Grid cols={3} gap="md">
                <div className="demo-box">1</div>
                <div className="demo-box">2</div>
                <div className="demo-box">3</div>
              </Grid>
            </section>
          </>
        )}

        {activeTab === 'feedback' && (
          <>
            <section>
              <h2>Spinners</h2>
              <Grid cols={4} gap="md">
                <Spinner size="sm" />
                <Spinner size="md" />
                <Spinner size="lg" />
                <Spinner size="xl" />
              </Grid>
            </section>

            <section>
              <h2>Alerts</h2>
              <Stack spacing="md">
                <Alert variant="info">This is an info message</Alert>
                <Alert variant="success">Success! Operation completed</Alert>
                <Alert variant="warning">Warning: Please check</Alert>
                <Alert variant="error">Error: Something went wrong</Alert>
              </Stack>
            </section>

            <section>
              <h2>Skeleton</h2>
              <Stack spacing="sm">
                <Skeleton width="100%" height={24} />
                <Skeleton width="80%" height={24} />
                <Skeleton width="60%" height={24} />
              </Stack>
            </section>
          </>
        )}

        {activeTab === 'overlays' && (
          <>
            <section>
              <h2>Modal</h2>
              <Button onClick={() => setModalOpen(true)}>Open Modal</Button>
              <Modal 
                isOpen={modalOpen} 
                onClose={() => setModalOpen(false)}
                title="Example Modal"
              >
                <p>This is a modal with some content inside.</p>
                <Button onClick={() => setModalOpen(false)}>Close</Button>
              </Modal>
            </section>

            <section>
              <h2>Tooltip</h2>
              <Tooltip content="This is a tooltip">
                <Button variant="secondary">Hover me</Button>
              </Tooltip>
            </section>
          </>
        )}
      </Stack>
    </Container>
  );
}
