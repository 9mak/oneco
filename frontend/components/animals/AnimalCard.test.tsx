import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AnimalCard } from './AnimalCard';
import { AnimalPublic } from '@/types/animal';

describe('AnimalCard', () => {
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

  it('動物の種別と性別が表示される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    expect(screen.getByRole('heading', { name: /犬 \/ 男の子/ })).toBeInTheDocument();
  });

  it('推定年齢が月から年に変換されて表示される (12ヶ月以上)', () => {
    render(<AnimalCard animal={mockAnimal} />);
    expect(screen.getByText('2歳')).toBeInTheDocument();
  });

  it('推定年齢が月単位で表示される (12ヶ月未満)', () => {
    const youngAnimal = { ...mockAnimal, age_months: 6 };
    render(<AnimalCard animal={youngAnimal} />);
    expect(screen.getByText('6ヶ月')).toBeInTheDocument();
  });

  it('推定年齢がnullの場合、「不明」と表示される', () => {
    const unknownAgeAnimal = { ...mockAnimal, age_months: null };
    render(<AnimalCard animal={unknownAgeAnimal} />);
    expect(screen.getByText('不明')).toBeInTheDocument();
  });

  it('収容日が日本語フォーマットで表示される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    expect(screen.getByText(/2024年1月15日/)).toBeInTheDocument();
  });

  it('収容場所が表示される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    expect(screen.getByText('高知県中央小動物管理センター')).toBeInTheDocument();
  });

  it('カテゴリバッジが表示される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    // CategoryBadge は "譲渡対象" テキストを表示
    expect(screen.getByText('譲渡対象')).toBeInTheDocument();
  });

  it('画像のalt属性が適切に設定される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    const image = screen.getByAltText('犬の画像');
    expect(image).toBeInTheDocument();
    expect(image).toHaveAttribute('src', 'https://example.com/dog1.jpg');
  });

  it('画像URLが空の場合、プレースホルダー画像が使用される', () => {
    const noImageAnimal = { ...mockAnimal, image_urls: [] };
    render(<AnimalCard animal={noImageAnimal} />);
    const image = screen.getByAltText('犬の画像');
    expect(image).toHaveAttribute('src', '/images/placeholder-animal.svg');
  });

  it('詳細ページへのリンクが正しく設定される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', '/animals/1');
  });

  it('カードにフォーカス時、フォーカスリングが表示される', () => {
    render(<AnimalCard animal={mockAnimal} />);
    const link = screen.getByRole('link');
    expect(link).toHaveClass('focus:ring-2');
  });

  it('迷子カテゴリの動物カードが正しく表示される', () => {
    const lostAnimal = { ...mockAnimal, category: 'lost' as const };
    render(<AnimalCard animal={lostAnimal} />);
    expect(screen.getByText('迷子')).toBeInTheDocument();
  });
});
