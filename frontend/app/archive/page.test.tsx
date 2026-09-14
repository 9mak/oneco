import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// 外部 API (バックエンドの /archive/animals) だけを差し替える
vi.mock('@/lib/archive', () => ({
  fetchArchivedAnimals: vi.fn(async () => ({
    items: [],
    meta: {
      total_count: 0,
      limit: 24,
      offset: 0,
      current_page: 1,
      total_pages: 0,
      has_next: false,
    },
  })),
}));

import ArchivePage from './page';

describe('ArchivePage の空表示 (T414)', () => {
  it('記録が無いとき、実際には動いていない「一定期間後に記録される」を約束しない', async () => {
    render(await ArchivePage());

    expect(screen.getByText('まだ卒業した子の記録はありません')).toBeInTheDocument();
    expect(screen.queryByText(/一定期間経過後にこちらへ記録されます/)).not.toBeInTheDocument();
  });

  it('記録が無いとき、いま家族を待っている子の一覧への行き先を示す', async () => {
    render(await ArchivePage());

    expect(screen.getByText(/いま家族を待っている子は「動物一覧」からさがせます/)).toBeInTheDocument();
  });

  it('記録が無いとき「出会い」の件数を出さない', async () => {
    render(await ArchivePage());

    expect(screen.queryByText(/件の出会いが生まれました/)).not.toBeInTheDocument();
  });
});
