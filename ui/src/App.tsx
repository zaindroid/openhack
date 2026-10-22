export function App() {
  const api = import.meta.env.VITE_API_URL ?? "http://localhost:18000";

  return (
    <main>
      <h1>FloodSense EU</h1>
      <p>Skeleton UI. The console is not built yet.</p>
      <p>
        API health: <code>{api}/health</code>
      </p>
    </main>
  );
}
