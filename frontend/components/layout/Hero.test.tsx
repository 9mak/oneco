import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Hero } from './Hero';

describe('Hero', () => {
  it('キャッチコピーの見出しが表示される', () => {
    render(<Hero />);
    expect(
      screen.getByRole('heading', { name: /全国の保護動物/ }),
    ).toBeInTheDocument();
  });

  it('サービスの説明文が表示される', () => {
    render(<Hero />);
    expect(screen.getByText(/まとめて検索できる/)).toBeInTheDocument();
  });

  it('利用の流れ3ステップが表示される', () => {
    render(<Hero />);
    expect(screen.getByText(/さがす/)).toBeInTheDocument();
    expect(screen.getByText(/見つける/)).toBeInTheDocument();
    expect(screen.getByText(/問い合わせ/)).toBeInTheDocument();
  });

  it('region ランドマークとして公開される', () => {
    render(<Hero />);
    expect(
      screen.getByRole('region', { name: /onecoとは/ }),
    ).toBeInTheDocument();
  });
});
