import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnimalGrid } from './AnimalGrid';
import type { AnimalPublic, FilterState } from '@/types/animal';

// 子コンポーネントはモックし、AnimalGrid 単体の責務
// （件数表示・EmptyState 分岐・障害表示・aria）に集中する。
vi.mock('./AnimalCard', () => ({
  AnimalCard: ({ animal }: { animal: AnimalPublic }) => (
    <div data-testid="animal-card">{animal.id}</div>
  ),
}));
vi.mock('./LoadMore', () => ({
  LoadMore: () => <div data-testid="load-more" />,
}));

function mockAnimal(id: number): AnimalPublic {
  return {
    id,
    species: '犬',
    sex: '男の子',
    age_months: 24,
    color: '茶色',
    size: '中型',
    shelter_date: '2024-01-15',
    location: '高知県中央小動物管理センター',
    prefecture: '高知県',
    phone: '088-831-7939',
    image_urls: [],
    source_url: `https://example.com/${id}`,
    category: 'adoption',
  };
}

describe('AnimalGrid', () => {
  const emptyFilters: FilterState = {};

  it('件数を3桁区切りでローカライズ表示する', () => {
    render(
      <AnimalGrid
        initialItems={[mockAnimal(1)]}
        totalCount={1234}
        filters={emptyFilters}
      />,
    );

    expect(screen.getByText('1,234')).toBeInTheDocument();
    expect(screen.getByText(/件の動物/)).toBeInTheDocument();
  });

  it('件数表示は aria-live="polite" / aria-atomic="true" を持つ', () => {
    render(
      <AnimalGrid
        initialItems={[mockAnimal(1)]}
        totalCount={5}
        filters={emptyFilters}
      />,
    );

    const countParagraph = screen.getByText(/件の動物/).closest('p');
    expect(countParagraph).toHaveAttribute('aria-live', 'polite');
    expect(countParagraph).toHaveAttribute('aria-atomic', 'true');
  });

  it('各アイテムを AnimalCard として描画する', () => {
    render(
      <AnimalGrid
        initialItems={[mockAnimal(1), mockAnimal(2), mockAnimal(3)]}
        totalCount={3}
        filters={emptyFilters}
      />,
    );

    expect(screen.getAllByTestId('animal-card')).toHaveLength(3);
  });

  it('fetchFailed のときは「0件」ではなく障害として案内する', () => {
    render(
      <AnimalGrid
        initialItems={[]}
        totalCount={0}
        filters={emptyFilters}
        fetchFailed
      />,
    );

    expect(screen.getByText('現在情報を取得できません')).toBeInTheDocument();
    // 障害時は件数表示を出さない
    expect(screen.queryByText(/件の動物/)).not.toBeInTheDocument();
    expect(screen.queryByTestId('animal-card')).not.toBeInTheDocument();
  });

  it('フィルタ適用中の0件は「条件に合う動物が見つかりませんでした」＋クリア導線', () => {
    render(
      <AnimalGrid
        initialItems={[]}
        totalCount={0}
        filters={{ species: '犬' }}
      />,
    );

    expect(
      screen.getByText('条件に合う動物が見つかりませんでした'),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'フィルタをクリア' }),
    ).toBeInTheDocument();
  });

  it('フィルタ未適用の0件は「現在表示できる動物がいません」案内', () => {
    render(
      <AnimalGrid
        initialItems={[]}
        totalCount={0}
        filters={{ status: 'sheltered' }}
      />,
    );

    expect(
      screen.getByText('現在表示できる動物がいません'),
    ).toBeInTheDocument();
    // クリア導線は出さない
    expect(
      screen.queryByRole('link', { name: 'フィルタをクリア' }),
    ).not.toBeInTheDocument();
  });
});
