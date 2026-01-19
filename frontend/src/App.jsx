import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Box, Text, Center, Stack } from '@mantine/core';
import { CheckCircle } from '@phosphor-icons/react';

function TestPage() {
  return (
    <Center h="100vh" style={{ background: '#1a1a1a' }}>
      <Stack align="center" gap="lg">
        <CheckCircle 
          size={64} 
          weight="duotone"
          className="icon-gradient"
          style={{
            '--accent-start': '#5a8fc7',
            '--accent-end': '#7aa5d9'
          }}
        />
        <Text size="32px" fw={600}>UCM Frontend v2.0</Text>
        <Text size="15px" c="dimmed">React + Mantine + Vite</Text>
        <Box
          p="md"
          style={{
            background: '#2a2a2a',
            borderRadius: '3px',
            border: '1px solid #3a3a3a'
          }}
        >
          <Text size="13px" ff="JetBrains Mono">
            ✅ React 18.2<br/>
            ✅ Mantine 7.4<br/>
            ✅ Phosphor Icons<br/>
            ✅ Vite 5.0<br/>
            ✅ API Proxy configured
          </Text>
        </Box>
      </Stack>
    </Center>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<TestPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
