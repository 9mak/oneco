/**
 * E2E Accessibility Tests
 * Playwright + axe-coreを使用したE2Eアクセシビリティテスト
 * WCAG 2.1 AA準拠の検証、キーボードナビゲーション、ランドマーク要素の確認
 */

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility - Home Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should have no accessibility violations on home page', async ({ page }) => {
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('should have proper landmark elements', async ({ page }) => {
    // header, nav, main, footer が存在することを確認
    await expect(page.locator('header')).toBeVisible();
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('footer')).toBeVisible();
  });

  test('should have proper heading structure', async ({ page }) => {
    // h1が1つだけ存在することを確認
    const h1Count = await page.locator('h1').count();
    expect(h1Count).toBe(1);

    // h1にテキストが含まれていることを確認
    const h1Text = await page.locator('h1').textContent();
    expect(h1Text).toBeTruthy();
  });

  test('should support keyboard navigation', async ({ page }) => {
    // Tabキーでフォーカス可能な要素に移動できることを確認
    await page.keyboard.press('Tab');

    // フォーカスされた要素が存在することを確認
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toBeVisible();
  });

  test('should have visible focus indicators', async ({ page }) => {
    // Tabキーで最初のフォーカス可能な要素に移動
    await page.keyboard.press('Tab');

    // フォーカスリングが表示されていることを確認
    const focusedElement = page.locator(':focus');
    const outline = await focusedElement.evaluate((el) => {
      const styles = window.getComputedStyle(el);
      return styles.outline || styles.boxShadow;
    });

    // アウトラインまたはボックスシャドウが設定されていることを確認
    expect(outline).not.toBe('none');
  });
});

test.describe('Accessibility - Filter Panel', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should have accessible filter controls', async ({ page }) => {
    // フィルターパネルが存在する場合のみテスト
    const filterPanel = page.locator('[data-testid="filter-panel"]');
    const filterPanelExists = await filterPanel.count();

    if (filterPanelExists > 0) {
      // セレクトボックスにラベルが関連付けられていることを確認
      const selects = await page.locator('select').all();
      for (const select of selects) {
        const id = await select.getAttribute('id');
        if (id) {
          const label = page.locator(`label[for="${id}"]`);
          await expect(label).toBeVisible();
        }
      }
    }
  });

  test('should be operable with keyboard only', async ({ page }) => {
    // フィルターパネルが存在する場合のみテスト
    const filterPanel = page.locator('[data-testid="filter-panel"]');
    const filterPanelExists = await filterPanel.count();

    if (filterPanelExists > 0) {
      // Tabキーでフィルターコントロールにアクセスできることを確認
      let foundFilter = false;
      for (let i = 0; i < 20; i++) {
        await page.keyboard.press('Tab');
        const focusedRole = await page.locator(':focus').getAttribute('role');
        const focusedTag = await page.locator(':focus').evaluate((el) => el.tagName.toLowerCase());

        if (focusedTag === 'select' || focusedTag === 'button' || focusedRole === 'combobox') {
          foundFilter = true;
          break;
        }
      }
      expect(foundFilter).toBe(true);
    }
  });
});

test.describe('Accessibility - Animal Cards', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should have accessible animal cards', async ({ page }) => {
    const accessibilityScanResults = await new AxeBuilder({ page })
      .include('[data-testid="animal-card"]')
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    // カードが存在する場合のみ検証
    if (accessibilityScanResults.violations.length > 0) {
      console.log('Accessibility violations:', accessibilityScanResults.violations);
    }
    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('should have alt text for all images', async ({ page }) => {
    const images = await page.locator('img').all();

    for (const image of images) {
      const alt = await image.getAttribute('alt');
      expect(alt).toBeTruthy();
    }
  });

  test('should navigate to detail page with Enter key', async ({ page }) => {
    // 最初の動物カードへTabキーで移動
    const animalCards = page.locator('a[href^="/animals/"]');
    const cardCount = await animalCards.count();

    if (cardCount > 0) {
      // 最初のカードにフォーカス
      await animalCards.first().focus();

      // Enterキーで詳細ページに遷移
      await page.keyboard.press('Enter');

      // URLが変わったことを確認
      await expect(page).toHaveURL(/\/animals\/\d+/);
    }
  });
});

test.describe('Accessibility - Animal Detail Page', () => {
  test('should have no accessibility violations on detail page', async ({ page }) => {
    // 詳細ページに直接アクセス
    await page.goto('/animals/1');

    // ページが存在する場合のみテスト
    const pageTitle = await page.title();
    if (!pageTitle.includes('404')) {
      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      expect(accessibilityScanResults.violations).toEqual([]);
    }
  });

  test('should have back button accessible by keyboard', async ({ page }) => {
    await page.goto('/animals/1');

    // 「一覧に戻る」ボタンが存在する場合
    const backButton = page.getByRole('button', { name: /一覧に戻る|戻る/i });
    const buttonExists = await backButton.count();

    if (buttonExists > 0) {
      // フォーカスを設定してEnterキーで動作することを確認
      await backButton.focus();
      await expect(backButton).toBeFocused();
    }
  });

  test('image gallery should be keyboard navigable', async ({ page }) => {
    await page.goto('/animals/1');

    // 画像ギャラリーが存在する場合
    const gallery = page.locator('[data-testid="image-gallery"]');
    const galleryExists = await gallery.count();

    if (galleryExists > 0) {
      // 画像がクリック可能であることを確認
      const images = await gallery.locator('button, [role="button"]').all();
      for (const image of images) {
        await expect(image).toHaveAttribute('tabindex', /.*/);
      }
    }
  });
});

test.describe('Accessibility - Mobile Responsiveness', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('should be accessible on mobile viewport', async ({ page }) => {
    await page.goto('/');

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });

  test('should have touch-friendly button sizes (44x44px minimum)', async ({ page }) => {
    await page.goto('/');

    const buttons = await page.locator('button').all();

    for (const button of buttons) {
      const boundingBox = await button.boundingBox();
      if (boundingBox) {
        // WCAG 2.5.5: 最小タッチターゲットサイズ
        expect(boundingBox.width).toBeGreaterThanOrEqual(44);
        expect(boundingBox.height).toBeGreaterThanOrEqual(44);
      }
    }
  });
});

test.describe('Accessibility - Color Contrast', () => {
  test('should pass color contrast checks', async ({ page }) => {
    await page.goto('/');

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(['cat.color'])
      .analyze();

    expect(accessibilityScanResults.violations).toEqual([]);
  });
});
