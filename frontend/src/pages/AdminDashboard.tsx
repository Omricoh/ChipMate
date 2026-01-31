import { Layout } from '../components/common/Layout';

export default function AdminDashboard() {
  return (
    <Layout>
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">
          Admin Dashboard
        </h1>
        <p className="text-gray-500 mb-8">
          System overview, game list, and stats.
        </p>
        <div className="w-full rounded-lg border border-dashed border-gray-300 bg-gray-50 p-8">
          <p className="text-sm text-gray-400">
            Admin dashboard content will be implemented here.
          </p>
        </div>
      </div>
    </Layout>
  );
}
