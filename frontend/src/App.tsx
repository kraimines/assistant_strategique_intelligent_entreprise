import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './stores/authStore';
import { ThemeProvider } from './contexts/ThemeContext';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import DigitalTwin from './pages/DigitalTwin';
import Simulation from './pages/Simulation';
import WorldModelExplorer from './pages/WorldModelExplorer';
import CompetitiveIntel from './pages/CompetitiveIntel';
import MarketAnalysis from './pages/MarketAnalysis';
import MarketSimulate from './pages/MarketSimulate';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();
  if (isAuthenticated) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
          <Route path="/signup" element={<PublicRoute><Signup /></PublicRoute>} />

          {/* Protected */}
          <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/chat" element={<ProtectedRoute><Chat /></ProtectedRoute>} />
          <Route path="/digital-twin" element={<ProtectedRoute><DigitalTwin /></ProtectedRoute>} />
          <Route path="/simulation" element={<ProtectedRoute><Simulation /></ProtectedRoute>} />
          <Route path="/world-model" element={<ProtectedRoute><WorldModelExplorer /></ProtectedRoute>} />
          <Route path="/competitive-intel" element={<ProtectedRoute><CompetitiveIntel /></ProtectedRoute>} />
          <Route path="/market-analysis"  element={<ProtectedRoute><MarketAnalysis /></ProtectedRoute>} />
          <Route path="/market-simulate"  element={<ProtectedRoute><MarketSimulate /></ProtectedRoute>} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
    </ThemeProvider>
  );
}
