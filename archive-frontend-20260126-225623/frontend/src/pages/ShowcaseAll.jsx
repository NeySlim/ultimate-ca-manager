import React, { useState } from 'react';
import { Container, Stack, Grid, Inline, Button, Card, Input, GlassCard, GradientBadge, AnimatedCheckbox, Alert, SuccessCheckmark, Confetti } from '../design-system';
import { ThemeToggle } from '../design-system/themes';
import './Showcase.css';

export default function ShowcaseAll() {
  const [showSuccess, setShowSuccess] = useState(false);
  const [showConfetti, setShowConfetti] = useState(false);
  const [checked, setChecked] = useState(false);
  
  const handleSuccess = () => {
    setShowSuccess(true);
    setShowConfetti(true);
    setTimeout(() => setShowSuccess(false), 3000);
  };
  
  return (
    <Container>
      {showConfetti && <Confetti duration={3000} onComplete={() => setShowConfetti(false)} />}
      
      <div className="showcase-header">
        <div>
          <h1>🎨 Complete UI Showcase</h1>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            All Phase 1-5 features in one page
          </p>
        </div>
        <ThemeToggle />
      </div>

      <Stack spacing="xl">
        <section>
          <h2>✨ Ripple Buttons</h2>
          <Grid cols={4} gap="md">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="danger">Danger</Button>
          </Grid>
        </section>

        <section>
          <h2>🎴 Hover Cards</h2>
          <Grid cols={3} gap="lg">
            <Card hover>
              <h3 style={{ margin: '0 0 8px 0' }}>Standard Card</h3>
              <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', margin: 0 }}>
                Lift effect on hover
              </p>
            </Card>
            <Card hover gradient>
              <h3 style={{ margin: '0 0 8px 0' }}>Gradient Card</h3>
              <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', margin: 0 }}>
                With gradient background
              </p>
            </Card>
            <GlassCard>
              <h3 style={{ margin: '0 0 8px 0' }}>Glass Card</h3>
              <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', margin: 0 }}>
                Glassmorphism effect
              </p>
            </GlassCard>
          </Grid>
        </section>

        <section>
          <h2>💎 Gradient Badges</h2>
          <Inline spacing="md">
            <GradientBadge variant="blue">Blue Badge</GradientBadge>
            <GradientBadge variant="green">Success</GradientBadge>
            <GradientBadge variant="purple">Premium</GradientBadge>
            <GradientBadge variant="orange" glow>With Glow</GradientBadge>
          </Inline>
        </section>

        <section>
          <h2>📝 Enhanced Inputs</h2>
          <Stack spacing="md">
            <Input placeholder="Focus me to see enhanced ring..." />
            <Input placeholder="With placeholder text..." />
            <Input error placeholder="Error state with red ring" />
          </Stack>
        </section>

        <section>
          <h2>✅ Animated Checkbox</h2>
          <Stack spacing="sm">
            <AnimatedCheckbox checked={checked} onChange={(e) => setChecked(e.target.checked)}>
              Click me to see bounce animation!
            </AnimatedCheckbox>
            <AnimatedCheckbox>Another checkbox</AnimatedCheckbox>
            <AnimatedCheckbox>One more option</AnimatedCheckbox>
          </Stack>
        </section>

        <section>
          <h2>🎉 Success Animation</h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
            <Button onClick={handleSuccess}>
              Trigger Success Animation
            </Button>
            {showSuccess && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                <SuccessCheckmark size={48} />
                <span style={{ fontSize: '18px', fontWeight: 600, color: 'var(--color-green-500)' }}>
                  Success!
                </span>
              </div>
            )}
          </div>
          <Alert variant="info" style={{ marginTop: '16px' }}>
            Click the button above to see animated checkmark + confetti!
          </Alert>
        </section>

        <section>
          <h2>🌈 All Together</h2>
          <Grid cols={2} gap="lg">
            <GlassCard>
              <Stack spacing="md">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <GradientBadge variant="blue">New</GradientBadge>
                  <h3 style={{ margin: 0 }}>Glass Form</h3>
                </div>
                <Input placeholder="Username..." />
                <Input type="password" placeholder="Password..." />
                <AnimatedCheckbox>Remember me</AnimatedCheckbox>
                <Button variant="primary" style={{ width: '100%' }}>Sign In</Button>
              </Stack>
            </GlassCard>

            <Card hover gradient>
              <Stack spacing="md">
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <GradientBadge variant="green">Active</GradientBadge>
                  <h3 style={{ margin: 0 }}>Statistics</h3>
                </div>
                <div style={{ fontSize: '32px', fontWeight: 'bold' }}>1,234</div>
                <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)', margin: 0 }}>
                  Total certificates managed
                </p>
                <Button variant="secondary">View Details</Button>
              </Stack>
            </Card>
          </Grid>
        </section>

        <Alert variant="success">
          🎉 All phases (1-5) implemented! Design system is production-ready.
        </Alert>
      </Stack>
    </Container>
  );
}
