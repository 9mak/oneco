/**
 * Hero Component
 * 初訪問者にサービスの目的と使い方を伝える導入セクション。
 * ホーム（フィルタ未適用時）でのみ表示する。
 */

const STEPS = [
  {
    icon: '🔍',
    title: 'さがす',
    body: '地域・種類・キーワードでしぼり込み、気になる子を探します。',
  },
  {
    icon: '🐾',
    title: '見つける',
    body: '写真や収容場所などの詳細を確認。お気に入りに保存できます。',
  },
  {
    icon: '📞',
    title: '問い合わせ',
    body: '掲載元の自治体・動物愛護センターに直接ご連絡ください。',
  },
];

export function Hero() {
  return (
    <section
      aria-label="onecoとは"
      className="rounded-2xl bg-gradient-to-br from-[var(--color-primary-50)] via-white to-[var(--color-accent-50)] border border-[var(--color-primary-100)] p-6 sm:p-10"
    >
      <div className="max-w-3xl">
        <h2
          className="text-2xl sm:text-3xl font-bold text-[var(--color-text-primary)] leading-snug"
        >
          全国の保護動物を、ひとつの場所で。
        </h2>
        <p className="mt-3 text-sm sm:text-base text-[var(--color-text-secondary)] leading-relaxed">
          各自治体の動物愛護センターに収容・譲渡対象として登録された犬や猫の情報を、
          oneco がまとめて検索できるようにしています。新しい家族を探している方も、
          迷子の子を探している飼い主の方も、まずはここから。
        </p>
      </div>

      <ol className="mt-8 grid grid-cols-1 sm:grid-cols-3 gap-4">
        {STEPS.map((step, i) => (
          <li
            key={step.title}
            className="relative flex flex-col gap-1 rounded-xl bg-white/70 backdrop-blur-sm p-4 border border-[var(--color-primary-100)]"
          >
            <div className="flex items-center gap-2">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--color-accent-100)] text-lg"
                aria-hidden="true"
              >
                {step.icon}
              </span>
              <span className="text-xs font-semibold text-[var(--color-accent-700)]">
                STEP {i + 1}
              </span>
            </div>
            <h3 className="mt-1 text-base font-semibold text-[var(--color-text-primary)]">
              {step.title}
            </h3>
            <p className="text-sm text-[var(--color-text-secondary)] leading-relaxed">
              {step.body}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
