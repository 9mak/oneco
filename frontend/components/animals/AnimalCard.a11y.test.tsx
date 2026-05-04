/**
 * AnimalCard Accessibility Tests
 * axe-coreを使用したWCAG 2.1 AA準拠のアクセシビリティテスト
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { AnimalCard } from './AnimalCard';
import { AnimalPublic } from '@/types/animal';

expect.extend(toHaveNoViolations);

const mockAnimal: AnimalPublic = {
  id: 1,
  species: '犬',
  sex: '男の子',
  age_months: 24,
  color: '茶色',
  size: '中型',
  shelter_date: '2025-01-01',
  location: '高知県動物愛護センター',
  prefecture: '高知県',
  phone: '088-123-4567',
  image_urls: ['https://example.com/dog.jpg'],
  source_url: 'https://example.com/dog/1',
  category: 'adoption',
};

describe('AnimalCard Accessibility', () => {
  it('should have no accessibility violations', async () => {
    const { container } = render(<AnimalCard animal={mockAnimal} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have no accessibility violations with lost category', async () => {
    const lostAnimal = { ...mockAnimal, category: 'lost' as const };
    const { container } = render(<AnimalCard animal={lostAnimal} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have no accessibility violations without images', async () => {
    const animalWithoutImage = { ...mockAnimal, image_urls: [] };
    const { container } = render(<AnimalCard animal={animalWithoutImage} />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should have alt text for images', () => {
    const { getByRole } = render(<AnimalCard animal={mockAnimal} />);
    const image = getByRole('img');
    expect(image).toHaveAttribute('alt', '犬の画像');
  });

  it('should be keyboard navigable as a link', () => {
    const { getByRole } = render(<AnimalCard animal={mockAnimal} />);
    const link = getByRole('link');
    expect(link).toHaveAttribute('href', '/animals/1');
  });
});
