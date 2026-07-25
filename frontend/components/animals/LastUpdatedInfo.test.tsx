import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LastUpdatedInfo } from './LastUpdatedInfo';

describe('LastUpdatedInfo', () => {
  it('lastCollectedAt があれば「最終更新: YYYY-MM-DD」を表示する', () => {
    render(<LastUpdatedInfo lastCollectedAt="2026-07-20T09:00:00+00:00" />);
    expect(screen.getByText(/最終更新: 2026-07-20/)).toBeInTheDocument();
  });

  it('「壊れています」等の断定的な文言は含めない', () => {
    render(<LastUpdatedInfo lastCollectedAt="2026-01-01T00:00:00+00:00" />);
    expect(screen.queryByText(/壊れ/)).not.toBeInTheDocument();
    expect(screen.queryByText(/停止/)).not.toBeInTheDocument();
  });

  it('lastCollectedAt が null なら何も表示しない', () => {
    const { container } = render(<LastUpdatedInfo lastCollectedAt={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('lastCollectedAt が未指定(undefined)なら何も表示しない', () => {
    const { container } = render(<LastUpdatedInfo />);
    expect(container.firstChild).toBeNull();
  });

  it('不正な日付文字列なら何も表示しない', () => {
    const { container } = render(<LastUpdatedInfo lastCollectedAt="invalid-date" />);
    expect(container.firstChild).toBeNull();
  });

  it('元のサイトを確認するよう促すtitle属性を持つ', () => {
    render(<LastUpdatedInfo lastCollectedAt="2026-07-20T09:00:00+00:00" />);
    const el = screen.getByText(/最終更新/);
    expect(el).toHaveAttribute('title');
  });
});
