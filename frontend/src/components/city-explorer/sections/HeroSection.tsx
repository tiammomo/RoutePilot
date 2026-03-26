'use client';

import React from 'react';
import type { CitySummary } from '@/types';
import { CuratedPromptPanel } from './hero/CuratedPromptPanel';
import { FavoriteShortlistPanel } from './hero/FavoriteShortlistPanel';
import { HeroSummaryHeader } from './hero/HeroSummaryHeader';

interface CityExplorerHeroProps {
  compareCities: CitySummary[];
  favoriteCities: CitySummary[];
  onUsePrompt: (prompt: string) => void;
  summaryText: string;
}

export const CityExplorerHero: React.FC<CityExplorerHeroProps> = ({
  compareCities,
  favoriteCities,
  onUsePrompt,
  summaryText,
}) => (
  <div
    style={{
      display: 'grid',
      gap: 16,
      position: 'relative',
      zIndex: 1,
    }}
  >
    <HeroSummaryHeader
      compareCount={compareCities.length}
      favoriteCount={favoriteCities.length}
      summaryText={summaryText}
    />

    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: 16,
        alignItems: 'stretch',
      }}
    >
      <CuratedPromptPanel onUsePrompt={onUsePrompt} />
      <FavoriteShortlistPanel favoriteCities={favoriteCities} onUsePrompt={onUsePrompt} />
    </div>
  </div>
);
