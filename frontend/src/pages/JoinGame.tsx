import { useParams } from 'react-router-dom';
import { Layout } from '../components/common/Layout';

export default function JoinGame() {
  const { gameCode } = useParams<{ gameCode?: string }>();

  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Join Game
        </h1>
        <p className="text-gray-500">
          {gameCode
            ? `Joining game with code: ${gameCode}`
            : 'Enter a game code and your display name to join.'}
        </p>
        <div className="mt-8 w-full max-w-xs rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8">
          <p className="text-sm text-gray-400">
            Join form will be implemented here.
          </p>
        </div>
      </div>
    </Layout>
  );
}
