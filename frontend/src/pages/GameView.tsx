import { useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';
import { useAuth } from '../hooks/useAuth';

export default function GameView() {
  const { gameId } = useParams<{ gameId: string }>();
  const { user, isManager } = useAuth();

  const gameCode =
    user?.kind === 'player' ? user.gameCode : undefined;

  return (
    <Layout gameCode={gameCode}>
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          {isManager ? 'Manager Dashboard' : 'Game View'}
        </h1>
        <p className="text-gray-500 mb-4">
          Game ID: {gameId}
        </p>
        <div className="w-full rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8">
          <p className="text-sm text-gray-400">
            {isManager
              ? 'Manager game dashboard will be implemented here.'
              : 'Player game view will be implemented here.'}
          </p>
        </div>
      </div>
    </Layout>
  );
}
