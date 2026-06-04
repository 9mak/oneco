import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PrefectureContextBar } from './PrefectureContextBar';

describe('PrefectureContextBar', () => {
  it('選択中の都道府県が見出しに表示される', () => {
    render(<PrefectureContextBar prefecture="東京都" backHref="/" />);
    expect(
      screen.getByRole('heading', { name: /東京都の保護動物/ }),
    ).toBeInTheDocument();
  });

  it('全国マップに戻るリンクが backHref を指す（他フィルタ保持）', () => {
    render(<PrefectureContextBar prefecture="東京都" backHref="/?species=犬" />);
    const link = screen.getByRole('link', { name: /全国マップに戻る/ });
    expect(link).toHaveAttribute('href', '/?species=犬');
  });
});
