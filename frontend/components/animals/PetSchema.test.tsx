import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PetSchema, OrganizationSchema } from './PetSchema';
import type { AnimalPublic } from '@/types/animal';

/**
 * 2026-08-26のSEO監査で、JSON-LDの `@type: 'Pet'` / `@type: 'Animal'` が
 * schema.org に実在しない型であることを curl で実測 (https://schema.org/Pet,
 * https://schema.org/Animal ともに404)。実在する型への是正を担保する
 * リグレッションテスト。
 *
 * 2026-08-28のreviewer指摘で、`about`(@type: Thing) 直下の `additionalProperty`
 * も domainIncludes 不適合と判明 (公式JSON-LDコンテキストを実測すると
 * additionalProperty の domainIncludes は MerchantReturnPolicy / Offer /
 * Place / Product / QualitativeValue / QuantitativeValue のみで Thing を
 * 含まない)。`identifier` (domainIncludes: Thing) に是正した。
 */

const baseAnimal: AnimalPublic = {
  id: 1,
  species: '犬',
  sex: '男の子',
  age_months: 12,
  color: '茶色',
  size: '中型',
  shelter_date: '2026-08-01',
  location: '高知市',
  prefecture: '高知県',
  phone: null,
  image_urls: ['https://example.com/a.jpg'],
  source_url: 'https://example.com/source',
  category: 'adoption',
};

function getJsonLd(container: HTMLElement) {
  const script = container.querySelector('script[type="application/ld+json"]');
  expect(script).not.toBeNull();
  return JSON.parse(script!.innerHTML);
}

describe('PetSchema', () => {
  it('schema.org に実在しない @type: Pet / Animal を使わない', () => {
    const { container } = render(<PetSchema animal={baseAnimal} siteUrl="https://oneco.example.com" />);
    const json = JSON.stringify(getJsonLd(container));
    expect(json).not.toContain('"@type":"Pet"');
    expect(json).not.toContain('"@type":"Animal"');
  });

  it('about は実在する @type: Thing で、性別・所在地を identifier (PropertyValue) で表現する', () => {
    const { container } = render(<PetSchema animal={baseAnimal} siteUrl="https://oneco.example.com" />);
    const data = getJsonLd(container);
    expect(data.about['@type']).toBe('Thing');
    expect(data.about.additionalProperty).toBeUndefined();
    expect(Array.isArray(data.about.identifier)).toBe(true);

    const props: Array<{ '@type': string; name: string; value: string }> = data.about.identifier;
    expect(props.every((p) => p['@type'] === 'PropertyValue')).toBe(true);
    expect(props.find((p) => p.name === '性別')?.value).toBe('男の子');
    expect(props.find((p) => p.name === '所在地')?.value).toBe('高知市');
    expect(props.find((p) => p.name === '毛色')?.value).toBe('茶色');
  });

  it('color が null の場合は毛色の identifier を含めない', () => {
    const { container } = render(
      <PetSchema animal={{ ...baseAnimal, color: null }} siteUrl="https://oneco.example.com" />,
    );
    const data = getJsonLd(container);
    const props: Array<{ name: string }> = data.about.identifier;
    expect(props.find((p) => p.name === '毛色')).toBeUndefined();
  });

  it('Article に author / publisher (Organization) を含める', () => {
    const { container } = render(<PetSchema animal={baseAnimal} siteUrl="https://oneco.example.com" />);
    const data = getJsonLd(container);
    expect(data['@type']).toBe('Article');
    expect(data.author).toEqual({ '@type': 'Organization', name: 'oneco' });
    expect(data.publisher).toEqual({ '@type': 'Organization', name: 'oneco' });
  });
});

describe('OrganizationSchema', () => {
  it('既存通り @type: Organization を使う (実在する型)', () => {
    const { container } = render(<OrganizationSchema siteUrl="https://oneco.example.com" siteName="oneco" />);
    const data = getJsonLd(container);
    expect(data['@type']).toBe('Organization');
  });
});
