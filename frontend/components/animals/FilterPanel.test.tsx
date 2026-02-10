import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FilterPanel } from './FilterPanel';
import { FilterState } from '@/types/animal';

describe('FilterPanel', () => {
  const mockOnFilterChange = vi.fn();
  const mockOnClearFilters = vi.fn();

  const defaultFilters: FilterState = {};

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('フィルタパネルが正しくレンダリングされる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    expect(screen.getByText('絞り込み検索')).toBeInTheDocument();
    expect(screen.getByText('42件の動物')).toBeInTheDocument();
  });

  it('カテゴリフィルタが変更されるとonFilterChangeが呼ばれる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    const categorySelect = screen.getByLabelText('カテゴリ');
    fireEvent.change(categorySelect, { target: { value: 'adoption' } });

    expect(mockOnFilterChange).toHaveBeenCalledWith('category', 'adoption');
  });

  it('種別フィルタが変更されるとonFilterChangeが呼ばれる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    const speciesSelect = screen.getByLabelText('種別');
    fireEvent.change(speciesSelect, { target: { value: '犬' } });

    expect(mockOnFilterChange).toHaveBeenCalledWith('species', '犬');
  });

  it('性別フィルタが変更されるとonFilterChangeが呼ばれる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    const sexSelect = screen.getByLabelText('性別');
    fireEvent.change(sexSelect, { target: { value: '男の子' } });

    expect(mockOnFilterChange).toHaveBeenCalledWith('sex', '男の子');
  });

  it('地域フィルタが入力できる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    const locationInput = screen.getByLabelText('地域') as HTMLInputElement;
    fireEvent.change(locationInput, { target: { value: '高知' } });

    // 入力値が設定される
    expect(locationInput.value).toBe('高知');
  });

  it('フィルタが適用されている場合、「フィルタをクリア」ボタンが表示される', () => {
    const activeFilters: FilterState = { category: 'adoption' };
    render(
      <FilterPanel
        filters={activeFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={10}
      />
    );

    expect(screen.getByRole('button', { name: 'フィルタをクリア' })).toBeInTheDocument();
  });

  it('フィルタが適用されていない場合、「フィルタをクリア」ボタンが表示されない', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    expect(screen.queryByRole('button', { name: 'フィルタをクリア' })).not.toBeInTheDocument();
  });

  it('「フィルタをクリア」ボタンをクリックするとonClearFiltersが呼ばれる', () => {
    const activeFilters: FilterState = { category: 'adoption', species: '犬' };
    render(
      <FilterPanel
        filters={activeFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={10}
      />
    );

    const clearButton = screen.getByRole('button', { name: 'フィルタをクリア' });
    fireEvent.click(clearButton);

    expect(mockOnClearFilters).toHaveBeenCalledTimes(1);
  });

  it('現在適用されているフィルタ値が選択状態で表示される', () => {
    const activeFilters: FilterState = {
      category: 'lost',
      species: '猫',
      sex: '女の子',
      location: '北海道',
    };
    render(
      <FilterPanel
        filters={activeFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={5}
      />
    );

    expect(screen.getByLabelText('カテゴリ')).toHaveValue('lost');
    expect(screen.getByLabelText('種別')).toHaveValue('猫');
    expect(screen.getByLabelText('性別')).toHaveValue('女の子');
    expect(screen.getByLabelText('地域')).toHaveValue('北海道');
  });

  it('フィルタをデフォルト値に戻すとundefinedが渡される', () => {
    const activeFilters: FilterState = { category: 'adoption' };
    render(
      <FilterPanel
        filters={activeFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={10}
      />
    );

    const categorySelect = screen.getByLabelText('カテゴリ');
    fireEvent.change(categorySelect, { target: { value: '' } });

    expect(mockOnFilterChange).toHaveBeenCalledWith('category', undefined);
  });

  it('キーボードナビゲーションで全フィルタにフォーカスできる', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={42}
      />
    );

    const categorySelect = screen.getByLabelText('カテゴリ');
    const speciesSelect = screen.getByLabelText('種別');
    const sexSelect = screen.getByLabelText('性別');
    const locationInput = screen.getByLabelText('地域');

    // フォーカス可能なことを確認
    categorySelect.focus();
    expect(categorySelect).toHaveFocus();

    speciesSelect.focus();
    expect(speciesSelect).toHaveFocus();

    sexSelect.focus();
    expect(sexSelect).toHaveFocus();

    locationInput.focus();
    expect(locationInput).toHaveFocus();
  });

  it('結果件数が正しく表示される', () => {
    render(
      <FilterPanel
        filters={defaultFilters}
        onFilterChange={mockOnFilterChange}
        onClearFilters={mockOnClearFilters}
        resultCount={123}
      />
    );

    expect(screen.getByText('123件の動物')).toBeInTheDocument();
  });
});
