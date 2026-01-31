import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import type { ReactNode } from 'react';

interface RouteGuardProps {
  children: ReactNode;
}

/**
 * Redirects to `/` if the user is not authenticated at all.
 */
export function ProtectedRoute({ children }: RouteGuardProps) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

/**
 * Redirects to `/admin` (login page) if the user is not an admin.
 */
export function AdminRoute({ children }: RouteGuardProps) {
  const { isAdmin } = useAuth();
  const location = useLocation();

  if (!isAdmin) {
    return <Navigate to="/admin" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

/**
 * Redirects to `/` if the user does not have a player token.
 */
export function GameRoute({ children }: RouteGuardProps) {
  const { isPlayer } = useAuth();
  const location = useLocation();

  if (!isPlayer) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
