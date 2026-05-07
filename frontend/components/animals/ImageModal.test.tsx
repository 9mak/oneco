import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ImageModal } from './ImageModal';

describe('ImageModal', () => {
  const onClose = vi.fn();

  it('imageUrl の画像が表示される', () => {
    render(<ImageModal imageUrl="https://example.com/cat.jpg" alt="猫" onClose={onClose} />);
    const img = screen.getByAltText('猫');
    expect(img).toHaveAttribute('src', expect.stringContaining('cat.jpg'));
  });

  it('画像が読み込み失敗したらプレースホルダーへ切り替わる', () => {
    render(<ImageModal imageUrl="https://example.com/cat.jpg" alt="猫" onClose={onClose} />);
    const img = screen.getByAltText('猫');
    fireEvent.error(img);
    expect(screen.getByAltText('猫')).toHaveAttribute(
      'src',
      '/images/placeholder-animal.svg',
    );
  });
});
