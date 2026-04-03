import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';
import sitemap from '@astrojs/sitemap';
import { readFileSync, readdirSync } from 'fs';
import { resolve } from 'path';

// IDs das pessoas protegidas — excluir do sitemap (têm noindex)
const noindexIds = new Set();
try {
  for (const f of readdirSync(resolve('src/data/pessoas'))) {
    if (f.endsWith('.json')) {
      const p = JSON.parse(readFileSync(resolve('src/data/pessoas', f), 'utf-8'));
      if (p.protegida) noindexIds.add(p.id);
    }
  }
} catch {}

export default defineConfig({
  site: 'https://franquinho.info',
  output: 'static',
  integrations: [
    react(),
    tailwind(),
    sitemap({
      filter: (page) => {
        const m = page.match(/\/pessoas\/(I\d+)\/?$/);
        return m ? !noindexIds.has(m[1]) : true;
      },
    }),
  ],
});
