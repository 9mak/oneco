import { ImageResponse } from 'next/og';

export const alt = 'oneco - 全国の保護動物を、ひとつに。';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

/**
 * OGP 画像（新ブランド版）
 * ふたつの円 = コーラル(犬のポム) × ブルーグリーン(猫のビリー)。
 * ティール側を半透明にして重なりの色を作る (satori は mix-blend-mode 非対応)。
 * 右端で円が見切れる構図は原案の「切れた円」の継承。
 */
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          position: 'relative',
          background: '#FCFBF9',
          fontFamily: '"Hiragino Sans", "Yu Gothic", sans-serif',
        }}
      >
        {/* コーラルの円 (ポム) */}
        <div
          style={{
            position: 'absolute',
            left: 600,
            top: 70,
            width: 400,
            height: 400,
            borderRadius: 9999,
            background: 'radial-gradient(circle at 35% 30%, #F4A28E 0%, #E8826E 55%, #DB6C58 100%)',
          }}
        />
        {/* ブルーグリーンの円 (ビリー・大きい方・右端で見切れる) */}
        <div
          style={{
            position: 'absolute',
            left: 790,
            top: 120,
            width: 470,
            height: 470,
            borderRadius: 9999,
            opacity: 0.85,
            background:
              'linear-gradient(180deg, #83BCC6 0%, #6FAEBB 38%, #A9BD90 58%, #D8BE82 72%, #7FAFC2 88%, #6BA3B8 100%)',
          }}
        />
        {/* テキストブロック */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            paddingLeft: 90,
            height: '100%',
          }}
        >
          <div
            style={{
              fontSize: 120,
              fontWeight: 700,
              color: '#23262B',
              letterSpacing: '0.02em',
            }}
          >
            oneco
          </div>
          <div
            style={{
              fontSize: 38,
              color: '#23262B',
              fontWeight: 500,
              marginTop: 28,
              letterSpacing: '0.14em',
            }}
          >
            全国の保護動物を、ひとつに。
          </div>
          <div
            style={{
              fontSize: 24,
              color: '#6E7178',
              marginTop: 20,
              letterSpacing: '0.06em',
            }}
          >
            47都道府県の自治体公開情報を毎日集約
          </div>
        </div>
      </div>
    ),
    size,
  );
}
