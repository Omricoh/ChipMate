import { Link, useNavigate } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { useAuth } from '../hooks/useAuth';
import { useEffect } from 'react';

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // If the user already has an active session, redirect them
  useEffect(() => {
    if (user?.kind === 'admin') {
      navigate('/admin/dashboard', { replace: true });
    } else if (user?.kind === 'player') {
      navigate(`/game/${user.gameId}`, { replace: true });
    }
  }, [user, navigate]);

  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[70vh] text-center">
        <h1 className="text-5xl font-bold text-primary-700 mb-2">
          ChipMate
        </h1>
        <p className="text-gray-500 text-lg mb-12">
          Live Poker Game Management
        </p>

        <div className="w-full space-y-4">
          <Link
            to="/create"
            className="block w-full rounded-xl bg-primary-600 px-6 py-4 text-center text-lg font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-800"
          >
            New Game
          </Link>

          <Link
            to="/join"
            className="block w-full rounded-xl border-2 border-primary-600 px-6 py-4 text-center text-lg font-semibold text-primary-700 hover:bg-primary-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 active:bg-primary-100"
          >
            Join Game
          </Link>
        </div>

        <Link
          to="/admin"
          className="mt-16 text-sm text-gray-400 hover:text-gray-600 focus:outline-none focus-visible:underline"
        >
          Admin
        </Link>
      </div>
    </Layout>
  );
}
