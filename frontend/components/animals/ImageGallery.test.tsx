import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ImageGallery } from './ImageGallery';

// ImageModalをモック
vi.mock('./ImageModal', () => ({
  ImageModal: ({ imageUrl, alt, onClose }: { imageUrl: string; alt: string; onClose: () => void }) => (
    <div data-testid="image-modal">
      <img src={imageUrl} alt={alt} />
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

describe('ImageGallery', () => {
  const mockImageUrls = [
    'https://example.com/image1.jpg',
    'https://example.com/image2.jpg',
    'https://example.com/image3.jpg',
  ];

  it('画像配列が空の場合、「画像がありません」メッセージが表示される', () => {
    render(<ImageGallery imageUrls={[]} alt="犬" />);
    expect(screen.getByText('画像がありません')).toBeInTheDocument();
  });

  it('画像配列がnullの場合、「画像がありません」メッセージが表示される', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    render(<ImageGallery imageUrls={null as any} alt="犬" />);
    expect(screen.getByText('画像がありません')).toBeInTheDocument();
  });

  it('画像がグリッド形式で表示される', () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const images = screen.getAllByRole('button', { name: /犬の画像\d+を拡大表示/ });
    expect(images).toHaveLength(3);
  });

  it('各画像に適切なalt属性が設定される', () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    expect(screen.getByAltText('犬の画像1')).toBeInTheDocument();
    expect(screen.getByAltText('犬の画像2')).toBeInTheDocument();
    expect(screen.getByAltText('犬の画像3')).toBeInTheDocument();
  });

  it('画像をクリックすると拡大モーダルが表示される', async () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const firstImageButton = screen.getByRole('button', { name: '犬の画像1を拡大表示' });
    await userEvent.click(firstImageButton);

    const modal = screen.getByTestId('image-modal');
    expect(modal).toBeInTheDocument();

    const modalImage = within(modal).getByAltText('犬の画像1');
    expect(modalImage).toHaveAttribute('src', 'https://example.com/image1.jpg');
  });

  it('モーダルが開いている状態で別の画像をクリックするとモーダルの画像が切り替わる', async () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    // 1枚目をクリック
    const firstImageButton = screen.getByRole('button', { name: '犬の画像1を拡大表示' });
    await userEvent.click(firstImageButton);

    let modal = screen.getByTestId('image-modal');
    expect(within(modal).getByAltText('犬の画像1')).toBeInTheDocument();

    // モーダルを閉じる
    const closeButton = within(modal).getByRole('button', { name: 'Close' });
    await userEvent.click(closeButton);

    // 2枚目をクリック
    const secondImageButton = screen.getByRole('button', { name: '犬の画像2を拡大表示' });
    await userEvent.click(secondImageButton);

    modal = screen.getByTestId('image-modal');
    expect(within(modal).getByAltText('犬の画像2')).toBeInTheDocument();
  });

  it('モーダルの閉じるボタンをクリックするとモーダルが閉じる', async () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const firstImageButton = screen.getByRole('button', { name: '犬の画像1を拡大表示' });
    await userEvent.click(firstImageButton);

    const modal = screen.getByTestId('image-modal');
    const closeButton = within(modal).getByRole('button', { name: 'Close' });
    await userEvent.click(closeButton);

    expect(screen.queryByTestId('image-modal')).not.toBeInTheDocument();
  });

  it('キーボードフォーカスで全ての画像ボタンにアクセスできる', async () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const imageButtons = screen.getAllByRole('button', { name: /犬の画像\d+を拡大表示/ });

    imageButtons[0].focus();
    expect(imageButtons[0]).toHaveFocus();

    await userEvent.tab();
    expect(imageButtons[1]).toHaveFocus();

    await userEvent.tab();
    expect(imageButtons[2]).toHaveFocus();
  });

  it('画像ボタンにフォーカスリングが適用される', () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const firstImageButton = screen.getByRole('button', { name: '犬の画像1を拡大表示' });
    expect(firstImageButton).toHaveClass('focus:ring-2');
  });

  it('画像がlazyローディングで読み込まれる', () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const images = screen.getAllByRole('img', { name: /犬の画像\d+/ });
    images.forEach((image) => {
      expect(image).toHaveAttribute('loading', 'lazy');
    });
  });

  it('レスポンシブグリッドクラスが適用される', () => {
    const { container } = render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const gridContainer = container.querySelector('.grid-cols-2');
    expect(gridContainer).toBeInTheDocument();
    expect(gridContainer).toHaveClass('md:grid-cols-3');
  });

  it('1枚の画像でもギャラリーが正しく表示される', () => {
    render(<ImageGallery imageUrls={['https://example.com/single.jpg']} alt="猫" />);

    const imageButton = screen.getByRole('button', { name: '猫の画像1を拡大表示' });
    expect(imageButton).toBeInTheDocument();
  });

  it('画像ボタンにaria-labelが設定されている', () => {
    render(<ImageGallery imageUrls={mockImageUrls} alt="犬" />);

    const firstImageButton = screen.getByRole('button', { name: '犬の画像1を拡大表示' });
    expect(firstImageButton).toHaveAttribute('aria-label', '犬の画像1を拡大表示');
  });
});
