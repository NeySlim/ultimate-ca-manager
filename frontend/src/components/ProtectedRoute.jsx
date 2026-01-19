import { Navigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { Center, Loader } from '@mantine/core';

export const ProtectedRoute = ({ children }) => {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <Center h="100vh" style={{ background: '#1a1a1a' }}>
        <Loader size="lg" color="blue" />
      </Center>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return children;
};
