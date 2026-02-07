import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import type { ReactNode } from 'react';

interface RouteGuardProps {
  children: ReactNode;
}

/**
 * Simple loading spinner shown while validating session.
 */
function LoadingScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-500 mx-auto" />
        <p className="mt-4 text-gray-400">Loading...</p>
      </div>
    </div>
  );
}

/**
 * Redirects to `/` if the user is not authenticated at all.
 */
export function ProtectedRoute({ children }: RouteGuardProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

/**
 * Redirects to `/admin` (login page) if the user is not an admin.
 */
export function AdminRoute({ children }: RouteGuardProps) {
  const { isAdmin, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isAdmin) {
    return <Navigate to="/admin" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}

/**
 * Redirects to `/` if the user does not have a player token.
 * Waits for session validation before redirecting.
 */
export function GameRoute({ children }: RouteGuardProps) {
  const { isPlayer, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return <LoadingScreen />;
  }

  if (!isPlayer) {
    return <Navigate to="/" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
