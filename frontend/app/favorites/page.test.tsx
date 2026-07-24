import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import type { AnimalPublic } from '@/types/animal';
import FavoritesPage from './page';

// localStorage 非依存にするため useFavorites を固定 3 件でモックする。
vi.mock('@/lib/favorites', () => ({
  useFavorites: () => ({
    favorites: [1, 2, 3],
    add: vi.fn(),
    remove: vi.fn(),
    toggle: vi.fn(),
    has: (id: number) => [1, 2, 3].includes(id),
  }),
}));

const mockAnimal: AnimalPublic = {
  id: 1,
  species: '犬',
  sex: '男の子',
  age_months: 24,
  color: '茶色',
  size: '中型',
  shelter_date: '2024-01-15',
  location: '高知県中央小動物管理センター',
  prefecture: '高知県',
  phone: '088-831-7939',
  image_urls: ['https://example.com/dog1.jpg'],
  source_url: 'https://kochi-apc.com/jouto/dog1',
  category: 'adoption',
};

/** id ごとに HTTP ステータスを差し替えられる fetch モック */
function stubFetch(byId: Record<number, number>) {
  const fetchMock = vi.fn((url: string) => {
    const id = Number(url.split('/').pop());
    const status = byId[id] ?? 200;
    if (status === 200) {
      return Promise.resolve({
        ok: true,
        status,
        json: () => Promise.resolve({ ...mockAnimal, id }),
      });
    }
    return Promise.resolve({ ok: false, status });
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('FavoritesPage の取得失敗分類', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('404 のみを「譲渡済み等」、5xx は一時障害として分けて表示する', async () => {
    // id1=200(取得成功) / id2=404(譲渡済み等) / id3=500(一時障害)
    stubFetch({ 1: 200, 2: 404, 3: 500 });

    render(<FavoritesPage />);

    // 取得できた個体は通常カードとして表示される
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '犬' })).toBeInTheDocument(),
    );

    // 404 は「譲渡済み等」注記（1件）
    expect(
      screen.getByText(/1件は元データが見つかりませんでした（譲渡済み等）/),
    ).toBeInTheDocument();
    // 500 は「譲渡済み」と混同せず一時障害として案内（1件）
    expect(screen.getByText(/1件は一時的に読み込めませんでした/)).toBeInTheDocument();
    // 一部成功しているので全面エラー画面にはしない
    expect(screen.queryByText(/読み込みに失敗しました/)).not.toBeInTheDocument();
  });

  it('全件 5xx のときは「譲渡済み」ではなく全面エラーを表示する', async () => {
    stubFetch({ 1: 503, 2: 500, 3: 502 });

    render(<FavoritesPage />);

    await waitFor(() =>
      expect(screen.getByText(/読み込みに失敗しました/)).toBeInTheDocument(),
    );
    // 一時障害を「譲渡済み等」と誤案内しない
    expect(screen.queryByText(/譲渡済み等/)).not.toBeInTheDocument();
  });
});
