/**
 * UI Components Accessibility Tests
 * axe-coreを使用したWCAG 2.1 AA準拠のアクセシビリティテスト
 */

import { describe, it, expect, vi } from 'vitest';
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
      <EmptyState showClearButton onClearFilters={() => {}} />
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have role="alert" for important messages', () => {
    render(<EmptyState />);
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
  });

  it('should have accessible clear button with aria-label', () => {
    render(<EmptyState showClearButton onClearFilters={() => {}} />);
    const button = screen.getByRole('button', { name: /フィルタをクリア/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-label', 'フィルタをクリア');
  });

  it('clear button should meet minimum touch target size', () => {
    render(<EmptyState showClearButton onClearFilters={() => {}} />);
    const button = screen.getByRole('button', { name: /フィルタをクリア/i });
    expect(button.className).toContain('min-h-[44px]');
    expect(button.className).toContain('min-w-[44px]');
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

  it('should have role="status" for screen readers', () => {
    render(<CategoryBadge category="adoption" />);
    const badge = screen.getByRole('status');
    expect(badge).toBeInTheDocument();
  });

  it('should have descriptive aria-label', () => {
    render(<CategoryBadge category="adoption" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'カテゴリ: 譲渡対象');
  });

  it('should display correct text for lost category', () => {
    render(<CategoryBadge category="lost" />);
    const badge = screen.getByRole('status');
    expect(badge).toHaveAttribute('aria-label', 'カテゴリ: 迷子');
    expect(badge).toHaveTextContent('迷子');
  });
});
