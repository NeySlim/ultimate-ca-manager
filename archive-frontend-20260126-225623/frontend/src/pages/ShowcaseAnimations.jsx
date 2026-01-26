import React from 'react';
import { Container, Stack, Grid, Button, Card, Badge, Alert } from '../design-system';
import { ThemeToggle } from '../design-system/themes';
import './Showcase.css';

export default function ShowcaseAnimations() {
  return (
    <Container>
      <div className="showcase-header">
        <div>
          <h1>✨ Animation Showcase</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            Hover, click, and interact with these elements
          </p>
        </div>
        <ThemeToggle />
      </div>

      <Stack spacing="xl">
        <section>
          <h2>🎯 Button Ripple Effect</h2>
          <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
            Click buttons to see ripple animation
          </p>
          <Grid cols={3} gap="md">
            <Button variant="primary" size="lg">Click Me! 🎉</Button>
            <Button variant="secondary" size="lg">Try This Too</Button>
            <Button variant="danger" size="lg">And This!</Button>
          </Grid>
        </section>

        <section>
          <h2>🎴 Card Hover Effects</h2>
          <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', marginBottom: '16px' }}>
            Hover cards to see lift effect (shadow + translateY)
          </p>
          <Grid cols={3} gap="lg">
            <Card hover>
              <h3 style={{ margin: '0 0 8px 0' }}>Standard Card</h3>
              <p style={{ margin: 0, fontSize: '14px', color: 'var(--color-text-secondary)' }}>
                Hover me to see the lift effect with enhanced shadow
              </p>
            </Card>
            <Card hover gradient>
              <h3 style={{ margin: '0 0 8px 0' }}>Gradient Card</h3>
              <p style={{ margin: 0, fontSize: '14px', color: 'var(--color-text-secondary)' }}>
                I have a subtle gradient background too!
              </p>
            </Card>
            <Card hover>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                <Badge variant="success">NEW</Badge>
                <h3 style={{ margin: 0 }}>With Badge</h3>
              </div>
              <p style={{ margin: 0, fontSize: '14px', color: 'var(--color-text-secondary)' }}>
                Combining multiple components for rich cards
              </p>
            </Card>
          </Grid>
        </section>

        <section>
          <h2>🎨 Badges with Variants</h2>
          <Grid cols={3} gap="md">
            <Card hover>
              <Badge variant="success" size="lg">✅ Active</Badge>
              <p style={{ fontSize: '12px', marginTop: '8px', color: 'var(--color-text-secondary)' }}>
                Success variant
              </p>
            </Card>
            <Card hover>
              <Badge variant="warning" size="lg">⚠️ Warning</Badge>
              <p style={{ fontSize: '12px', marginTop: '8px', color: 'var(--color-text-secondary)' }}>
                Warning variant
              </p>
            </Card>
            <Card hover>
              <Badge variant="danger" size="lg">❌ Error</Badge>
              <p style={{ fontSize: '12px', marginTop: '8px', color: 'var(--color-text-secondary)' }}>
                Danger variant
              </p>
            </Card>
          </Grid>
        </section>

        <section>
          <h2>💫 Interactive Elements</h2>
          <Stack spacing="md">
            <Alert variant="info">
              Click the theme toggle in the top right to see smooth theme transitions!
            </Alert>
            <Alert variant="success">
              All animations use CSS transitions for smooth, performant effects
            </Alert>
            <Alert variant="warning" onDismiss={() => alert('Dismissed!')}>
              Click the × to dismiss this alert
            </Alert>
          </Stack>
        </section>

        <section>
          <h2>🚀 Quick Action Buttons</h2>
          <Grid cols={4} gap="sm">
            {['Save', 'Cancel', 'Delete', 'Refresh', 'Export', 'Import', 'Settings', 'Help'].map(label => (
              <Button key={label} variant={label === 'Delete' ? 'danger' : 'secondary'}>
                {label}
              </Button>
            ))}
          </Grid>
        </section>
      </Stack>
    </Container>
  );
}
