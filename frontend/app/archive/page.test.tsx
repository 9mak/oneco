import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { ArchivedAnimalPublic } from '@/types/animal';

// 外部 API (バックエンドの /archive/animals) だけを差し替える
vi.mock('@/lib/archive', () => ({
  fetchArchivedAnimals: vi.fn(),
}));

import { fetchArchivedAnimals } from '@/lib/archive';
import ArchivePage, { metadata } from './page';

const graduated: ArchivedAnimalPublic = {
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

function respond(items: ArchivedAnimalPublic[], totalCount: number) {
  vi.mocked(fetchArchivedAnimals).mockResolvedValue({
    items,
    meta: {
      total_count: totalCount,
      limit: 24,
      offset: 0,
      current_page: 1,
      total_pages: totalCount > 0 ? 1 : 0,
      has_next: false,
    },
  });
}

describe('ArchivePage の空表示 (T414)', () => {
  beforeEach(() => {
    respond([], 0);
  });

  it('記録が無いとき、実際には動いていない「一定期間後に記録される」を約束しない', async () => {
    render(await ArchivePage());

    expect(screen.getByText('まだ卒業した子の記録はありません')).toBeInTheDocument();
    expect(screen.queryByText(/一定期間経過後にこちらへ記録されます/)).not.toBeInTheDocument();
  });

  it('記録が無いとき、いま家族を待っている子の一覧へタップで行けるリンクを出す', async () => {
    render(await ArchivePage());

    // ヘッダーの「動物一覧」は幅 640px 未満で非表示のため、空表示そのものにリンクを置く
    const link = screen.getByRole('link', { name: '動物一覧を見る' });
    expect(link).toHaveAttribute('href', '/');
  });

  it('記録が無いとき件数を出さない', async () => {
    render(await ArchivePage());

    expect(screen.queryByText(/これまでに/)).not.toBeInTheDocument();
  });
});

describe('ArchivePage の文言が未検証の因果を主張しない (T414)', () => {
  it('description は oneco を通じて出会いが生まれたとは書かない', () => {
    expect(String(metadata.description)).not.toMatch(/出会い/);
    expect(String(metadata.description)).toMatch(/譲渡/);
  });

  it('記録があるとき、件数は「出会い」ではなく記録の件数として出す', async () => {
    respond([graduated], 3);
    render(await ArchivePage());

    expect(screen.getByText('これまでに 3 件の卒業を記録しています')).toBeInTheDocument();
    expect(screen.queryByText(/出会いが生まれました/)).not.toBeInTheDocument();
  });
});
