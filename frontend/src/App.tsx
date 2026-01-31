import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import JoinGame from './pages/JoinGame';
import GameView from './pages/GameView';
import AdminLogin from './pages/AdminLogin';
import AdminDashboard from './pages/AdminDashboard';
import NotFound from './pages/NotFound';
import { GameRoute, AdminRoute } from './components/common/RouteGuard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<Home />} />
        <Route path="/join" element={<JoinGame />} />
        <Route path="/join/:gameCode" element={<JoinGame />} />

        {/* Player / Manager routes */}
        <Route
          path="/game/:gameId"
          element={
            <GameRoute>
              <GameView />
            </GameRoute>
          }
        />

        {/* Admin routes */}
        <Route path="/admin" element={<AdminLogin />} />
        <Route
          path="/admin/dashboard"
          element={
            <AdminRoute>
              <AdminDashboard />
            </AdminRoute>
          }
        />

        {/* Catch-all */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
