import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ArchivedAnimalCard } from './ArchivedAnimalCard';
import { ArchivedAnimalPublic } from '@/types/animal';

const base: ArchivedAnimalPublic = {
  id: 99,
  original_id: 12,
  species: '犬',
  sex: '男の子',
  age_months: 24,
  color: '茶白',
  size: '中型',
  shelter_date: '2025-09-01',
  location: '高知県中央小動物管理センター',
  prefecture: '高知県',
  phone: '088-831-7939',
  image_urls: ['https://example.com/img1.jpg'],
  source_url: 'https://example.com/animal/12',
  category: 'adoption',
  status: 'adopted',
  status_changed_at: '2025-10-15T00:00:00',
  outcome_date: '2025-10-15',
  archived_at: '2026-04-15T00:00:00',
};

describe('ArchivedAnimalCard', () => {
  it('見出しには動物種別のみが表示される（性別を連結しない）', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.getByRole('heading', { name: '犬' })).toBeInTheDocument();
  });

  it('性別はラベル付きの項目として表示される', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.getByText('性別')).toBeInTheDocument();
    expect(screen.getByText('男の子')).toBeInTheDocument();
  });

  it('譲渡済バッジが表示される', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.getByText('譲渡')).toBeInTheDocument();
  });

  it('返還済の場合は返還バッジを表示する', () => {
    render(<ArchivedAnimalCard animal={{ ...base, status: 'returned' }} />);
    expect(screen.getByText('飼い主の元へ')).toBeInTheDocument();
  });

  it('卒業日（outcome_date）が表示される', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.getByText(/2025年10月15日/)).toBeInTheDocument();
  });

  it('outcome_date が無い場合は archived_at から表示する', () => {
    render(
      <ArchivedAnimalCard animal={{ ...base, outcome_date: null }} />,
    );
    expect(screen.getByText(/2026年4月15日/)).toBeInTheDocument();
  });

  it('問い合わせ不可の注意書きが表示される', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.getByText(/お問い合わせは受け付けて/)).toBeInTheDocument();
  });

  it('問い合わせ導線（電話番号リンク）は表示されない', () => {
    render(<ArchivedAnimalCard animal={base} />);
    expect(screen.queryByRole('link', { name: /088-831-7939/ })).not.toBeInTheDocument();
  });
});
