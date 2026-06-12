import { sendGAEvent } from '@next/third-parties/google';

const GA_MEASUREMENT_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function isGAEnabled(): boolean {
  if (!GA_MEASUREMENT_ID) return false;
  if (typeof window === 'undefined') return false;
  return true;
}

type EventParams = Record<string, string | number | boolean | undefined>;

function send(name: string, params: EventParams): void {
  if (!isGAEnabled()) return;
  const sanitized: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue;
    sanitized[key] = value;
  }
  try {
    sendGAEvent('event', name, sanitized);
  } catch {
    // GA 呼び出し失敗は黙殺（計測欠落のため UX を壊さない）
  }
}

export function trackExternalLinkClick(params: {
  linkUrl: string;
  prefecture?: string;
  animalId?: string;
}): void {
  send('external_link_click', {
    link_url: params.linkUrl,
    prefecture: params.prefecture,
    animal_id: params.animalId,
  });
}

export function trackSearchUsed(params: {
  queryLength: number;
  hasResults: boolean;
}): void {
  send('search_used', {
    query_length: params.queryLength,
    has_results: params.hasResults,
  });
}

export const _internal = { isGAEnabled, send };
