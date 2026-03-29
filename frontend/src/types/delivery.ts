'use client';

export interface ArtifactOverviewMetric {
  label: string;
  value: string;
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'info';
}

export interface ArtifactDeliverySection {
  key: string;
  title: string;
  items: string[];
}

export interface ArtifactDeliveryDescriptor {
  title: string;
  filenameBase: string;
  summary: string;
  summaryLines: string[];
  metrics: ArtifactOverviewMetric[];
  warnings: string[];
  subagentTrail: string[];
  shareContent: string;
  htmlDocumentTitle: string;
  htmlSections: ArtifactDeliverySection[];
}

export interface ArtifactDeliveryShareMetadata {
  title: string;
  content: string;
}

export interface ArtifactDeliveryBundle {
  schemaVersion: '2026-03-29';
  descriptor: ArtifactDeliveryDescriptor;
  artifact: Record<string, unknown> | null;
  executionReceipt: Record<string, unknown> | null;
  htmlContent: string;
  share: ArtifactDeliveryShareMetadata;
}
