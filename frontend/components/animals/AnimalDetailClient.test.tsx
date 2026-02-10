import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AnimalDetailClient } from './AnimalDetailClient';
import { AnimalPublic } from '@/types/animal';
import React from 'react';

// Mock Next.js navigation
const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

// Mock CategoryBadge component
vi.mock('@/components/ui/CategoryBadge', () => ({
  CategoryBadge: ({ category }: { category: string }) =>
    React.createElement('span', {}, category === 'adoption' ? '譲渡対象' : '迷子'),
}));

// Mock ImageGallery component
vi.mock('./ImageGallery', () => ({
  ImageGallery: ({ imageUrls, alt }: { imageUrls: string[]; alt: string }) =>
    React.createElement(
      'div',
      { 'data-testid': 'image-gallery' },
      React.createElement('p', {}, `Gallery for ${alt}`),
      React.createElement('p', {}, `${imageUrls.length} images`)
    ),
}));

// Mock ContactInfo component
vi.mock('./ContactInfo', () => ({
  ContactInfo: ({ location, phone, category }: { location: string; phone: string; category: string }) =>
    React.createElement(
      'div',
      { 'data-testid': 'contact-info' },
      React.createElement('p', {}, location),
      React.createElement('p', {}, phone),
      React.createElement('p', {}, category)
    ),
}));

// Mock ExternalLink component
vi.mock('./ExternalLink', () => ({
  ExternalLink: ({ sourceUrl }: { sourceUrl: string }) =>
    React.createElement('a', { 'data-testid': 'external-link', href: sourceUrl }, '元のページを見る'),
}));

describe('AnimalDetailClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockAnimal: AnimalPublic = {
    id: 1,
    species: '柴犬',
    sex: '男の子',
    age_months: 30,
    color: '茶色',
    size: '中型',
    shelter_date: '2024-01-15',
    location: '高知県中央小動物管理センター',
    phone: '088-831-7939',
    image_urls: [
      'https://example.com/image1.jpg',
      'https://example.com/image2.jpg',
    ],
    source_url: 'https://kochi-apc.com/jouto/dog1',
    category: 'adoption',
  };

  it('動物の詳細情報が正しく表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    expect(screen.getByRole('heading', { level: 1, name: '柴犬' })).toBeInTheDocument();
    expect(screen.getByText('高知県中央小動物管理センターで保護')).toBeInTheDocument();
  });

  it('カテゴリバッジが目立つ位置に表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);
    expect(screen.getByText('譲渡対象')).toBeInTheDocument();
  });

  it('詳細情報セクションが表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    expect(screen.getByRole('heading', { level: 2, name: '詳細情報' })).toBeInTheDocument();
    expect(screen.getByText('種別')).toBeInTheDocument();
    expect(screen.getByText('性別')).toBeInTheDocument();
    expect(screen.getByText('推定年齢')).toBeInTheDocument();
    expect(screen.getByText('毛色')).toBeInTheDocument();
    expect(screen.getByText('体格')).toBeInTheDocument();
    expect(screen.getByText('収容日')).toBeInTheDocument();
  });

  it('推定年齢が正しくフォーマットされる (2年6ヶ月)', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);
    expect(screen.getByText('約2歳6ヶ月')).toBeInTheDocument();
  });

  it('推定年齢が正しくフォーマットされる (1年未満)', () => {
    const youngAnimal = { ...mockAnimal, age_months: 8 };
    render(<AnimalDetailClient animal={youngAnimal} />);
    expect(screen.getByText('約8ヶ月')).toBeInTheDocument();
  });

  it('推定年齢が正しくフォーマットされる (ちょうど2歳)', () => {
    const exactAgeAnimal = { ...mockAnimal, age_months: 24 };
    render(<AnimalDetailClient animal={exactAgeAnimal} />);
    expect(screen.getByText('約2歳')).toBeInTheDocument();
  });

  it('推定年齢がnullの場合「不明」と表示される', () => {
    const unknownAgeAnimal = { ...mockAnimal, age_months: null };
    render(<AnimalDetailClient animal={unknownAgeAnimal} />);
    expect(screen.getByText('不明')).toBeInTheDocument();
  });

  it('毛色がnullの場合表示されない', () => {
    const noColorAnimal = { ...mockAnimal, color: null };
    render(<AnimalDetailClient animal={noColorAnimal} />);

    // 「毛色」というラベルが存在しないことを確認
    const colorLabels = screen.queryAllByText('毛色');
    expect(colorLabels).toHaveLength(0);
  });

  it('体格がnullの場合表示されない', () => {
    const noSizeAnimal = { ...mockAnimal, size: null };
    render(<AnimalDetailClient animal={noSizeAnimal} />);

    // 「体格」というラベルが存在しないことを確認
    const sizeLabels = screen.queryAllByText('体格');
    expect(sizeLabels).toHaveLength(0);
  });

  it('収容日が日本語フォーマットで表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);
    expect(screen.getByText('2024年1月15日')).toBeInTheDocument();
  });

  it('画像ギャラリーが表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const gallery = screen.getByTestId('image-gallery');
    expect(gallery).toBeInTheDocument();
    expect(screen.getByText('Gallery for 柴犬')).toBeInTheDocument();
    expect(screen.getByText('2 images')).toBeInTheDocument();
  });

  it('連絡先情報コンポーネントが表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const contactInfo = screen.getByTestId('contact-info');
    expect(contactInfo).toBeInTheDocument();
  });

  it('外部リンクコンポーネントが表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const externalLink = screen.getByTestId('external-link');
    expect(externalLink).toBeInTheDocument();
    expect(externalLink).toHaveAttribute('href', 'https://kochi-apc.com/jouto/dog1');
  });

  it('「一覧に戻る」ボタンをクリックするとトップページに遷移する', async () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const backButton = screen.getByRole('button', { name: '一覧に戻る' });
    await userEvent.click(backButton);

    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('「一覧に戻る」ボタンにフォーカスリングが適用される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const backButton = screen.getByRole('button', { name: '一覧に戻る' });
    expect(backButton).toHaveClass('focus:ring-2');
  });

  it('見出し構造が適切に設定されている', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1).toHaveTextContent('柴犬');

    const h2Elements = screen.getAllByRole('heading', { level: 2 });
    expect(h2Elements.length).toBeGreaterThan(0);
    expect(h2Elements.some(h2 => h2.textContent === '写真')).toBe(true);
    expect(h2Elements.some(h2 => h2.textContent === '詳細情報')).toBe(true);
  });

  it('レスポンシブグリッドレイアウトが適用される', () => {
    const { container } = render(<AnimalDetailClient animal={mockAnimal} />);

    const gridContainer = container.querySelector('.grid-cols-1');
    expect(gridContainer).toBeInTheDocument();
    expect(gridContainer).toHaveClass('lg:grid-cols-3');
  });

  it('迷子カテゴリの動物が正しく表示される', () => {
    const lostAnimal = { ...mockAnimal, category: 'lost' as const };
    render(<AnimalDetailClient animal={lostAnimal} />);

    expect(screen.getByText('迷子')).toBeInTheDocument();
  });

  it('全ての必須情報が表示される', () => {
    render(<AnimalDetailClient animal={mockAnimal} />);

    // h1タイトルとして柴犬が表示される
    expect(screen.getByRole('heading', { level: 1, name: '柴犬' })).toBeInTheDocument();

    // 詳細情報セクションに情報が表示される
    const detailsSection = screen.getByRole('heading', { level: 2, name: '詳細情報' }).parentElement;
    expect(detailsSection).toHaveTextContent('男の子');
    expect(detailsSection).toHaveTextContent('茶色');
    expect(detailsSection).toHaveTextContent('中型');
    expect(detailsSection).toHaveTextContent('2024年1月15日');
  });
});
