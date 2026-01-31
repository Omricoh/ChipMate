import { Layout } from '../components/common/Layout';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';

export default function AdminLogin() {
  const { isAdmin } = useAuth();
  const navigate = useNavigate();

  // If already logged in as admin, go to dashboard
  useEffect(() => {
    if (isAdmin) {
      navigate('/admin/dashboard', { replace: true });
    }
  }, [isAdmin, navigate]);

  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Admin Login
        </h1>
        <p className="text-gray-500 mb-8">
          Log in with your admin credentials.
        </p>
        <div className="w-full max-w-xs rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8">
          <p className="text-sm text-gray-400">
            Admin login form will be implemented here.
          </p>
        </div>
      </div>
    </Layout>
  );
}
