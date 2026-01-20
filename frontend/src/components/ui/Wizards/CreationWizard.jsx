import React from 'react';
import { Paper, Group, Text, Button, Box, Stepper, ScrollArea } from '../../../components/ui';

export const CreationWizard = ({ 
  title, 
  steps, 
  activeStep, 
  onStepChange, 
  onCancel, 
  onComplete, 
  loading = false,
  children 
}) => {
  const currentStep = steps[activeStep];
  const isLastStep = activeStep === steps.length - 1;

  return (
    <div style={{ 
      height: '100%', 
      display: 'flex', 
      flexDirection: 'column', 
      background: 'var(--bg-app)', 
      position: 'relative',
      overflow: 'hidden',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px'
    }}>
      {/* Widget Container */}
      <Paper 
        radius="xs" 
        style={{ 
          width: '100%', 
          maxWidth: '800px', 
          height: 'fit-content', 
          maxHeight: '100%',
          display: 'flex', 
          flexDirection: 'column',
          border: '1px solid var(--border-color)',
          background: 'var(--bg-panel)',
          overflow: 'hidden',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.2)'
        }}
      >
        {/* Header */}
        <div style={{ 
          padding: '16px 24px', 
          borderBottom: '1px solid var(--border-color)',
          background: 'var(--bg-panel)'
        }}>
          <Text size="lg" fw={600} style={{ color: 'var(--text-primary)' }}>{title}</Text>
          <Text size="xs" c="dimmed" mt={4}>{currentStep.description}</Text>
          
          <Box mt="md">
            <Stepper 
              active={activeStep} 
              onStepClick={onStepChange} 
              size="xs"
              styles={{
                stepIcon: {
                  borderRadius: 'var(--radius)',
                  borderWidth: '1px',
                  backgroundColor: 'var(--bg-element)',
                  borderColor: 'var(--border-color)',
                  color: 'var(--text-secondary)'
                },
                stepCompletedIcon: {
                  backgroundColor: 'var(--accent-primary)',
                  borderColor: 'var(--accent-primary)',
                  color: 'white'
                },
                separator: {
                  backgroundColor: 'var(--border-color)',
                  height: '1px'
                },
                stepLabel: {
                  fontSize: '13px',
                  color: 'var(--text-primary)'
                },
                stepDescription: {
                   fontSize: '11px',
                   color: 'var(--text-muted)'
                }
              }}
            >
              {steps.map((step, index) => (
                <Stepper.Step 
                  key={index} 
                  label={step.label} 
                  description={step.description}
                  allowStepSelect={activeStep > index}
                />
              ))}
            </Stepper>
          </Box>
        </div>

        {/* Content Body */}
        <ScrollArea style={{ flex: 1, backgroundColor: 'var(--bg-surface)' }}>
          <div style={{ padding: '24px' }}>
            {children}
          </div>
        </ScrollArea>

        {/* Footer Actions - Inside Widget */}
        <div style={{ 
          padding: '16px 24px', 
          borderTop: '1px solid var(--border-color)',
          background: 'var(--bg-panel)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <Button 
            variant="subtle" 
            color="gray" 
            onClick={onCancel}
            size="xs"
          >
            Cancel
          </Button>

          <Group gap="sm">
            {activeStep > 0 && (
              <Button 
                variant="default" 
                onClick={() => onStepChange(activeStep - 1)}
                size="xs"
                style={{ background: 'var(--bg-element)', borderColor: 'var(--border-color)', color: 'var(--text-primary)' }}
              >
                Back
              </Button>
            )}
            
            <Button 
              onClick={() => {
                if (isLastStep) {
                  onComplete();
                } else {
                  onStepChange(activeStep + 1);
                }
              }}
              loading={loading}
              size="xs"
              disabled={currentStep.disabled}
              style={{ 
                background: 'var(--accent-primary)',
                color: 'white',
                border: 'none'
              }}
            >
              {isLastStep ? 'Create' : 'Next'}
            </Button>
          </Group>
        </div>
      </Paper>
    </div>
  );
};

export const WizardStep = ({ children }) => (
  <Paper p="lg" radius="xs" style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-color)' }}>
    {children}
  </Paper>
);
