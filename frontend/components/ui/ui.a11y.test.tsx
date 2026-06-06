/**
 * UI Components Accessibility Tests
 * axe-coreを使用したWCAG 2.1 AA準拠のアクセシビリティテスト
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { LoadingSpinner } from './LoadingSpinner';
import { EmptyState } from './EmptyState';
import { CategoryBadge } from './CategoryBadge';

expect.extend(toHaveNoViolations);

describe('LoadingSpinner Accessibility', () => {
  it('should have no accessibility violations', async () => {
    const { container } = render(<LoadingSpinner />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have role="status" for screen readers', () => {
    render(<LoadingSpinner />);
    const spinner = screen.getByRole('status');
    expect(spinner).toHaveAttribute('aria-label', '読み込み中...');
  });

  it('should support custom label', () => {
    render(<LoadingSpinner label="データを取得中..." />);
    const spinner = screen.getByRole('status');
    expect(spinner).toHaveAttribute('aria-label', 'データを取得中...');
  });
});

describe('EmptyState Accessibility', () => {
  it('should have no accessibility violations', async () => {
    const { container } = render(<EmptyState />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have no accessibility violations with clear button', async () => {
    const { container } = render(
      <EmptyState showClearButton />
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have role="alert" for important messages', () => {
    render(<EmptyState />);
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
  });

  it('should have accessible clear link with aria-label', () => {
    render(<EmptyState showClearButton />);
    const link = screen.getByRole('link', { name: /フィルタをクリア/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('aria-label', 'フィルタをクリア');
    expect(link).toHaveAttribute('href', '/');
  });

  it('clear link should meet minimum touch target size', () => {
    render(<EmptyState showClearButton />);
    const link = screen.getByRole('link', { name: /フィルタをクリア/i });
    expect(link.className).toContain('min-h-[44px]');
    expect(link.className).toContain('min-w-[44px]');
  });
});

describe('CategoryBadge Accessibility', () => {
  it('should have no accessibility violations for adoption category', async () => {
    const { container } = render(<CategoryBadge category="adoption" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have no accessibility violations for lost category', async () => {
    const { container } = render(<CategoryBadge category="lost" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should expose category via aria-label without a live-region role', () => {
    render(<CategoryBadge category="adoption" />);
    // 静的バッジを role="status" (ライブリージョン) にすると一覧で多数の
    // バッジが描画時に一斉読み上げされるため、aria-label のみで識別する。
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByLabelText('カテゴリ: 譲渡対象')).toBeInTheDocument();
  });

  it('should have descriptive aria-label', () => {
    render(<CategoryBadge category="adoption" />);
    expect(screen.getByLabelText('カテゴリ: 譲渡対象')).toBeInTheDocument();
  });

  it('should display correct text for lost category', () => {
    render(<CategoryBadge category="lost" />);
    const badge = screen.getByLabelText('カテゴリ: 迷子');
    expect(badge).toHaveTextContent('迷子');
  });
});
