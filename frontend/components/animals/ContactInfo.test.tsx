import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ContactInfo } from './ContactInfo';

describe('ContactInfo', () => {
  const baseProps = {
    location: '高知県中央小動物管理センター',
    phone: '088-831-7939',
    category: 'adoption' as const,
  };

  it('収容場所を表示する', () => {
    render(<ContactInfo {...baseProps} />);
    expect(screen.getByText('高知県中央小動物管理センター')).toBeInTheDocument();
  });

  it('電話番号を tel: リンクで表示する', () => {
    render(<ContactInfo {...baseProps} />);
    const link = screen.getByRole('link', { name: '088-831-7939' });
    expect(link).toHaveAttribute('href', 'tel:088-831-7939');
  });

  it('phone が null のときは電話番号を表示しない', () => {
    render(<ContactInfo {...baseProps} phone={null} />);
    expect(screen.queryByText('電話番号')).not.toBeInTheDocument();
  });

  it('adoption カテゴリの案内文を表示する', () => {
    render(<ContactInfo {...baseProps} category="adoption" />);
    expect(
      screen.getByText('譲渡についてはお電話でお問い合わせください'),
    ).toBeInTheDocument();
  });

  it('lost カテゴリの案内文を表示する', () => {
    render(<ContactInfo {...baseProps} category="lost" />);
    expect(
      screen.getByText('飼い主の方はお早めにご連絡ください'),
    ).toBeInTheDocument();
  });

  it('情報鮮度の補助テキスト（元サイト確認の促し）を表示する', () => {
    render(<ContactInfo {...baseProps} />);
    expect(
      screen.getByText(/自治体の元サイトから自動取得/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/最新の掲載状況を元のサイトでもご確認ください/),
    ).toBeInTheDocument();
  });

  it('phone が null でも補助テキストは表示される', () => {
    render(<ContactInfo {...baseProps} phone={null} />);
    expect(
      screen.getByText(/最新の掲載状況を元のサイトでもご確認ください/),
    ).toBeInTheDocument();
  });
});
