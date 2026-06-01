import { describe, it, expect, beforeAll, afterAll, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StaleDataBadge } from './StaleDataBadge';

describe('StaleDataBadge', () => {
  beforeAll(() => {
    // 今日を 2026-06-01 に固定 (テスト独立性のため)
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-01T12:00:00+09:00'));
  });
  afterAll(() => {
    vi.useRealTimers();
  });

  it('収容から30日未満は何も表示しない', () => {
    // 2026-05-20 = 12日前
    const { container } = render(<StaleDataBadge shelterDate="2026-05-20" />);
    expect(container.firstChild).toBeNull();
  });

  it('収容から30日以上60日未満は「掲載から30日以上」を表示', () => {
    // 2026-04-15 = 47日前
    render(<StaleDataBadge shelterDate="2026-04-15" />);
    expect(screen.getByText(/30日以上/)).toBeInTheDocument();
  });

  it('収容から60日以上は「掲載から60日以上」を表示', () => {
    // 2026-03-01 = 92日前
    render(<StaleDataBadge shelterDate="2026-03-01" />);
    expect(screen.getByText(/60日以上/)).toBeInTheDocument();
  });

  it('境界(30日ちょうど)で「30日以上」を表示', () => {
    // 2026-05-02 = 30日前
    render(<StaleDataBadge shelterDate="2026-05-02" />);
    expect(screen.getByText(/30日以上/)).toBeInTheDocument();
  });

  it('未来日付は何も表示しない (異常値)', () => {
    const { container } = render(<StaleDataBadge shelterDate="2026-12-01" />);
    expect(container.firstChild).toBeNull();
  });

  it('不正な日付は何も表示しない', () => {
    const { container } = render(<StaleDataBadge shelterDate="invalid-date" />);
    expect(container.firstChild).toBeNull();
  });

  it('aria-label に経過情報が含まれる (スクリーンリーダー向け)', () => {
    render(<StaleDataBadge shelterDate="2026-03-01" />);
    const badge = screen.getByLabelText(/掲載から.*60日以上.*元のサイト.*確認/);
    expect(badge).toBeInTheDocument();
  });
});
