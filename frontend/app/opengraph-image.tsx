import { ImageResponse } from 'next/og';

export const alt = 'oneco - 全国の保護動物情報';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background:
            'linear-gradient(135deg, #fff7ed 0%, #ffedd5 50%, #fed7aa 100%)',
          fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
        }}
      >
        <div
          style={{
            fontSize: 96,
            fontWeight: 700,
            color: '#9a3412',
            letterSpacing: '-0.02em',
            marginBottom: 32,
          }}
        >
          oneco
        </div>
        <div
          style={{
            fontSize: 36,
            color: '#7c2d12',
            fontWeight: 500,
            textAlign: 'center',
            maxWidth: 900,
          }}>
          全国の保護動物を一つに
        </div>
        <div
          style={{
            fontSize: 22,
            color: '#9a3412',
            marginTop: 24,
            opacity: 0.8,
          }}
        >
          自治体の保護動物情報を統一プラットフォームで
        </div>
        <div
          style={{
            display: 'flex',
            gap: 12,
            marginTop: 48,
            fontSize: 32,
          }}
        >
          <span>🐕</span>
          <span>🐈</span>
        </div>
      </div>
    ),
    size,
  );
}
