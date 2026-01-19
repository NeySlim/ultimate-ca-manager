/**
 * Modern Login Page
 * Progressive auth flow with smooth transitions
 */

import { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Title,
  Text,
  TextInput,
  PasswordInput,
  Button,
  Checkbox,
  Anchor,
  Stack,
  Group,
  Box,
  Transition,
  Loader,
  Alert,
} from '@mantine/core';
import {
  IconLock,
  IconFingerprint,
  IconShieldCheck,
  IconAlertCircle,
  IconCheck,
} from '@tabler/icons-react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import classes from './LoginPage.module.css';

export function LoginPage() {
  const { login, loginWithWebAuthn, authState, resetIdentity, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      await login(username, password, rememberMe);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    }
  };

  const handleWebAuthnLogin = async () => {
    setError('');
    try {
      await loginWithWebAuthn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'WebAuthn failed');
    }
  };

  // Get remembered username
  const rememberedUsername = localStorage.getItem('ucm-username');

  return (
    <div className={classes.wrapper}>
      <Container size={420} className={classes.container}>
        <Box className={classes.logoBox}>
          <IconShieldCheck size={48} className={classes.logo} />
          <Title order={1} className={classes.title}>
            UCM
          </Title>
          <Text c="dimmed" size="sm" mt="xs">
            Ultimate Certificate Manager
          </Text>
        </Box>

        <Paper className={classes.card} shadow="xl" p="xl" radius="md">
          {/* Checking state */}
          <Transition
            mounted={authState === 'checking'}
            transition="fade"
            duration={300}
            timingFunction="ease"
          >
            {(styles) => (
              <Stack style={styles} align="center" gap="md" py="xl">
                <Loader size="lg" />
                <Text c="dimmed" size="sm">
                  Checking authentication...
                </Text>
              </Stack>
            )}
          </Transition>

          {/* mTLS detected */}
          <Transition
            mounted={authState === 'mtls_detected'}
            transition="slide-up"
            duration={400}
            timingFunction="ease"
          >
            {(styles) => (
              <Stack style={styles} align="center" gap="md" py="xl">
                <IconShieldCheck size={64} className={classes.successIcon} />
                <Text fw={500} size="lg">
                  Certificate detected
                </Text>
                <Text c="dimmed" size="sm" ta="center">
                  Authenticating with mTLS certificate...
                </Text>
                <Loader size="sm" />
              </Stack>
            )}
          </Transition>

          {/* WebAuthn available */}
          <Transition
            mounted={authState === 'webauthn_available'}
            transition="slide-up"
            duration={400}
            timingFunction="ease"
          >
            {(styles) => (
              <Stack style={styles} gap="md">
                {rememberedUsername && (
                  <Alert icon={<IconCheck size={16} />} color="blue" variant="light">
                    Welcome back, <strong>{rememberedUsername}</strong>
                  </Alert>
                )}

                <Button
                  size="lg"
                  leftSection={<IconFingerprint size={20} />}
                  onClick={handleWebAuthnLogin}
                  loading={authState === 'authenticating'}
                  fullWidth
                >
                  Use Biometric Login
                </Button>

                <Button variant="subtle" fullWidth onClick={() => navigate('/login/password')}>
                  Use password instead
                </Button>

                <Anchor
                  size="sm"
                  c="dimmed"
                  ta="center"
                  onClick={resetIdentity}
                  style={{ cursor: 'pointer' }}
                >
                  Not you?
                </Anchor>
              </Stack>
            )}
          </Transition>

          {/* Password form */}
          <Transition
            mounted={authState === 'password_required' || authState === 'authenticating' || authState === 'failed'}
            transition="slide-up"
            duration={400}
            timingFunction="ease"
          >
            {(styles) => (
              <form onSubmit={handlePasswordLogin} style={styles}>
                <Stack gap="md">
                  <Title order={3} ta="center" fw={500}>
                    Sign in
                  </Title>

                  {error && (
                    <Alert icon={<IconAlertCircle size={16} />} color="red" variant="light">
                      {error}
                    </Alert>
                  )}

                  {authState === 'failed' && (
                    <Alert icon={<IconAlertCircle size={16} />} color="red" variant="light">
                      Authentication failed. Please try again.
                    </Alert>
                  )}

                  <TextInput
                    label="Username"
                    placeholder="Your username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    disabled={authState === 'authenticating'}
                  />

                  <PasswordInput
                    label="Password"
                    placeholder="Your password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    disabled={authState === 'authenticating'}
                  />

                  <Group justify="space-between">
                    <Checkbox
                      label="Remember me"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.currentTarget.checked)}
                      disabled={authState === 'authenticating'}
                    />
                    <Anchor size="sm" c="dimmed">
                      Forgot password?
                    </Anchor>
                  </Group>

                  <Button
                    type="submit"
                    fullWidth
                    size="md"
                    leftSection={<IconLock size={18} />}
                    loading={authState === 'authenticating'}
                  >
                    Sign in
                  </Button>

                  {rememberedUsername && (
                    <Anchor
                      size="sm"
                      c="dimmed"
                      ta="center"
                      onClick={resetIdentity}
                      style={{ cursor: 'pointer' }}
                    >
                      Not you?
                    </Anchor>
                  )}
                </Stack>
              </form>
            )}
          </Transition>

          {/* Authenticated */}
          <Transition
            mounted={authState === 'authenticated'}
            transition="fade"
            duration={300}
            timingFunction="ease"
          >
            {(styles) => (
              <Stack style={styles} align="center" gap="md" py="xl">
                <IconCheck size={64} className={classes.successIcon} />
                <Text fw={500} size="lg">
                  Welcome back!
                </Text>
                <Text c="dimmed" size="sm">
                  Redirecting to dashboard...
                </Text>
              </Stack>
            )}
          </Transition>
        </Paper>

        <Text c="dimmed" size="xs" ta="center" mt="xl">
          Secured by UCM • v2.0
        </Text>
      </Container>
    </div>
  );
}
