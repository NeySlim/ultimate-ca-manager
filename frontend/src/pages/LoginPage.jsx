import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import {
  Box,
  Stack,
  TextInput,
  PasswordInput,
  Button,
  Text,
  Center,
  Paper,
  Group,
  Checkbox
} from '@mantine/core';
import { Certificate, SignIn } from '@phosphor-icons/react';
import { notifications } from '@mantine/notifications';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!username || !password) {
      notifications.show({
        title: 'Validation Error',
        message: 'Please enter username and password',
        color: 'orange'
      });
      return;
    }

    setLoading(true);
    const result = await login(username, password);
    setLoading(false);

    if (result.success) {
      notifications.show({
        title: 'Welcome!',
        message: 'Successfully logged in',
        color: 'green'
      });
      navigate('/dashboard');
    } else {
      notifications.show({
        title: 'Login Failed',
        message: result.error || 'Invalid credentials',
        color: 'red'
      });
    }
  };

  return (
    <Box
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px'
      }}
    >
      <Paper
        p="xl"
        radius="md"
        withBorder
        style={{
          width: '100%',
          maxWidth: '400px',
          background: '#2a2a2a',
          borderColor: '#3a3a3a'
        }}
      >
        <Stack gap="lg">
          {/* Logo */}
          <Center>
            <Group gap="sm">
              <Certificate
                size={48}
                weight="duotone"
                className="icon-gradient"
                style={{
                  '--accent-start': '#5a8fc7',
                  '--accent-end': '#7aa5d9'
                }}
              />
              <div>
                <Text size="24px" fw={600}>UCM</Text>
                <Text size="13px" c="dimmed">Certificate Manager</Text>
              </div>
            </Group>
          </Center>

          {/* Login Form */}
          <form onSubmit={handleSubmit}>
            <Stack gap="md">
              <TextInput
                label="Username"
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                size="sm"
                styles={{
                  label: { fontSize: '13px', fontWeight: 500 }
                }}
              />

              <PasswordInput
                label="Password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                size="sm"
                styles={{
                  label: { fontSize: '13px', fontWeight: 500 }
                }}
              />

              <Group justify="space-between">
                <Checkbox
                  label="Remember me"
                  size="xs"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.currentTarget.checked)}
                />
                <Text size="xs" c="dimmed" style={{ cursor: 'pointer' }}>
                  Forgot password?
                </Text>
              </Group>

              <Button
                type="submit"
                fullWidth
                loading={loading}
                leftSection={<SignIn size={16} />}
                style={{
                  height: '32px',
                  background: 'linear-gradient(135deg, #5a8fc7, #7aa5d9)',
                  border: 'none'
                }}
              >
                Sign In
              </Button>
            </Stack>
          </form>

          <Text size="11px" c="dimmed" ta="center">
            v2.0.0 • React + Mantine
          </Text>
        </Stack>
      </Paper>
    </Box>
  );
}
