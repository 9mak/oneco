import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { FilterPanel } from './FilterPanel';
import { FilterState } from '@/types/animal';

const mockReplace = vi.fn();
let currentSearchParams = new URLSearchParams();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: mockReplace,
  }),
  useSearchParams: () => currentSearchParams,
}));

describe('FilterPanel', () => {
  beforeEach(() => {
    mockReplace.mockClear();
    currentSearchParams = new URLSearchParams();
  });

  const defaultFilters: FilterState = {};

  it('フィルタパネルが正しくレンダリングされる', () => {
    render(<FilterPanel filters={defaultFilters} />);

    expect(screen.getByRole('tab', { name: '収容中の子を探す' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '家族を迎える' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '迷子情報' })).toBeInTheDocument();
  });

  it('迷子情報タブをクリックするとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.click(screen.getByRole('tab', { name: '迷子情報' }));

    expect(mockReplace).toHaveBeenCalledWith('?category=lost', { scroll: false });
  });

  it('カテゴリタブをクリックするとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.click(screen.getByRole('tab', { name: '家族を迎える' }));

    expect(mockReplace).toHaveBeenCalledWith('?category=adoption', { scroll: false });
  });

  it('種別フィルタを変更するとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.change(screen.getByLabelText('種別'), { target: { value: '犬' } });

    expect(mockReplace).toHaveBeenCalledWith('?species=%E7%8A%AC', { scroll: false });
  });

  it('キーワード検索はdebounce後にURLを更新する', () => {
    vi.useFakeTimers();
    try {
      render(<FilterPanel filters={defaultFilters} />);

      fireEvent.change(screen.getByLabelText('キーワード検索'), {
        target: { value: 'shiba' },
      });
      // debounce 経過前は更新しない
      expect(mockReplace).not.toHaveBeenCalled();

      act(() => { vi.advanceTimersByTime(400); });
      expect(mockReplace).toHaveBeenCalledWith('?q=shiba', { scroll: false });
    } finally {
      vi.useRealTimers();
    }
  });

  it('連続入力では最後の値のみで一度だけ更新する', () => {
    vi.useFakeTimers();
    try {
      render(<FilterPanel filters={defaultFilters} />);
      const input = screen.getByLabelText('キーワード検索');

      fireEvent.change(input, { target: { value: 's' } });
      act(() => { vi.advanceTimersByTime(100); });
      fireEvent.change(input, { target: { value: 'shi' } });
      act(() => { vi.advanceTimersByTime(100); });
      fireEvent.change(input, { target: { value: 'shiba' } });
      act(() => { vi.advanceTimersByTime(400); });

      expect(mockReplace).toHaveBeenCalledTimes(1);
      expect(mockReplace).toHaveBeenCalledWith('?q=shiba', { scroll: false });
    } finally {
      vi.useRealTimers();
    }
  });

  it('適用中フィルタがチップとして表示される', () => {
    currentSearchParams = new URLSearchParams('species=犬&prefecture=東京都');
    render(
      <FilterPanel filters={{ species: '犬', prefecture: '東京都' }} />,
    );

    expect(
      screen.getByRole('button', { name: /犬 の絞り込みを解除/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /東京都 の絞り込みを解除/ }),
    ).toBeInTheDocument();
  });

  it('チップの解除ボタンで該当フィルタが外れる', () => {
    currentSearchParams = new URLSearchParams('species=犬');
    render(<FilterPanel filters={{ species: '犬' }} />);

    fireEvent.click(screen.getByRole('button', { name: /犬 の絞り込みを解除/ }));

    expect(mockReplace).toHaveBeenCalledWith('/', { scroll: false });
  });

  it('並び替えを「古い順」に変更するとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.change(screen.getByLabelText('並び替え'), { target: { value: 'oldest' } });

    expect(mockReplace).toHaveBeenCalledWith('?sort=oldest', { scroll: false });
  });

  it('並び替えを「新着順」に戻すとsortパラメータが消える', () => {
    currentSearchParams = new URLSearchParams('sort=oldest');
    render(<FilterPanel filters={{ sort: 'oldest' }} />);

    fireEvent.change(screen.getByLabelText('並び替え'), { target: { value: 'newest' } });

    expect(mockReplace).toHaveBeenCalledWith('/', { scroll: false });
  });

  it('性別フィルタを変更するとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.change(screen.getByLabelText('性別'), { target: { value: '男の子' } });

    expect(mockReplace).toHaveBeenCalledWith(
      '?sex=%E7%94%B7%E3%81%AE%E5%AD%90',
      { scroll: false },
    );
  });

  it('地域フィルタを変更するとURLが更新される', () => {
    render(<FilterPanel filters={defaultFilters} />);

    fireEvent.change(screen.getByLabelText('地域'), { target: { value: '高知県' } });

    expect(mockReplace).toHaveBeenCalledWith(
      '?prefecture=%E9%AB%98%E7%9F%A5%E7%9C%8C',
      { scroll: false },
    );
  });

  it('フィルタが空のときはクリアボタンが表示されない', () => {
    render(<FilterPanel filters={defaultFilters} />);
    expect(
      screen.queryByRole('button', { name: 'フィルタをクリア' }),
    ).not.toBeInTheDocument();
  });

  it('フィルタが適用されている時にクリアボタンが表示される', () => {
    const filters: FilterState = { species: '犬' };
    currentSearchParams = new URLSearchParams({ species: '犬' });
    render(<FilterPanel filters={filters} />);

    const clearButton = screen.getByRole('button', { name: 'フィルタをクリア' });
    expect(clearButton).toBeInTheDocument();

    fireEvent.click(clearButton);
    expect(mockReplace).toHaveBeenCalledWith('/', { scroll: false });
  });

  it('「収容中の子を探す」タブをクリックするとカテゴリ制約が外れる', () => {
    const filters: FilterState = { category: 'adoption' };
    currentSearchParams = new URLSearchParams({ category: 'adoption' });
    render(<FilterPanel filters={filters} />);

    fireEvent.click(screen.getByRole('tab', { name: '収容中の子を探す' }));

    // category=adoption が削除され、sheltered タブ（デフォルト）に戻る
    expect(mockReplace).toHaveBeenCalledWith('/', { scroll: false });
  });

  it('デフォルト状態では「収容中の子を探す」タブが active', () => {
    render(<FilterPanel filters={{ status: 'sheltered' }} />);

    const shelteredTab = screen.getByRole('tab', { name: '収容中の子を探す' });
    expect(shelteredTab).toHaveAttribute('aria-selected', 'true');
  });

  it('category=adoption 時は「家族を迎える」タブが active', () => {
    render(
      <FilterPanel
        filters={{ status: 'sheltered', category: 'adoption' }}
      />,
    );

    const adoptionTab = screen.getByRole('tab', { name: '家族を迎える' });
    expect(adoptionTab).toHaveAttribute('aria-selected', 'true');
  });

  it('種別を空に戻すとパラメータが削除される', () => {
    const filters: FilterState = { species: '犬' };
    currentSearchParams = new URLSearchParams({ species: '犬' });
    render(<FilterPanel filters={filters} />);

    fireEvent.change(screen.getByLabelText('種別'), { target: { value: '' } });

    expect(mockReplace).toHaveBeenCalledWith('/', { scroll: false });
  });
});
