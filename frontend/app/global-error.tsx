'use client';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="ja">
      <body>
        <main
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#f9fafb',
            fontFamily: 'system-ui, sans-serif',
          }}
        >
          <div style={{ textAlign: 'center', padding: '0 16px', maxWidth: '480px' }}>
            <h1 style={{ fontSize: '28px', fontWeight: 700, marginBottom: '16px' }}>
              アプリケーションエラー
            </h1>
            <p style={{ color: '#4b5563', marginBottom: '24px' }}>
              申し訳ありません、致命的なエラーが発生しました。
            </p>
            <button
              type="button"
              onClick={reset}
              style={{
                padding: '12px 24px',
                backgroundColor: '#f97316',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontSize: '16px',
                cursor: 'pointer',
              }}
            >
              再試行
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}
